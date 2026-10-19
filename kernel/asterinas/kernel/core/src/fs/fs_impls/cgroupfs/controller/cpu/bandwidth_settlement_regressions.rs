// SPDX-License-Identifier: MPL-2.0

//! G1-b configuration ordering on the original bandwidth owner.
//!
//! These kernel tests use real, unstarted Process/Task objects and the same
//! runtime helper as the production local runqueue. Deterministic timestamps
//! expose sub-tick accounting; they are not live scheduling or SMP evidence.

use alloc::sync::Arc;

use aster_systree::{SysBranchNode, SysNode};
use ostd::{arch::read_tsc, prelude::ktest};

use super::{CpuMax, charge_task_cpu, max_config::CpuMaxConfig};
use crate::{
    fs::cgroupfs::{
        CgroupMembership, CgroupNode, CgroupSysNode, CgroupSystem,
        controller::{Controller, SubCtrlType},
    },
    process::{Process, posix_thread::AsPosixThread, test_util},
    sched::CpuRuntimeFixture,
};

struct OwnerFixture {
    root: &'static Arc<CgroupSystem>,
    group: Arc<CgroupNode>,
    process: Arc<Process>,
    original_root_budget: CpuMax,
    enabled_root_cpu: bool,
    name: &'static str,
    start: u64,
}

impl OwnerFixture {
    fn new(name: &'static str) -> (Self, Arc<ostd::task::Task>) {
        aster_systree::init_for_ktest();
        let root = CgroupSystem::singleton();
        let enabled_root_cpu = !root
            .controller()
            .active_set()
            .contains_type(SubCtrlType::Cpu);
        if enabled_root_cpu {
            root.store_attr("cgroup.subtree_control", "+cpu").unwrap();
        }
        let group = Arc::downcast::<CgroupNode>(root.create_child(name).unwrap()).unwrap();
        let original_root_budget = budget(root.controller());
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let start = (read_tsc() / period + 2) * period;
        replace_budget(
            group.controller(),
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
        let (process, task) = test_util::new_unstarted_process();
        CgroupMembership::write_lock()
            .move_process_to_node(process.clone(), &group)
            .unwrap();
        (
            Self {
                root,
                group,
                process,
                original_root_budget,
                enabled_root_cpu,
                name,
                start,
            },
            task,
        )
    }

    fn configure(&self, content: &str, now: u64) {
        let config = CpuMaxConfig::parse(content).unwrap();
        let cpu = self.group.controller().cpu.read();
        cpu.get()
            .inner
            .as_ref()
            .unwrap()
            .control()
            .unwrap()
            .max
            .lock()
            .reconfigure(config, now)
            .unwrap();
    }

    fn budget(&self) -> CpuMax {
        budget(self.group.controller())
    }
}

impl Drop for OwnerFixture {
    fn drop(&mut self) {
        CgroupMembership::write_lock().move_process_to_root(&self.process);
        // The process's task collection can still retain an exited task after
        // the runtime fixture drops. Release its test-only final charge lease
        // after all accounting assertions and before deleting this test node.
        for task in self.process.tasks().lock().as_slice() {
            task.as_posix_thread().unwrap().set_cpu_cgroup(None);
        }
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
    cpu.get()
        .inner
        .as_ref()
        .unwrap()
        .control()
        .unwrap()
        .max
        .lock()
        .max
}

fn replace_budget(controller: &Controller, budget: CpuMax) {
    let cpu = controller.cpu.read();
    cpu.get()
        .inner
        .as_ref()
        .unwrap()
        .control()
        .unwrap()
        .max
        .lock()
        .max = budget;
}

#[ktest]
fn same_value_write_settles_old_window_debt_before_advancing() {
    let (owner, task) = OwnerFixture::new("g1b-config-window");
    let quota = CpuMax::us_to_clocks(1_000);
    let boundary = owner.start + CpuMax::us_to_clocks(100_000).max(1);
    let already_used = quota * 3 / 4;
    let old_pending = quota / 2;
    let new_pending = quota / 4;
    charge_task_cpu(&task, owner.start, owner.start + already_used);

    let mut runtime = CpuRuntimeFixture::new(task, boundary - old_pending);
    let apply_at = boundary + new_pending;
    runtime.configure(apply_at, |now| owner.configure("1000 100000", now));
    let after = owner.budget();
    assert_eq!(after.window_start, boundary);
    assert_eq!(after.used_clocks, new_pending);
    assert_eq!(after.carry_debt_clocks, already_used + old_pending - quota);

    let next = apply_at + new_pending;
    let full_runtime = next - (boundary - old_pending);
    assert_eq!(runtime.update(next), (full_runtime, full_runtime));
    assert_eq!(owner.budget().used_clocks, new_pending * 2);
    assert_eq!(runtime.update(next), (0, full_runtime));
    assert_eq!(owner.budget().used_clocks, new_pending * 2);
}

#[ktest]
fn repeated_configuration_partitions_bandwidth_without_consuming_cfs_runtime() {
    let (owner, task) = OwnerFixture::new("g1b-config-cursor");
    let start = owner.start + 100;
    let mut runtime = CpuRuntimeFixture::new(task, start);
    for elapsed in [17, 29, 29, 41] {
        runtime.configure(start + elapsed, |now| {
            assert_eq!(owner.budget().used_clocks, elapsed);
            owner.configure("1000 100000", now);
        });
        assert_eq!(owner.budget().used_clocks, elapsed);
    }

    // CFS still receives the whole interval since its own checkpoint, while
    // the bandwidth owner receives only the suffix after the last config.
    assert_eq!(runtime.update(start + 59), (59, 59));
    assert_eq!(owner.budget().used_clocks, 59);
    assert_eq!(runtime.update(start + 72), (13, 72));
    assert_eq!(owner.budget().used_clocks, 72);
}

#[ktest]
fn lowered_quota_includes_the_running_prefix_at_apply() {
    let (owner, task) = OwnerFixture::new("g1b-config-lower");
    owner.configure("10000 100000", owner.start);
    let quota = CpuMax::us_to_clocks(1_000);
    charge_task_cpu(&task, owner.start, owner.start + quota / 2);
    let start = owner.start + quota;
    let mut runtime = CpuRuntimeFixture::new(task, start);
    let apply_at = start + quota;
    runtime.configure(apply_at, |now| {
        assert_eq!(owner.budget().used_clocks, quota + quota / 2);
        owner.configure("1000 100000", now);
    });
    let mut after = owner.budget();
    assert_eq!(after.used_clocks, quota + quota / 2);
    assert!(!after.eligible(apply_at));
}

#[ktest]
fn final_debit_after_configuration_charges_only_the_remaining_suffix() {
    let (owner, task) = OwnerFixture::new("g1b-config-final");
    let start = owner.start + 100;
    let mut runtime = CpuRuntimeFixture::new(task, start);
    runtime.configure(start + 17, |now| {
        assert_eq!(owner.budget().used_clocks, 17);
        owner.configure("1000 100000", now);
    });
    test_util::mark_zombie(&owner.process);
    CgroupMembership::write_lock().move_process_to_root(&owner.process);
    assert_eq!(runtime.update(start + 37), (37, 37));
    assert_eq!(owner.budget().used_clocks, 37);
}
