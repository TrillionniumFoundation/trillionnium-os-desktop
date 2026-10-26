// SPDX-License-Identifier: MPL-2.0

use ostd::{irq::disable_local, prelude::ktest};

use super::*;
use crate::{sched::SchedPolicy, thread::kernel_thread::ThreadOptions};

#[ktest]
fn queue_refund_uses_the_original_debited_weight_after_pending_is_consumed() {
    let task = ThreadOptions::new(|| {}).build();
    let mut tree = GroupTree::root();
    {
        let _irq = disable_local();
        tree.enqueue(task.clone(), None).unwrap();
    }
    assert_eq!(tree.nodes[0].task_weight, WEIGHT_0);
    let attr = task.as_thread().unwrap().sched_attr();
    attr.set_policy(SchedPolicy::Fair(Nice::try_from(5).unwrap()));
    let (old, new) = attr.fair.fetch_weight();
    assert_eq!(old, WEIGHT_0);
    assert_ne!(new, old);
    let _irq = disable_local();
    let (selected, token) = tree.select().unwrap();
    assert!(Arc::ptr_eq(&selected, &task));
    assert_eq!(tree.nodes[0].task_weight, 0);
    assert_eq!(tree.len(), 0);
    tree.cancel(token);
}

#[ktest]
fn cold_fair_storage_install_preserves_keys_weights_and_retires_empty_buffer() {
    let mut tree = GroupTree::root();
    let first = ThreadOptions::new(|| {}).build();
    {
        let _irq = disable_local();
        tree.enqueue(first.clone(), None).unwrap();
    }
    let capacity = tree.nodes[0].tasks.capacity();
    let tasks: Vec<_> = (1..capacity)
        .map(|_| ThreadOptions::new(|| {}).build())
        .collect();
    {
        let _irq = disable_local();
        for task in &tasks {
            tree.enqueue(task.clone(), None).unwrap();
        }
    }
    let mut prepared = tree.root_capacity_need().unwrap().allocate().unwrap();
    {
        let _irq = disable_local();
        tree.install_and_reserve_root(&mut prepared);
        assert_eq!(tree.len(), capacity);
        assert_eq!(tree.nodes[0].task_weight, capacity as u64 * WEIGHT_0);
        assert_eq!(tree.nodes[0].reserved_incoming, 1);
        assert!(prepared.storage.as_ref().unwrap().is_empty());
        assert_eq!(prepared.storage.as_ref().unwrap().capacity(), capacity);
        tree.release_root_reservation();
        for _ in 0..capacity {
            let (_, selected) = tree.select().unwrap();
            tree.cancel(selected);
        }
        assert_eq!(tree.nodes[0].task_weight, 0);
    }
    drop(prepared);
}
