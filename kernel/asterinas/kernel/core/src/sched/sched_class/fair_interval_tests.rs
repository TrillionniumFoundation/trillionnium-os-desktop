// SPDX-License-Identifier: MPL-2.0

//! W1: actual class runqueues and Task objects at controlled cycle endpoints.
//!
//! These tasks are never injected into OSTD's live FIFO test scheduler. This
//! tests production queue transitions, not group shares or SMP context switches.

use ostd::prelude::ktest;

use super::*;
use crate::{
    sched::{CpuRunQueueFixture, RealTimePolicy, RealTimePriority, SchedPolicy},
    thread::kernel_thread::ThreadOptions,
};

const START: u64 = 1_000_000;

fn tasks() -> [Arc<Task>; 2] {
    aster_time::init_for_ktest();
    core::array::from_fn(|_| ThreadOptions::new(|| {}).build())
}

fn vruntime(task: &Task) -> u64 {
    task.as_thread()
        .unwrap()
        .sched_attr()
        .fair
        .vruntime
        .load(Ordering::Relaxed)
}

#[ktest]
fn fair_direct_handoff_charges_the_outgoing_tail_once() {
    let [outgoing, incoming] = tasks();
    let mut rq = CpuRunQueueFixture::new(outgoing.clone(), START);
    rq.enqueue(incoming.clone());
    let incoming_initial = vruntime(&incoming);
    assert!(Arc::ptr_eq(
        &rq.pick(&[START + 11, START + 29]).unwrap(),
        &incoming
    ));
    assert_eq!(vruntime(&outgoing), 29);
    assert_eq!(vruntime(&incoming), incoming_initial);
    rq.update(UpdateFlags::Tick, START + 41);
    assert_eq!(vruntime(&outgoing), 29);
    assert_eq!(vruntime(&incoming), incoming_initial + 12);
}

#[ktest]
fn fair_tick_and_yield_do_not_recharge_a_handoff_prefix() {
    for flag in [UpdateFlags::Tick, UpdateFlags::Yield] {
        let [outgoing, incoming] = tasks();
        let mut rq = CpuRunQueueFixture::new(outgoing.clone(), START);
        rq.enqueue(incoming);
        rq.update(flag, START + 11);
        assert_eq!(vruntime(&outgoing), 11);
        rq.pick(&[START + 17, START + 29]).unwrap();
        assert_eq!(vruntime(&outgoing), 29);
    }
}

fn assert_dequeue_tail(flag: UpdateFlags) {
    let [outgoing, incoming] = tasks();
    let mut rq = CpuRunQueueFixture::new(outgoing.clone(), START);
    rq.update(flag, START + 11);
    assert_eq!(vruntime(&outgoing), 11);
    assert!(Arc::ptr_eq(&rq.dequeue(START + 19).unwrap(), &outgoing));
    assert_eq!(vruntime(&outgoing), 19);
    assert!(rq.pick(&[START + 29]).is_none());
    assert_eq!(vruntime(&outgoing), 29);
    assert!(!rq.update(UpdateFlags::Tick, START + 31));
    assert_eq!(vruntime(&outgoing), 31);
    // The existing class slice stops at Wait/Exit; only the independently
    // retained execution cursor must advance through these handoff retries.
    assert_eq!(rq.cfs_runtime(), Some((START + 11, 11, 11)));
    rq.enqueue(incoming.clone());
    let incoming_initial = vruntime(&incoming);
    rq.pick(&[START + 37, START + 41]).unwrap();
    assert_eq!(vruntime(&outgoing), 41);
    rq.update(UpdateFlags::Tick, START + 53);
    assert_eq!(vruntime(&outgoing), 41);
    assert_eq!(vruntime(&incoming), incoming_initial + 12);
}

#[ktest]
fn fair_waiting_owner_retains_its_tail_through_empty_selection_retries() {
    assert_dequeue_tail(UpdateFlags::Wait);
}

#[ktest]
fn fair_exiting_owner_retains_its_tail_through_empty_selection_retries() {
    assert_dequeue_tail(UpdateFlags::Exit);
}

#[ktest]
fn fair_nice_change_does_not_reprice_the_already_running_interval() {
    let [outgoing, _] = tasks();
    let mut rq = CpuRunQueueFixture::new(outgoing.clone(), START);
    let attr = outgoing.as_thread().unwrap().sched_attr();
    let new_nice = Nice::try_from(5).unwrap();
    attr.set_policy(SchedPolicy::Fair(new_nice));
    rq.update(UpdateFlags::Tick, START + 100);
    assert_eq!(vruntime(&outgoing), 100);
    rq.update(UpdateFlags::Tick, START + 200);
    assert_eq!(
        vruntime(&outgoing),
        100 + 100 * WEIGHT_0 / nice_to_weight(new_nice)
    );
}

#[ktest]
fn fair_policy_change_keeps_execution_with_its_original_class_until_checkpoint() {
    let [outgoing, _] = tasks();
    let mut rq = CpuRunQueueFixture::new(outgoing.clone(), START);
    let attr = outgoing.as_thread().unwrap().sched_attr();
    attr.set_policy(SchedPolicy::RealTime {
        rt_prio: RealTimePriority::new(1),
        rt_policy: RealTimePolicy::Fifo,
    });
    rq.update(UpdateFlags::Tick, START + 11);
    assert_eq!(vruntime(&outgoing), 11);
    rq.update(UpdateFlags::Tick, START + 19);
    assert_eq!(vruntime(&outgoing), 11);
    attr.set_policy(SchedPolicy::Fair(Nice::default()));
    rq.update(UpdateFlags::Tick, START + 29);
    assert_eq!(vruntime(&outgoing), 11);
    rq.update(UpdateFlags::Tick, START + 41);
    assert_eq!(vruntime(&outgoing), 23);
}

#[ktest]
fn fair_backward_cycle_read_does_not_replay_a_charged_prefix() {
    let [outgoing, _] = tasks();
    let mut rq = CpuRunQueueFixture::new(outgoing.clone(), START);
    rq.update(UpdateFlags::Tick, START + 11);
    rq.update(UpdateFlags::Tick, START + 7);
    rq.update(UpdateFlags::Tick, START + 13);
    assert_eq!(vruntime(&outgoing), 13);
}
