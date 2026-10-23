// SPDX-License-Identifier: MPL-2.0

//! Real cgroup owners and the production OSTD delivery-lock backend. BOOTTIME
//! endpoints are explicit fixtures; the dedicated guest supplies syscall,
//! calibrated clock, first-resume and live scheduler qualification.

use aster_systree::{SysBranchNode, SysNode, SysObj};
use os_control::{
    BootId, CapSpaceId, DeliveryState, NativeDeliveryRequest, OriginalOwnerAuthorityWith,
    OwnerId, ReserveAttemptWith,
};
use ostd::{irq::disable_local, mm::VmReader, prelude::ktest, task::Task};

use super::*;
use crate::{
    fs::cgroupfs::{CgroupNode, CgroupSystem, controller::{SubControl, SubCtrlType}},
    process::{KernelControlBackend, Process, test_util},
};

type TestCore = ControlCoreWith<KernelControlBackend>;
type TestAuthority = OriginalOwnerAuthorityWith<KernelControlBackend>;

struct Fixture {
    root: &'static Arc<CgroupSystem>,
    leaf: Arc<CgroupNode>,
    owner: Arc<SubController<CpuController>>,
    managers: [Arc<NativeCpuManager>; 2],
    cores: [TestCore; 2],
    authorities: [TestAuthority; 2],
    process: Option<Arc<Process>>,
    task: Option<Arc<Task>>,
    original_root: CpuMax,
    enabled_cpu: bool,
    name: &'static str,
}

impl Fixture {
    fn new(name: &'static str) -> Self {
        aster_time::init_for_ktest();
        aster_systree::init_for_ktest();
        let root = CgroupSystem::singleton();
        let enabled_cpu = !root.controller().active_set().contains_type(SubCtrlType::Cpu);
        if enabled_cpu { root.store_attr("cgroup.subtree_control", "+cpu").unwrap(); }
        let root_owner = root.controller().cpu.read().get().clone();
        let original_root = with_state(&root_owner, |state| state.max);
        let leaf = Arc::downcast::<CgroupNode>(root.create_child(name).unwrap()).unwrap();
        let owner = leaf.controller().cpu.read().get().clone();
        let (process, task) = test_util::new_unstarted_process();
        CgroupMembership::write_lock().move_process_to_node(process.clone(), &leaf).unwrap();
        let id = u128::from(process.pid()) << 64;
        let target = leaf.controller().bind_native_cpu_once_for_owner(&owner,
            ResourceDomainId::from_u128(id | 1), StableObjectId::from_u128(id | 2),
            &mut CgroupMembership::write_lock()).unwrap();
        with_state(&owner, |state| {
            state.max = CpuMax {
                quota_usec: 50_000, quota_sub_usec_ns: 0, period_usec: 100_000,
                window_start_ns: 0, used_ns: 0, cumulative_ns: 0, last_observed_ns: 0,
                accounting_fault: false, native_window_valid_from_ns: Some(0),
                carry_debt_ns: 0, nr_periods: 0, nr_throttled: 0,
                throttled_since_ns: None, throttled_ns: 0,
            };
        });
        let publishers = [PublisherId::from_u128(id | 3), PublisherId::from_u128(id | 4)];
        let observer = Arc::new(NativeCpuObserver { node: leaf.clone(), owner: owner.clone(), target });
        let managers = NativeCpuManager::prepare_pair(observer, publishers, 10).unwrap();
        let owner_id = OwnerId::new(publishers[1].bytes());
        let (manager_core, manager_authority) = TestCore::with_original_owner(
            BootId::from_u128(id | 5), CapSpaceId::new(publishers[0].bytes()), owner_id).unwrap();
        let (recovery_core, recovery_authority) = TestCore::with_original_owner(
            BootId::from_u128(id | 5), CapSpaceId::new(publishers[1].bytes()), owner_id).unwrap();
        Self { root, leaf, owner, managers, cores: [manager_core, recovery_core],
            authorities: [manager_authority, recovery_authority], process: Some(process), task: Some(task),
            original_root, enabled_cpu, name }
    }

    fn request(&self, role: usize, sequence: u64, revision: u64, cap: u64) -> NativeDeliveryRequest {
        NativeDeliveryRequest::from_wire(sequence, self.managers[role].grant(), revision, cap, 2, 1).unwrap()
    }

    fn execute(&self, role: usize, sequence: u64, revision: u64, cap: u64, now: Option<u64>)
        -> core::result::Result<DeliveryObservation, DeliveryError>
    {
        let manager = &self.managers[role];
        let core = &self.cores[role];
        match core.reserve_native_or_get(self.request(role, sequence, revision, cap), manager.publisher())? {
            ReserveAttemptWith::Existing(observation) => Ok(observation),
            ReserveAttemptWith::Reserved(token) => {
                core.execute_native_reserved::<SubController<CpuController>, _>(
                    &token, manager.publisher(), |execution| {
                        let _irq = disable_local();
                        manager.apply_at(execution, now)
                    })
            }
        }
    }

    fn budget(&self) -> CpuMax { with_state(&self.owner, |state| state.max) }
    fn revision(&self) -> u64 { with_state(&self.owner, |state| state.native.as_ref().unwrap().revision()) }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        if let Some(process) = self.process.take() {
            test_util::mark_zombie(&process);
            CgroupMembership::write_lock().move_process_to_root(&process);
            drop(process);
        }
        drop(self.task.take());
        self.leaf.mark_as_dead(&mut CgroupMembership::write_lock()).unwrap();
        self.root.remove_child(self.name).unwrap();
        let root_owner = self.root.controller().cpu.read().get().clone();
        with_state(&root_owner, |state| state.max = self.original_root);
        if self.enabled_cpu { self.root.store_attr("cgroup.subtree_control", "-cpu").unwrap(); }
    }
}

fn with_state<R>(owner: &SubController<CpuController>, f: impl FnOnce(&mut CpuBandwidthState) -> R) -> R {
    let mut state = owner.inner.as_ref().unwrap().control().unwrap().max.lock();
    f(&mut state)
}

#[ktest]
fn native_budget_enforces_sub_microsecond_caps_on_the_original_owner() {
    for (name, cap) in [("g1d-zero-ns", 0), ("g1d-one-ns", 1),
        ("g1d-999-ns", 999), ("g1d-1001-ns", 1001)] {
        let fixture = Fixture::new(name);
        let receipt = fixture.execute(0, 1, fixture.revision(), cap, Some(10)).unwrap();
        assert_eq!(receipt.status, Some(DeliveryStatus::Ok));
        assert_eq!(fixture.budget().quota_ns(), cap);
        with_state(&fixture.owner, |state| {
            state.max.used_ns = cap.saturating_sub(1);
            state.max.cumulative_ns = cap.saturating_sub(1);
            state.max.carry_debt_ns = 0;
            assert_eq!(state.max.eligible(10_000), cap != 0);
            state.max.used_ns = cap;
            state.max.cumulative_ns = cap;
            assert!(!state.max.eligible(10_000));
        });
    }
}

#[ktest]
fn native_budget_update_and_replay_preserve_consumption_and_positive_debt() {
    let fixture = Fixture::new("g1d-preserve-debit");
    with_state(&fixture.owner, |state| {
        state.max.used_ns = 500;
        state.max.cumulative_ns = 500;
        state.max.carry_debt_ns = 20;
    });
    let first = fixture.execute(0, 1, 1, 1001, Some(1_000)).unwrap();
    assert_eq!(first.status, Some(DeliveryStatus::Ok));
    assert_eq!(first.consumed_ns, Some(500));
    let before = fixture.budget();
    assert_eq!((before.used_ns, before.carry_debt_ns, before.window_start_ns), (500, 20, 0));
    assert_eq!(fixture.execute(0, 1, 1, 1001, Some(2_000)).unwrap(), first);
    assert_eq!(fixture.budget(), before);
    assert_eq!(fixture.revision(), 2);
    let same = fixture.execute(0, 2, 2, 1001, Some(1_000)).unwrap();
    assert_eq!((same.previous_revision, same.saved_revision), (Some(2), Some(3)));
    assert_eq!(fixture.budget(), before);
    assert_eq!(fixture.execute(0, 1, 1, 999, Some(2_000)), Err(DeliveryError::Conflict));
    assert_eq!(fixture.revision(), 3);
}

#[ktest]
fn native_manager_revocation_preserves_recovery_and_saved_history() {
    let fixture = Fixture::new("g1d-independent-recovery");
    with_state(&fixture.owner, |state| {
        state.max.used_ns = 500;
        state.max.cumulative_ns = 500;
        state.max.carry_debt_ns = 20;
    });
    let first = fixture.execute(0, 1, 1, 1001, Some(1_000)).unwrap();
    assert_eq!(first.status, Some(DeliveryStatus::Ok));
    fixture.managers[0].revoke_at(Some(1_000));
    assert_eq!(fixture.execute(0, 2, 2, 50_000_000, Some(1_000)).unwrap().status,
        Some(DeliveryStatus::Revoked));
    assert_eq!(fixture.budget().quota_ns(), 1001);
    let recovered = fixture.execute(1, 1, 2, 50_000_000, Some(1_000)).unwrap();
    assert_eq!(recovered.status, Some(DeliveryStatus::Ok));
    assert_eq!(fixture.budget().quota_ns(), 50_000_000);
    assert_eq!((fixture.budget().used_ns, fixture.budget().cumulative_ns, fixture.budget().carry_debt_ns),
        (500, 500, 20));
    assert_eq!(fixture.cores[0].query_delivery(&fixture.cores[0].delivery_view(), 1).unwrap(), first);
    assert_eq!(fixture.execute(0, 1, 1, 1001, Some(2_000)).unwrap(), first);
}

#[ktest]
fn native_recovery_expiry_is_finite_single_use_and_replays_original_receipt() {
    let fixture = Fixture::new("g1d-recovery-expiry");
    let expiry = 10 + INITIAL_LEASE_NS;
    let last = expiry + RECOVERY_GRACE_NS - 1;
    let first = fixture.execute(0, 1, 1, 1001, Some(100)).unwrap();
    assert_eq!(first.status, Some(DeliveryStatus::Ok));
    assert_eq!(fixture.execute(0, 2, 2, MAX_INITIAL_CAP_NS, Some(expiry)).unwrap().status,
        Some(DeliveryStatus::Revoked));
    assert_eq!(fixture.execute(1, 1, 2, 999, Some(expiry)).unwrap().status,
        Some(DeliveryStatus::PermissionDenied));
    assert_eq!(fixture.execute(1, 2, 1, MAX_INITIAL_CAP_NS, Some(expiry)).unwrap().status,
        Some(DeliveryStatus::Conflict));
    assert_eq!(fixture.budget().quota_ns(), 1001);
    assert_eq!(fixture.revision(), 2);
    let recovered = fixture.execute(1, 3, 2, MAX_INITIAL_CAP_NS, Some(last)).unwrap();
    assert_eq!(recovered.status, Some(DeliveryStatus::Ok));
    assert_eq!(fixture.revision(), 3);
    let before = fixture.budget();
    assert_eq!(fixture.execute(1, 4, 3, 1001, Some(last)).unwrap().status,
        Some(DeliveryStatus::PermissionDenied));
    assert_eq!(fixture.execute(1, 5, 3, MAX_INITIAL_CAP_NS, Some(last + 1)).unwrap().status,
        Some(DeliveryStatus::Revoked));
    assert_eq!(fixture.execute(1, 3, 2, MAX_INITIAL_CAP_NS, Some(last + 2)).unwrap(), recovered);
    assert_eq!(fixture.budget(), before);
    assert_eq!(fixture.cores[0].query_delivery(&fixture.cores[0].delivery_view(), 1).unwrap(), first);
    let _irq = disable_local();
    assert_eq!(fixture.managers[1].read_usage_at(Some(last + 1)), Err(CpuUsageError::Expired));
}

#[ktest]
fn native_recovery_never_infers_resume_from_zero_or_unowned_budget() {
    for (name, source, cap) in [("g1d-recovery-zero", Some(0), 0),
        ("g1d-recovery-other-source", Some(1), 1001),
        ("g1d-recovery-initial", None, MAX_INITIAL_CAP_NS),
        ("g1d-recovery-no-throttle", Some(0), MAX_INITIAL_CAP_NS)]
    {
        let fixture = Fixture::new(name);
        if let Some(source) = source {
            assert_eq!(fixture.execute(source, 1, 1, cap, Some(100)).unwrap().status,
                Some(DeliveryStatus::Ok));
        }
        fixture.managers[0].revoke_at(Some(100));
        let before = fixture.budget();
        let revision = fixture.revision();
        let next = if source == Some(1) { 2 } else { 1 };
        assert_eq!(fixture.execute(1, next, revision, MAX_INITIAL_CAP_NS, Some(100)).unwrap().status,
            Some(DeliveryStatus::PermissionDenied));
        assert_eq!(fixture.budget(), before);
        assert_eq!(fixture.revision(), revision);
        with_state(&fixture.owner, |state| assert!(!state.trusted_management.as_ref().unwrap().recovery_consumed));
    }
}

#[ktest]
fn native_recovery_first_close_cut_is_not_renewed_and_missing_clock_fences() {
    {
        let fixture = Fixture::new("g1d-recovery-first-cut");
        assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)).unwrap().status, Some(DeliveryStatus::Ok));
        fixture.managers[0].revoke_at(Some(100));
        fixture.managers[0].revoke_at(Some(200));
        let _irq = disable_local();
        assert!(fixture.managers[1].read_usage_at(Some(100 + RECOVERY_GRACE_NS - 1)).is_ok());
        assert_eq!(fixture.managers[1].read_usage_at(Some(100 + RECOVERY_GRACE_NS)), Err(CpuUsageError::Expired));
        drop(_irq);
        assert_eq!(fixture.execute(1, 1, 2, MAX_INITIAL_CAP_NS, Some(100 + RECOVERY_GRACE_NS)).unwrap().status,
            Some(DeliveryStatus::Revoked));
        assert_eq!(fixture.budget().quota_ns(), 1001);
    }
    {
        let fixture = Fixture::new("g1d-recovery-clock-lost");
        assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)).unwrap().status, Some(DeliveryStatus::Ok));
        fixture.managers[0].revoke_at(None);
        fixture.managers[0].revoke_at(Some(100));
        let before = fixture.budget();
        assert_eq!(fixture.execute(1, 1, 2, MAX_INITIAL_CAP_NS, Some(100)).unwrap().status,
            Some(DeliveryStatus::Indeterminate));
        assert_eq!(fixture.budget(), before);
    }
}

#[ktest]
fn native_recovery_refuses_expired_final_cut_and_preserves_accounting_fault() {
    {
        let fixture = Fixture::new("g1d-recovery-expired-cut");
        assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)).unwrap().status, Some(DeliveryStatus::Ok));
        let before = fixture.budget();
        assert_eq!(fixture.execute(1, 1, 2, MAX_INITIAL_CAP_NS, Some(10 + INITIAL_LEASE_NS + RECOVERY_GRACE_NS)).unwrap().status,
            Some(DeliveryStatus::Revoked));
        assert_eq!(fixture.budget(), before);
    }
    {
        let fixture = Fixture::new("g1d-recovery-bad-accounting");
        assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)).unwrap().status, Some(DeliveryStatus::Ok));
        fixture.managers[0].revoke_at(Some(100));
        with_state(&fixture.owner, |state| state.max.accounting_fault = true);
        let before = fixture.budget();
        assert_eq!(fixture.execute(1, 1, 2, MAX_INITIAL_CAP_NS, Some(100)).unwrap().status,
            Some(DeliveryStatus::Indeterminate));
        assert_eq!(fixture.budget(), before);
        assert_eq!(fixture.revision(), 2);
        with_state(&fixture.owner, |state| assert!(!state.trusted_management.as_ref().unwrap().recovery_consumed));
    }
}

#[ktest]
fn native_management_lease_edges_and_clock_absence_do_not_change_budget() {
    let fixture = Fixture::new("g1d-lease-edges");
    let original = fixture.budget();
    for (sequence, now, status) in [
        (1, Some(9), DeliveryStatus::Indeterminate),
        (2, None, DeliveryStatus::Indeterminate),
        (3, Some(10 + INITIAL_LEASE_NS), DeliveryStatus::Revoked),
    ] {
        let first = fixture.execute(0, sequence, 1, 1001, now).unwrap();
        assert_eq!(first.status, Some(status));
        assert_eq!(fixture.budget(), original);
        assert_eq!(fixture.execute(0, sequence, 1, 1001, Some(10)).unwrap(), first);
    }
    let issued = fixture.execute(0, 4, 1, 1001, Some(10)).unwrap();
    assert_eq!(issued.status, Some(DeliveryStatus::Ok));
    let final_cut = fixture.execute(0, 5, 2, 999, Some(9 + INITIAL_LEASE_NS)).unwrap();
    assert_eq!(final_cut.status, Some(DeliveryStatus::Ok));
    let last_budget = fixture.budget();
    assert_eq!(fixture.execute(0, 6, 3, 1, Some(10 + INITIAL_LEASE_NS)).unwrap().status,
        Some(DeliveryStatus::Revoked));
    assert_eq!(fixture.budget(), last_budget);
}

#[ktest]
fn native_ceiling_and_revision_rejections_are_immutable_without_effect() {
    let fixture = Fixture::new("g1d-semantic-refusals");
    let before = fixture.budget();
    let cap = fixture.execute(0, 1, 1, MAX_INITIAL_CAP_NS + 1, Some(100)).unwrap();
    assert_eq!(cap.status, Some(DeliveryStatus::PermissionDenied));
    assert_eq!(fixture.budget(), before);
    let stale = fixture.execute(0, 2, 2, 1001, Some(100)).unwrap();
    assert_eq!(stale.status, Some(DeliveryStatus::Conflict));
    assert_eq!(fixture.revision(), 1);
    let success = fixture.execute(1, 1, 1, 999, Some(100)).unwrap();
    assert_eq!(success.status, Some(DeliveryStatus::Ok));
    assert_eq!(fixture.execute(0, 2, 2, 1001, Some(100)).unwrap(), stale);
    assert_eq!(fixture.budget().quota_ns(), 999);
}

#[ktest]
fn native_accounting_fault_cannot_publish_a_successful_budget_receipt() {
    let fixture = Fixture::new("g1d-accounting-fault");
    with_state(&fixture.owner, |state| state.max.accounting_fault = true);
    let before = fixture.budget();
    let failed = fixture.execute(0, 1, 1, 0, Some(100)).unwrap();
    assert_eq!(failed.status, Some(DeliveryStatus::Indeterminate));
    assert_eq!(fixture.revision(), 1);
    assert_eq!(fixture.budget(), before);
    assert_eq!(failed.hos2_saved_status_code(), Some(8));
}

#[ktest]
fn native_controlled_leaf_refuses_linux_configuration_and_membership_aliases() {
    let fixture = Fixture::new("g1d-linux-aliases");
    let before = fixture.budget();
    assert!(matches!(fixture.owner.inner.as_ref().unwrap().write_attr("cpu.max",
        &mut VmReader::from(b"max 100000".as_slice()).to_fallible()), Err(Error::PermissionDenied)));
    assert!(matches!(fixture.root.store_attr("cgroup.subtree_control", "-cpu"), Err(Error::PermissionDenied)));
    let sibling = Arc::downcast::<CgroupNode>(fixture.root.create_child("g1d-sibling").unwrap()).unwrap();
    assert!(matches!(CgroupMembership::write_lock().move_process_to_node(
        fixture.process.as_ref().unwrap().clone(), &sibling), Err(Error::PermissionDenied)));
    assert_eq!(fixture.process.as_ref().unwrap().cgroup().get().unwrap().id(), fixture.leaf.id());
    assert_eq!(fixture.budget(), before);
    assert_eq!(fixture.revision(), 1);
    sibling.mark_as_dead(&mut CgroupMembership::write_lock()).unwrap();
    fixture.root.remove_child("g1d-sibling").unwrap();
}

#[ktest]
fn native_bounded_history_retirement_never_reexecutes_an_old_cpu_delivery() {
    let fixture = Fixture::new("g1d-history-retire");
    let first = fixture.execute(0, 1, 1, 1001, Some(100)).unwrap();
    for sequence in 2..=1024 {
        assert_eq!(fixture.execute(0, sequence, sequence, 1001, Some(100)).unwrap().status,
            Some(DeliveryStatus::Ok));
    }
    assert_eq!(fixture.execute(0, 1025, 1025, 1001, Some(100)), Err(DeliveryError::ResourceExhausted));
    assert_eq!(fixture.cores[0].query_delivery(&fixture.cores[0].delivery_view(), 1).unwrap(), first);
    let authority = &fixture.authorities[0];
    let ack = authority.history_ack(512, [1; 32]).unwrap();
    assert_eq!(fixture.cores[0].retire_through(&fixture.cores[0].delivery_view(), ack, authority),
        Err(DeliveryError::PermissionDenied));
    let view = fixture.cores[0].delivery_view_for(authority.owner()).unwrap();
    let retired = fixture.cores[0].retire_through(&view, ack, authority).unwrap();
    assert_eq!((retired.retired_through, retired.next_sequence), (512, 1025));
    assert_eq!(fixture.execute(0, 1025, 1025, 999, Some(100)).unwrap().status,
        Some(DeliveryStatus::Ok));
    let before = fixture.budget();
    assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)), Err(DeliveryError::Retired));
    assert_eq!(fixture.cores[0].query_delivery(&view, 1).unwrap().state, DeliveryState::Retired);
    assert_eq!(fixture.budget(), before);
    assert_eq!(fixture.revision(), 1026);
}

// The production IRQ wrapper and real owner, with explicit fault cuts. The
// separate native probe must qualify the physical timer and image-close path.
fn watchdog_tick(fixture: &Fixture, now: Option<u64>) {
    let _irq = disable_local();
    fixture.managers[0].watchdog_tick_at(now, &fixture.process.as_ref().unwrap().status_observer());
}

fn arm_watchdog_fixture(fixture: &Fixture) {
    with_state(&fixture.owner, |state| {
        let watchdog = &mut state.trusted_management.as_mut().unwrap().watchdog;
        watchdog.armed = true;
        watchdog.workload = Some(fixture.process.as_ref().unwrap().status_observer());
    });
}

#[ktest]
fn native_watchdog_first_close_deadline_restores_once_with_original_receipt() {
    use super::watchdog::{WATCHDOG_DELAY_NS, WatchdogOutcome};
    let fixture = Fixture::new("g1d-watchdog-once");
    arm_watchdog_fixture(&fixture);
    assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)).unwrap().status, Some(DeliveryStatus::Ok));
    watchdog_tick(&fixture, Some(100 + WATCHDOG_DELAY_NS));
    assert_eq!(fixture.revision(), 2); // Healthy manager must retain authority.
    fixture.managers[0].revoke_at(Some(100 + WATCHDOG_DELAY_NS));
    fixture.managers[0].revoke_at(Some(200 + WATCHDOG_DELAY_NS));
    let due = 100 + 2 * WATCHDOG_DELAY_NS;
    watchdog_tick(&fixture, Some(due - 1));
    assert_eq!(fixture.budget().quota_ns(), 1001);
    with_state(&fixture.owner, |state| {
        // Same-window consumed CPU and positive debt survive the restoration.
        state.max.window_start_ns = due / CPU_PERIOD_NS * CPU_PERIOD_NS;
        state.max.used_ns = 70;
        state.max.cumulative_ns = 70;
        state.max.carry_debt_ns = 23;
    });
    watchdog_tick(&fixture, Some(due));
    let terminal = with_state(&fixture.owner, |state| state.trusted_management.as_ref().unwrap().watchdog.terminal.unwrap());
    let WatchdogOutcome::Restored(receipt) = terminal.0 else { panic!("missing native watchdog receipt"); };
    assert_eq!((receipt.previous_revision(), receipt.revision(), receipt.effective_boottime_ns(),
                receipt.consumed_at_apply_ns()), (2, 3, due, 70));
    assert_eq!(receipt.stable_object_id(), fixture.managers[0].observer.target.stable_object_id());
    assert_eq!(fixture.budget().quota_ns(), MAX_INITIAL_CAP_NS);
    let before = fixture.budget();
    assert_eq!((before.used_ns, before.carry_debt_ns), (70, 23));
    for tick in [Some(due), Some(due + 1), Some(due + RECOVERY_GRACE_NS), None] {
        watchdog_tick(&fixture, tick);
        assert_eq!(fixture.revision(), 3);
        assert_eq!(fixture.budget(), before);
        assert_eq!(with_state(&fixture.owner, |state| state.trusted_management.as_ref().unwrap().watchdog.terminal), Some(terminal));
    }
    // The timer consumes the original one-use recovery allowance. D is not
    // fabricated for the kernel effect, and a user retry has no second effect.
    let rejected = fixture.execute(1, 1, 3, MAX_INITIAL_CAP_NS, Some(due + 1)).unwrap();
    assert_eq!(rejected.status, Some(DeliveryStatus::PermissionDenied));
    assert_eq!(fixture.execute(1, 1, 3, MAX_INITIAL_CAP_NS, Some(due + 2)).unwrap(), rejected);
    assert_eq!(fixture.revision(), 3);
}

#[ktest]
fn native_watchdog_preserves_zero_job_stop_and_recovery_owned_budgets() {
    use super::watchdog::{WATCHDOG_DELAY_NS, WatchdogOutcome};
    use crate::process::signal::sig_num::SigNum;
    for (name, kind) in [("g1d-watchdog-zero", 0), ("g1d-watchdog-stopped", 1),
        ("g1d-watchdog-recovered", 2), ("g1d-watchdog-initial", 3)] {
        let fixture = Fixture::new(name);
        arm_watchdog_fixture(&fixture);
        if kind < 3 {
            assert_eq!(fixture.execute(0, 1, 1, if kind == 0 { 0 } else { 1001 }, Some(100)).unwrap().status,
                Some(DeliveryStatus::Ok));
        }
        fixture.managers[0].revoke_at(Some(100));
        let parent = (kind == 1).then(|| test_util::UnstartedParent::new(fixture.process.as_ref().unwrap()));
        if let Some(parent) = &parent {
            assert_parent_woken_by(parent.process(), || fixture.process.as_ref().unwrap().stop(SigNum::from_u8(19)));
        }
        if kind == 2 {
            assert_eq!(fixture.execute(1, 1, 2, MAX_INITIAL_CAP_NS, Some(101)).unwrap().status, Some(DeliveryStatus::Ok));
        }
        let before = fixture.budget();
        let revision = fixture.revision();
        watchdog_tick(&fixture, Some(100 + WATCHDOG_DELAY_NS));
        let expected = if kind == 1 { WatchdogOutcome::JobStopped } else { WatchdogOutcome::Ineligible };
        assert_eq!(with_state(&fixture.owner, |state| state.trusted_management.as_ref().unwrap().watchdog.terminal.unwrap().0), expected);
        assert_eq!(fixture.budget(), before);
        assert_eq!(fixture.revision(), revision);
        assert_eq!(fixture.process.as_ref().unwrap().is_stopped(), kind == 1);
        if kind == 1 {
            // A later original POSIX resume may change state, but cannot renew
            // or retroactively turn the terminal timer refusal into success.
            assert_parent_woken_by(parent.as_ref().unwrap().process(), || fixture.process.as_ref().unwrap().resume());
            watchdog_tick(&fixture, Some(101 + WATCHDOG_DELAY_NS));
            assert_eq!(fixture.budget(), before);
            assert_eq!(fixture.revision(), revision);
            test_util::mark_zombie(fixture.process.as_ref().unwrap());
            parent.as_ref().unwrap().detach_zombie_child();
        }
    }
}

#[ktest]
fn native_watchdog_expiry_clock_fault_and_late_tick_fail_closed() {
    use super::watchdog::{WATCHDOG_DELAY_NS, WatchdogOutcome};
    for (name, cut, tick, expected) in [
        ("g1d-watchdog-unknown", Some(100), None, WatchdogOutcome::ClockUnavailable),
        ("g1d-watchdog-rollback", Some(100), Some(99), WatchdogOutcome::ClockUnavailable),
        ("g1d-watchdog-close-clock", None, Some(100 + WATCHDOG_DELAY_NS), WatchdogOutcome::ClockUnavailable),
        ("g1d-watchdog-late", Some(100), Some(100 + RECOVERY_GRACE_NS), WatchdogOutcome::Expired),
    ] {
        let fixture = Fixture::new(name);
        arm_watchdog_fixture(&fixture);
        assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)).unwrap().status, Some(DeliveryStatus::Ok));
        fixture.managers[0].revoke_at(cut);
        let before = fixture.budget();
        watchdog_tick(&fixture, tick);
        assert_eq!(with_state(&fixture.owner, |state| state.trusted_management.as_ref().unwrap().watchdog.terminal.unwrap().0), expected);
        watchdog_tick(&fixture, Some(100 + WATCHDOG_DELAY_NS));
        assert_eq!(fixture.budget(), before);
        assert_eq!(fixture.revision(), 2);
    }
    // No exit notification is needed after the immutable normal lease expires.
    let fixture = Fixture::new("g1d-watchdog-lease");
    arm_watchdog_fixture(&fixture);
    assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)).unwrap().status, Some(DeliveryStatus::Ok));
    let due = 10 + INITIAL_LEASE_NS + WATCHDOG_DELAY_NS;
    watchdog_tick(&fixture, Some(due - 1));
    assert_eq!(fixture.revision(), 2);
    watchdog_tick(&fixture, Some(due));
    assert_eq!(fixture.revision(), 3);
    assert_eq!(fixture.budget().quota_ns(), MAX_INITIAL_CAP_NS);
}

#[ktest]
fn native_watchdog_fenced_or_bad_accounting_never_restores() {
    use super::watchdog::{WATCHDOG_DELAY_NS, WatchdogOutcome};
    for (name, fault) in [("g1d-watchdog-accounting", false), ("g1d-watchdog-detached", true)] {
        let fixture = Fixture::new(name);
        arm_watchdog_fixture(&fixture);
        assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)).unwrap().status, Some(DeliveryStatus::Ok));
        fixture.managers[0].revoke_at(Some(100));
        with_state(&fixture.owner, |state| {
            if fault { state.detach(); } else { state.max.accounting_fault = true; }
        });
        let before = fixture.budget();
        watchdog_tick(&fixture, Some(100 + WATCHDOG_DELAY_NS));
        assert_eq!(fixture.budget(), before);
        assert_eq!(fixture.revision(), 2);
        let expected = if fault { WatchdogOutcome::Closed } else { WatchdogOutcome::AccountingFault };
        assert_eq!(with_state(&fixture.owner, |state| state.trusted_management.as_ref().unwrap().watchdog.terminal.unwrap().0), expected);
    }
}

#[ktest]
fn native_watchdog_observes_original_status_without_retaining_process() {
    use crate::process::signal::sig_num::SigNum;
    aster_time::init_for_ktest();
    aster_systree::init_for_ktest();
    let (process, task) = test_util::new_unstarted_process();
    let parent = test_util::UnstartedParent::new(&process);
    let weak = Arc::downgrade(&process);
    let observer = process.status_observer();
    assert!(!observer.is_stopped());
    assert!(!observer.is_zombie());
    assert_parent_woken_by(parent.process(), || process.stop(SigNum::from_u8(19)));
    assert!(observer.is_stopped());
    assert_parent_woken_by(parent.process(), || process.resume());
    assert!(!observer.is_stopped());
    test_util::mark_zombie(&process);
    parent.detach_zombie_child();
    drop(task);
    drop(process);
    // In particular, a permanent timer must not delay Process::Drop/pidfile
    // HUP or retain the VMAR/TaskSet by pinning the entire Process.
    assert!(weak.upgrade().is_none());
    assert!(observer.is_zombie());
    // Keep the actual parent alive until after the child's Process is gone.
    drop(parent);
}

fn assert_parent_woken_by(parent: &Process, transition: impl FnOnce()) {
    let (waiter, waker) = ostd::sync::Waiter::new_pair();
    parent.children_wait_queue().enqueue(waker.clone());
    transition();
    // The waiter is still alive: false proves the original parent notification
    // already woke it, rather than being closed by dropping the test waiter.
    assert!(!waker.wake_up());
    assert_eq!(parent.children_wait_queue().wake_all(), 0);
    drop(waiter);
}

#[ktest]
fn native_watchdog_poll_admission_never_settles_or_changes_budget() {
    use super::watchdog::WATCHDOG_DELAY_NS;
    let fixture = Fixture::new("g1d-watchdog-poll");
    arm_watchdog_fixture(&fixture);
    assert_eq!(fixture.execute(0, 1, 1, 1001, Some(100)).unwrap().status, Some(DeliveryStatus::Ok));
    let before = fixture.budget();
    with_state(&fixture.owner, |state| {
        assert!(!state.watchdog_ready(Some(100 + WATCHDOG_DELAY_NS), 10, false, true));
        assert_eq!(state.max, before);
    });
    fixture.managers[0].revoke_at(Some(100 + WATCHDOG_DELAY_NS));
    with_state(&fixture.owner, |state| {
        assert!(!state.watchdog_ready(Some(99 + 2 * WATCHDOG_DELAY_NS), 10, false, true));
        assert!(state.watchdog_ready(Some(100 + 2 * WATCHDOG_DELAY_NS), 10, false, true));
        assert_eq!(state.max, before);
        assert_eq!(state.native.as_ref().unwrap().revision(), 2);
    });
}
