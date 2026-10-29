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

#[ktest]
fn removed_fair_entity_preserves_refund_and_exact_rollback_after_nice_update() {
    let task = ThreadOptions::new(|| {}).build();
    let mut tree = GroupTree::root();
    task.as_thread()
        .unwrap()
        .sched_attr()
        .fair
        .vruntime
        .store(500, Ordering::Relaxed);
    {
        let _irq = disable_local();
        tree.enqueue(task.clone(), None).unwrap();
    }
    tree.nodes[0].min_vruntime = 100;
    let attr = task.as_thread().unwrap().sched_attr();
    attr.set_policy(SchedPolicy::Fair(Nice::try_from(5).unwrap()));
    attr.fair.fetch_weight();
    let token = {
        let _irq = disable_local();
        let token = tree.take_root_task(&task).unwrap().unwrap();
        assert!(Arc::ptr_eq(token.task(), &task));
        assert_eq!(token.debt(), 400);
        assert_eq!(tree.nodes[0].task_weight, 0);
        assert_eq!(tree.nodes[0].reserved_incoming, 1);
        assert_eq!(tree.nodes[0].min_vruntime, 100);
        token
    };
    let capacity = tree.nodes[0].tasks.capacity();
    let others: Vec<_> = (0..capacity)
        .map(|_| ThreadOptions::new(|| {}).build())
        .collect();
    let _irq = disable_local();
    for other in &others {
        tree.enqueue(other.clone(), None).unwrap();
    }
    let before = tree.nodes[0].tasks.capacity();
    tree.restore_root_task(token);
    assert_eq!(tree.nodes[0].tasks.capacity(), before);
    assert_eq!(tree.nodes[0].reserved_incoming, 0);
    assert_eq!(
        tree.nodes[0].task_weight,
        (others.len() as u64 + 1) * WEIGHT_0
    );
    assert_eq!(attr.fair.vruntime.load(Ordering::Relaxed), 500);
    while let Some((_, selected)) = tree.select() {
        tree.cancel(selected);
    }
    assert_eq!(tree.nodes[0].task_weight, 0);
}

#[ktest]
fn fair_transfer_translates_positive_debt_instead_of_copying_another_cpu_floor() {
    let task = ThreadOptions::new(|| {}).build();
    let mut source = GroupTree::root();
    let mut destination = GroupTree::root();
    task.as_thread()
        .unwrap()
        .sched_attr()
        .fair
        .vruntime
        .store(500, Ordering::Relaxed);
    let _irq = disable_local();
    source.enqueue(task.clone(), None).unwrap();
    source.nodes[0].min_vruntime = 100;
    destination.nodes[0].min_vruntime = 10000;
    let mut removed = source.take_root_task(&task).unwrap().unwrap();
    destination.rebase_root_debt(&task, removed.debt()).unwrap();
    source.commit_root_removal(&mut removed);
    destination.enqueue(task.clone(), None).unwrap();
    assert_eq!(
        task.as_thread()
            .unwrap()
            .sched_attr()
            .fair
            .vruntime
            .load(Ordering::Relaxed),
        10400
    );
    assert_eq!(source.nodes[0].reserved_incoming, 0);
    assert_eq!(source.len(), 0);
    assert_eq!(destination.len(), 1);
    let (selected, token) = destination.select().unwrap();
    assert!(Arc::ptr_eq(&selected, &task));
    destination.cancel(token);
}
