// SPDX-License-Identifier: MPL-2.0

//! Regressions for the final-debit gap left after desktop PR #178.
//!
//! These tests capture the production CPU owner with real, unstarted
//! Process/Task objects and real membership transitions. They check quota state,
//! not the separate jiffies-based cpu.stat usage projection. They do not execute
//! the userspace exit syscall or claim to reproduce scheduler timing in SMP.

use alloc::sync::Arc;

use aster_systree::{SysBranchNode, SysNode};
use ostd::{arch::read_tsc, prelude::ktest};

use super::{CpuMax, charge_task_cpu};
use crate::{
    fs::cgroupfs::{
        CgroupMembership, CgroupNode, CgroupSysNode, CgroupSystem,
        controller::{Controller, SubCtrlType},
    },
    process::{posix_thread::AsPosixThread, test_util},
};

/// A private subtree under the actual root used by charge_task_cpu's root path.
/// No task in these tests is scheduled, so there are no competing POSIX debits.
struct Hierarchy {
    root: &'static Arc<CgroupSystem>,
    parent: Arc<CgroupNode>,
    leaves: [Arc<CgroupNode>; 2],
    original_root_budget: CpuMax,
    enabled_root_cpu: bool,
    name: &'static str,
    start: u64,
}

impl Hierarchy {
    fn new(name: &'static str) -> Self {
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

        let original_root_budget = budget(root.controller());
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let start = (read_tsc() / period + 2) * period;
        for controller in [
            root.controller(),
            parent.controller(),
            leaves[0].controller(),
            leaves[1].controller(),
        ] {
            replace_budget(
                controller,
                CpuMax {
                    quota_usec: 1_000,
                    period_usec: 100_000,
                    window_start: start,
                    used_clocks: 0,
                    carry_debt_clocks: 0,
                    nr_periods: 0,
                    nr_throttled: 0,
                    throttled_since: None,
                    throttled_clocks: 0,
                },
            );
        }

        Self {
            root,
            parent,
            leaves,
            original_root_budget,
            enabled_root_cpu,
            name,
            start,
        }
    }

    fn assert_used(&self, old: u64, new: u64, parent: u64, root: u64) {
        assert_eq!(budget(self.leaves[0].controller()).used_clocks, old);
        assert_eq!(budget(self.leaves[1].controller()).used_clocks, new);
        assert_eq!(budget(self.parent.controller()).used_clocks, parent);
        assert_eq!(budget(self.root.controller()).used_clocks, root);
    }
}

impl Drop for Hierarchy {
    fn drop(&mut self) {
        self.root.remove_child(self.name).unwrap();
        replace_budget(self.root.controller(), self.original_root_budget);
        if self.enabled_root_cpu {
            self.root
                .store_attr("cgroup.subtree_control", "-cpu")
                .unwrap();
        }
    }
}

fn budget(controller: &Controller) -> CpuMax {
    let cpu = controller.cpu.read();
    let value = cpu
        .get()
        .inner
        .as_ref()
        .unwrap()
        .control
        .as_ref()
        .unwrap()
        .max
        .lock()
        .max;
    value
}

fn replace_budget(controller: &Controller, budget: CpuMax) {
    let cpu = controller.cpu.read();
    cpu.get()
        .inner
        .as_ref()
        .unwrap()
        .control
        .as_ref()
        .unwrap()
        .max
        .lock()
        .max = budget;
}

#[ktest]
fn unreaped_zombie_final_interval_debits_old_leaf_and_ancestors_once() {
    let hierarchy = Hierarchy::new("a06-unreaped-final");
    let (process, task) = test_util::new_unstarted_process();
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &hierarchy.leaves[0])
        .unwrap();
    let start = hierarchy.start;
    charge_task_cpu(&task, start, start + 10);

    test_util::mark_zombie(&process);
    CgroupMembership::write_lock().move_process_to_root(&process);
    assert!(process.cgroup().is_none());
    assert!(
        task.as_posix_thread()
            .unwrap()
            .weak_process()
            .upgrade()
            .is_some()
    );

    charge_task_cpu(&task, start + 10, start + 37);
    hierarchy.assert_used(37, 0, 37, 37);
}

#[ktest]
fn reaped_process_final_interval_uses_the_same_retained_hierarchy() {
    let hierarchy = Hierarchy::new("a06-reaped-final");
    let (process, task) = test_util::new_unstarted_process();
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &hierarchy.leaves[0])
        .unwrap();
    test_util::mark_zombie(&process);
    CgroupMembership::write_lock().move_process_to_root(&process);
    drop(process);
    assert!(
        task.as_posix_thread()
            .unwrap()
            .weak_process()
            .upgrade()
            .is_none()
    );

    charge_task_cpu(&task, hierarchy.start, hierarchy.start + 29);
    hierarchy.assert_used(29, 0, 29, 29);
}

#[ktest]
fn live_migrations_change_the_owner_without_replaying_prior_debits() {
    let hierarchy = Hierarchy::new("a06-live-migrate");
    let (process, task) = test_util::new_unstarted_process();
    let start = hierarchy.start;
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &hierarchy.leaves[0])
        .unwrap();
    charge_task_cpu(&task, start, start + 11);
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &hierarchy.leaves[1])
        .unwrap();
    let snapshot = task.as_posix_thread().unwrap().cpu_cgroup().unwrap();
    assert!(Arc::ptr_eq(&snapshot, &hierarchy.leaves[1]));
    charge_task_cpu(&task, start + 11, start + 30);
    CgroupMembership::write_lock().move_process_to_root(&process);
    assert!(task.as_posix_thread().unwrap().cpu_cgroup().is_none());
    charge_task_cpu(&task, start + 30, start + 53);

    hierarchy.assert_used(11, 19, 30, 53);
    test_util::mark_zombie(&process);
    charge_task_cpu(&task, start + 53, start + 60);
    hierarchy.assert_used(11, 19, 30, 60);
}

#[ktest]
fn live_process_binding_wins_over_a_stale_final_charge_snapshot() {
    let hierarchy = Hierarchy::new("a06-live-binding");
    let (process, task) = test_util::new_unstarted_process();
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &hierarchy.leaves[1])
        .unwrap();
    // Exercise the publication interval during a live membership update:
    // process.cgroup is published before set_cpu_cgroup_for_tasks completes.
    task.as_posix_thread()
        .unwrap()
        .set_cpu_cgroup(Some(hierarchy.leaves[0].clone()));
    charge_task_cpu(&task, hierarchy.start, hierarchy.start + 17);
    hierarchy.assert_used(0, 17, 17, 17);
    CgroupMembership::write_lock().move_process_to_root(&process);
}

#[ktest]
fn zombie_before_detachment_preserves_its_present_process_binding() {
    let hierarchy = Hierarchy::new("a06-zombie-binding");
    let (process, task) = test_util::new_unstarted_process();
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &hierarchy.leaves[1])
        .unwrap();
    // A migration admitted before exit can publish the new process binding
    // before updating the thread snapshot, while exit has published zombie
    // but has not yet acquired the membership lock to detach the process.
    task.as_posix_thread()
        .unwrap()
        .set_cpu_cgroup(Some(hierarchy.leaves[0].clone()));
    test_util::mark_zombie(&process);
    assert!(process.cgroup().get().is_some());

    charge_task_cpu(&task, hierarchy.start, hierarchy.start + 31);
    hierarchy.assert_used(0, 31, 31, 31);
    CgroupMembership::write_lock().move_process_to_root(&process);
}

#[ktest]
fn zombie_final_interval_crossing_a_window_preserves_positive_quota_debt() {
    let hierarchy = Hierarchy::new("a06-final-window");
    let (process, task) = test_util::new_unstarted_process();
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &hierarchy.leaves[0])
        .unwrap();
    let quota = CpuMax::us_to_clocks(1_000);
    let boundary = hierarchy.start + CpuMax::us_to_clocks(100_000).max(1);
    charge_task_cpu(&task, boundary - quota * 2, boundary - quota);
    test_util::mark_zombie(&process);
    CgroupMembership::write_lock().move_process_to_root(&process);
    charge_task_cpu(&task, boundary - quota, boundary + quota / 2);

    for controller in [
        hierarchy.leaves[0].controller(),
        hierarchy.parent.controller(),
        hierarchy.root.controller(),
    ] {
        let budget = budget(controller);
        assert_eq!(budget.window_start, boundary);
        assert_eq!(budget.used_clocks, quota / 2);
        assert_eq!(budget.carry_debt_clocks, quota);
    }
    assert_eq!(budget(hierarchy.leaves[1].controller()).used_clocks, 0);
}
