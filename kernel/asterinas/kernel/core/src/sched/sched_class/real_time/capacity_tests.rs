// SPDX-License-Identifier: MPL-2.0

//! Actual Task queues at controlled endpoints; no physical migration evidence.

use alloc::vec::Vec;

use ostd::{irq::disable_local, prelude::ktest};

use super::*;
use crate::{sched::SchedPolicy, thread::kernel_thread::ThreadOptions};

const PRIORITY: u8 = 7;

fn task() -> Arc<Task> {
    ThreadOptions::new(|| {})
        .sched_policy(SchedPolicy::RealTime {
            rt_prio: RealTimePriority::new(PRIORITY),
            rt_policy: RealTimePolicy::Fifo,
        })
        .build()
}

#[ktest]
fn rt_reservations_remain_with_both_physical_arrays_after_flips() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let tasks = [task(), task()];
    let mut prepared = rq.capacity_need(PRIORITY).unwrap().allocate().unwrap();
    {
        let _irq = disable_local();
        assert!(rq.can_install_capacity(&prepared, PRIORITY));
        rq.install_and_reserve(&mut prepared, PRIORITY);
        rq.enqueue(tasks[0].clone(), None);
        let first = rq.pick_next().unwrap();
        assert!(Arc::ptr_eq(&first, &tasks[0]));
        assert!(rq.index);
        rq.enqueue(tasks[1].clone(), None);
        let second = rq.pick_next().unwrap();
        assert!(Arc::ptr_eq(&second, &tasks[1]));
        assert!(!rq.index);
        for array in &rq.array {
            assert_eq!(array.reserved[usize::from(PRIORITY)], 1);
            assert!(!array.map[usize::from(PRIORITY)]);
        }
        rq.release_reservation(PRIORITY);
        assert!(rq.array.iter().all(|array| array.reserved[7] == 0));
    }
    drop(prepared);
}

#[ktest]
fn rt_ordinary_enqueue_leaves_prepared_slots_available() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let mut prepared = rq.capacity_need(PRIORITY).unwrap().allocate().unwrap();
    {
        let _irq = disable_local();
        rq.install_and_reserve(&mut prepared, PRIORITY);
    }
    drop(prepared);
    let capacity = rq.array[1].queue[usize::from(PRIORITY)].capacity();
    let tasks: Vec<_> = (0..capacity).map(|_| task()).collect();
    let _irq = disable_local();
    for task in &tasks {
        rq.enqueue(task.clone(), None);
    }
    let queue = &rq.array[1].queue[usize::from(PRIORITY)];
    assert_eq!(queue.len(), capacity);
    assert!(queue.capacity() > capacity);
    assert_eq!(rq.array[1].reserved[usize::from(PRIORITY)], 1);
    assert!(queue.len() + rq.array[1].reserved[7] <= queue.capacity());
    rq.release_reservation(PRIORITY);
}

#[ktest]
fn rt_stale_capacity_preparation_refuses_without_changing_the_queue() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let prepared = rq.capacity_need(PRIORITY).unwrap().allocate().unwrap();
    let prepared_capacity = prepared.buffers[1].as_ref().unwrap().capacity();
    let tasks: Vec<_> = (0..=prepared_capacity).map(|_| task()).collect();
    {
        let _irq = disable_local();
        for task in &tasks {
            rq.enqueue(task.clone(), None);
        }
    }
    let queue = &rq.array[1].queue[usize::from(PRIORITY)];
    let remaining = queue.capacity() - queue.len();
    let extra: Vec<_> = (0..remaining).map(|_| task()).collect();
    let _irq = disable_local();
    for task in &extra {
        rq.enqueue(task.clone(), None);
    }
    let before = rq.capacity_need(PRIORITY).unwrap();
    let count = rq.nr_running;
    assert!(!rq.can_install_capacity(&prepared, PRIORITY));
    let after = rq.capacity_need(PRIORITY).unwrap();
    assert_eq!(before.required, after.required);
    assert_eq!(before.capacity, after.capacity);
    assert_eq!(rq.nr_running, count);
    assert!(rq.array.iter().all(|array| array.reserved[7] == 0));
    assert_eq!(rq.array[1].peek_prio(), Some(PRIORITY));
    assert!(rq.capacity_need(0).is_err());
    assert!(rq.capacity_need(100).is_err());
}

#[ktest]
fn rt_replacement_preserves_fifo_and_retires_only_empty_storage() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let first = task();
    {
        let _irq = disable_local();
        rq.enqueue(first.clone(), None);
    }
    let capacity = rq.array[1].queue[usize::from(PRIORITY)].capacity();
    let mut tasks = Vec::with_capacity(capacity);
    tasks.push(first);
    tasks.extend((1..capacity).map(|_| task()));
    {
        let _irq = disable_local();
        for task in &tasks[1..] {
            rq.enqueue(task.clone(), None);
        }
    }
    let need = rq.capacity_need(PRIORITY).unwrap();
    assert_eq!(need.priority, PRIORITY);
    let mut prepared = need.allocate().unwrap();
    {
        let _irq = disable_local();
        rq.install_and_reserve(&mut prepared, PRIORITY);
        assert_eq!(rq.nr_running, tasks.len());
        assert!(prepared.buffers.iter().flatten().all(VecDeque::is_empty));
        assert_eq!(prepared.buffers[1].as_ref().unwrap().capacity(), capacity);
        let installed = rq.capacity_need(PRIORITY).unwrap().capacity;
        rq.release_reservation(PRIORITY);
        assert_eq!(rq.capacity_need(PRIORITY).unwrap().capacity, installed);
        for expected in &tasks {
            let actual = rq.pick_next().unwrap();
            assert!(Arc::ptr_eq(&actual, expected));
        }
        assert_eq!(rq.nr_running, 0);
        assert!(rq.array.iter().all(|array| array.reserved[7] == 0));
    }
    drop(prepared);
}

#[ktest]
#[should_panic(expected = "RT capacity reservation already released")]
fn rt_capacity_cancellation_cannot_refund_the_last_slot_twice() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let mut prepared = rq.capacity_need(PRIORITY).unwrap().allocate().unwrap();
    let _irq = disable_local();
    rq.install_and_reserve(&mut prepared, PRIORITY);
    rq.release_reservation(PRIORITY);
    rq.release_reservation(PRIORITY);
}
