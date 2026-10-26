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
