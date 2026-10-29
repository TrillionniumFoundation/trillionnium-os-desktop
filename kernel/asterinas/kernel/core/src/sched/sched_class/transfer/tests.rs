// SPDX-License-Identifier: MPL-2.0

//! Actual production Task queues, controlled ownership, no physical SMP claim.

use ostd::prelude::ktest;

use super::*;
use crate::thread::kernel_thread::ThreadOptions;

fn task() -> Arc<Task> {
    ThreadOptions::new(|| {}).build()
}

#[ktest]
fn parked_removal_retains_original_slot_without_fair_weight_refund() {
    let mut rq = PerCpuClassRqSet::new(CpuId::bsp());
    let parked = task();
    {
        let _irq = disable_local();
        rq.park_throttled(parked.clone());
    }
    let capacity = rq.throttled.capacity();
    let others: Vec<_> = (0..capacity).map(|_| task()).collect();
    let _irq = disable_local();
    let removed = rq.take_queued_task(&parked).unwrap().unwrap();
    assert!(Arc::ptr_eq(removed.task(), &parked));
    assert_eq!(rq.throttled_reserved, 1);
    assert_eq!(rq.fair.len(), 0);
    assert_eq!(rq.real_time.len(), 0);
    for task in &others {
        rq.park_throttled(task.clone());
    }
    let before = rq.throttled.capacity();
    rq.restore_removed_task(removed);
    assert_eq!(rq.throttled.capacity(), before);
    assert_eq!(rq.throttled_reserved, 0);
    assert_eq!(rq.throttled.len(), others.len() + 1);
    assert_eq!(rq.fair.len(), 0);
}

#[ktest]
fn parked_commit_only_releases_rollback_capacity() {
    let mut rq = PerCpuClassRqSet::new(CpuId::bsp());
    let parked = task();
    let _irq = disable_local();
    rq.park_throttled(parked.clone());
    let mut removed = rq.take_queued_task(&parked).unwrap().unwrap();
    rq.commit_removed_task(&mut removed);
    assert_eq!(rq.throttled_reserved, 0);
    assert!(rq.throttled.is_empty());
    assert!(rq.take_queued_task(&parked).unwrap().is_none());
    assert!(Arc::ptr_eq(removed.task(), &parked));
}

#[ktest]
fn incoming_and_outgoing_reserved_entities_are_not_removed_as_queued() {
    aster_time::init_for_ktest();
    let mut rq = PerCpuClassRqSet::new(CpuId::bsp());
    let previous = task();
    let incoming = task();
    let _irq = disable_local();
    rq.current = Some((
        (previous.clone(), previous.as_thread().unwrap().clone()),
        CurrentRuntime::new_at(&previous, CpuClockSample::fixture(0)),
    ));
    rq.fair.attach_current(&previous);
    rq.enqueue_entity(
        (incoming.clone(), incoming.as_thread().unwrap().clone()),
        None,
    );
    assert!(rq.take_queued_task(&previous).unwrap().is_none());
    let mut samples = [1, 2].into_iter();
    rq.try_pick_next_at(
        || CpuClockSample::fixture(samples.next().unwrap()),
        Some(&previous),
    )
    .unwrap();
    assert!(rq.take_queued_task(&previous).unwrap().is_none());
    assert!(rq.take_queued_task(&incoming).unwrap().is_none());
    assert_eq!(rq.throttled_reserved, 0);
    rq.finish_switch_at(&previous, CpuClockSample::fixture(3));
    rq.complete_switch_at(&previous, CpuClockSample::fixture(4));
    let removed = rq.take_queued_task(&previous).unwrap().unwrap();
    rq.restore_removed_task(removed);
}

#[ktest]
fn prepared_route_removal_is_explicitly_refused_without_root_fallback() {
    let mut rq = PerCpuClassRqSet::new(CpuId::bsp());
    let task = task();
    rq.fair.groups = fair::group::GroupTree::prepare(&[], &[]).unwrap();
    let _irq = disable_local();
    assert!(matches!(
        rq.take_queued_task(&task),
        Err(ostd::Error::InvalidArgs)
    ));
    assert_eq!(rq.throttled_reserved, 0);
    assert_eq!(rq.fair.len(), 0);
}

#[ktest]
fn detached_raii_drop_restores_original_task_and_slot() {
    let scheduler = ClassScheduler::new();
    let parked = task();
    let removed = {
        let _irq = disable_local();
        let mut rq = scheduler.rqs[0].lock();
        rq.park_throttled(parked.clone());
        rq.take_queued_task(&parked).unwrap().unwrap()
    };
    let rollback = QueuedRemoval::new(&scheduler, removed);
    {
        let _irq = disable_local();
        let rq = scheduler.rqs[0].lock();
        assert_eq!(rq.throttled_reserved, 1);
        assert!(rq.throttled.is_empty());
    }
    // No rq is held when cancellation reacquires the original queue.
    drop(rollback);
    let _irq = disable_local();
    let rq = scheduler.rqs[0].lock();
    assert_eq!(rq.throttled_reserved, 0);
    assert_eq!(rq.throttled.len(), 1);
    assert!(Arc::ptr_eq(&rq.throttled[0], &parked));
}

#[ktest]
fn detached_raii_after_publication_refunds_only_old_slot() {
    let scheduler = ClassScheduler::new();
    let parked = task();
    let removed = {
        let _irq = disable_local();
        let mut rq = scheduler.rqs[0].lock();
        rq.park_throttled(parked.clone());
        rq.take_queued_task(&parked).unwrap().unwrap()
    };
    let mut rollback = QueuedRemoval::new(&scheduler, removed);
    // Controlled owner-transfer boundary; this test does not run a CPU move.
    rollback.disarm_rollback();
    drop(rollback);
    let _irq = disable_local();
    let rq = scheduler.rqs[0].lock();
    assert_eq!(rq.throttled_reserved, 0);
    assert!(rq.throttled.is_empty());
    assert_eq!(rq.fair.len(), 0);
    assert_eq!(rq.real_time.len(), 0);
}
