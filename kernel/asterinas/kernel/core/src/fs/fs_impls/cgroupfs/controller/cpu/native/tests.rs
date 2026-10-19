// SPDX-License-Identifier: MPL-2.0

//! G1-a regressions on real cgroup controllers, RCU replacement and deletion.
//!
//! Debit intervals are controlled fixtures; these tests do not execute HOS2,
//! model a second scheduler, or establish BOOTTIME/SMP accounting qualification.

use alloc::sync::Arc;

use aster_systree::{Error, Result, SysBranchNode, SysNode};
use os_control::{
    CPU_PERIOD_NS, NativeResourceError, NativeResourceState, NativeResourceUpdate, NativeTarget,
    ResourceDomainId, StableObjectId,
};
use ostd::{arch::read_tsc, cpu::CpuId, mm::VmReader, panic, prelude::ktest};

use super::super::{
    super::{Controller, SubControl, SubController, SubCtrlType},
    CpuController, CpuMax, CpuStatKind, charge_task_cpu,
};
use crate::{
    fs::cgroupfs::{CgroupMembership, CgroupNode, CgroupSysNode, CgroupSystem},
    prelude::Errno,
    process::test_util,
};

struct Hierarchy {
    root: &'static Arc<CgroupSystem>,
    parent: Arc<CgroupNode>,
    leaf: Arc<CgroupNode>,
    name: &'static str,
    enabled_root_cpu: bool,
    leaf_removed: bool,
    original_root_budget: CpuMax,
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
        let leaf = Arc::downcast::<CgroupNode>(parent.create_child("leaf").unwrap()).unwrap();
        let original_root_budget = budget(&owner(root.controller()));
        Self {
            root,
            parent,
            leaf,
            name,
            enabled_root_cpu,
            leaf_removed: false,
            original_root_budget,
        }
    }

    fn remove_leaf(&mut self) -> crate::prelude::Result<()> {
        let mut membership = CgroupMembership::write_lock();
        self.leaf.mark_as_dead(&mut membership)?;
        self.parent.remove_child("leaf").unwrap();
        self.leaf_removed = true;
        Ok(())
    }
}

impl Drop for Hierarchy {
    fn drop(&mut self) {
        if !self.leaf_removed {
            self.remove_leaf().unwrap();
        }
        {
            let mut membership = CgroupMembership::write_lock();
            self.parent.mark_as_dead(&mut membership).unwrap();
            self.root.remove_child(self.name).unwrap();
        }
        let root_cpu = owner(self.root.controller());
        root_cpu
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

fn bind(
    controller: &Controller,
    owner: &Arc<SubController<CpuController>>,
    id: u128,
) -> Result<NativeTarget> {
    controller.bind_native_cpu_once_for_owner(
        owner,
        ResourceDomainId::from_u128(id),
        StableObjectId::from_u128(id + 1),
        &mut CgroupMembership::write_lock(),
    )
}

fn write(owner: &SubController<CpuController>, input: &str) -> Result<usize> {
    owner.inner.as_ref().unwrap().write_attr(
        "cpu.max",
        &mut VmReader::from(input.as_bytes()).to_fallible(),
    )
}

fn assert_native_refused(owner: &SubController<CpuController>, expected: NativeResourceError) {
    let control = owner.inner.as_ref().unwrap().control().unwrap();
    let mut state = control.max.lock();
    let before = state.max;
    let native = state.native.as_mut().unwrap();
    let request = NativeResourceUpdate {
        target: native.id(),
        stable_object_id: native.stable_object_id(),
        expected_revision: 1,
        period_ns: CPU_PERIOD_NS,
        cap_ns: 0,
    };
    let mut called = false;
    assert_eq!(
        native.apply(request, 0, 0, &mut || called = true),
        Err(expected)
    );
    assert!(!called);
    assert_eq!(state.max, before);
}

#[ktest]
fn binding_preserves_current_budget_and_cannot_be_repeated() {
    let hierarchy = Hierarchy::new("g1a-bind-once");
    let cpu = owner(hierarchy.leaf.controller());
    write(&cpu, "2000 250000").unwrap();
    let before = budget(&cpu);
    assert!(matches!(
        bind(hierarchy.leaf.controller(), &cpu, 0),
        Err(Error::InvalidOperation)
    ));
    let target = bind(hierarchy.leaf.controller(), &cpu, 10).unwrap();
    assert!(matches!(
        bind(hierarchy.leaf.controller(), &cpu, 20),
        Err(Error::AlreadyExists)
    ));
    let state = cpu.inner.as_ref().unwrap().control().unwrap().max.lock();
    let native = state.native.as_ref().unwrap();
    assert_eq!(native.id(), target.id());
    assert_eq!(native.stable_object_id(), target.stable_object_id());
    assert_eq!(native.revision(), 1);
    assert_eq!(state.max, before);
}

#[ktest]
fn ordinary_cpu_max_write_advances_revision_without_refilling_debt() {
    let hierarchy = Hierarchy::new("g1a-shared-revision");
    let cpu = owner(hierarchy.leaf.controller());
    write(&cpu, "1000 100000").unwrap();
    bind(hierarchy.leaf.controller(), &cpu, 30).unwrap();
    let control = cpu.inner.as_ref().unwrap().control().unwrap();
    let quota = CpuMax::us_to_clocks(1_000);
    {
        let mut state = control.max.lock();
        // Exclude elapsed-window repayment from this configuration test. The
        // existing charge tests own clock/window integration qualification.
        state.max.window_start = read_tsc().saturating_add(CpuMax::us_to_clocks(10_000_000));
        state.max.used_clocks = quota;
        state.max.carry_debt_clocks = quota / 2;
    }
    hierarchy.leaf.store_attr("cpu.max", "1000 100000").unwrap();
    {
        let state = control.max.lock();
        assert_eq!(state.native.as_ref().unwrap().revision(), 2);
        assert_eq!(state.max.used_clocks, quota);
        assert_eq!(state.max.carry_debt_clocks, quota / 2);
    }
    assert_native_refused(
        &cpu,
        NativeResourceError::RevisionConflict {
            expected: 1,
            actual: 2,
        },
    );
}

#[ktest]
fn malformed_writes_do_not_consume_the_bound_revision() {
    let hierarchy = Hierarchy::new("g1a-invalid-config");
    let cpu = owner(hierarchy.leaf.controller());
    bind(hierarchy.leaf.controller(), &cpu, 40).unwrap();
    let before = budget(&cpu);
    for input in [
        "",
        "1000 nope",
        "max nope",
        "1000 100000 extra",
        "0 100000",
        "1000 999",
        "18446744073709551616",
    ] {
        assert!(
            matches!(write(&cpu, input), Err(Error::InvalidOperation)),
            "{input:?}"
        );
        let state = cpu.inner.as_ref().unwrap().control().unwrap().max.lock();
        assert_eq!(state.native.as_ref().unwrap().revision(), 1);
        assert_eq!(state.max, before);
    }
}

#[ktest]
fn replacement_closes_bound_old_arc_and_does_not_inherit_metadata() {
    let hierarchy = Hierarchy::new("g1a-replace-bound");
    let old = owner(hierarchy.leaf.controller());
    let old_target = bind(hierarchy.leaf.controller(), &old, 50).unwrap();
    old.inner
        .as_ref()
        .unwrap()
        .account(CpuId::bsp(), CpuStatKind::User);
    let old_usage = old.inner.as_ref().unwrap().stats.user.sum_all_cpus();
    let before = budget(&old);
    hierarchy
        .parent
        .store_attr("cgroup.subtree_control", "-cpu")
        .unwrap();
    let inactive = owner(hierarchy.leaf.controller());
    assert!(!Arc::ptr_eq(&old, &inactive));
    assert!(matches!(
        bind(hierarchy.leaf.controller(), &old, 60),
        Err(Error::IsDead)
    ));
    assert!(matches!(
        bind(hierarchy.leaf.controller(), &inactive, 60),
        Err(Error::AttributeError)
    ));
    assert!(matches!(write(&old, "2000 100000"), Err(Error::IsDead)));
    assert_eq!(budget(&old), before);
    assert_native_refused(&old, NativeResourceError::Invalidated);

    hierarchy
        .parent
        .store_attr("cgroup.subtree_control", "+cpu")
        .unwrap();
    let new = owner(hierarchy.leaf.controller());
    assert!(!Arc::ptr_eq(&old, &new));
    assert!(!Arc::ptr_eq(&inactive, &new));
    assert!(matches!(
        bind(hierarchy.leaf.controller(), &inactive, 60),
        Err(Error::IsDead)
    ));
    assert!(
        new.inner
            .as_ref()
            .unwrap()
            .control()
            .unwrap()
            .max
            .lock()
            .native
            .is_none()
    );
    assert_eq!(
        new.inner.as_ref().unwrap().stats.user.sum_all_cpus(),
        old_usage
    );
    let new_target = bind(hierarchy.leaf.controller(), &new, 70).unwrap();
    assert_ne!(old_target.id(), new_target.id());
    let state = old.inner.as_ref().unwrap().control().unwrap().max.lock();
    assert!(state.is_detached);
    assert_eq!(state.native.as_ref().unwrap().id(), old_target.id());
    assert_eq!(state.native.as_ref().unwrap().revision(), 1);
}

#[ktest]
fn replacement_also_closes_an_unbound_old_arc() {
    let hierarchy = Hierarchy::new("g1a-replace-unbound");
    let old = owner(hierarchy.leaf.controller());
    hierarchy
        .parent
        .store_attr("cgroup.subtree_control", "-cpu")
        .unwrap();
    hierarchy
        .parent
        .store_attr("cgroup.subtree_control", "+cpu")
        .unwrap();
    assert!(matches!(
        bind(hierarchy.leaf.controller(), &old, 80),
        Err(Error::IsDead)
    ));
    assert!(matches!(write(&old, "2000 100000"), Err(Error::IsDead)));
    let state = old.inner.as_ref().unwrap().control().unwrap().max.lock();
    assert!(state.is_detached);
    assert!(state.native.is_none());
}

#[ktest]
fn deleted_unbound_current_arc_cannot_be_bound_afterward() {
    let mut hierarchy = Hierarchy::new("g1a-delete-unbound");
    let old = owner(hierarchy.leaf.controller());
    hierarchy.remove_leaf().unwrap();
    // The retained node still contains this exact RCU Arc. Pointer equality
    // alone cannot reject this late bind; detached must survive native=None.
    assert!(Arc::ptr_eq(&old, &owner(hierarchy.leaf.controller())));
    assert!(matches!(
        bind(hierarchy.leaf.controller(), &old, 90),
        Err(Error::IsDead)
    ));
    assert!(matches!(write(&old, "2000 100000"), Err(Error::IsDead)));
    let state = old.inner.as_ref().unwrap().control().unwrap().max.lock();
    assert!(state.is_detached);
    assert!(state.native.is_none());
}

#[ktest]
fn deletion_keeps_bound_identity_revision_and_accounting() {
    let mut hierarchy = Hierarchy::new("g1a-delete-bound");
    let old = owner(hierarchy.leaf.controller());
    let target = bind(hierarchy.leaf.controller(), &old, 100).unwrap();
    write(&old, "1000 100000").unwrap();
    let before = budget(&old);
    hierarchy.remove_leaf().unwrap();
    assert!(matches!(write(&old, "3000 100000"), Err(Error::IsDead)));
    assert!(matches!(
        bind(hierarchy.leaf.controller(), &old, 110),
        Err(Error::IsDead)
    ));
    assert_eq!(budget(&old), before);
    assert_native_refused(&old, NativeResourceError::Invalidated);
    let state = old.inner.as_ref().unwrap().control().unwrap().max.lock();
    let native = state.native.as_ref().unwrap();
    assert_eq!(native.id(), target.id());
    assert_eq!(native.stable_object_id(), target.stable_object_id());
    assert_eq!(native.revision(), 2);
}

#[ktest]
fn last_revision_succeeds_then_real_owner_writes_fail_without_wrapping() {
    let hierarchy = Hierarchy::new("g1a-revision-limit");
    let cpu = owner(hierarchy.leaf.controller());
    let target = bind(hierarchy.leaf.controller(), &cpu, 120).unwrap();
    let control = cpu.inner.as_ref().unwrap().control().unwrap();
    control.max.lock().native = Some(
        NativeResourceState::new_at_revision_for_ktest(
            target.id(),
            target.stable_object_id(),
            u64::MAX - 1,
        )
        .unwrap(),
    );
    write(&cpu, "2000 100000").unwrap();
    let before = budget(&cpu);
    for input in ["3000 100000", "2000 100000", "max 250000"] {
        assert!(matches!(write(&cpu, input), Err(Error::Overflow)));
        let state = control.max.lock();
        assert_eq!(state.native.as_ref().unwrap().revision(), u64::MAX);
        assert_eq!(state.max, before);
    }
    assert_native_refused(
        &cpu,
        NativeResourceError::RevisionConflict {
            expected: 1,
            actual: u64::MAX,
        },
    );
}

#[ktest]
fn ambiguous_metadata_mutation_stays_indeterminate_after_detachment() {
    let mut hierarchy = Hierarchy::new("g1a-indeterminate");
    let cpu = owner(hierarchy.leaf.controller());
    bind(hierarchy.leaf.controller(), &cpu, 130).unwrap();
    let before = budget(&cpu);
    let control = cpu.inner.as_ref().unwrap().control().unwrap();
    let result = panic::catch_unwind(|| {
        let mut state = control.max.lock();
        state
            .native
            .as_mut()
            .unwrap()
            .apply_owner_configuration(&mut || {
                panic!("g1a expected ambiguous owner mutation");
            })
            .unwrap();
    });
    assert!(result.is_err());
    assert!(matches!(
        write(&cpu, "2000 100000"),
        Err(Error::ResourceUnavailable)
    ));
    assert_eq!(budget(&cpu), before);
    assert_native_refused(&cpu, NativeResourceError::Indeterminate);
    hierarchy.remove_leaf().unwrap();
    assert_native_refused(&cpu, NativeResourceError::Indeterminate);
    let state = control.max.lock();
    assert!(state.is_detached);
    assert!(state.native.as_ref().unwrap().is_indeterminate());
    assert_eq!(state.native.as_ref().unwrap().revision(), 1);
}

#[ktest]
fn final_charge_lease_blocks_deletion_until_the_real_debit_is_retained() {
    let mut hierarchy = Hierarchy::new("g1a-final-charge");
    let old = owner(hierarchy.leaf.controller());
    bind(hierarchy.leaf.controller(), &old, 140).unwrap();
    let (process, task) = test_util::new_unstarted_process();
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &hierarchy.leaf)
        .unwrap();
    test_util::mark_zombie(&process);
    CgroupMembership::write_lock().move_process_to_root(&process);
    assert_eq!(hierarchy.remove_leaf().unwrap_err().error(), Errno::EBUSY);
    {
        let state = old.inner.as_ref().unwrap().control().unwrap().max.lock();
        assert!(!state.is_detached);
        assert!(!state.native.as_ref().unwrap().is_fenced());
    }
    // The real unstarted task retains its old leaf through the production
    // zombie lease. Only its explicit scheduler interval is charged here.
    let period = CpuMax::us_to_clocks(100_000).max(1);
    let start = (read_tsc() / period + 2) * period;
    old.inner
        .as_ref()
        .unwrap()
        .control()
        .unwrap()
        .max
        .lock()
        .max
        .window_start = start;
    drop(process);
    charge_task_cpu(&task, start, start + 37);
    assert_eq!(budget(&old).used_clocks, 37);
    assert_eq!(hierarchy.remove_leaf().unwrap_err().error(), Errno::EBUSY);
    drop(task);
    hierarchy.remove_leaf().unwrap();
    assert_eq!(budget(&old).used_clocks, 37);
    assert_native_refused(&old, NativeResourceError::Invalidated);
    // A retained accounting reference must still settle already incurred time
    // after management closure; closing the incarnation must not erase debt.
    old.charge_bandwidth_hierarchy(start + 37, start + 53);
    assert_eq!(budget(&old).used_clocks, 53);
}
