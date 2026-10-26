// SPDX-License-Identifier: MPL-2.0

//! Existing legacy-root CPU placement only. No live non-root admission and no
//! group weights are enabled. All effectful publication owns one off-CPU Task.

use ostd::sync::Waiter;

use super::{
    capacity::Placement,
    request::{AffinityRequest, Outcome},
    transfer::QueuedRemoval,
    *,
};
use crate::prelude::{Errno, Result};

pub(super) fn active_request(task: &Task) -> Option<Arc<AffinityRequest<'static>>> {
    task.as_thread()?
        .sched_attr()
        .affinity_request()
        .filter(|request| request.outcome().is_none())
}

pub(super) fn needs_migration(task: &Task, cpu: CpuId) -> bool {
    active_request(task).is_some_and(|request| request.destination() != cpu)
}

fn placement(thread: &Thread) -> Placement {
    match thread.sched_attr().policy() {
        SchedPolicy::Fair(_) => Placement::Fair,
        SchedPolicy::RealTime { rt_prio, .. } => Placement::RealTime(rt_prio.get()),
        _ => panic!("non-POSIX policy admitted to affinity transfer"),
    }
}

pub(super) fn finish_request(
    task: &Task,
    request: &Arc<AffinityRequest<'static>>,
    outcome: Outcome,
) {
    let finished = request.finish(outcome);
    drop(finished.unused_capacity);
    drop(
        task.as_thread()
            .unwrap()
            .sched_attr()
            .retire_affinity_request(request),
    );
}

pub(super) fn finish_unclaimed(
    task: &Task,
    request: &Arc<AffinityRequest<'static>>,
    outcome: Outcome,
) {
    if let Some(finished) = request.finish_if_pending(outcome) {
        drop(finished.unused_capacity);
        drop(
            task.as_thread()
                .unwrap()
                .sched_attr()
                .retire_affinity_request(request),
        );
    }
}

pub(crate) fn set_thread_affinity(thread: &Thread, mask: &CpuSet) -> Result<()> {
    if mask.is_empty() {
        return Err(Errno::EINVAL.into());
    }
    let task = thread.try_task().ok_or(Errno::ESRCH)?;
    if thread.is_exited() {
        return Err(Errno::ESRCH.into());
    }
    let scheduler = *CLASS_SCHEDULER.get().ok_or(Errno::EAGAIN)?;
    scheduler.change_affinity(task, mask)
}

impl ClassScheduler {
    fn choose_affinity_cpu(&self, task: &Task, mask: &CpuSet) -> CpuId {
        if let Some(cpu) = task.cpu().get().filter(|cpu| mask.contains(*cpu)) {
            return cpu;
        }
        if let Some(cpu) = task
            .as_thread()
            .unwrap()
            .sched_attr()
            .last_cpu()
            .filter(|cpu| mask.contains(*cpu))
        {
            return cpu;
        }
        let _irq = disable_local();
        mask.iter()
            .min_by_key(|cpu| self.rqs[cpu.as_usize()].lock().load_stats().queue_len)
            .unwrap()
    }

    fn change_affinity(&'static self, task: Arc<Task>, mask: &CpuSet) -> Result<()> {
        let thread = task.as_thread().ok_or(Errno::EPERM)?.clone();
        let mut admin = thread.sched_attr().administer();
        if thread.is_exited() {
            return Err(Errno::ESRCH.into());
        }
        if !matches!(
            admin.policy(),
            SchedPolicy::Fair(_) | SchedPolicy::RealTime { .. }
        ) {
            return Err(Errno::EOPNOTSUPP.into());
        }
        // No production API replaces these layouts. Refuse a prepared layout
        // before any mask publication rather than pretending it is root.
        for rq in &self.rqs {
            let _irq = disable_local();
            if !rq.lock().fair.root_migration_supported() {
                return Err(Errno::EOPNOTSUPP.into());
            }
        }
        let destination = self.choose_affinity_cpu(&task, mask);
        let capacity = self
            .reserve_migration_capacity(destination, placement(&thread))
            .map_err(|error| match error {
                ostd::Error::NoMemory => Errno::ENOMEM,
                ostd::Error::Overflow => Errno::EOVERFLOW,
                _ => Errno::EAGAIN,
            })?;
        let is_self =
            Task::current().is_some_and(|current| core::ptr::eq(&*current, task.as_ref()));
        let (waiter, controller) = if is_self {
            (None, None)
        } else {
            let (waiter, controller) = Waiter::try_new_pair().map_err(|_| Errno::ENOMEM)?;
            (Some(waiter), Some(controller))
        };
        let generation = admin
            .next_affinity_generation()
            .map_err(|_| Errno::EOVERFLOW)?;
        let request =
            AffinityRequest::new(generation, capacity, controller).map_err(|_| Errno::ENOMEM)?;
        // Keep this CPU non-preemptible through releasing administration: a
        // remotely published RT target must not strand its controller's lock.
        let irq = disable_local();
        let retired = thread
            .sched_attr()
            .install_affinity_request(request.clone(), &thread, mask);
        drop(admin);
        drop(retired);
        self.drive_affinity(&task, &request);
        drop(irq);
        let outcome = if let Some(waiter) = waiter {
            waiter
                .wait_until_or_cancelled(|| request.outcome(), || Ok::<(), ()>(()))
                .unwrap()
        } else {
            request.wait()
        };
        outcome.map_err(Into::into)
    }

    fn drive_affinity(&self, task: &Arc<Task>, request: &Arc<AffinityRequest<'static>>) {
        loop {
            let Some(cpu) = task.cpu().get() else {
                finish_unclaimed(task, request, Ok(()));
                return;
            };
            let removed = {
                let mut rq = self.rqs[cpu.as_usize()].lock();
                if task.cpu().get() != Some(cpu) {
                    continue;
                }
                if cpu == request.destination() {
                    drop(rq);
                    finish_unclaimed(task, request, Ok(()));
                    return;
                }
                // Current/incoming/outgoing owners finish via their actual
                // completed switch; timer/yield observes the pending request.
                rq.take_queued_task(task)
                    .expect("admitted CPU layout changed")
            };
            let Some(removed) = removed else { return };
            let rollback = QueuedRemoval::new(self, removed);
            let debt = rollback.debt();
            let entity = (rollback.task().clone(), task.as_thread().unwrap().clone());
            self.publish_detached(entity, None, Some(debt), Some(rollback), None);
            return;
        }
    }

    fn detached_debt(&self, task: &Task) -> u64 {
        let Some(source) = task.as_thread().unwrap().sched_attr().last_cpu() else {
            return 0;
        };
        self.rqs[source.as_usize()]
            .lock()
            .fair
            .debt(task)
            .expect("unadmitted source route")
    }

    /// Caller holds the scheduling token (cpu stays Some while detached), and
    /// no rq lock. Preserve one IRQ scope through publication and completion.
    pub(super) fn publish_detached(
        &self,
        entity: SchedEntity,
        flags: Option<EnqueueFlags>,
        debt: Option<u64>,
        mut rollback: Option<QueuedRemoval<'_>>,
        mut initial_cpu: Option<CpuId>,
    ) -> Option<CpuId> {
        let _irq = disable_local();
        let (task, thread) = entity;
        let source = thread.sched_attr().last_cpu();
        let mut debt = debt;
        loop {
            let request = active_request(&task);
            let mut forced = request
                .as_ref()
                .and_then(|request| request.claim().map(|capacity| (request.clone(), capacity)));
            let destination = forced.as_ref().map_or_else(
                || {
                    // A new Task already advanced round-robin when claiming its
                    // token. Reuse that choice once, while retaining the same
                    // forced-request priority and final mask checks below.
                    initial_cpu
                        .take()
                        .filter(|cpu| {
                            thread
                                .atomic_cpu_affinity()
                                .load(Ordering::Acquire)
                                .contains(*cpu)
                        })
                        .unwrap_or_else(|| {
                            self.select_cpu(&thread, flags.unwrap_or(EnqueueFlags::Wake))
                        })
                },
                |(request, _)| request.destination(),
            );
            if debt.is_none() && source.is_some_and(|cpu| cpu != destination) {
                debt = Some(self.detached_debt(&task));
            }
            let mut rq = self.rqs[destination.as_usize()].lock();
            if forced.is_none() {
                // Synchronize with request+mask installation before publishing
                // a waker's stale pre-selection, including a dormant ack race.
                let latest = thread.sched_attr().affinity_request();
                if latest.as_ref().is_some_and(|request| {
                    request.outcome().is_none() && request.destination() != destination
                }) || !thread
                    .atomic_cpu_affinity()
                    .load(Ordering::Acquire)
                    .contains(destination)
                {
                    drop(rq);
                    continue;
                }
            }
            let preempt = rq.should_preempt_for(&thread);
            if let Some((request, capacity)) = &mut forced {
                assert_eq!(
                    request.placement(),
                    placement(&thread),
                    "policy changed through placement pin"
                );
                capacity.consume(&mut rq);
            }
            if source.is_some_and(|cpu| cpu != destination) {
                rq.fair
                    .rebase_debt(&task, debt.unwrap_or(0))
                    .expect("unadmitted destination route");
            }
            if let Some(rollback) = &mut rollback {
                rollback.disarm_rollback();
            }
            task.cpu().set_anyway(destination);
            thread.sched_attr().set_last_cpu(destination);
            let now = CpuClockSample::read();
            rq.settle_runtime(now);
            if task_cpu_eligible(&task, now.boottime_ns) {
                rq.enqueue_entity((task.clone(), thread.clone()), flags);
            } else {
                rq.park_throttled(task.clone());
            }
            drop(rq);
            drop(rollback);
            if let Some((request, capacity)) = forced {
                drop(capacity);
                finish_request(&task, &request, Ok(()));
                // Destination tick observes the new queue. No new IPI closure
                // allocation is required to commit a forced migration.
                return None;
            }
            return preempt.then_some(destination);
        }
    }
}
