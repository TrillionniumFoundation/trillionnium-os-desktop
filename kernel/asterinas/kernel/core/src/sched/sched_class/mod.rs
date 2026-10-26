// SPDX-License-Identifier: MPL-2.0

//! Completely Fair Scheduler (CFS).

#![warn(unused)]

use alloc::{boxed::Box, sync::Arc, vec::Vec};
use core::{fmt, ops::Bound, sync::atomic::Ordering};

use ostd::{
    arch::read_tsc as sched_clock,
    cpu::{CpuId, CpuSet, PinCurrentCpu, all_cpus},
    irq::disable_local,
    sync::{LocalIrqDisabled, Mutex, SpinLock},
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

mod administration;
mod capacity;
mod clock;
mod policy;
mod time;

mod fair;
mod idle;
mod real_time;
mod stop;
#[cfg(ktest)]
mod switch_tests;

pub(crate) use self::{
    administration::{SchedAdministration, UserSchedSnapshot},
    policy::{LinuxSchedPolicy, SchedPolicy},
    real_time::{RealTimePolicy, RealTimePriority},
};
use self::{
    clock::CpuClockSample,
    policy::{SchedPolicyKind, SchedPolicyState},
};

type SchedEntity = (Arc<Task>, Arc<Thread>);

struct SelectedEntity {
    entity: SchedEntity,
    fair: Option<fair::FairSelection>,
}

impl SelectedEntity {
    fn other(entity: SchedEntity) -> Self {
        Self { entity, fair: None }
    }
}

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
pub(crate) fn with_current_cpu_bandwidth_settled<R>(apply: impl FnOnce(Option<u64>) -> R) -> R {
    let irq_guard = disable_local();
    let Some(scheduler) = CLASS_SCHEDULER.get() else {
        // No class-scheduled POSIX task can run before scheduler initialization.
        // This also allows standalone owner ktests using OSTD's FIFO scheduler.
        return apply(CpuClockSample::read().boottime_ns);
    };
    let mut rq = scheduler.rqs[irq_guard.current_cpu().as_usize()].lock();
    let now = CpuClockSample::read();
    rq.settle_runtime(now);
    apply(now.boottime_ns)
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
        rq.settle_runtime(CpuClockSample::read());
    }
    let result = publish();
    {
        let mut rq = rq.lock();
        rq.settle_runtime(CpuClockSample::read());
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
    cpu: CpuId,
    stop: stop::StopClassRq,
    real_time: real_time::RealTimeClassRq,
    fair: fair::FairClassRq,
    idle: idle::IdleClassRq,
    // Runqueue-local parked tasks; no userspace syscall is required to refill.
    throttled: Vec<Arc<Task>>,
    throttled_reserved: usize,
    current: Option<(SchedEntity, CurrentRuntime)>,
    // dequeue_current() changes runnable state before OSTD selects the next
    // task. Move (not copy) the same accounting segment here until handoff,
    // including selection retries. It holds no additional budget or usage.
    dequeued: Option<SwitchedOut>,
    dequeue_exiting: bool,
    // OSTD has selected current but is still physically executing previous.
    // Neither previous nor a late wake may be published to any queue yet.
    switching: Option<PendingSwitch>,
}

#[derive(Clone, Copy)]
enum OutgoingState {
    Runnable,
    Waiting { woken: bool },
    Exiting,
}

struct SwitchedOut {
    entity: SchedEntity,
    runtime: CurrentRuntime,
    state: OutgoingState,
}

struct PendingSwitch {
    previous: SwitchedOut,
    fair: Option<fair::FairSelection>,
    finished: bool,
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
    // Independent of the class slice: also retains Wait/Exit handoff tails.
    fair: fair::FairRuntime,
    // This cursor partitions debits to the original cgroup bandwidth owner.
    // It stores no quota or usage. Configuration must not advance `start`,
    // which is still needed for the next CFS/RT runtime update.
    bandwidth_accounted_through_ns: Option<u64>,
    // Reference only: all accounting remains in the original CpuMax. Resolve
    // at a segment boundary, never after the interval has already executed.
    bandwidth_owner: Option<CpuChargeOwner>,
}

impl CurrentRuntime {
    fn new_at(task: &Task, now: CpuClockSample) -> Self {
        CurrentRuntime {
            start: now.cycles,
            delta: 0,
            period_delta: 0,
            fair: fair::FairRuntime::new_at(task, now.cycles),
            bandwidth_accounted_through_ns: now.boottime_ns,
            bandwidth_owner: CpuChargeOwner::for_task(task),
        }
    }

    fn update_at(&mut self, now: u64) {
        // A failed paired sample can retain an older conversion base. Preserve
        // the CFS/RT high-water mark so recovery cannot replay those cycles;
        // bandwidth independently fences the unreliable nanosecond interval.
        self.delta = now.saturating_sub(self.start);
        self.start = self.start.max(now);
        self.period_delta = self.period_delta.saturating_add(self.delta);
    }

    fn settle_runtime(&mut self, task: &Task, now: CpuClockSample) -> Option<u64> {
        let fair_delta = self.fair.settle(task, now.cycles);
        match (self.bandwidth_accounted_through_ns, now.boottime_ns) {
            (Some(from), Some(until)) if until >= from => {
                if until > from
                    && let Some(owner) = &self.bandwidth_owner
                {
                    owner.charge(from, until);
                }
                self.bandwidth_accounted_through_ns = Some(until);
            }
            _ => {
                if let Some(owner) = &self.bandwidth_owner {
                    owner.invalidate_accounting();
                }
                // A later successful read cannot account for a missing prefix.
                self.bandwidth_accounted_through_ns = None;
            }
        }

        // The next interval may belong to a newly published incarnation. An
        // exited task keeps its original owner even after the Process is
        // detached or reaped. Re-resolving its node would redirect its tail.
        if !task.as_thread().is_some_and(|thread| thread.is_exited()) {
            self.bandwidth_owner = CpuChargeOwner::for_task(task);
        }
        fair_delta
    }

    #[cfg(ktest)]
    fn with_bandwidth_settled<R>(
        &mut self,
        task: &Task,
        now: CpuClockSample,
        apply: impl FnOnce(Option<u64>) -> R,
    ) -> R {
        let _ = self.settle_runtime(task, now);
        apply(now.boottime_ns)
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
        let runtime = CurrentRuntime::new_at(&task, CpuClockSample::fixture(now));
        Self { task, runtime }
    }

    pub(crate) fn configure<R>(&mut self, now: u64, apply: impl FnOnce(u64) -> R) -> R {
        self.runtime
            .with_bandwidth_settled(&self.task, CpuClockSample::fixture(now), |sample| {
                apply(sample.unwrap())
            })
    }

    pub(crate) fn update(&mut self, now: u64) -> (u64, u64) {
        self.runtime.update_at(now);
        let _ = self
            .runtime
            .settle_runtime(&self.task, CpuClockSample::fixture(now));
        (self.runtime.delta, self.runtime.period_delta)
    }

    /// Starts the actual runtime using a sample from an original ClockSource.
    pub(crate) fn new_sample(task: Arc<Task>, sample: aster_time::ClockSourceSample) -> Self {
        let runtime = CurrentRuntime::new_at(&task, CpuClockSample::from_sample(sample));
        Self { task, runtime }
    }

    /// Settles calibrated nanoseconds while preserving the separate CFS cycles.
    pub(crate) fn update_sample(&mut self, sample: aster_time::ClockSourceSample) -> (u64, u64) {
        let sample = CpuClockSample::from_sample(sample);
        self.runtime.update_at(sample.cycles);
        let _ = self.runtime.settle_runtime(&self.task, sample);
        (self.runtime.delta, self.runtime.period_delta)
    }

    pub(crate) fn configure_sample<R>(
        &mut self,
        sample: aster_time::ClockSourceSample,
        apply: impl FnOnce(Option<u64>) -> R,
    ) -> R {
        self.runtime
            .with_bandwidth_settled(&self.task, CpuClockSample::from_sample(sample), apply)
    }

    /// Runs the production runtime's two checkpoints around a real owner
    /// publication. No fixture is inserted into the FIFO ktest scheduler.
    pub(crate) fn publish<R>(&mut self, before: u64, after: u64, publish: impl FnOnce() -> R) -> R {
        let _ = self
            .runtime
            .settle_runtime(&self.task, CpuClockSample::fixture(before));
        let result = publish();
        let _ = self
            .runtime
            .settle_runtime(&self.task, CpuClockSample::fixture(after));
        result
    }
}

/// Exercises the actual class queues without replacing OSTD's ktest scheduler.
#[cfg(ktest)]
pub(crate) struct CpuRunQueueFixture {
    rq: PerCpuClassRqSet,
}

#[cfg(ktest)]
impl CpuRunQueueFixture {
    pub(crate) fn new(task: Arc<Task>, now: u64) -> Self {
        let cpu = disable_local().current_cpu();
        let mut rq = PerCpuClassRqSet::new(cpu);
        let _irq_guard = disable_local();
        let thread = task.as_thread().unwrap().clone();
        let runtime = CurrentRuntime::new_at(&task, CpuClockSample::fixture(now));
        if thread.sched_attr().policy_kind() == SchedPolicyKind::Fair {
            rq.fair.attach_current(&task);
        }
        rq.current = Some(((task, thread), runtime));
        Self { rq }
    }

    /// An immutable, fully prepared internal topology; not a live membership
    /// admission interface. Preparation and all capacity growth precede IRQ
    /// disabling and use the same production queues/selection transactions.
    pub(crate) fn with_groups(
        task: Arc<Task>,
        now: u64,
        groups: &[(crate::fs::cgroupfs::CpuSchedulingGroup, usize)],
        bindings: &[(Arc<Task>, usize)],
    ) -> ostd::Result<Self> {
        let prepared = fair::group::GroupTree::prepare(groups, bindings)?;
        let mut fixture = Self::new(task.clone(), now);
        fixture
            .rq
            .throttled
            .try_reserve_exact(bindings.len())
            .map_err(|_| ostd::Error::NoMemory)?;
        fixture.rq.fair.groups = prepared;
        fixture.rq.fair.attach_current(&task);
        Ok(fixture)
    }

    pub(crate) fn try_group_enqueue(
        &mut self,
        task: Arc<Task>,
    ) -> core::result::Result<(), Arc<Task>> {
        let _irq_guard = disable_local();
        self.rq.fair.try_enqueue(task, Some(EnqueueFlags::Spawn))
    }

    pub(crate) fn group_state(&self, id: usize) -> (u64, usize, bool) {
        self.rq.fair.groups.state(id)
    }

    pub(crate) fn group_capacities(&self) -> alloc::vec::Vec<(usize, usize)> {
        self.rq.fair.groups.capacities()
    }

    pub(crate) fn enqueue(&mut self, task: Arc<Task>) {
        let _irq_guard = disable_local();
        let thread = task.as_thread().unwrap().clone();
        self.rq
            .enqueue_entity((task, thread), Some(EnqueueFlags::Spawn));
    }

    pub(crate) fn pick(&mut self, samples: &[u64]) -> Option<Arc<Task>> {
        let _irq_guard = disable_local();
        let mut samples = samples.iter();
        let next = self
            .rq
            .try_pick_next_with_clock(|| {
                CpuClockSample::fixture(*samples.next().expect("unexpected clock read"))
            })
            .cloned();
        assert!(samples.next().is_none(), "unused clock sample");
        next
    }

    /// Controlled physical-boundary simulation on the production transaction.
    /// Does not run a fixture Task in OSTD or establish a hardware switch.
    pub(crate) fn pick_switch(&mut self, samples: &[u64]) -> Option<Arc<Task>> {
        let _irq_guard = disable_local();
        let physical = self
            .rq
            .current
            .as_ref()
            .map(|(entity, _)| entity.0.clone())
            .or_else(|| self.rq.dequeued.as_ref().map(|old| old.entity.0.clone()))?;
        let mut samples = samples.iter();
        let result = self
            .rq
            .try_pick_next_at(
                || CpuClockSample::fixture(*samples.next().expect("unexpected clock read")),
                Some(&physical),
            )
            .cloned();
        assert!(samples.next().is_none(), "unused clock sample");
        result
    }

    pub(crate) fn finish_switch(&mut self, previous: &Arc<Task>, now: u64) -> bool {
        let _irq_guard = disable_local();
        self.rq
            .finish_switch_at(previous, CpuClockSample::fixture(now))
    }

    pub(crate) fn complete_switch(&mut self, previous: &Arc<Task>, now: u64) -> Option<Arc<Task>> {
        let _irq_guard = disable_local();
        self.rq
            .complete_switch_at(previous, CpuClockSample::fixture(now))
            .map(|entity| entity.0)
    }

    pub(crate) fn wake_outgoing(&mut self, task: &Arc<Task>) -> bool {
        let _irq_guard = disable_local();
        self.rq.latch_outgoing_wake(task)
    }

    pub(crate) fn queued_count(&self) -> u32 {
        self.rq.load_stats().queue_len
    }

    pub(crate) fn update(&mut self, flags: UpdateFlags, now: u64) -> bool {
        let _irq_guard = disable_local();
        self.rq
            .update_current_at(flags, CpuClockSample::fixture(now))
    }

    pub(crate) fn dequeue(&mut self, now: u64) -> Option<Arc<Task>> {
        let _irq_guard = disable_local();
        self.rq.dequeue_current_at(CpuClockSample::fixture(now))
    }

    pub(crate) fn has_current(&self) -> bool {
        self.rq.current.is_some()
    }

    pub(crate) fn cfs_runtime(&self) -> Option<(u64, u64, u64)> {
        let rt = self
            .rq
            .current
            .as_ref()
            .map(|(_, rt)| rt)
            .or_else(|| self.rq.dequeued.as_ref().map(|previous| &previous.runtime))?;
        Some((rt.start, rt.delta, rt.period_delta))
    }

    pub(crate) fn is_throttled(&self, task: &Arc<Task>) -> bool {
        self.rq
            .throttled
            .iter()
            .any(|queued| Arc::ptr_eq(queued, task))
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
    administration: Mutex<administration::AdministrationState>,
    policy: SchedPolicyState,
    last_cpu: AtomicCpuId,
    real_time: real_time::RealTimeAttr,
    fair: fair::FairAttr,
}

impl SchedAttr {
    /// Constructs a new `SchedAttr` with the given scheduling policy.
    pub(crate) fn new(policy: SchedPolicy) -> Self {
        Self {
            administration: Mutex::new(administration::AdministrationState::new(policy)),
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
    fn apply_policy(&self, policy: SchedPolicy) {
        self.policy.set(policy, |policy| match policy {
            SchedPolicy::RealTime { rt_prio, rt_policy } => {
                self.real_time.update(rt_prio.get(), rt_policy);
            }
            SchedPolicy::Fair(nice) => self.fair.update(nice),
            _ => {}
        });
    }

    #[cfg(ktest)]
    fn apply_policy_update<T>(&self, f: impl FnOnce(&mut SchedPolicy) -> T) -> T {
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

    // Controlled queue fixtures construct non-live policies without sleeping.
    #[cfg(ktest)]
    pub(crate) fn set_policy(&self, policy: SchedPolicy) {
        self.apply_policy(policy);
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
        loop {
            let selected = self.select_cpu(&thread, flags);
            let cpu = match task.cpu().set_if_is_none(selected) {
                Ok(()) => {
                    let mut rq = self.rqs[selected.as_usize()].lock();
                    let preempt = rq.should_preempt_for(&thread);
                    thread.sched_attr().set_last_cpu(selected);
                    rq.enqueue_entity((task, thread), Some(flags));
                    return preempt.then_some(selected);
                }
                Err(owner) => owner,
            };
            let mut rq = self.rqs[cpu.as_usize()].lock();
            // Completion may have published sleep or moved a woken waiter
            // while we waited. Never claim None back onto this stale CPU.
            if task.cpu().get() != Some(cpu) {
                continue;
            }
            if flags == EnqueueFlags::Wake && rq.latch_outgoing_wake(&task) {
                // A merged wake is not permission to preempt the reserved
                // incoming task (which may be higher-priority RT). Retry
                // consumes its latch naturally; completed publication makes
                // the actual destination priority decision after release.
                return None;
            }
            // The owning queue/current/transit token already holds this task.
            return None;
        }
    }

    fn finish_switch(&self, previous: &Arc<Task>) -> bool {
        let guard = disable_local();
        self.rqs[guard.current_cpu().as_usize()]
            .lock()
            .finish_switch_at(previous, CpuClockSample::read())
    }

    fn complete_switch(&self, previous: &Arc<Task>) -> Option<CpuId> {
        let guard = disable_local();
        let cpu = guard.current_cpu();
        let outgoing = {
            let mut rq = self.rqs[cpu.as_usize()].lock();
            rq.complete_switch_at(previous, CpuClockSample::read())?
        };
        // The detached token keeps cpu=origin, so duplicate wakers cannot
        // claim it. Select and publish with the source rq already unlocked.
        let target = self.select_cpu(&outgoing.1, EnqueueFlags::Wake);
        let mut destination = self.rqs[target.as_usize()].lock();
        let preempt = destination.should_preempt_for(&outgoing.1);
        outgoing.0.cpu().set_anyway(target);
        outgoing.1.sched_attr().set_last_cpu(target);
        destination.enqueue_entity(outgoing, Some(EnqueueFlags::Wake));
        preempt.then_some(target)
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
        let class_rq = |cpu| SpinLock::new(PerCpuClassRqSet::new(cpu));
        ClassScheduler {
            rqs: all_cpus().map(class_rq).collect(),
            last_chosen_cpu: AtomicCpuId::default(),
        }
    }

    // TODO: Implement a better algorithm and replace the current naive implementation.
    fn select_cpu(&self, thread: &Thread, flags: EnqueueFlags) -> CpuId {
        let affinity = thread.atomic_cpu_affinity().load(Ordering::Relaxed);
        if let Some(last_cpu) = thread.sched_attr().last_cpu()
            && affinity.contains(last_cpu)
        {
            return last_cpu;
        }
        let _ = flags;

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
    fn new(cpu: CpuId) -> Self {
        Self {
            cpu,
            stop: stop::StopClassRq::new(),
            real_time: real_time::RealTimeClassRq::new(cpu),
            fair: fair::FairClassRq::new(cpu),
            idle: idle::IdleClassRq::new(),
            throttled: Vec::new(),
            throttled_reserved: 0,
            current: None,
            dequeued: None,
            dequeue_exiting: false,
            switching: None,
        }
    }

    fn should_preempt_for(&self, thread: &Thread) -> bool {
        self.current.as_ref().is_none_or(|((_, current), _)| {
            thread.sched_attr().policy() < current.sched_attr().policy()
        })
    }

    fn latch_outgoing_wake(&mut self, task: &Arc<Task>) -> bool {
        let previous = self
            .switching
            .as_mut()
            .map(|pending| &mut pending.previous)
            .or(self.dequeued.as_mut());
        let Some(previous) = previous.filter(|old| Arc::ptr_eq(&old.entity.0, task)) else {
            return false;
        };
        if let OutgoingState::Waiting { woken } = &mut previous.state {
            *woken = true;
        }
        // Exiting never becomes runnable; Runnable already owns its wake.
        true
    }

    fn settle_runtime(&mut self, now: CpuClockSample) {
        let executing = if let Some(pending) = self.switching.as_mut().filter(|p| !p.finished) {
            Some((&pending.previous.entity.0, &mut pending.previous.runtime))
        } else if let Some(((task, _), rt)) = self.current.as_mut() {
            Some((&*task, rt))
        } else {
            self.dequeued
                .as_mut()
                .map(|old| (&old.entity.0, &mut old.runtime))
        };
        if let Some((task, rt)) = executing
            && let Some(delta) = rt.settle_runtime(task, now)
        {
            self.fair.charge_current(task, delta);
        }
    }

    fn finish_switch_at(&mut self, previous: &Arc<Task>, now: CpuClockSample) -> bool {
        let Some(pending) = self.switching.as_ref() else {
            // Bootstrap / a scheduler without a class-accounted outgoing task.
            return false;
        };
        assert!(!pending.finished);
        assert!(Arc::ptr_eq(&pending.previous.entity.0, previous));
        self.settle_runtime(now);
        let pending = self.switching.as_mut().unwrap();
        if let Some(selection) = pending.fair.take() {
            self.fair.commit(selection);
        } else {
            self.fair.finish_current();
        }
        let (incoming, runtime) = self.current.as_mut().unwrap();
        *runtime = CurrentRuntime::new_at(&incoming.0, now);
        pending.finished = true;
        // This is a physical completion checkpoint, not a cancellable
        // admission. A shared-owner tail may exhaust quota after selection.
        // Request another decision only after OSTD's switch cleanup is safe.
        !task_cpu_eligible(&incoming.0, now.boottime_ns)
    }

    fn complete_switch_at(
        &mut self,
        previous: &Arc<Task>,
        now: CpuClockSample,
    ) -> Option<SchedEntity> {
        let pending = self.switching.take()?;
        assert!(pending.finished);
        assert!(Arc::ptr_eq(&pending.previous.entity.0, previous));
        self.settle_runtime(now);
        match pending.previous.state {
            OutgoingState::Runnable => {
                // W3A retains runnable/throttled placement on the source CPU.
                if task_cpu_eligible(previous, now.boottime_ns) {
                    self.enqueue_entity(pending.previous.entity, None);
                } else {
                    self.park_throttled(pending.previous.entity.0);
                }
                None
            }
            OutgoingState::Waiting { woken: true } => Some(pending.previous.entity),
            OutgoingState::Waiting { woken: false } | OutgoingState::Exiting => {
                previous.cpu().set_to_none();
                None
            }
        }
    }

    fn park_throttled(&mut self, task: Arc<Task>) {
        let required = self
            .throttled
            .len()
            .checked_add(self.throttled_reserved)
            .and_then(|count| count.checked_add(1))
            .expect("throttled capacity overflow");
        if required > self.throttled.capacity() {
            self.throttled.reserve(required - self.throttled.len());
        }
        self.throttled.push(task);
    }

    fn replenish_throttled(&mut self, now: CpuClockSample) {
        // Inspect the existing allocation in place. The former mem::take()
        // discarded its capacity every tick and pushed blocked tasks into a
        // fresh Vec while the IRQ-disabled runqueue spinlock was held.
        // swap_remove leaves capacity intact and never reallocates this Vec.
        let mut index = 0;
        while index < self.throttled.len() {
            if !task_cpu_eligible(&self.throttled[index], now.boottime_ns) {
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

    fn pick_next_entity(&mut self, now: CpuClockSample) -> Option<SelectedEntity> {
        self.replenish_throttled(now);
        if let Some(task) = self.stop.pick_next() {
            return task
                .as_thread()
                .cloned()
                .map(|thread| SelectedEntity::other((task, thread)));
        }
        for _ in 0..self.real_time.len() {
            let task = self.real_time.pick_next().unwrap();
            if task_cpu_eligible(&task, now.boottime_ns) {
                let thread = task.as_thread().unwrap().clone();
                return Some(SelectedEntity::other((task, thread)));
            }
            self.park_throttled(task);
        }
        for _ in 0..self.fair.len() {
            let (task, selection) = self.fair.select_next().unwrap();
            if task_cpu_eligible(&task, now.boottime_ns) {
                let thread = task.as_thread().unwrap().clone();
                return Some(SelectedEntity {
                    entity: (task, thread),
                    fair: Some(selection),
                });
            }
            self.fair.cancel(selection);
            self.park_throttled(task);
        }
        self.idle.pick_next().and_then(|task| {
            task.as_thread()
                .cloned()
                .map(|thread| SelectedEntity::other((task, thread)))
        })
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

    fn try_pick_next_with_clock(
        &mut self,
        read_clock: impl FnMut() -> CpuClockSample,
    ) -> Option<&Arc<Task>> {
        let physical = Task::current();
        self.try_pick_next_at(read_clock, physical.as_ref().map(|task| task.as_ref()))
    }

    fn try_pick_next_at(
        &mut self,
        mut read_clock: impl FnMut() -> CpuClockSample,
        physical: Option<&Task>,
    ) -> Option<&Arc<Task>> {
        // OSTD's might_preempt() can call try_pick_next() directly after a
        // runnable task is enqueued, without a preceding update_current().
        // A switch in that path must not discard the outgoing task's TSC
        // runtime when a new CurrentRuntime replaces its old accounting
        // state. Charge before pick_next_entity() checks another task's
        // eligibility and potentially advances a shared cgroup ancestor.
        let mut now = read_clock();
        if self.switching.is_some() {
            self.settle_runtime(now);
            return None;
        }
        if let Some((_, rt)) = &mut self.current {
            rt.update_at(now.cycles);
        }
        self.settle_runtime(now);
        if self
            .dequeued
            .as_ref()
            .is_some_and(|old| matches!(old.state, OutgoingState::Waiting { woken: true }))
        {
            // A wake during a no-next Retry must restore the same task: OSTD
            // returns via its ptr_eq DoNothing path, with no physical switch.
            let old = self.dequeued.take().unwrap();
            self.current = Some((old.entity, old.runtime));
            return self.current.as_ref().map(|((task, _), _)| task);
        }
        while let Some(mut next) = self.pick_next_entity(now) {
            let cut = read_clock();
            // The dispatcher still has this original running owner. Close
            // its tail at exactly the next segment's start before dropping
            // the runtime or advancing any shared ancestor to this time.
            self.settle_runtime(cut);
            // Selection can straddle a window or spend the remaining quota.
            // The candidate must still be eligible after that actual debit.
            if !task_cpu_eligible(&next.entity.0, cut.boottime_ns) {
                if let Some(selection) = next.fair.take() {
                    self.fair.cancel(selection);
                }
                self.park_throttled(next.entity.0);
                now = cut;
                continue;
            }
            let previous = self
                .current
                .take()
                .map(|(entity, runtime)| SwitchedOut {
                    entity,
                    runtime,
                    state: OutgoingState::Runnable,
                })
                .or_else(|| self.dequeued.take());
            let physical_previous = previous.as_ref().is_some_and(|old| {
                physical.is_some_and(|physical| core::ptr::eq(physical, old.entity.0.as_ref()))
            });
            let runtime = CurrentRuntime::new_at(&next.entity.0, cut);
            self.current = Some((next.entity, runtime));
            if physical_previous {
                // Keep the FAIR selection pending and previous out of every
                // selectable queue until OSTD has really saved its context.
                self.switching = Some(PendingSwitch {
                    previous: previous.unwrap(),
                    fair: next.fair.take(),
                    finished: false,
                });
            } else {
                // Bootstrap has no class-accounted outgoing task. Standalone
                // queue fixtures likewise do not run their tasks in OSTD.
                if let Some(selection) = next.fair.take() {
                    self.fair.commit(selection);
                } else {
                    self.fair.finish_current();
                }
                if let Some(old) = previous {
                    if matches!(old.state, OutgoingState::Runnable) {
                        if task_cpu_eligible(&old.entity.0, cut.boottime_ns) {
                            self.enqueue_entity(old.entity, None);
                        } else {
                            self.park_throttled(old.entity.0);
                        }
                    } else {
                        old.entity.0.cpu().set_to_none();
                    }
                }
            }
            return self.current.as_ref().map(|((task, _), _)| task);
        }
        None
    }

    fn update_current_at(&mut self, flags: UpdateFlags, now: CpuClockSample) -> bool {
        if let Some(pending) = self.switching.as_mut().filter(|p| !p.finished) {
            pending.previous.runtime.update_at(now.cycles);
            self.settle_runtime(now);
            return false;
        }
        if matches!(flags, UpdateFlags::Wait | UpdateFlags::Exit) {
            self.dequeue_exiting = flags == UpdateFlags::Exit;
        }

        // Settle the running task FIRST. Replenishment invokes
        // task_cpu_eligible() and can advance the same cgroup or a common
        // ancestor's quota window before the retained owner sees a tick that
        // straddles the boundary. That loses old-window CPU runtime and
        // defeats positive overrun debt. N0 keeps all these transitions
        // serialized inside the existing IRQ-disabled per-CPU runqueue lock.
        if let Some((_, rt)) = &mut self.current {
            rt.update_at(now.cycles);
        }
        self.settle_runtime(now);
        let mut quota_exhausted = false;
        let (should_preempt, mut lookahead) = if let Some(((task, cur), rt)) = &mut self.current {
            quota_exhausted = !task_cpu_eligible(task, now.boottime_ns);
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
        self.replenish_throttled(now);

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

    fn dequeue_current_at(&mut self, now: CpuClockSample) -> Option<Arc<Task>> {
        self.settle_runtime(now);
        let current = self.current.take()?;
        debug_assert!(self.dequeued.is_none());
        assert!(self.switching.is_none());
        let task = current.0.0.clone();
        self.dequeued = Some(SwitchedOut {
            entity: current.0,
            runtime: current.1,
            state: if self.dequeue_exiting {
                OutgoingState::Exiting
            } else {
                OutgoingState::Waiting { woken: false }
            },
        });
        Some(task)
    }
}

impl LocalRunQueue for PerCpuClassRqSet {
    fn current(&self) -> Option<&Arc<Task>> {
        self.current.as_ref().map(|((task, _), _)| task)
    }

    fn try_pick_next(&mut self) -> Option<&Arc<Task>> {
        self.try_pick_next_with_clock(CpuClockSample::read)
    }

    fn update_current(&mut self, flags: UpdateFlags) -> bool {
        self.update_current_at(flags, CpuClockSample::read())
    }

    fn dequeue_current(&mut self) -> Option<Arc<Task>> {
        self.dequeue_current_at(CpuClockSample::read())
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
