// SPDX-License-Identifier: MPL-2.0

//! Controlled Scheduler-trait notifications, not physical-switch evidence.

use ostd::prelude::ktest;

use super::*;
use crate::thread::kernel_thread::ThreadOptions;

#[ktest]
fn a_new_task_advances_round_robin_once_through_actual_enqueue() {
    // A06 run 40373542005: two selections per spawn cancelled rotation on
    // two CPUs, leaving the real two-pthread unlimited baseline near 100%.
    // Count the actual selection path even in the ordinary one-CPU ktest.
    aster_time::init_for_ktest();
    let scheduler = ClassScheduler::new();
    let task = ThreadOptions::new(|| {}).build();
    assert!(task.cpu().get().is_none());
    assert!(task.as_thread().unwrap().sched_attr().last_cpu().is_none());
    scheduler.enqueue(task.clone(), EnqueueFlags::Spawn);
    assert_eq!(scheduler.round_robin_selections.load(Ordering::Relaxed), 1);
    let cpu = task.cpu().get().unwrap();
    assert_eq!(task.as_thread().unwrap().sched_attr().last_cpu(), Some(cpu));
    let _irq = disable_local();
    let rq = scheduler.rqs[cpu.as_usize()].lock();
    assert_eq!(rq.load_stats().queue_len, 1);
}

#[ktest]
fn merged_wait_wake_does_not_preempt_the_reserved_rt_task() {
    aster_time::init_for_ktest();
    let scheduler = ClassScheduler::new();
    let guard = disable_local();
    let cpu = guard.current_cpu();
    let previous = ThreadOptions::new(|| {}).build();
    let incoming = ThreadOptions::new(|| {}).build();
    incoming
        .as_thread()
        .unwrap()
        .sched_attr()
        .set_policy(SchedPolicy::RealTime {
            rt_prio: RealTimePriority::new(1),
            rt_policy: RealTimePolicy::Fifo,
        });
    previous.cpu().set_anyway(cpu);
    previous.as_thread().unwrap().sched_attr().set_last_cpu(cpu);
    {
        let mut rq = scheduler.rqs[cpu.as_usize()].lock();
        rq.current = Some((
            (incoming.clone(), incoming.as_thread().unwrap().clone()),
            CurrentRuntime::new_at(&incoming, CpuClockSample::fixture(100)),
        ));
        rq.switching = Some(PendingSwitch {
            previous: SwitchedOut {
                entity: (previous.clone(), previous.as_thread().unwrap().clone()),
                runtime: CurrentRuntime::new_at(&previous, CpuClockSample::fixture(0)),
                state: OutgoingState::Waiting { woken: false },
            },
            fair: None,
            finished: false,
            fair_debt: None,
        });
    }
    assert!(
        scheduler
            .enqueue(previous.clone(), EnqueueFlags::Wake)
            .is_none()
    );
    let rq = scheduler.rqs[cpu.as_usize()].lock();
    assert!(matches!(
        rq.switching.as_ref().unwrap().previous.state,
        OutgoingState::Waiting { woken: true }
    ));
    assert!(Arc::ptr_eq(&rq.current.as_ref().unwrap().0.0, &incoming));
    assert_eq!(rq.load_stats().queue_len, 0);
}
