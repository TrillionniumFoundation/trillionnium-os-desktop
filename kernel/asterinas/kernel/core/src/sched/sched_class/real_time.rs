// SPDX-License-Identifier: MPL-2.0

use alloc::{collections::VecDeque, sync::Arc};
use core::{
    array,
    num::NonZero,
    sync::atomic::{AtomicBool, AtomicU8, AtomicU64, Ordering::Relaxed},
};

use aster_util::ranged_integer::RangedU8;
use bitvec::{BitArr, bitarr};
use ostd::{
    Error, Result,
    cpu::CpuId,
    task::{
        Task,
        scheduler::{EnqueueFlags, UpdateFlags},
    },
};

use super::{CurrentRuntime, SchedAttr, SchedClassRq, time::base_slice_clocks};
use crate::thread::AsThread;

pub(crate) type RealTimePriority = RangedU8<1, 99>;

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub(crate) enum RealTimePolicy {
    Fifo,
    RoundRobin {
        base_slice_factor: Option<NonZero<u32>>,
    },
}

impl Default for RealTimePolicy {
    fn default() -> Self {
        Self::RoundRobin {
            base_slice_factor: None,
        }
    }
}

impl RealTimePolicy {
    fn to_time_slice(self) -> u64 {
        match self {
            RealTimePolicy::RoundRobin { base_slice_factor } => {
                base_slice_clocks()
                    * base_slice_factor
                        .map_or(DEFAULT_BASE_SLICE_FACTOR, |factor| u64::from(factor.get()))
            }
            RealTimePolicy::Fifo => 0,
        }
    }
}

/// The scheduling attribute for the REAL-TIME scheduling class.
///
/// This structure provides not-only the priority of the thread,
/// but also the time slice for the thread, measured in [`sched_clock`]s.
///
/// - If the time slice is not set, the thread is considered to be a FIFO
///   thread, and will be executed to its end if there no thread with a
///   lower priority.
/// - If the time slice is set, the thread is considered to be an RR
///   (round-robin) thread, and will be executed for the time slice, and
///   then it will be put back to the inactive array.
///
/// [`sched_clock`]: super::sched_clock
#[derive(Debug)]
pub(crate) struct RealTimeAttr {
    prio: AtomicU8,
    time_slice: AtomicU64, // 0 for SCHED_FIFO; other for SCHED_RR
}

const DEFAULT_BASE_SLICE_FACTOR: u64 = 20;

impl RealTimeAttr {
    pub(crate) fn new(prio: u8, policy: RealTimePolicy) -> Self {
        RealTimeAttr {
            prio: prio.into(),
            time_slice: AtomicU64::new(policy.to_time_slice()),
        }
    }

    pub(crate) fn update(&self, prio: u8, policy: RealTimePolicy) {
        self.prio.store(prio, Relaxed);
        self.time_slice.store(policy.to_time_slice(), Relaxed);
    }
}

#[derive(Debug)]
pub(super) struct RtQueueItem {
    task: Arc<Task>,
    enqueue_sequence: u64,
}

struct PrioArray {
    map: BitArr![for 100],
    queue: [VecDeque<RtQueueItem>; 100],
    reserved: [usize; 100],
}

impl core::fmt::Debug for PrioArray {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.debug_struct("PrioArray")
            .field_with("map", |f| {
                f.debug_list().entries(self.map.iter_ones()).finish()
            })
            .field_with("queue", |f| {
                f.debug_list()
                    .entries(
                        (self.queue.iter().flatten())
                            .map(|item| item.task.as_thread().unwrap().sched_attr()),
                    )
                    .finish()
            })
            .finish()
    }
}

impl PrioArray {
    fn enqueue(&mut self, item: RtQueueItem, prio: u8) {
        let priority = usize::from(prio);
        let queue = &mut self.queue[priority];
        let required = queue
            .len()
            .checked_add(self.reserved[priority])
            .and_then(|count| count.checked_add(1))
            .expect("RT queue capacity overflow");
        if required > queue.capacity() {
            // Ordinary enqueue retains its legacy growth path, but cannot
            // consume the slots promised to a prepared transfer.
            queue.reserve(required - queue.len());
        }
        let is_empty = queue.is_empty();
        queue.push_back(item);
        if is_empty {
            self.map.set(usize::from(prio), true);
        }
    }

    fn pop(&mut self) -> Option<Arc<Task>> {
        let mut iter = self.map.iter_ones();
        let prio = iter.next()? as u8;

        let queue = &mut self.queue[usize::from(prio)];
        let item = queue.pop_front().unwrap();

        if queue.is_empty() {
            self.map.set(usize::from(prio), false);
        }
        Some(item.task)
    }

    fn peek_prio(&self) -> Option<u8> {
        let prio = self.map.iter_ones().next()?;
        Some(prio as u8)
    }
}

/// A cold allocation snapshot for one priority in both physical RT arrays.
#[derive(Clone, Copy, Debug)]
pub(super) struct RtCapacityNeed {
    pub(super) priority: u8,
    pub(super) required: [usize; 2],
    pub(super) capacity: [usize; 2],
}

impl RtCapacityNeed {
    /// Allocate replacement storage before disabling IRQs or locking a queue.
    pub(super) fn allocate(&self) -> Result<PreparedRtCapacity> {
        ostd::task::atomic_mode::might_sleep();
        let mut prepared = PreparedRtCapacity {
            buffers: array::from_fn(|_| None),
        };
        for index in 0..2 {
            if self.required[index] <= self.capacity[index] {
                continue;
            }
            let mut buffer = VecDeque::new();
            buffer
                .try_reserve_exact(self.required[index])
                .map_err(|_| Error::NoMemory)?;
            prepared.buffers[index] = Some(buffer);
        }
        Ok(prepared)
    }
}

/// Empty replacement/retired buffers, retained for destruction outside the rq.
#[derive(Debug)]
pub(super) struct PreparedRtCapacity {
    pub(super) buffers: [Option<VecDeque<RtQueueItem>>; 2],
}

/// One removed entry and its source slot, not a newly enqueued task.
///
/// The caller must restore or commit it under the original rq lock before
/// dropping it. The outer transfer protocol owns rq identity and lifetime;
/// this token cannot acquire that lock from Drop. It is intentionally not Clone.
#[derive(Debug)]
#[must_use = "removed RT task must be restored or committed under its source rq lock"]
pub(super) struct RemovedRt {
    item: RtQueueItem,
    source_cpu: CpuId,
    array: usize,
    priority: usize,
    reservation_active: AtomicBool,
}

impl RemovedRt {
    pub(super) fn task(&self) -> &Arc<Task> {
        &self.item.task
    }
}

/// The per-cpu run queue for the REAL-TIME scheduling class.
///
/// The REAL-TIME scheduling class is implemented as a classic O(1)
/// priority algorithm.
///
/// It uses a bit array to track which priority levels have runnable
/// threads, and a vector of queues to store the threads.
///
/// Threads are popped & dequeued from the active array (`array[index]`), and
/// are enqueued into the inactive array (`array[!index]`). When the active array
/// is empty, the 2 arrays are swapped by `index`.
#[derive(Debug)]
pub(super) struct RealTimeClassRq {
    cpu: CpuId,
    index: bool,
    array: [PrioArray; 2],
    nr_running: usize,
    next_enqueue_sequence: u64,
}

impl RealTimeClassRq {
    pub(crate) fn new(cpu: CpuId) -> RealTimeClassRq {
        RealTimeClassRq {
            cpu,
            index: false,
            array: array::from_fn(|_| PrioArray {
                map: bitarr![0; 100],
                queue: array::from_fn(|_| VecDeque::new()),
                reserved: [0; 100],
            }),
            nr_running: 0,
            next_enqueue_sequence: 0,
        }
    }

    fn active_array(&mut self) -> &mut PrioArray {
        &mut self.array[usize::from(self.index)]
    }

    fn inactive_array(&mut self) -> &mut PrioArray {
        &mut self.array[usize::from(!self.index)]
    }

    fn swap_arrays(&mut self) {
        self.index = !self.index;
    }

    pub(super) fn capacity_need(&self, priority: u8) -> Result<RtCapacityNeed> {
        if !(RealTimePriority::MIN.get()..=RealTimePriority::MAX.get()).contains(&priority) {
            return Err(Error::InvalidArgs);
        }
        let mut required = [0; 2];
        let mut capacity = [0; 2];
        for index in 0..2 {
            let array = &self.array[index];
            let queue = &array.queue[usize::from(priority)];
            required[index] = queue
                .len()
                .checked_add(array.reserved[usize::from(priority)])
                .and_then(|count| count.checked_add(1))
                .ok_or(Error::Overflow)?;
            capacity[index] = queue.capacity();
        }
        Ok(RtCapacityNeed {
            priority,
            required,
            capacity,
        })
    }

    pub(super) fn can_install_capacity(&self, prepared: &PreparedRtCapacity, priority: u8) -> bool {
        let Ok(need) = self.capacity_need(priority) else {
            return false;
        };
        (0..2).all(|index| {
            need.required[index] <= need.capacity[index]
                || prepared.buffers[index].as_ref().is_some_and(|buffer| {
                    buffer.is_empty() && buffer.capacity() >= need.required[index]
                })
        })
    }

    /// The caller revalidates and installs while holding the same rq lock.
    /// Both physical arrays retain a slot, even if active/inactive flips later.
    pub(super) fn install_and_reserve(&mut self, prepared: &mut PreparedRtCapacity, priority: u8) {
        assert!(
            self.can_install_capacity(prepared, priority),
            "RT capacity must be revalidated before installation"
        );
        let priority = usize::from(priority);
        for index in 0..2 {
            let array = &mut self.array[index];
            let queue = &mut array.queue[priority];
            let required = queue.len() + array.reserved[priority] + 1;
            if required > queue.capacity() {
                let mut buffer = prepared.buffers[index].take().unwrap();
                // Revalidation proves append cannot grow this empty buffer.
                buffer.append(queue);
                core::mem::swap(queue, &mut buffer);
                // The retired allocation is empty and is dropped by the cold
                // caller only after releasing the rq lock and IRQ guard.
                prepared.buffers[index] = Some(buffer);
            }
            array.reserved[priority] += 1;
        }
    }

    pub(super) fn release_reservation(&mut self, priority: u8) {
        let priority = usize::from(priority);
        assert!(
            priority < 100 && self.array.iter().all(|array| array.reserved[priority] > 0),
            "RT capacity reservation already released"
        );
        for array in &mut self.array {
            array.reserved[priority] -= 1;
        }
    }

    /// Remove from the actual physical bucket, which can predate a policy edit.
    /// This controlled transfer path scans existing storage without allocating.
    pub(super) fn take_task(&mut self, task: &Arc<Task>) -> Option<RemovedRt> {
        for index in 0..2 {
            let array = &mut self.array[index];
            for priority in 0..100 {
                let queue = &mut array.queue[priority];
                let Some(position) = queue.iter().position(|item| Arc::ptr_eq(&item.task, task))
                else {
                    continue;
                };
                let reserved = array.reserved[priority]
                    .checked_add(1)
                    .expect("RT removal reservation overflow");
                let remaining = self
                    .nr_running
                    .checked_sub(1)
                    .expect("removed RT task was not counted");
                let item = queue.remove(position).unwrap();
                // Preserve the released slot before any other enqueue can use
                // this rq. len + reserved is unchanged by the removal.
                array.reserved[priority] = reserved;
                if queue.is_empty() {
                    array.map.set(priority, false);
                }
                self.nr_running = remaining;
                return Some(RemovedRt {
                    item,
                    source_cpu: self.cpu,
                    array: index,
                    priority,
                    reservation_active: AtomicBool::new(true),
                });
            }
        }
        None
    }

    /// Restore original FIFO order among all entries still in the source bucket.
    pub(super) fn restore_task(&mut self, removed: RemovedRt) {
        assert_eq!(
            removed.source_cpu, self.cpu,
            "RT removal belongs to another CPU"
        );
        assert!(
            removed.reservation_active.load(Relaxed),
            "removed RT reservation already consumed"
        );
        let array = &mut self.array[removed.array];
        let queue = &mut array.queue[removed.priority];
        assert!(
            array.reserved[removed.priority] > 0
                && queue.len() < queue.capacity()
                && queue.len() + array.reserved[removed.priority] <= queue.capacity(),
            "RT rollback slot is missing"
        );
        let count = self
            .nr_running
            .checked_add(1)
            .expect("RT runnable count overflow");
        let position = queue
            .iter()
            .position(|item| item.enqueue_sequence > removed.item.enqueue_sequence)
            .unwrap_or(queue.len());
        assert!(
            removed.reservation_active.swap(false, Relaxed),
            "removed RT reservation already consumed"
        );
        array.reserved[removed.priority] -= 1;
        // The rollback reservation guarantees insert cannot grow the deque.
        queue.insert(position, removed.item);
        array.map.set(removed.priority, true);
        self.nr_running = count;
    }

    /// Release only the source slot; the transfer token retains its Task Arc.
    pub(super) fn commit_removed(&mut self, removed: &RemovedRt) {
        assert_eq!(
            removed.source_cpu, self.cpu,
            "RT removal belongs to another CPU"
        );
        assert!(
            removed.reservation_active.load(Relaxed),
            "removed RT reservation already consumed"
        );
        let reserved = &mut self.array[removed.array].reserved[removed.priority];
        assert!(*reserved > 0, "RT removal slot is missing");
        assert!(
            removed.reservation_active.swap(false, Relaxed),
            "removed RT reservation already consumed"
        );
        *reserved -= 1;
    }
}

impl SchedClassRq for RealTimeClassRq {
    fn enqueue(&mut self, entity: Arc<Task>, _: Option<EnqueueFlags>) {
        let sched_attr = entity.as_thread().unwrap().sched_attr();
        let prio = sched_attr.real_time.prio.load(Relaxed);
        let enqueue_sequence = self.next_enqueue_sequence;
        self.next_enqueue_sequence = enqueue_sequence
            .checked_add(1)
            .expect("RT enqueue sequence overflow");
        self.inactive_array().enqueue(
            RtQueueItem {
                task: entity,
                enqueue_sequence,
            },
            prio,
        );
        self.nr_running += 1;
    }

    fn len(&self) -> usize {
        self.nr_running
    }

    fn is_empty(&self) -> bool {
        self.nr_running == 0
    }

    fn pick_next(&mut self) -> Option<Arc<Task>> {
        if self.nr_running == 0 {
            return None;
        }

        (self.active_array().pop())
            .or_else(|| {
                self.swap_arrays();
                self.active_array().pop()
            })
            .inspect(|_| self.nr_running -= 1)
    }

    fn update_current(
        &mut self,
        rt: &CurrentRuntime,
        attr: &SchedAttr,
        flags: UpdateFlags,
    ) -> bool {
        let attr = &attr.real_time;

        match flags {
            UpdateFlags::Tick | UpdateFlags::Yield => match attr.time_slice.load(Relaxed) {
                0 => {
                    self.active_array().peek_prio().is_some()
                        || self
                            .inactive_array()
                            .peek_prio()
                            .is_some_and(|prio| prio < attr.prio.load(Relaxed))
                }
                ts => ts <= rt.period_delta && !self.is_empty(),
            },
            UpdateFlags::Wait | UpdateFlags::Exit => !self.is_empty(),
        }
    }
}

#[cfg(ktest)]
mod capacity_tests;

#[cfg(ktest)]
mod removal_tests;
