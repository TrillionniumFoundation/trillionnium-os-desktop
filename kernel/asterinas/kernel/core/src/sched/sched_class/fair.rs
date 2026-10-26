// SPDX-License-Identifier: MPL-2.0

use alloc::{collections::BinaryHeap, sync::Arc};
use core::{
    cmp::{self, Reverse},
    sync::atomic::{AtomicU64, Ordering},
};

use ostd::{
    cpu::{CpuId, num_cpus},
    sync::SpinLock,
    task::{
        Task,
        scheduler::{EnqueueFlags, UpdateFlags},
    },
};

use super::{
    CurrentRuntime, SchedAttr,
    time::{base_slice_clocks, min_period_clocks},
};
use crate::{
    sched::nice::{Nice, NiceValue},
    thread::AsThread,
};

pub(super) mod group;
pub(super) use group::Selection as FairSelection;

const WEIGHT_0: u64 = 1024;

const HAS_PENDING: u64 = 1 << (u64::BITS - 1);

pub(crate) const fn nice_to_weight(nice: Nice) -> u64 {
    // Calculated by the formula below:
    //
    //     weight = 1024 * 1.25^(-nice)
    //
    // We propose that every increment of the nice value results
    // in 12.5% change of the CPU load weight.
    const FACTOR_NUMERATOR: u64 = 5;
    const FACTOR_DENOMINATOR: u64 = 4;

    const NICE_TO_WEIGHT: [u64; 40] = const {
        let mut ret = [0; 40];

        let mut index = 0;
        let mut nice = NiceValue::MIN.get();
        while nice <= NiceValue::MAX.get() {
            ret[index] = match nice {
                0 => WEIGHT_0,
                nice @ 1.. => {
                    let numerator = FACTOR_DENOMINATOR.pow(nice as u32);
                    let denominator = FACTOR_NUMERATOR.pow(nice as u32);
                    WEIGHT_0 * numerator / denominator
                }
                nice => {
                    let numerator = FACTOR_NUMERATOR.pow((-nice) as u32);
                    let denominator = FACTOR_DENOMINATOR.pow((-nice) as u32);
                    WEIGHT_0 * numerator / denominator
                }
            };
            assert!(ret[index] & HAS_PENDING == 0);

            index += 1;
            nice += 1;
        }
        ret
    };

    NICE_TO_WEIGHT[(nice.value().get() + 20) as usize]
}

/// The scheduling entity for the FAIR scheduling class.
///
/// The structure contains a significant indicator: `vruntime`.
///
/// # `vruntime`
///
/// The vruntime (virtual runtime) is calculated by the formula:
///
///     vruntime += runtime_delta * WEIGHT_0 / weight
///
/// and a thread with a lower vruntime gains a greater privilege to be
/// scheduled, making the whole run queue balanced on vruntime (thus FAIR).
///
/// # Scheduling periods
///
/// Scheduling periods are designed to calculate the time slice for each threads.
///
/// The time slice for each threads is calculated by the formula:
///
///     time_slice = period * weight / total_weight
///
/// where `total_weight` is the sum of all weights in the run queue including
/// the current thread and the per-node scheduling period is calculated
/// regarding the number of running threads.
///
/// When a thread meets the condition below, it will be preempted to the
/// run queue. See [`FairClassRq::update_current`] for more details.
///
///     period_delta > time_slice
///         || vruntime > rq_min_vruntime + normalized_time_slice
///
/// # The weight update process
///
/// The weight of a thread can be updated by the `sched_setattr` syscall series in
/// any thread. This makes it difficult to re-evaluate the data of its run queue
/// instantly after the update without a direct backward reference (which is
/// impossible to be represented in safe Rust).
///
/// To handle this problem, we use a `pending_weight` field to store the new weight.
/// When the thread is scheduled within the run queue, we will check if the weight
/// needs to be updated since both the old and new weights are needed for re-evaluation.
///
/// To indicate whether the weight needs to be updated, we pack the `weight` field
/// with a bit flag `HAS_PENDING`. When accessing the `weight` field:
///
/// - If the weight does not need to be updated (i.e., `weight & HAS_PENDING == 0`),
///   we simply return the weight.
/// - If the weight needs to be updated (i.e., `weight & HAS_PENDING != 0`), we try to
///   store the new weight into the `weight` field, which shouldn't take too much time
///   since the update frequency is usually relatively low.
/// - After a successful update, we re-evaluate the data of the run queue.
///
/// Most of the time, this mechanism allows the access to the weight lock-free and
/// ensures that only one load is needed.
#[derive(Debug)]
pub(crate) struct FairAttr {
    // Updates to the `weight` field must be serialized with the `pending_weight` lock.
    weight: AtomicU64,
    pending_weight: SpinLock<u64>,
    vruntime: AtomicU64,
}

impl FairAttr {
    pub(crate) fn new(nice: Nice) -> Self {
        let weight = nice_to_weight(nice);
        FairAttr {
            weight: weight.into(),
            pending_weight: SpinLock::new(weight),
            vruntime: Default::default(),
        }
    }

    pub(crate) fn update(&self, nice: Nice) {
        let mut pending_weight = self.pending_weight.lock();
        *pending_weight = nice_to_weight(nice);
        self.weight.store(
            self.weight.load(Ordering::Relaxed) | HAS_PENDING,
            Ordering::Relaxed,
        );
    }

    fn update_vruntime(&self, delta: u64, weight: u64) -> u64 {
        let delta = delta * WEIGHT_0 / weight;
        self.vruntime.fetch_add(delta, Ordering::Relaxed) + delta
    }

    fn fetch_weight(&self) -> (u64, u64) {
        // Synchronization is done via the `pending_weight` lock. Therefore, no additional ordering
        // is required to access the atomic variable.
        let weight = self.weight.load(Ordering::Relaxed);
        if weight & HAS_PENDING == 0 {
            return (weight, weight);
        }

        let new_weight = {
            // `pending_weight` always stores the latest weight.
            let pending_weight = self.pending_weight.lock();
            self.weight.store(*pending_weight, Ordering::Relaxed);
            *pending_weight
        };
        let old_weight = weight & !HAS_PENDING;

        // The `vruntime` field is an accumulated value, and we don't update
        // it here.

        (old_weight, new_weight)
    }
}

/// The original class/weight and high-water mark of one running interval.
///
/// This cursor is separate from the class time slice: the dispatcher still
/// executes on behalf of a waiting/exiting task until another task takes over.
/// Policy changes become effective for accounting at the next checkpoint;
/// they never reprice execution that has already occurred.
pub(super) struct FairRuntime {
    accounted_through: u64,
    weight: Option<u64>,
}

impl FairRuntime {
    pub(super) fn new_at(task: &Task, now: u64) -> Self {
        let attr = task.as_thread().unwrap().sched_attr();
        Self {
            accounted_through: now,
            weight: Self::weight(attr),
        }
    }

    pub(super) fn settle(&mut self, task: &Task, now: u64) -> Option<u64> {
        let attr = task.as_thread().unwrap().sched_attr();
        let delta = now.saturating_sub(self.accounted_through);
        self.accounted_through = self.accounted_through.max(now);
        if let Some(weight) = self.weight {
            attr.fair.update_vruntime(delta, weight);
        }
        let charged = self.weight.map(|_| delta);
        self.weight = Self::weight(attr);
        charged
    }

    fn weight(attr: &SchedAttr) -> Option<u64> {
        // Read the complete policy under its existing lock. Separate atomic
        // kind and pending-weight reads could straddle a policy update.
        match attr.policy() {
            super::SchedPolicy::Fair(nice) => Some(nice_to_weight(nice)),
            _ => None,
        }
    }
}

/// The wrapper for threads in the FAIR run queue.
///
/// This structure is used to provide the capability for keying in the
/// run queue implemented by `BTreeSet` in the `FairClassRq`.
// Cache the exact weight debited to this queue. A pending nice update may be
// consumed elsewhere before an arbitrary control-path removal or rollback.
struct FairQueueItem(Arc<Task>, u64, u64);

impl core::fmt::Debug for FairQueueItem {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "{:?}", self.key())
    }
}

impl FairQueueItem {
    fn key(&self) -> u64 {
        self.1
    }
}

impl PartialEq for FairQueueItem {
    fn eq(&self, other: &Self) -> bool {
        self.key().eq(&other.key())
    }
}

impl Eq for FairQueueItem {}

impl PartialOrd for FairQueueItem {
    fn partial_cmp(&self, other: &Self) -> Option<cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for FairQueueItem {
    fn cmp(&self, other: &Self) -> cmp::Ordering {
        self.key().cmp(&other.key())
    }
}

/// The per-cpu run queue for the FAIR scheduling class.
///
/// See [`FairAttr`] for the explanation of vruntimes and scheduling periods.
///
/// The structure contains a `BTreeSet` to store the threads in the run queue to
/// ensure the efficiency for finding next-to-run threads.
#[derive(Debug)]
pub(super) struct FairClassRq {
    #[expect(unused)]
    cpu: CpuId,
    pub(super) groups: group::GroupTree,
}

pub(super) struct FairCapacityNeed {
    pub(super) required: usize,
    pub(super) capacity: usize,
}

pub(super) struct PreparedFairCapacity {
    storage: Option<alloc::vec::Vec<Reverse<FairQueueItem>>>,
}

impl FairCapacityNeed {
    pub(super) fn allocate(self) -> ostd::Result<PreparedFairCapacity> {
        ostd::task::atomic_mode::might_sleep();
        let storage = if self.required > self.capacity {
            let mut slots = alloc::vec::Vec::new();
            slots
                .try_reserve_exact(self.required)
                .map_err(|_| ostd::Error::NoMemory)?;
            Some(slots)
        } else {
            None
        };
        Ok(PreparedFairCapacity { storage })
    }
}

impl FairClassRq {
    pub(super) fn root_migration_supported(&self) -> bool {
        self.groups.root_migration_supported()
    }

    pub(super) fn capacity_need(&self) -> ostd::Result<FairCapacityNeed> {
        self.groups.root_capacity_need()
    }

    pub(super) fn can_install_capacity(&self, prepared: &PreparedFairCapacity) -> bool {
        self.groups.can_install_root_capacity(prepared)
    }

    pub(super) fn install_and_reserve(&mut self, prepared: &mut PreparedFairCapacity) {
        self.groups.install_and_reserve_root(prepared);
    }

    pub(super) fn release_reservation(&mut self) {
        self.groups.release_root_reservation();
    }
    pub(crate) fn new(cpu: CpuId) -> Self {
        Self {
            cpu,
            groups: group::GroupTree::root(),
        }
    }

    pub(super) fn enqueue(&mut self, task: Arc<Task>, flags: Option<EnqueueFlags>) {
        self.try_enqueue(task, flags)
            .unwrap_or_else(|_| panic!("runnable task lacks prepared group admission"));
    }

    pub(super) fn try_enqueue(
        &mut self,
        task: Arc<Task>,
        flags: Option<EnqueueFlags>,
    ) -> core::result::Result<(), Arc<Task>> {
        self.groups.enqueue(task, flags)
    }

    pub(super) fn len(&self) -> usize {
        self.groups.len()
    }
    pub(super) fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub(super) fn select_next(&mut self) -> Option<(Arc<Task>, FairSelection)> {
        self.groups.select()
    }

    pub(super) fn cancel(&mut self, selected: FairSelection) {
        self.groups.cancel(selected);
    }
    pub(super) fn commit(&mut self, selected: FairSelection) {
        self.groups.commit(selected);
    }
    pub(super) fn finish_current(&mut self) {
        self.groups.finish_current();
    }
    pub(super) fn attach_current(&mut self, task: &Arc<Task>) {
        self.groups.attach_current(task);
    }
    pub(super) fn charge_current(&mut self, task: &Task, delta: u64) {
        self.groups.charge(task, delta);
    }

    pub(super) fn update_current(
        &mut self,
        rt: &CurrentRuntime,
        attr: &SchedAttr,
        flags: UpdateFlags,
    ) -> bool {
        self.groups.should_preempt(rt, attr, flags)
    }
}

#[cfg(ktest)]
#[path = "fair_interval_tests.rs"]
mod tests;
