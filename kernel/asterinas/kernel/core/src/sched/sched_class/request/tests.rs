// SPDX-License-Identifier: MPL-2.0

//! Request ownership and actual container reservations; not live placement.

use ostd::{cpu::CpuId, irq::disable_local, prelude::ktest};

use super::*;
use crate::sched::sched_class::ClassScheduler;

#[ktest]
fn claimed_request_preserves_first_terminal_result() {
    let scheduler = ClassScheduler::new();
    let capacity = scheduler
        .reserve_migration_capacity(CpuId::bsp(), Placement::Fair)
        .unwrap();
    let request = AffinityRequest::new(7, capacity, None).unwrap();
    assert_eq!(request.generation(), 7);
    assert_eq!(request.destination(), CpuId::bsp());
    assert_eq!(request.placement(), Placement::Fair);
    let claimed = request.claim().unwrap();
    assert!(request.claim().is_none());
    assert_eq!(request.outcome(), None);
    let first = request.finish(Err(Errno::ESRCH));
    assert!(first.changed && first.unused_capacity.is_none());
    let repeated = request.finish(Ok(()));
    assert!(!repeated.changed && repeated.unused_capacity.is_none());
    assert_eq!(request.wait(), Err(Errno::ESRCH));
    assert!(request.claim().is_none());
    drop(claimed);
    let _irq = disable_local();
    assert_eq!(scheduler.rqs[0].lock().throttled_reserved, 0);
}

#[ktest]
fn unclaimed_completion_returns_capacity_for_outer_scope_refund() {
    let scheduler = ClassScheduler::new();
    let capacity = scheduler
        .reserve_migration_capacity(CpuId::bsp(), Placement::Fair)
        .unwrap();
    let request = AffinityRequest::new(8, capacity, None).unwrap();
    let retired = request.finish(Ok(()));
    assert!(retired.changed && retired.unused_capacity.is_some());
    {
        let _irq = disable_local();
        assert_eq!(scheduler.rqs[0].lock().throttled_reserved, 1);
    }
    assert_eq!(request.wait(), Ok(()));
    drop(retired);
    let _irq = disable_local();
    assert_eq!(scheduler.rqs[0].lock().throttled_reserved, 0);
}

#[ktest]
fn dropping_unpublished_request_cancels_its_original_capacity() {
    let scheduler = ClassScheduler::new();
    let capacity = scheduler
        .reserve_migration_capacity(CpuId::bsp(), Placement::RealTime(7))
        .unwrap();
    let request = AffinityRequest::new(9, capacity, None).unwrap();
    drop(request);
    let _irq = disable_local();
    assert_eq!(scheduler.rqs[0].lock().throttled_reserved, 0);
}

#[ktest]
fn nonowner_ack_cannot_finish_a_claimed_transfer() {
    let scheduler = ClassScheduler::new();
    let capacity = scheduler
        .reserve_migration_capacity(CpuId::bsp(), Placement::Fair)
        .unwrap();
    let request = AffinityRequest::new(10, capacity, None).unwrap();
    let claimed = request.claim().unwrap();
    assert!(request.finish_if_pending(Ok(())).is_none());
    assert_eq!(request.outcome(), None);
    assert!(request.claim().is_none());
    // Only the owner may publish/restore and then terminate the attempt.
    drop(claimed);
    assert!(request.finish(Ok(())).changed);
    assert_eq!(request.outcome(), Some(Ok(())));
}

#[ktest]
fn terminal_request_releases_controller_before_last_request_drop() {
    let scheduler = ClassScheduler::new();
    let capacity = scheduler
        .reserve_migration_capacity(CpuId::bsp(), Placement::Fair)
        .unwrap();
    let (waiter, controller) = ostd::sync::Waiter::try_new_pair().unwrap();
    assert_eq!(Arc::strong_count(&controller), 2);
    let request = AffinityRequest::new(11, capacity, Some(controller.clone())).unwrap();
    assert_eq!(Arc::strong_count(&controller), 3);
    let finished = request.finish_if_pending(Ok(())).unwrap();
    assert!(finished.changed);
    // A later last request Arc can be retired by a hot scheduler path. It no
    // longer owns the controller Waker (and hence the controller Task data).
    assert_eq!(Arc::strong_count(&controller), 2);
    assert!(!request.finish(Ok(())).changed);
    drop(finished);
    drop(request);
    assert_eq!(Arc::strong_count(&controller), 2);
    drop(waiter);
}
