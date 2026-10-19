// SPDX-License-Identifier: MPL-2.0

//! Original CPU owner references across publication, exit and rescheduling.
//!
//! Real cgroups and Process/Task objects exercise the production runtime at
//! controlled timestamps. These are owner/ordering regressions, not evidence
//! of live SMP migration or BOOTTIME qualification.

use alloc::sync::Arc;

use aster_systree::{Error, SysBranchNode, SysNode};
use ostd::{prelude::ktest, task::Task};

use super::{
    super::{Controller, SubController, SubCtrlType},
    CpuChargeOwner, CpuController, CpuMax,
    max_config::CpuMaxConfig,
};
use crate::{
    fs::cgroupfs::{CgroupMembership, CgroupNode, CgroupSysNode, CgroupSystem},
    prelude::Errno,
    process::{Process, posix_thread::AsPosixThread, test_util},
    sched::CpuRuntimeFixture,
};

struct Fixture {
    root: &'static Arc<CgroupSystem>,
    parent: Arc<CgroupNode>,
    leaves: [Arc<CgroupNode>; 2],
    process: Option<Arc<Process>>,
    task: Arc<Task>,
    original_root_budget: CpuMax,
    enabled_root_cpu: bool,
    name: &'static str,
    start: u64,
}

impl Fixture {
    fn new(name: &'static str) -> Self {
        aster_time::init_for_ktest();
        aster_systree::init_for_ktest();
        let root = CgroupSystem::singleton();
        let enabled_root_cpu = !root
            .controller()
            .active_set()
            .contains_type(SubCtrlType::Cpu);
        if enabled_root_cpu {
            root.store_attr("cgroup.subtree_control", "+cpu").unwrap();
        }
        let parent = Arc::downcast::<CgroupNode>(root.create_child(name).unwrap()).unwrap();
        parent.store_attr("cgroup.subtree_control", "+cpu").unwrap();
        let leaves = ["old", "new"]
            .map(|name| Arc::downcast::<CgroupNode>(parent.create_child(name).unwrap()).unwrap());
        let original_root_budget = budget(&owner(root.controller()));
        let period = CpuMax::us_to_ns(100_000).max(1);
        let start = (aster_time::try_read_monotonic_sample()
            .unwrap()
            .checked_nanos()
            .unwrap()
            / period
            + 2)
            * period;
        for controller in [
            root.controller(),
            parent.controller(),
            leaves[0].controller(),
            leaves[1].controller(),
        ] {
            reset(&owner(controller), start);
        }
        let (process, task) = test_util::new_unstarted_process();
        CgroupMembership::write_lock()
            .move_process_to_node(process.clone(), &leaves[0])
            .unwrap();
        Self {
            root,
            parent,
            leaves,
            process: Some(process),
            task,
            original_root_budget,
            enabled_root_cpu,
            name,
            start,
        }
    }

    fn runtime(&self, start: u64) -> CpuRuntimeFixture {
        CpuRuntimeFixture::new(self.task.clone(), start)
    }

    fn replace_leaf(&self) {
        self.parent
            .store_attr("cgroup.subtree_control", "-cpu")
            .unwrap();
        self.parent
            .store_attr("cgroup.subtree_control", "+cpu")
            .unwrap();
        for leaf in &self.leaves {
            reset(&owner(leaf.controller()), self.start);
        }
    }

    fn replace_parent_and_leaves(&self) {
        self.parent
            .store_attr("cgroup.subtree_control", "-cpu")
            .unwrap();
        self.root
            .store_attr("cgroup.subtree_control", "-cpu")
            .unwrap();
        self.root
            .store_attr("cgroup.subtree_control", "+cpu")
            .unwrap();
        self.parent
            .store_attr("cgroup.subtree_control", "+cpu")
            .unwrap();
        reset(&owner(self.parent.controller()), self.start);
        for leaf in &self.leaves {
            reset(&owner(leaf.controller()), self.start);
        }
    }

    fn detach_zombie(&self) {
        let process = self.process.as_ref().unwrap();
        test_util::mark_zombie(process);
        CgroupMembership::write_lock().move_process_to_root(process);
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        if let Some(process) = &self.process {
            CgroupMembership::write_lock().move_process_to_root(process);
        }
        // All runtime fixtures are dropped before their hierarchy. Release
        // test-only snapshots on the deliberately unstarted/exited task.
        self.task.as_posix_thread().unwrap().set_cpu_cgroup(None);
        self.parent.remove_child("old").unwrap();
        self.parent.remove_child("new").unwrap();
        self.root.remove_child(self.name).unwrap();
        owner(self.root.controller())
            .inner
            .as_ref()
            .unwrap()
            .control()
            .unwrap()
            .max
            .lock()
            .max = self.original_root_budget;
        if self.enabled_root_cpu {
            self.root
                .store_attr("cgroup.subtree_control", "-cpu")
                .unwrap();
        }
    }
}

fn owner(controller: &Controller) -> Arc<SubController<CpuController>> {
    controller.cpu.read().get().clone()
}

fn budget(owner: &SubController<CpuController>) -> CpuMax {
    owner
        .inner
        .as_ref()
        .unwrap()
        .control()
        .unwrap()
        .max
        .lock()
        .max
}

fn reset(owner: &SubController<CpuController>, start: u64) {
    owner
        .inner
        .as_ref()
        .unwrap()
        .control()
        .unwrap()
        .max
        .lock()
        .max = CpuMax {
        quota_usec: 1_000,
        period_usec: 100_000,
        window_start_ns: start,
        used_ns: 0,
        cumulative_ns: 0,
        last_observed_ns: 0,
        accounting_fault: false,
        native_window_valid_from_ns: Some(0),
        carry_debt_ns: 0,
        nr_periods: 0,
        nr_throttled: 0,
        throttled_since_ns: None,
        throttled_ns: 0,
    };
}

fn assert_closed(owner: &SubController<CpuController>, now: u64) {
    let mut state = owner.inner.as_ref().unwrap().control().unwrap().max.lock();
    let before = state.max;
    assert!(matches!(
        state.reconfigure(CpuMaxConfig::parse("1000 100000").unwrap(), now),
        Err(Error::IsDead)
    ));
    assert_eq!(state.max, before);
}

#[ktest]
fn controller_publication_charges_the_entire_prefix_to_the_old_incarnation() {
    let fixture = Fixture::new("g1b-owner-publish");
    let old = owner(fixture.leaves[0].controller());
    let mut runtime = fixture.runtime(fixture.start);
    runtime.publish(fixture.start + 11, fixture.start + 19, || {
        assert_eq!(budget(&old).used_ns, 11);
        fixture.replace_leaf();
        assert_closed(&old, fixture.start + 11);
        assert_eq!(budget(&old).used_ns, 11);
    });
    let new = owner(fixture.leaves[0].controller());
    assert!(!Arc::ptr_eq(&old, &new));
    assert_eq!(budget(&old).used_ns, 19);
    assert_eq!(budget(&new).used_ns, 0);
    assert_eq!(runtime.update(fixture.start + 47), (47, 47));
    assert_eq!(budget(&old).used_ns, 19);
    assert_eq!(budget(&new).used_ns, 28);
    assert_eq!(budget(&owner(fixture.parent.controller())).used_ns, 47);
    assert_eq!(budget(&owner(fixture.root.controller())).used_ns, 47);
}

#[ktest]
fn retained_leaf_debits_its_original_ancestor_chain_after_parent_replacement() {
    let fixture = Fixture::new("g1b-owner-ancestors");
    let old_leaf = owner(fixture.leaves[0].controller());
    let old_parent = owner(fixture.parent.controller());
    let mut runtime = fixture.runtime(fixture.start);
    runtime.publish(fixture.start + 11, fixture.start + 19, || {
        fixture.replace_parent_and_leaves();
        assert_closed(&old_leaf, fixture.start + 11);
        assert_closed(&old_parent, fixture.start + 11);
    });
    let new_leaf = owner(fixture.leaves[0].controller());
    let new_parent = owner(fixture.parent.controller());
    assert!(!Arc::ptr_eq(&old_parent, &new_parent));
    assert_eq!(budget(&old_leaf).used_ns, 19);
    assert_eq!(budget(&old_parent).used_ns, 19);
    assert_eq!(runtime.update(fixture.start + 47), (47, 47));
    assert_eq!(budget(&old_leaf).used_ns, 19);
    assert_eq!(budget(&old_parent).used_ns, 19);
    assert_eq!(budget(&new_leaf).used_ns, 28);
    assert_eq!(budget(&new_parent).used_ns, 28);
    assert_eq!(budget(&owner(fixture.root.controller())).used_ns, 47);
}

#[ktest]
fn live_migration_partitions_leaf_time_and_charges_common_ancestors_once() {
    let fixture = Fixture::new("g1b-owner-migrate");
    let old = owner(fixture.leaves[0].controller());
    let new = owner(fixture.leaves[1].controller());
    let mut runtime = fixture.runtime(fixture.start);
    runtime.publish(fixture.start + 11, fixture.start + 19, || {
        CgroupMembership::write_lock()
            .move_process_to_node(
                fixture.process.as_ref().unwrap().clone(),
                &fixture.leaves[1],
            )
            .unwrap();
    });
    assert_eq!(runtime.update(fixture.start + 29), (29, 29));
    assert_eq!(budget(&old).used_ns, 19);
    assert_eq!(budget(&new).used_ns, 10);
    runtime.publish(fixture.start + 29, fixture.start + 31, || {
        CgroupMembership::write_lock()
            .move_process_to_node(
                fixture.process.as_ref().unwrap().clone(),
                &fixture.leaves[1],
            )
            .unwrap();
    });
    runtime.publish(fixture.start + 37, fixture.start + 41, || {
        CgroupMembership::write_lock().move_process_to_root(fixture.process.as_ref().unwrap());
    });
    assert_eq!(runtime.update(fixture.start + 53), (24, 53));
    assert_eq!(budget(&old).used_ns, 19);
    assert_eq!(budget(&new).used_ns, 22);
    assert_eq!(budget(&owner(fixture.parent.controller())).used_ns, 41);
    assert_eq!(budget(&owner(fixture.root.controller())).used_ns, 53);
}

#[ktest]
fn exited_task_resumes_its_retained_incarnation_after_replacement_and_reap() {
    let mut fixture = Fixture::new("g1b-owner-resume");
    let old_leaf = owner(fixture.leaves[0].controller());
    let old_parent = owner(fixture.parent.controller());
    let mut runtime = fixture.runtime(fixture.start);
    assert_eq!(runtime.update(fixture.start + 13), (13, 13));
    fixture.detach_zombie();
    fixture.replace_parent_and_leaves();
    assert_eq!(runtime.update(fixture.start + 23), (10, 23));
    drop(runtime);
    drop(fixture.process.take());
    assert!(
        fixture
            .task
            .as_posix_thread()
            .unwrap()
            .weak_process()
            .upgrade()
            .is_none()
    );

    // Six TSC cycles off-CPU are excluded. A fresh runtime must retain the exact
    // old leaf/ancestors rather than dereference the node's new RCU slot.
    let mut resumed = fixture.runtime(fixture.start + 29);
    assert_eq!(resumed.update(fixture.start + 41), (12, 12));
    assert_eq!(budget(&old_leaf).used_ns, 35);
    assert_eq!(budget(&old_parent).used_ns, 35);
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 0);
    assert_eq!(budget(&owner(fixture.parent.controller())).used_ns, 0);
    assert_eq!(budget(&owner(fixture.root.controller())).used_ns, 35);
    assert_closed(&old_leaf, fixture.start + 41);
    assert_closed(&old_parent, fixture.start + 41);
}

#[ktest]
fn zero_length_publication_changes_only_the_next_segment_owner() {
    let fixture = Fixture::new("g1b-owner-zero");
    let old = owner(fixture.leaves[0].controller());
    let mut runtime = fixture.runtime(fixture.start);
    runtime.publish(fixture.start, fixture.start, || fixture.replace_leaf());
    let new = owner(fixture.leaves[0].controller());
    assert_eq!(budget(&old).used_ns, 0);
    assert_eq!(budget(&new).used_ns, 0);
    assert_eq!(runtime.update(fixture.start + 17), (17, 17));
    assert_eq!(runtime.update(fixture.start + 17), (0, 17));
    assert_eq!(budget(&old).used_ns, 0);
    assert_eq!(budget(&new).used_ns, 17);
    assert_eq!(budget(&owner(fixture.root.controller())).used_ns, 17);
}

#[ktest]
fn original_owner_reference_keeps_the_node_live_until_its_last_clone_drops() {
    aster_time::init_for_ktest();
    aster_systree::init_for_ktest();
    let root = CgroupSystem::singleton();
    let name = "g1b-owner-node-lease";
    let group = Arc::downcast::<CgroupNode>(root.create_child(name).unwrap()).unwrap();
    let owner = CpuChargeOwner::from_cgroup(Some(group.clone()));
    let copy = owner.clone();
    assert_eq!(
        group
            .mark_as_dead(&mut CgroupMembership::write_lock())
            .unwrap_err()
            .error(),
        Errno::EBUSY
    );
    drop(owner);
    assert_eq!(
        group
            .mark_as_dead(&mut CgroupMembership::write_lock())
            .unwrap_err()
            .error(),
        Errno::EBUSY
    );
    drop(copy);
    group
        .mark_as_dead(&mut CgroupMembership::write_lock())
        .unwrap();
    root.remove_child(name).unwrap();
}
