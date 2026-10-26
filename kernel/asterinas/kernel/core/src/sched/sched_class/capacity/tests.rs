// SPDX-License-Identifier: MPL-2.0

//! Real scheduler queues and Tasks; no physical migration is claimed here.

use ostd::prelude::ktest;

use super::*;
use crate::thread::kernel_thread::ThreadOptions;

fn task() -> Arc<Task> {
    ThreadOptions::new(|| {}).build()
}

#[ktest]
fn capacity_cancellation_refunds_class_and_throttle_once() {
    let scheduler = ClassScheduler::new();
    let cpu = CpuId::bsp();
    let ticket = scheduler
        .reserve_migration_capacity(cpu, Placement::Fair)
        .unwrap();
    {
        let _irq = disable_local();
        let rq = scheduler.rqs[cpu.as_usize()].lock();
        assert_eq!(rq.throttled_reserved, 1);
        assert_eq!(rq.fair.capacity_need().unwrap().required, 2);
    }
    drop(ticket);
    let _irq = disable_local();
    let rq = scheduler.rqs[cpu.as_usize()].lock();
    assert_eq!(rq.throttled_reserved, 0);
    assert_eq!(rq.fair.capacity_need().unwrap().required, 1);
}

#[ktest]
fn ordinary_fair_producer_preserves_the_transfer_slot_until_commit() {
    let scheduler = ClassScheduler::new();
    let cpu = CpuId::bsp();
    let mut ticket = scheduler
        .reserve_migration_capacity(cpu, Placement::Fair)
        .unwrap();
    let capacity = {
        let _irq = disable_local();
        scheduler.rqs[cpu.as_usize()]
            .lock()
            .fair
            .capacity_need()
            .unwrap()
            .capacity
    };
    let tasks: Vec<_> = (0..=capacity).map(|_| task()).collect();
    for task in &tasks[..capacity] {
        scheduler.enqueue(task.clone(), EnqueueFlags::Spawn);
    }
    {
        let _irq = disable_local();
        let mut rq = scheduler.rqs[cpu.as_usize()].lock();
        let before = rq.fair.capacity_need().unwrap().capacity;
        assert!(before > capacity);
        ticket.consume(&mut rq);
        let task = tasks.last().unwrap().clone();
        let thread = task.as_thread().unwrap().clone();
        rq.enqueue_entity((task, thread), None);
        assert_eq!(rq.fair.capacity_need().unwrap().capacity, before);
        assert_eq!(rq.fair.len(), tasks.len());
        assert_eq!(rq.throttled_reserved, 0);
    }
    drop(ticket);
}

#[ktest]
fn ordinary_throttle_parking_preserves_the_transfer_slot() {
    let scheduler = ClassScheduler::new();
    let cpu = CpuId::bsp();
    let mut ticket = scheduler
        .reserve_migration_capacity(cpu, Placement::Fair)
        .unwrap();
    let capacity = {
        let _irq = disable_local();
        scheduler.rqs[cpu.as_usize()].lock().throttled.capacity()
    };
    let tasks: Vec<_> = (0..=capacity).map(|_| task()).collect();
    {
        let _irq = disable_local();
        let mut rq = scheduler.rqs[cpu.as_usize()].lock();
        for task in &tasks[..capacity] {
            rq.park_throttled(task.clone());
        }
        let before = rq.throttled.capacity();
        assert!(before > capacity);
        ticket.consume(&mut rq);
        rq.park_throttled(tasks.last().unwrap().clone());
        assert_eq!(rq.throttled.capacity(), before);
        assert_eq!(rq.throttled.len(), tasks.len());
    }
    drop(ticket);
}

#[ktest]
fn stale_preparation_changes_neither_queue_nor_reservations() {
    let mut rq = PerCpuClassRqSet::new(CpuId::bsp());
    let prepared = rq
        .migration_capacity_need(Placement::Fair)
        .unwrap()
        .allocate()
        .unwrap();
    let first = task();
    {
        let _irq = disable_local();
        rq.enqueue_entity((first.clone(), first.as_thread().unwrap().clone()), None);
    }
    let capacity = rq.fair.capacity_need().unwrap().capacity;
    let more: Vec<_> = (1..capacity).map(|_| task()).collect();
    let _irq = disable_local();
    for task in more {
        let thread = task.as_thread().unwrap().clone();
        rq.enqueue_entity((task, thread), None);
    }
    let count = rq.fair.len();
    assert!(!rq.can_install_migration_capacity(&prepared, Placement::Fair));
    assert_eq!(rq.fair.len(), count);
    assert_eq!(rq.throttled_reserved, 0);
    assert_eq!(rq.fair.capacity_need().unwrap().required, count + 1);
    drop(_irq);
    drop(prepared);
}

#[ktest]
fn closed_prepared_root_is_not_a_legacy_migration_fallback() {
    let scheduler = ClassScheduler::new();
    let prepared = fair::group::GroupTree::prepare(&[], &[]).unwrap();
    {
        let _irq = disable_local();
        scheduler.rqs[0].lock().fair.groups = prepared;
    }
    assert!(matches!(
        scheduler.reserve_migration_capacity(CpuId::bsp(), Placement::Fair),
        Err(ostd::Error::InvalidArgs)
    ));
    let _irq = disable_local();
    let rq = scheduler.rqs[0].lock();
    assert!(!rq.fair.root_migration_supported());
    assert_eq!(rq.fair.len(), 0);
    assert_eq!(rq.throttled_reserved, 0);
}

#[ktest]
fn capacity_overflow_fails_cold_without_a_partial_ticket() {
    let need = CapacityNeed {
        fair: None,
        rt: None,
        throttled_required: usize::MAX,
        throttled_capacity: 0,
    };
    assert!(matches!(need.allocate(), Err(ostd::Error::NoMemory)));
}

#[ktest]
#[should_panic(expected = "capacity ticket belongs to another runqueue")]
fn ticket_cannot_consume_another_scheduler_same_cpu_reservation() {
    let source = ClassScheduler::new();
    let other = ClassScheduler::new();
    let mut ticket = source
        .reserve_migration_capacity(CpuId::bsp(), Placement::Fair)
        .unwrap();
    let _other_ticket = other
        .reserve_migration_capacity(CpuId::bsp(), Placement::Fair)
        .unwrap();
    let _irq = disable_local();
    let mut wrong_rq = other.rqs[0].lock();
    ticket.consume(&mut wrong_rq);
}
