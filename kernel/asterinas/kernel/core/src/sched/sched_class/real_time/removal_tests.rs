// SPDX-License-Identifier: MPL-2.0

//! Controlled original-queue transfers, not live affinity or CPU-share evidence.

use alloc::vec::Vec;

use ostd::{irq::disable_local, prelude::ktest};

use super::*;
use crate::{sched::SchedPolicy, thread::kernel_thread::ThreadOptions};

const PRIORITY: u8 = 7;
const BUCKET: usize = PRIORITY as usize;

fn task() -> Arc<Task> {
    ThreadOptions::new(|| {})
        .sched_policy(SchedPolicy::RealTime {
            rt_prio: RealTimePriority::new(PRIORITY),
            rt_policy: RealTimePolicy::Fifo,
        })
        .build()
}

#[ktest]
fn rt_removal_uses_the_original_bucket_after_a_priority_change() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let original = task();
    let unknown = task();
    let _irq = disable_local();
    rq.enqueue(original.clone(), None);
    original
        .as_thread()
        .unwrap()
        .sched_attr()
        .set_policy(SchedPolicy::RealTime {
            rt_prio: RealTimePriority::new(2),
            rt_policy: RealTimePolicy::Fifo,
        });
    assert!(rq.take_task(&unknown).is_none());
    assert_eq!(rq.nr_running, 1);
    let removed = rq.take_task(&original).unwrap();
    assert!(Arc::ptr_eq(removed.task(), &original));
    assert_eq!(removed.array, 1);
    assert_eq!(removed.priority, BUCKET);
    assert_eq!(rq.nr_running, 0);
    assert!(!rq.array[1].map[BUCKET]);
    assert_eq!(rq.array[1].reserved[BUCKET], 1);
    assert_eq!(rq.array[0].reserved[BUCKET], 0);
    assert!(rq.array[1].queue[2].is_empty());
    let capacity = rq.array[1].queue[BUCKET].capacity();
    rq.restore_task(removed);
    assert_eq!(rq.array[1].queue[BUCKET].capacity(), capacity);
    assert_eq!(rq.array[1].reserved[BUCKET], 0);
    assert!(rq.array[1].map[BUCKET]);
    assert_eq!(rq.nr_running, 1);
    assert!(Arc::ptr_eq(&rq.pick_next().unwrap(), &original));
    assert_eq!(rq.nr_running, 0);
}

#[ktest]
fn rt_rollback_restores_sequence_order_after_pops_appends_and_array_flips() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let tasks: [Arc<Task>; 7] = core::array::from_fn(|_| task());
    let _irq = disable_local();
    for task in &tasks[..4] {
        rq.enqueue(task.clone(), None);
    }
    let third = rq.take_task(&tasks[2]).unwrap();
    let fourth = rq.take_task(&tasks[3]).unwrap();
    assert_eq!(rq.array[1].reserved[BUCKET], 2);
    assert!(Arc::ptr_eq(&rq.pick_next().unwrap(), &tasks[0]));
    assert!(Arc::ptr_eq(&rq.pick_next().unwrap(), &tasks[1]));
    assert!(rq.index);
    // Drain a subsequent active-array cycle while both original slots remain
    // held. New entries can then reach the original physical bucket again.
    rq.enqueue(tasks[4].clone(), None);
    assert!(Arc::ptr_eq(&rq.pick_next().unwrap(), &tasks[4]));
    assert!(!rq.index);
    rq.enqueue(tasks[5].clone(), None);
    rq.enqueue(tasks[6].clone(), None);
    let capacity = rq.array[1].queue[BUCKET].capacity();
    rq.restore_task(fourth);
    rq.restore_task(third);
    assert_eq!(rq.array[1].queue[BUCKET].capacity(), capacity);
    assert_eq!(rq.array[1].reserved[BUCKET], 0);
    assert_eq!(rq.nr_running, 4);
    for index in [2, 3, 5, 6] {
        assert!(Arc::ptr_eq(&rq.pick_next().unwrap(), &tasks[index]));
    }
    assert_eq!(rq.nr_running, 0);
    assert!(!rq.array[1].map[BUCKET]);
}

#[ktest]
fn rt_ordinary_enqueue_cannot_consume_a_rollback_slot() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let original = task();
    let removed = {
        let _irq = disable_local();
        rq.enqueue(original.clone(), None);
        rq.take_task(&original).unwrap()
    };
    let capacity = rq.array[1].queue[BUCKET].capacity();
    let tasks: Vec<_> = (0..capacity).map(|_| task()).collect();
    let _irq = disable_local();
    for task in &tasks {
        rq.enqueue(task.clone(), None);
    }
    assert_eq!(rq.array[1].reserved[BUCKET], 1);
    assert!(rq.array[1].queue[BUCKET].capacity() > capacity);
    let installed_capacity = rq.array[1].queue[BUCKET].capacity();
    rq.restore_task(removed);
    assert_eq!(rq.array[1].queue[BUCKET].capacity(), installed_capacity);
    assert_eq!(rq.array[1].reserved[BUCKET], 0);
    assert!(Arc::ptr_eq(&rq.pick_next().unwrap(), &original));
    for expected in &tasks {
        assert!(Arc::ptr_eq(&rq.pick_next().unwrap(), expected));
    }
    assert_eq!(rq.nr_running, 0);
}

#[ktest]
fn rt_commit_removed_refunds_only_its_slot_without_requeueing() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let tasks = [task(), task()];
    let _irq = disable_local();
    for task in &tasks {
        rq.enqueue(task.clone(), None);
    }
    let first = rq.take_task(&tasks[0]).unwrap();
    let second = rq.take_task(&tasks[1]).unwrap();
    let capacity = rq.array[1].queue[BUCKET].capacity();
    rq.commit_removed(&first);
    assert!(Arc::ptr_eq(first.task(), &tasks[0]));
    assert_eq!(rq.array[1].reserved[BUCKET], 1);
    assert_eq!(rq.array[1].queue[BUCKET].capacity(), capacity);
    assert_eq!(rq.nr_running, 0);
    assert!(!rq.array[1].map[BUCKET]);
    assert!(rq.pick_next().is_none());
    assert!(rq.take_task(&tasks[0]).is_none());
    rq.restore_task(second);
    assert_eq!(rq.array[1].reserved[BUCKET], 0);
    assert!(Arc::ptr_eq(&rq.pick_next().unwrap(), &tasks[1]));
    assert_eq!(rq.nr_running, 0);
}

#[ktest]
#[should_panic(expected = "removed RT reservation already consumed")]
fn rt_removed_commit_cannot_refund_another_tokens_slot() {
    let mut rq = RealTimeClassRq::new(CpuId::bsp());
    let tasks = [task(), task()];
    let _irq = disable_local();
    for task in &tasks {
        rq.enqueue(task.clone(), None);
    }
    let first = rq.take_task(&tasks[0]).unwrap();
    let _second = rq.take_task(&tasks[1]).unwrap();
    rq.commit_removed(&first);
    assert_eq!(rq.array[1].reserved[BUCKET], 1);
    // The second reservation is live: checking only the pooled count would
    // incorrectly let this repeated commit consume it.
    rq.commit_removed(&first);
}
