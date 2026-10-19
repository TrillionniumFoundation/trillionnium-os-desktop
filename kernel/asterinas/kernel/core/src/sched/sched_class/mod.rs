// SPDX-License-Identifier: MPL-2.0

//! Completely Fair Scheduler (CFS).

#![warn(unused)]

use alloc::{boxed::Box, sync::Arc, vec::Vec};
use core::{fmt, ops::Bound, sync::atomic::Ordering};

use ostd::{
    arch::read_tsc as sched_clock,
    cpu::{CpuId, CpuSet, PinCurrentCpu, all_cpus},
    irq::disable_local,
    sync::{LocalIrqDisabled, SpinLock},
    task::{
        AtomicCpuId, Task,
        scheduler::{
            EnqueueFlags, LocalRunQueue, Scheduler, UpdateFlags, enable_preemption_on_cpu,
            info::CommonSchedInfo, inject_scheduler,
        },
    },
    util::id_set::Id,
};

use spin::Once;

use super::{
    nice::Nice,
    stats::{SchedulerStats, set_stats_from_scheduler},
};
use crate::{
    fs::cgroupfs::{CpuChargeOwner, task_cpu_eligible},
    thread::{AsThread, Thread},
};

mod policy;
mod time;

mod fair;
mod idle;
mod real_time;
mod stop;

use self::policy::{SchedPolicyKind, SchedPolicyState};
pub(crate) use self::{
    policy::{LinuxSchedPolicy, SchedPolicy},
    real_time::{RealTimePolicy, RealTimePriority},
};

type SchedEntity = (Arc<Task>, Arc<Thread>);

static CLASS_SCHEDULER: Once<&'static ClassScheduler> = Once::new();

pub(crate) fn init() {
    let scheduler = Box::leak(Box::new(ClassScheduler::new()));

    // Inject the scheduler into the ostd for actual scheduling work.
    inject_scheduler(scheduler);
    CLASS_SCHEDULER.call_once(|| scheduler);

    // Set the scheduler into the system for statistics.
    // We set this after injecting the scheduler into ostd,
    // so that the loadavg statistics are updated after the scheduler is used.
    set_stats_from_scheduler(scheduler);
}

pub(crate) fn init_on_each_cpu() {
    enable_preemption_on_cpu();
}

/// Settles the current CPU's pending bandwidth interval before an owner update.
///
/// The caller must copy and validate inputs first. The callback runs with local
/// IRQs disabled and the local runqueue locked; it may acquire bandwidth locks,
/// but must not allocate, block, copy user memory, or acquire a runqueue lock.
/// On N0's single CPU, other tasks have already settled when leaving the CPU.
/// This is not a rendezvous with tasks running on remote CPUs.
pub(crate) fn with_current_cpu_bandwidth_settled<R>(apply: impl FnOnce(u64) -> R) -> R {
    let irq_guard = disable_local();
    let Some(scheduler) = CLASS_SCHEDULER.get() else {
        // No class-scheduled POSIX task can run before scheduler initialization.
        // This also allows standalone owner ktests using OSTD's FIFO scheduler.
        return apply(sched_clock());
    };
    let mut rq = scheduler.rqs[irq_guard.current_cpu().as_usize()].lock();
    let now = sched_clock();
    if let Some(((task, _), rt)) = &mut rq.current {
        rt.with_bandwidth_settled(task, now, apply)
    } else {
        apply(now)
    }
}

/// Publishes a CPU owner binding between two local bandwidth checkpoints.
///
/// The caller already holds the membership and any necessary node locks.
/// `publish` must not acquire a sleeping lock, block, copy user memory, or
/// recursively change CPU bindings. It runs with IRQs disabled but WITHOUT a
/// runqueue lock: the existing RCU update registers deferred destruction and
/// may allocate using OSDK's IRQ-safe heap/frame allocator. It does not wait
/// for the grace period or execute the registered destructors here.
///
/// All execution through the second checkpoint belongs to the retained old
/// owner; the new segment begins at that checkpoint. No N0 scheduler observer
/// can see the intermediate publication. Remote CPUs only notice at their
/// next checkpoint; this is not an SMP migration rendezvous.
pub(crate) fn with_current_cpu_bandwidth_owner_update<R>(publish: impl FnOnce() -> R) -> R {
    let irq_guard = disable_local();
    let Some(scheduler) = CLASS_SCHEDULER.get() else {
        return publish();
    };
    let rq = &scheduler.rqs[irq_guard.current_cpu().as_usize()];
    {
        let mut rq = rq.lock();
        if let Some(((task, _), rt)) = &mut rq.current {
            rt.settle_bandwidth(task, sched_clock());
        }
    }
    let result = publish();
    {
        let mut rq = rq.lock();
        if let Some(((task, _), rt)) = &mut rq.current {
            rt.settle_bandwidth(task, sched_clock());
        }
    }
    result
}

/// Represents the middle layer between scheduling classes and generic scheduler
/// traits. It consists of all the sets of run queues for CPU cores. Other global
/// information may also be stored here.
pub(crate) struct ClassScheduler {
    /// The per-CPU runqueues.
    ///
    /// We use the `LocalIrqDisabled` marker for this spinlock to ensure local IRQs are always disabled,
    /// preventing potential deadlocks due to the fact that
    /// the runqueues may be accessed in both the task and interrupt context (L1 and L2).
    rqs: Box<[SpinLock<PerCpuClassRqSet, LocalIrqDisabled>]>,
    last_chosen_cpu: AtomicCpuId,
}

/// Represents the run queue for each CPU core. It stores a list of run queues for
/// scheduling classes in its corresponding CPU core. The current task of this CPU
/// core is also stored in this structure.
struct PerCpuClassRqSet {
    stop: stop::StopClassRq,
    real_time: real_time::RealTimeClassRq,
    fair: fair::FairClassRq,
    idle: idle::IdleClassRq,
    // Runqueue-local parked tasks; no userspace syscall is required to refill.
    throttled: Vec<Arc<Task>>,
    current: Option<(SchedEntity, CurrentRuntime)>,
}

/// Stores the runtime information of the current task.
///
/// This is used to calculate the time slice of the current task.
///
/// This struct is independent of the current `Arc<Task>` instead encapsulating the
/// task, because the scheduling class implementations use `CurrentRuntime` and
/// `SchedAttr` only.
struct CurrentRuntime {
    start: u64,
    delta: u64,
    period_delta: u64,
    // This cursor partitions debits to the original cgroup bandwidth owner.
    // It stores no quota or usage. Configuration must not advance `start`,
    // which is still needed for the next CFS/RT runtime update.
    bandwidth_accounted_through: u64,
    // Reference only: all accounting remains in the original CpuMax. Resolve
    // at a segment boundary, never after the interval has already executed.
    bandwidth_owner: Option<CpuChargeOwner>,
}

impl CurrentRuntime {
    fn new(task: &Task) -> Self {
        Self::new_at(task, sched_clock())
    }

    fn new_at(task: &Task, now: u64) -> Self {
        CurrentRuntime {
            start: now,
            delta: 0,
            period_delta: 0,
            bandwidth_accounted_through: now,
            bandwidth_owner: CpuChargeOwner::for_task(task),
        }
    }

    fn update(&mut self) {
        self.update_at(sched_clock());
    }

    fn update_at(&mut self, now: u64) {
        self.delta = now - core::mem::replace(&mut self.start, now);
        self.period_delta += self.delta;
    }

    fn settle_bandwidth(&mut self, task: &Task, now: u64) {
        if now > self.bandwidth_accounted_through {
            if let Some(owner) = &self.bandwidth_owner {
                owner.charge(self.bandwidth_accounted_through, now);
            }
            self.bandwidth_accounted_through = now;
        }

        // The next interval may belong to a newly published incarnation. An
        // exited task keeps its original owner even after the Process is
        // detached or reaped. Re-resolving its node would redirect its tail.
        if !task.as_thread().is_some_and(|thread| thread.is_exited()) {
            self.bandwidth_owner = CpuChargeOwner::for_task(task);
        }
    }

    fn with_bandwidth_settled<R>(
        &mut self,
        task: &Task,
        now: u64,
        apply: impl FnOnce(u64) -> R,
    ) -> R {
        self.settle_bandwidth(task, now);
        apply(now)
    }
}

/// Deterministic timestamps on the production runtime and real POSIX owner.
/// No test task is injected into OSTD's running FIFO test scheduler.
#[cfg(ktest)]
pub(crate) struct CpuRuntimeFixture {
    task: Arc<Task>,
    runtime: CurrentRuntime,
}

#[cfg(ktest)]
impl CpuRuntimeFixture {
    pub(crate) fn new(task: Arc<Task>, now: u64) -> Self {
        let runtime = CurrentRuntime::new_at(&task, now);
        Self {
            task,
            runtime,
        }
    }

    pub(crate) fn configure<R>(&mut self, now: u64, apply: impl FnOnce(u64) -> R) -> R {
        self.runtime.with_bandwidth_settled(&self.task, now, apply)
    }

    pub(crate) fn update(&mut self, now: u64) -> (u64, u64) {
        self.runtime.update_at(now);
        self.runtime.settle_bandwidth(&self.task, now);
        (self.runtime.delta, self.runtime.period_delta)
    }

    /// Runs the production runtime's two checkpoints around a real owner
    /// publication. No fixture is inserted into the FIFO ktest scheduler.
    pub(crate) fn publish<R>(
        &mut self,
        before: u64,
        after: u64,
        publish: impl FnOnce() -> R,
    ) -> R {
        self.runtime.settle_bandwidth(&self.task, before);
        let result = publish();
        self.runtime.settle_bandwidth(&self.task, after);
        result
    }
}

/// The run queue for scheduling classes (the main trait). Scheduling classes
/// should implement this trait to function as expected.
trait SchedClassRq: Send + fmt::Debug {
    /// Enqueues a task into the run queue.
    fn enqueue(&mut self, task: Arc<Task>, flags: Option<EnqueueFlags>);

    /// Returns the number of threads in the run queue.
    fn len(&self) -> usize;

    /// Checks if the run queue is empty.
    fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Picks the next task for running.
    fn pick_next(&mut self) -> Option<Arc<Task>>;

    /// Update the information of the current task.
    ///
    /// The return value of this method indicates whether there is another task
    /// **in this run queue** to replace the current one.
    fn update_current(&mut self, rt: &CurrentRuntime, attr: &SchedAttr, flags: UpdateFlags)
    -> bool;
}

/// The scheduling attribute for a thread.
///
/// This is used to store the scheduling policy and runtime parameters for each
/// scheduling class.
#[derive(Debug)]
pub(crate) struct SchedAttr {
    policy: SchedPolicyState,
    last_cpu: AtomicCpuId,
    real_time: real_time::RealTimeAttr,
    fair: fair::FairAttr,
}

impl SchedAttr {
    /// Constructs a new `SchedAttr` with the given scheduling policy.
    pub(crate) fn new(policy: SchedPolicy) -> Self {
        Self {
            policy: SchedPolicyState::new(policy),
            last_cpu: AtomicCpuId::default(),
            real_time: {
                let (prio, policy) = match policy {
                    SchedPolicy::RealTime { rt_prio, rt_policy } => (rt_prio.get(), rt_policy),
                    _ => (RealTimePriority::MAX.get(), Default::default()),
                };
                real_time::RealTimeAttr::new(prio, policy)
            },
            fair: fair::FairAttr::new(match policy {
                SchedPolicy::Fair(nice) => nice,
                _ => Nice::default(),
            }),
        }
    }

    /// Retrieves the current scheduling policy of the thread.
    pub(crate) fn policy(&self) -> SchedPolicy {
        self.policy.get()
    }

    fn policy_kind(&self) -> SchedPolicyKind {
        self.policy.kind()
    }

    /// Updates the scheduling policy of the thread.
    ///
    /// Specifically for real-time policies, if the new policy doesn't
    /// specify a base slice factor for RR, the old one will be kept.
    pub(crate) fn set_policy(&self, policy: SchedPolicy) {
        self.policy.set(policy, |policy| match policy {
            SchedPolicy::RealTime { rt_prio, rt_policy } => {
                self.real_time.update(rt_prio.get(), rt_policy);
            }
            SchedPolicy::Fair(nice) => self.fair.update(nice),
            _ => {}
        });
    }

    pub(crate) fn update_policy<T>(&self, f: impl FnOnce(&mut SchedPolicy) -> T) -> T {
        self.policy.update(|policy| {
            let ret = f(policy);
            match *policy {
                SchedPolicy::RealTime { rt_prio, rt_policy } => {
                    self.real_time.update(rt_prio.get(), rt_policy);
                }
                SchedPolicy::Fair(nice) => self.fair.update(nice),
                _ => {}
            }
            ret
        })
    }

    pub(crate) fn last_cpu(&self) -> Option<CpuId> {
        self.last_cpu.get()
    }

    fn set_last_cpu(&self, cpu_id: CpuId) {
        self.last_cpu.set_anyway(cpu_id);
    }
}

impl Scheduler for ClassScheduler {
    fn enqueue(&self, task: Arc<Task>, flags: EnqueueFlags) -> Option<CpuId> {
        let thread = task.as_thread()?.clone();

        let (still_in_rq, cpu) = {
            let selected_cpu_id = self.select_cpu(&thread, flags);

            if let Err(task_cpu_id) = task.cpu().set_if_is_none(selected_cpu_id) {
                debug_assert!(flags != EnqueueFlags::Spawn);
                (true, task_cpu_id)
            } else {
                (false, selected_cpu_id)
            }
        };

        let mut rq = self.rqs[cpu.as_usize()].lock();

        // Note: call set_if_is_none again to prevent a race condition.
        if still_in_rq && task.cpu().set_if_is_none(cpu).is_err() {
            return None;
        }

        // Preempt if the new task has a higher priority.
        let should_preempt = rq
            .current
            .as_ref()
            .is_none_or(|((_, rq_current_thread), _)| {
                thread.sched_attr().policy() < rq_current_thread.sched_attr().policy()
            });

        thread.sched_attr().set_last_cpu(cpu);
        rq.enqueue_entity((task, thread), Some(flags));

        should_preempt.then_some(cpu)
    }

    fn mut_local_rq_with(&self, f: &mut dyn FnMut(&mut dyn LocalRunQueue)) {
        let guard = disable_local();
        let mut lock = self.rqs[guard.current_cpu().as_usize()].lock();
        f(&mut *lock)
    }

    fn local_rq_with(&self, f: &mut dyn FnMut(&dyn LocalRunQueue)) {
        let guard = disable_local();
        f(&*self.rqs[guard.current_cpu().as_usize()].lock())
    }
}

impl ClassScheduler {
    pub(crate) fn new() -> Self {
        let class_rq = |cpu| {
            SpinLock::new(PerCpuClassRqSet {
                stop: stop::StopClassRq::new(),
                real_time: real_time::RealTimeClassRq::new(cpu),
                fair: fair::FairClassRq::new(cpu),
                idle: idle::IdleClassRq::new(),
                throttled: Vec::new(),
                current: None,
            })
        };
        ClassScheduler {
            rqs: all_cpus().map(class_rq).collect(),
            last_chosen_cpu: AtomicCpuId::default(),
        }
    }

    // TODO: Implement a better algorithm and replace the current naive implementation.
    fn select_cpu(&self, thread: &Thread, flags: EnqueueFlags) -> CpuId {
        if let Some(last_cpu) = thread.sched_attr().last_cpu() {
            return last_cpu;
        }
        debug_assert!(flags == EnqueueFlags::Spawn);

        let guard = disable_local();

        let mut selected = guard.current_cpu();
        let mut minimum_load = u32::MAX;

        // Set `selected` as `candidate` if the candidate's load is smaller.
        let test_candidate = |candidate: CpuId| {
            let PerCpuLoadStats { queue_len, .. } =
                self.rqs[candidate.as_usize()].lock().load_stats();
            let load = queue_len;
            if load < minimum_load {
                minimum_load = load;
                selected = candidate;
            }
        };

        let affinity = thread.atomic_cpu_affinity().load(Ordering::Relaxed);
        match self.last_chosen_cpu.get() {
            Some(cpu) => {
                // Perform a round-robin selection starting after the last chosen CPU.
                //
                // It still checks every CPU in the affinity set to find the one with the
                // minimum load, but avoids selecting the same CPU again in case of a tie.
                Self::cycle_after(cpu, &affinity).for_each(test_candidate)
            }
            None => affinity.iter().for_each(test_candidate),
        }

        self.last_chosen_cpu.set_anyway(selected);
        selected
    }

    /// Returns a cycling iterator over the CPUs in the [`CpuSet`], starting *after*
    /// the given [`CpuId`].
    ///
    /// The iteration order is ascending up to the wrapping point, after which it
    /// continues from the first CPU in the set in ascending order again.
    ///
    /// If the given [`CpuId`] is in the set, it will be the last element yielded.
    fn cycle_after(cpu: CpuId, cpu_set: &CpuSet) -> impl Iterator<Item = CpuId> + '_ {
        cpu_set
            .iter_in((Bound::Excluded(cpu), Bound::Unbounded))
            .chain(cpu_set.iter_in(..=cpu))
    }
}

impl PerCpuClassRqSet {
    fn replenish_throttled(&mut self, now: u64) {
        // Inspect the existing allocation in place. The former mem::take()
        // discarded its capacity every tick and pushed blocked tasks into a
        // fresh Vec while the IRQ-disabled runqueue spinlock was held.
        // swap_remove leaves capacity intact and never reallocates this Vec.
        let mut index = 0;
        while index < self.throttled.len() {
            if !task_cpu_eligible(&self.throttled[index], now) {
                index += 1;
                continue;
            }
            let task = self.throttled.swap_remove(index);
            if let Some(thread) = task.as_thread().cloned() {
                self.enqueue_entity((task, thread), None);
            }
            // Examine the element swapped into this position next; if this
            // was the last element, the loop exits naturally.
        }
    }

    fn pick_next_entity(&mut self) -> Option<SchedEntity> {
        let now = sched_clock();
        self.replenish_throttled(now);
        if let Some(task) = self.stop.pick_next() {
            return task.as_thread().cloned().map(|thread| (task, thread));
        }
        for _ in 0..self.real_time.len() {
            let task = self.real_time.pick_next().unwrap();
            if task_cpu_eligible(&task, now) {
                let thread = task.as_thread().unwrap().clone();
                return Some((task, thread));
            }
            self.throttled.push(task);
        }
        for _ in 0..self.fair.len() {
            let task = self.fair.pick_next().unwrap();
            if task_cpu_eligible(&task, now) {
                let thread = task.as_thread().unwrap().clone();
                return Some((task, thread));
            }
            self.throttled.push(task);
        }
        self.idle
            .pick_next()
            .and_then(|task| task.as_thread().cloned().map(|thread| (task, thread)))
    }

    fn enqueue_entity(&mut self, (task, thread): SchedEntity, flags: Option<EnqueueFlags>) {
        match thread.sched_attr().policy_kind() {
            SchedPolicyKind::Stop => self.stop.enqueue(task, flags),
            SchedPolicyKind::RealTime => self.real_time.enqueue(task, flags),
            SchedPolicyKind::Fair => self.fair.enqueue(task, flags),
            SchedPolicyKind::Idle => self.idle.enqueue(task, flags),
        }
    }

    fn load_stats(&self) -> PerCpuLoadStats {
        let queue_len =
            (self.stop.len() + self.real_time.len() + self.fair.len() + self.throttled.len())
                as u32;
        let is_idle = match &self.current {
            Some(((_, thread), _)) => thread.sched_attr().policy_kind() == SchedPolicyKind::Idle,
            None => true,
        };
        PerCpuLoadStats { queue_len, is_idle }
    }
}

impl LocalRunQueue for PerCpuClassRqSet {
    fn current(&self) -> Option<&Arc<Task>> {
        self.current.as_ref().map(|((task, _), _)| task)
    }

    fn try_pick_next(&mut self) -> Option<&Arc<Task>> {
        // OSTD's might_preempt() can call try_pick_next() directly after a
        // runnable task is enqueued, without a preceding update_current().
        // A switch in that path must not discard the outgoing task's TSC
        // runtime when CurrentRuntime::new() replaces its old accounting
        // state. Charge before pick_next_entity() checks another task's
        // eligibility and potentially advances a shared cgroup ancestor.
        if let Some(((task, _), rt)) = &mut self.current {
            rt.update();
            rt.settle_bandwidth(task, rt.start);
        }
        self.pick_next_entity().and_then(|next| {
            // We guarantee that a task can appear at once in a `PerCpuClassRqSet`. So, the `next` cannot be the same
            // as the current task here.
            let runtime = CurrentRuntime::new(&next.0);
            if let Some((old, _)) = self.current.replace((next, runtime)) {
                if task_cpu_eligible(&old.0, sched_clock()) {
                    self.enqueue_entity(old, None);
                } else {
                    self.throttled.push(old.0);
                }
            }
            self.current.as_ref().map(|((task, _), _)| task)
        })
    }

    fn update_current(&mut self, flags: UpdateFlags) -> bool {
        // Settle the running task FIRST. Replenishment invokes
        // task_cpu_eligible() and can advance the same cgroup or a common
        // ancestor's quota window before the retained owner sees a tick that
        // straddles the boundary. That loses old-window CPU runtime and
        // defeats positive overrun debt. N0 keeps all these transitions
        // serialized inside the existing IRQ-disabled per-CPU runqueue lock.
        let mut quota_exhausted = false;
        let (should_preempt, mut lookahead) = if let Some(((task, cur), rt)) = &mut self.current {
            rt.update();
            rt.settle_bandwidth(task, rt.start);
            quota_exhausted = !task_cpu_eligible(task, rt.start);
            let attr = &cur.sched_attr();

            match attr.policy_kind() {
                SchedPolicyKind::Stop => (self.stop.update_current(rt, attr, flags), 0),
                SchedPolicyKind::RealTime => (self.real_time.update_current(rt, attr, flags), 1),
                SchedPolicyKind::Fair => (self.fair.update_current(rt, attr, flags), 2),
                SchedPolicyKind::Idle => (self.idle.update_current(rt, attr, flags), 3),
            }
        } else {
            (false, 4)
        };

        // This timer callback also fires when idle. Once the current task's
        // exact interval is charged, reconsider throttled tasks and update
        // the available queues without letting an early eligibility check
        // erase the last active cgroup period.
        self.replenish_throttled(sched_clock());

        if matches!(flags, UpdateFlags::Wait | UpdateFlags::Exit) {
            lookahead = 4;
        }

        quota_exhausted
            || should_preempt
            || (lookahead >= 1 && !self.stop.is_empty())
            || (lookahead >= 2 && !self.real_time.is_empty())
            || (lookahead >= 3 && !self.fair.is_empty())
            || (lookahead >= 4 && !self.idle.is_empty())
    }

    fn dequeue_current(&mut self) -> Option<Arc<Task>> {
        self.current.take().map(|((cur_task, _), _)| {
            cur_task.schedule_info().cpu.set_to_none();
            cur_task
        })
    }
}

/// Holds per-CPU load information.
struct PerCpuLoadStats {
    /// The length of the run queue (excluding the idle task).
    queue_len: u32,
    /// If the CPU is currently idle.
    ///
    /// A CPU is said to be idle when it is running the idle task, or it is not
    /// running any task at all. The latter case is very unlikely to happen
    /// (almost a bug if it happens) as the idle task should always be runnable.
    is_idle: bool,
}

impl SchedulerStats for ClassScheduler {
    fn nr_queued_and_running(&self) -> (u32, u32) {
        self.rqs.iter().fold((0, 0), |(queued, running), rq| {
            let PerCpuLoadStats { queue_len, is_idle } = rq.lock().load_stats();
            (queued + queue_len, running + u32::from(!is_idle))
        })
    }
}

impl Default for ClassScheduler {
    fn default() -> Self {
        Self::new()
    }
}
