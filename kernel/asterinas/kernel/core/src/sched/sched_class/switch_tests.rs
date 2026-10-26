// SPDX-License-Identifier: MPL-2.0

//! Controlled Scheduler-trait notifications, not physical-switch evidence.

use ostd::prelude::ktest;

use super::*;
use crate::thread::kernel_thread::ThreadOptions;

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
