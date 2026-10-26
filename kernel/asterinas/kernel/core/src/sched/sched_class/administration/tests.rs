// SPDX-License-Identifier: MPL-2.0

use alloc::sync::Arc;
use core::sync::atomic::{AtomicBool, Ordering};

use ostd::{
    prelude::ktest,
    task::{Task, TaskOptions},
};

use super::*;
use crate::sched::Nice;

#[ktest]
fn administration_serializes_writers_without_blocking_policy_readers() {
    let attr = SchedAttr::new(SchedPolicy::default());
    let mut writer = attr.administer();
    let policy = SchedPolicy::Fair(Nice::try_from(3).unwrap());
    writer.set_policy(policy);
    assert_eq!(attr.policy(), policy);
    assert!(attr.administration.try_lock().is_none());
    drop(writer);
    assert!(attr.administration.try_lock().is_some());
    assert_eq!(attr.policy(), policy);
}

#[ktest]
fn administration_waiter_sleeps_and_resumes_after_original_writer_releases() {
    let attr = Arc::new(SchedAttr::new(SchedPolicy::default()));
    let entered = Arc::new(AtomicBool::new(false));
    let finished = Arc::new(AtomicBool::new(false));
    let writer = attr.administer();
    let helper = TaskOptions::new({
        let attr = attr.clone();
        let entered = entered.clone();
        let finished = finished.clone();
        move || {
            entered.store(true, Ordering::Release);
            let mut admin = attr.administer();
            admin.set_policy(SchedPolicy::Fair(Nice::try_from(4).unwrap()));
            finished.store(true, Ordering::Release);
        }
    })
    .spawn()
    .unwrap();
    Task::yield_now();
    assert!(entered.load(Ordering::Acquire));
    assert!(!finished.load(Ordering::Acquire));
    drop(writer);
    for _ in 0..8 {
        Task::yield_now();
        if finished.load(Ordering::Acquire) {
            break;
        }
    }
    assert!(finished.load(Ordering::Acquire));
    assert_eq!(attr.policy(), SchedPolicy::Fair(Nice::try_from(4).unwrap()));
    drop(helper);
}

#[ktest]
#[should_panic(expected = "This function might break atomic mode")]
fn administration_rejects_even_uncontended_irq_context() {
    let attr = SchedAttr::new(SchedPolicy::default());
    let _irq = ostd::irq::disable_local();
    let _admin = attr.administer();
}

#[ktest]
fn static_nice_and_declared_idle_survive_rt_policy_administration() {
    let attr = SchedAttr::new(SchedPolicy::Fair(Nice::try_from(8).unwrap()));
    let mut admin = attr.administer();
    admin.set_policy(SchedPolicy::RealTime {
        rt_prio: super::super::RealTimePriority::new(90),
        rt_policy: super::super::RealTimePolicy::Fifo,
    });
    assert_eq!(admin.nice(), Nice::try_from(8).unwrap());
    admin.set_user_idle();
    assert_eq!(admin.user_policy(), LinuxSchedPolicy::Idle);
    assert_eq!(admin.nice(), Nice::try_from(8).unwrap());
    admin.set_policy(SchedPolicy::Fair(Nice::MAX));
    assert_eq!(admin.user_policy(), LinuxSchedPolicy::Normal);
    assert_eq!(admin.nice(), Nice::MAX);
    admin.update_policy(|policy| *policy = SchedPolicy::Fair(Nice::try_from(4).unwrap()));
    assert_eq!(admin.nice(), Nice::try_from(4).unwrap());
    assert_eq!(attr.policy(), SchedPolicy::Fair(Nice::try_from(4).unwrap()));
}

#[ktest]
fn copied_user_snapshot_reconstructs_static_nice_declared_idle_and_rt_priority() {
    let attr = SchedAttr::new(SchedPolicy::Fair(Nice::try_from(8).unwrap()));
    let mut admin = attr.administer();
    admin.set_policy(SchedPolicy::RealTime {
        rt_prio: super::super::RealTimePriority::new(90),
        rt_policy: super::super::RealTimePolicy::RoundRobin {
            base_slice_factor: None,
        },
    });
    let rt = admin.snapshot();
    assert_eq!(rt.static_priority(), 10);
    assert_eq!(rt.nice(), Nice::try_from(8).unwrap());
    let reconstructed = SchedAttr::from_user_snapshot(rt);
    assert_eq!(reconstructed.user_snapshot(), rt);
    admin.set_user_idle();
    let idle = admin.snapshot();
    assert_eq!(idle.linux_policy(), LinuxSchedPolicy::Idle);
    assert_eq!(SchedAttr::from_user_snapshot(idle).user_snapshot(), idle);
    admin.set_policy(SchedPolicy::Fair(Nice::MAX));
    let normal19 = admin.snapshot();
    assert_eq!(normal19.linux_policy(), LinuxSchedPolicy::Normal);
    assert_eq!(normal19.nice(), Nice::MAX);
    assert_eq!(
        SchedAttr::from_user_snapshot(normal19).user_snapshot(),
        normal19
    );
}

#[ktest]
fn static_nice_updates_publish_fair_but_preserve_rt_and_declared_idle_class() {
    let attr = SchedAttr::new(SchedPolicy::Fair(Nice::try_from(8).unwrap()));
    let mut admin = attr.administer();
    admin.set_nice(Nice::try_from(9).unwrap());
    assert_eq!(attr.policy(), SchedPolicy::Fair(Nice::try_from(9).unwrap()));
    let rt = SchedPolicy::RealTime {
        rt_prio: super::super::RealTimePriority::new(90),
        rt_policy: super::super::RealTimePolicy::Fifo,
    };
    admin.set_policy(rt);
    admin.set_nice(Nice::try_from(-5).unwrap());
    assert_eq!(attr.policy(), rt);
    assert_eq!(admin.snapshot().nice(), Nice::try_from(-5).unwrap());
    admin.set_user_idle();
    admin.set_nice(Nice::try_from(4).unwrap());
    assert_eq!(attr.policy(), SchedPolicy::Fair(Nice::MAX));
    assert_eq!(admin.snapshot().linux_policy(), LinuxSchedPolicy::Idle);
    assert_eq!(admin.snapshot().nice(), Nice::try_from(4).unwrap());
    attr.set_last_cpu(ostd::cpu::CpuId::current_racy());
    let child = SchedAttr::from_user_snapshot(admin.snapshot());
    assert_eq!(child.last_cpu(), None);
    assert_eq!(child.user_snapshot(), admin.snapshot());
}
