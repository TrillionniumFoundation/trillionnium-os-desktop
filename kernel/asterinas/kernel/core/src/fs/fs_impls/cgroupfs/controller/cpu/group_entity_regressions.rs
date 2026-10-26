// SPDX-License-Identifier: MPL-2.0

//! W2A internal entities on real CPU incarnations, Tasks and production queues.
//! Controlled endpoints do not qualify live group scheduling or SMP migration.

use alloc::vec::Vec;

use aster_systree::{SysBranchNode, SysNode, SysObj};
use ostd::{prelude::ktest, task::scheduler::UpdateFlags};

use super::*;
use crate::{
    process::{posix_thread::AsPosixThread, test_util},
    sched::{CpuRunQueueFixture, SchedPolicy},
};

struct Fixture {
    root: &'static Arc<CgroupSystem>,
    parent: Arc<CgroupNode>,
    leaves: [Arc<CgroupNode>; 3],
    processes: Vec<Arc<Process>>,
    tasks: Vec<Arc<Task>>,
    original_root: CpuMax,
    enabled: bool,
    start: u64,
    name: &'static str,
}

fn cpu(controller: &super::super::Controller) -> Arc<super::super::SubController<CpuController>> {
    controller.cpu.read().get().clone()
}

impl Fixture {
    fn new(name: &'static str) -> Self {
        aster_time::init_for_ktest();
        aster_systree::init_for_ktest();
        let root = CgroupSystem::singleton();
        let enabled = !root
            .controller()
            .active_set()
            .contains_type(super::super::SubCtrlType::Cpu);
        if enabled {
            root.store_attr("cgroup.subtree_control", "+cpu").unwrap();
        }
        let parent = Arc::downcast::<CgroupNode>(root.create_child(name).unwrap()).unwrap();
        parent.store_attr("cgroup.subtree_control", "+cpu").unwrap();
        let p = Arc::downcast::<CgroupNode>(parent.create_child("p").unwrap()).unwrap();
        p.store_attr("cgroup.subtree_control", "+cpu").unwrap();
        let leaves = [
            Arc::downcast::<CgroupNode>(p.create_child("a").unwrap()).unwrap(),
            Arc::downcast::<CgroupNode>(p.create_child("b").unwrap()).unwrap(),
            Arc::downcast::<CgroupNode>(parent.create_child("q").unwrap()).unwrap(),
        ];
        let original_root = cpu(root.controller())
            .inner
            .as_ref()
            .unwrap()
            .control()
            .unwrap()
            .max
            .lock()
            .max;
        let period = 100_000_000;
        let start = (aster_time::try_read_monotonic_sample()
            .unwrap()
            .checked_nanos()
            .unwrap()
            / period
            + 3)
            * period;
        for controller in [
            root.controller(),
            parent.controller(),
            p.controller(),
            leaves[0].controller(),
            leaves[1].controller(),
            leaves[2].controller(),
        ] {
            let owner = cpu(controller);
            let mut state = owner.inner.as_ref().unwrap().control().unwrap().max.lock();
            state.max = CpuMax {
                quota_usec: u64::MAX,
                quota_sub_usec_ns: 0,
                period_usec: 100_000,
                window_start_ns: start,
                used_ns: 0,
                cumulative_ns: 0,
                last_observed_ns: start,
                accounting_fault: false,
                native_window_valid_from_ns: Some(0),
                carry_debt_ns: 0,
                nr_periods: 0,
                nr_throttled: 0,
                throttled_since_ns: None,
                throttled_ns: 0,
            };
        }
        let mut processes = Vec::new();
        let mut tasks = Vec::new();
        for index in 0..10 {
            let (process, task) = test_util::new_unstarted_process();
            let leaf = if index == 0 {
                0
            } else if index == 9 {
                2
            } else {
                1
            };
            CgroupMembership::write_lock()
                .move_process_to_node(process.clone(), &leaves[leaf])
                .unwrap();
            processes.push(process);
            tasks.push(task);
        }
        Self {
            root,
            parent,
            leaves,
            processes,
            tasks,
            original_root,
            enabled,
            start,
            name,
        }
    }

    fn runqueue(&self) -> CpuRunQueueFixture {
        let a = CpuSchedulingGroup::for_task(&self.tasks[0]).unwrap();
        let b = CpuSchedulingGroup::for_task(&self.tasks[1]).unwrap();
        let q = CpuSchedulingGroup::for_task(&self.tasks[9]).unwrap();
        let p = a.parent().unwrap();
        let parent = p.parent().unwrap();
        let groups = [(parent, 0), (p, 1), (a, 2), (b, 2), (q, 1)];
        let bindings: Vec<_> = self
            .tasks
            .iter()
            .enumerate()
            .map(|(index, task)| {
                (
                    task.clone(),
                    if index == 0 {
                        3
                    } else if index == 9 {
                        5
                    } else {
                        4
                    },
                )
            })
            .collect();
        CpuRunQueueFixture::with_groups(self.tasks[0].clone(), self.start, &groups, &bindings)
            .unwrap()
    }

    fn limit(&self, node: &CgroupNode, used: u64) {
        let owner = cpu(node.controller());
        let mut state = owner.inner.as_ref().unwrap().control().unwrap().max.lock();
        state.max.quota_usec = 1;
        state.max.used_ns = used;
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        for (process, task) in self.processes.iter().zip(&self.tasks) {
            CgroupMembership::write_lock().move_process_to_root(process);
            task.as_posix_thread().unwrap().set_cpu_cgroup(None);
        }
        let p = Arc::downcast::<CgroupNode>(self.leaves[0].parent().unwrap()).unwrap();
        p.remove_child("a").unwrap();
        p.remove_child("b").unwrap();
        self.parent.remove_child("p").unwrap();
        self.parent.remove_child("q").unwrap();
        self.root.remove_child(self.name).unwrap();
        cpu(self.root.controller())
            .inner
            .as_ref()
            .unwrap()
            .control()
            .unwrap()
            .max
            .lock()
            .max = self.original_root;
        if self.enabled {
            self.root
                .store_attr("cgroup.subtree_control", "-cpu")
                .unwrap();
        }
    }
}

#[ktest]
fn prepared_group_entities_compete_once_and_retain_nested_debt() {
    let fixture = Fixture::new("w2a-entities");
    let mut rq = fixture.runqueue();
    for task in &fixture.tasks[1..] {
        rq.enqueue(task.clone());
    }
    let capacities = rq.group_capacities();
    let mut current = fixture.tasks[0].clone();
    let mut counts = [0u64; 3];
    for round in 1..=2400 {
        let index = fixture
            .tasks
            .iter()
            .position(|task| Arc::ptr_eq(task, &current))
            .unwrap();
        counts[if index == 0 {
            0
        } else if index == 9 {
            2
        } else {
            1
        }] += 1;
        let now = fixture.start + round * 1_000_000;
        if rq.update(UpdateFlags::Tick, now) {
            current = rq.pick(&[now, now]).unwrap();
        }
    }
    assert!(
        counts[0].abs_diff(counts[1]) < 40,
        "one task must compete equally with eight: {counts:?}"
    );
    assert!(
        (counts[0] + counts[1]).abs_diff(counts[2]) < 40,
        "P subtree must compete once with Q: {counts:?}"
    );
    assert_eq!(capacities, rq.group_capacities());
    assert!(rq.group_state(2).0 > 0 && rq.group_state(5).0 > 0);
}

#[ktest]
fn prepared_group_selection_cancels_before_quota_admission_and_replenishes_same_leaf() {
    let fixture = Fixture::new("w2a-first-check");
    let mut rq = fixture.runqueue();
    for task in &fixture.tasks[1..9] {
        rq.enqueue(task.clone());
    }
    let capacities = rq.group_capacities();
    fixture.limit(&fixture.leaves[1], 1000);
    assert!(rq.pick(&[fixture.start + 100]).is_none());
    for task in &fixture.tasks[1..9] {
        assert!(rq.is_throttled(task));
    }
    assert_eq!(rq.group_state(4), (0, 0, false));
    assert!(rq.group_state(3).2);
    let now = fixture.start + 100_000_100;
    let next = rq.pick(&[now, now]).unwrap();
    assert!(
        fixture.tasks[1..9]
            .iter()
            .any(|task| Arc::ptr_eq(task, &next))
    );
    assert!(rq.group_state(4).2);
    assert_eq!(capacities, rq.group_capacities());
}

#[ktest]
fn prepared_group_selection_cancels_after_shared_quota_cut_without_charging_candidate() {
    let fixture = Fixture::new("w2a-second-check");
    let mut rq = fixture.runqueue();
    for task in &fixture.tasks[1..9] {
        rq.enqueue(task.clone());
    }
    fixture.tasks[9]
        .as_thread()
        .unwrap()
        .sched_attr()
        .set_policy(SchedPolicy::Idle);
    rq.enqueue(fixture.tasks[9].clone());
    let p = Arc::downcast::<CgroupNode>(fixture.leaves[0].parent().unwrap()).unwrap();
    fixture.limit(&p, 0);
    let next = rq
        .pick(&[
            fixture.start + 400,
            fixture.start + 1200,
            fixture.start + 1205,
        ])
        .unwrap();
    assert!(Arc::ptr_eq(&next, &fixture.tasks[9]));
    assert_eq!(rq.group_state(4), (0, 0, false));
    assert_eq!(rq.group_state(3).0, 1205);
    assert_eq!(rq.group_state(2).0, 1205);
    assert!(!rq.group_state(2).2);
}

#[ktest]
fn prepared_group_identity_keeps_original_incarnation_and_rejects_stale_admission() {
    let fixture = Fixture::new("w2a-incarnation");
    let original = CpuSchedulingGroup::for_task(&fixture.tasks[0]).unwrap();
    let original_parent = original.parent().unwrap();
    let original_base = original_parent.parent().unwrap();
    let p = Arc::downcast::<CgroupNode>(fixture.leaves[0].parent().unwrap()).unwrap();
    p.store_attr("cgroup.subtree_control", "-cpu").unwrap();
    p.store_attr("cgroup.subtree_control", "+cpu").unwrap();
    let replacement = CpuSchedulingGroup::for_task(&fixture.tasks[0]).unwrap();
    assert!(!original.same_incarnation(&replacement));
    assert!(
        original
            .parent()
            .unwrap()
            .same_incarnation(&original_parent)
    );
    assert_eq!(original.weight(), 100);
    let groups = [(original_base, 0), (original_parent, 1), (original, 2)];
    let bindings = [(fixture.tasks[0].clone(), 3)];
    assert!(
        CpuRunQueueFixture::with_groups(
            fixture.tasks[0].clone(),
            fixture.start,
            &groups,
            &bindings
        )
        .is_err()
    );
    assert!(fixture.leaves[0].store_attr("cpu.weight", "200").is_err());
}

#[ktest]
fn prepared_group_admission_rejects_wrong_parent_and_duplicate_task_slots() {
    let fixture = Fixture::new("w2a-admission");
    let a = CpuSchedulingGroup::for_task(&fixture.tasks[0]).unwrap();
    let p = a.parent().unwrap();
    let base = p.parent().unwrap();
    let wrong = [(a.clone(), 0)];
    assert!(
        CpuRunQueueFixture::with_groups(fixture.tasks[0].clone(), fixture.start, &wrong, &[])
            .is_err()
    );
    let groups = [(base, 0), (p, 1), (a, 2)];
    let duplicate = [(fixture.tasks[0].clone(), 3), (fixture.tasks[0].clone(), 3)];
    assert!(
        CpuRunQueueFixture::with_groups(
            fixture.tasks[0].clone(),
            fixture.start,
            &groups,
            &duplicate
        )
        .is_err()
    );
}

#[ktest]
fn prepared_group_queue_refuses_an_unadmitted_task_without_losing_it_or_growing() {
    let fixture = Fixture::new("w2a-unknown-task");
    let mut rq = fixture.runqueue();
    let (process, task) = test_util::new_unstarted_process();
    let capacities = rq.group_capacities();
    let returned = rq
        .try_group_enqueue(task.clone())
        .err()
        .expect("missing slot must refuse");
    assert!(Arc::ptr_eq(&returned, &task));
    assert_eq!(rq.group_state(0).1, 0);
    assert_eq!(capacities, rq.group_capacities());
    drop(returned);
    drop(task);
    drop(process);
}

#[ktest]
fn prepared_route_keeps_deep_cpu_topology_until_the_last_queue_is_retired() {
    let fixture = Fixture::new("w4a-route-toggle");
    let rq = fixture.runqueue();
    let p = Arc::downcast::<CgroupNode>(fixture.leaves[0].parent().unwrap()).unwrap();
    let original = cpu(fixture.leaves[0].controller());
    let refused = p.store_attr("cgroup.subtree_control", "-cpu").is_err();
    let unchanged = Arc::ptr_eq(&original, &cpu(fixture.leaves[0].controller()));
    // Preserve cleanup on the old implementation too: its actual acceptance
    // is recorded by the deferred assertion, never hidden by a cleanup panic.
    if !refused {
        p.store_attr("cgroup.subtree_control", "+cpu").unwrap();
    }
    drop(rq);
    p.store_attr("cgroup.subtree_control", "-cpu").unwrap();
    p.store_attr("cgroup.subtree_control", "+cpu").unwrap();
    drop(fixture);
    assert!(
        refused,
        "prepared route allowed its CPU incarnation to be replaced"
    );
    assert!(
        unchanged,
        "refusal must leave the original CPU incarnation installed"
    );
}

#[ktest]
fn prepared_route_pins_inactive_raw_cpu_levels_before_normalization() {
    let fixture = Fixture::new("w4a-route-inactive");
    let p = Arc::downcast::<CgroupNode>(fixture.leaves[0].parent().unwrap()).unwrap();
    p.store_attr("cgroup.subtree_control", "-cpu").unwrap();
    let effective = CpuSchedulingGroup::for_task(&fixture.tasks[0]).unwrap();
    let parent = effective.parent().unwrap();
    let groups = [(parent, 0), (effective, 1)];
    let bindings = [(fixture.tasks[0].clone(), 2)];
    let rq = CpuRunQueueFixture::with_groups(
        fixture.tasks[0].clone(),
        fixture.start,
        &groups,
        &bindings,
    )
    .unwrap();
    let original = cpu(fixture.leaves[0].controller());
    let refused = p.store_attr("cgroup.subtree_control", "+cpu").is_err();
    let unchanged = Arc::ptr_eq(&original, &cpu(fixture.leaves[0].controller()));
    if !refused {
        p.store_attr("cgroup.subtree_control", "-cpu").unwrap();
    }
    drop(rq);
    p.store_attr("cgroup.subtree_control", "+cpu").unwrap();
    drop(fixture);
    assert!(
        refused,
        "normalization discarded an inactive raw incarnation lease"
    );
    assert!(
        unchanged,
        "rejected activation replaced an inactive raw incarnation"
    );
}

#[ktest]
fn prepared_route_keeps_an_empty_node_until_the_last_queue_is_retired() {
    let mut fixture = Fixture::new("w4a-route-rmdir");
    let rq = fixture.runqueue();
    for (process, task) in fixture.processes.iter().zip(&fixture.tasks) {
        CgroupMembership::write_lock().move_process_to_root(process);
        task.as_posix_thread().unwrap().set_cpu_cgroup(None);
    }
    // b has no CurrentRuntime; only its prepared, currently empty task slots
    // can retain it once all real memberships/final-charge backups are gone.
    let p = Arc::downcast::<CgroupNode>(fixture.leaves[1].parent().unwrap()).unwrap();
    let refused = p.remove_child("b").is_err();
    if !refused {
        fixture.leaves[1] = Arc::downcast::<CgroupNode>(p.create_child("b").unwrap()).unwrap();
    }
    drop(rq);
    p.remove_child("b").unwrap();
    fixture.leaves[1] = Arc::downcast::<CgroupNode>(p.create_child("b").unwrap()).unwrap();
    drop(fixture);
    assert!(
        refused,
        "prepared task slots allowed their original node to be removed"
    );
}
