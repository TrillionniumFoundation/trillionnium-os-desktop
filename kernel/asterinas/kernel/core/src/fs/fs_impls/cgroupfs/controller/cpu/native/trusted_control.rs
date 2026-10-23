// SPDX-License-Identifier: MPL-2.0

//! The actual CPU owner's bounded G1-d management seam.
//!
//! Immutable Process slots pin this owner and saved delegation terms. The
//! canonical ManagementGrantState and resource revision remain beside CpuMax,
//! under its original IRQ-disabling lock. Delivery storage remains entirely
//! in os-control. No image/table lock spans scheduler or bandwidth work.

use os_control::{
    ControlCoreWith, DeliveryError, DeliveryObservation, DeliveryStatus, LockBackend,
    ManagementGrantConfig, ManagementGrantId, ManagementGrantState, NativeExecution,
    NativeGrant, NativeResourceUpdate, PublishOutcome, PublisherId, ReserveTokenWith,
};

use super::*;
use crate::fs::cgroupfs::CgroupSysNode;

mod watchdog;
use watchdog::WatchdogState;

pub(crate) const MAX_INITIAL_CAP_NS: u64 = 50_000_000;
pub(crate) const INITIAL_LEASE_NS: u64 = 300_000_000_000;
pub(crate) const RECOVERY_GRACE_NS: u64 = 30_000_000_000;

/// The last successful budget source, in the sole CPU owner. A bare zero cap
/// contains no user intent, so it must never be inferred to be recoverable.
#[derive(Clone, Copy, PartialEq, Eq)]
enum BudgetCause {
    Bootstrap,
    Manager,
    Recovery,
    UnclassifiedPause,
}

#[derive(Clone, Copy)]
enum ManagerClosure {
    Open,
    At(u64),
    ClockUnavailable,
}

/// Policy and canonical delegations live under the original bandwidth lock.
/// No D delivery result, current revision or current budget is duplicated here.
/// The watchdog retains only its immutable owner-produced effect receipt.
/// The restore cap is an immutable pre-delegation limit, not a mutable quota.
pub(super) struct TrustedCpuManagement {
    grants: [ManagementGrantState; 2],
    manager_expires_ns: u64,
    restore_cap_ns: u64,
    manager_closed: ManagerClosure,
    budget_cause: BudgetCause,
    recovery_consumed: bool,
    watchdog: WatchdogState,
}

impl TrustedCpuManagement {
    /// `true` denotes the restricted, one-effect recovery phase. Its first
    /// close cut cannot move when closure repeats or when a caller retries.
    fn recovery_phase(&self, index: usize, now: u64) -> core::result::Result<bool, DeliveryStatus> {
        if self.grants[index].is_revoked() {
            return Err(DeliveryStatus::Revoked);
        }
        if index == 0 {
            return if now < self.manager_expires_ns { Ok(false) } else { Err(DeliveryStatus::Revoked) };
        }
        let cut = match self.manager_closed {
            ManagerClosure::At(cut) => cut.min(self.manager_expires_ns),
            ManagerClosure::ClockUnavailable => return Err(DeliveryStatus::Indeterminate),
            ManagerClosure::Open if self.grants[0].is_revoked() => return Err(DeliveryStatus::Indeterminate),
            ManagerClosure::Open if now < self.manager_expires_ns => return Ok(false),
            ManagerClosure::Open => self.manager_expires_ns,
        };
        if now < cut {
            return Err(DeliveryStatus::Indeterminate);
        }
        // prepare_pair checked the maximum (normal expiry + grace) before
        // publication, and an earlier close can only shorten this endpoint.
        if now >= cut + RECOVERY_GRACE_NS {
            return Err(DeliveryStatus::Revoked);
        }
        Ok(true)
    }

    fn recovery_budget_allowed(&self, current_cap: u64, requested_cap: u64) -> bool {
        !self.recovery_consumed && self.budget_cause == BudgetCause::Manager
            && current_cap > 0 && current_cap < self.restore_cap_ns && requested_cap == self.restore_cap_ns
    }

    fn applied(&mut self, index: usize, cap: u64, recovering: bool) {
        self.budget_cause = if cap == 0 { BudgetCause::UnclassifiedPause }
            else if index == 0 { BudgetCause::Manager } else { BudgetCause::Recovery };
        self.recovery_consumed |= recovering;
    }
}

/// A saved capability resolved only by the stopped, sealed bootstrap plan.
/// Cloning an Arc to this value is not minting a current owner delegation.
pub(crate) struct NativeCpuManager {
    observer: Arc<NativeCpuObserver>,
    grant: NativeGrant,
    index: usize,
    issued_ns: u64,
    expires_ns: u64,
}

impl NativeCpuManager {
    /// Install both independent delegations before any role can run. The
    /// caller owns the actual prepared workload and the two image identities.
    #[cfg(any(ktest, feature = "g1d-trusted-control"))]
    pub(crate) fn prepare_pair(
        observer: Arc<NativeCpuObserver>,
        publishers: [PublisherId; 2],
        issued_ns: u64,
    ) -> crate::prelude::Result<[Arc<Self>; 2]> {
        use crate::prelude::*;

        let expires_ns = issued_ns.checked_add(INITIAL_LEASE_NS).ok_or_else(|| {
            Error::with_message(Errno::EOVERFLOW, "initial management lease overflow")
        })?;
        let recovery_expires_ns = expires_ns.checked_add(RECOVERY_GRACE_NS).ok_or_else(|| {
            Error::with_message(Errno::EOVERFLOW, "initial recovery endpoint overflow")
        })?;
        let make_state = |publisher: PublisherId, end: u64| {
            ManagementGrantState::new(ManagementGrantConfig {
                id: ManagementGrantId::new(publisher.bytes()),
                publisher,
                target: observer.target.id(),
                stable_object_id: observer.target.stable_object_id(),
                epoch: 1,
                issued_at_ns: issued_ns,
                expires_at_ns: end,
                max_cap_ns: MAX_INITIAL_CAP_NS,
            }).map_err(|_| Error::with_message(Errno::EINVAL, "invalid initial delegation"))
        };
        let grants = [make_state(publishers[0], expires_ns)?, make_state(publishers[1], recovery_expires_ns)?];
        let mut snapshots = Vec::with_capacity(2);
        for state in &grants {
            snapshots.push(NativeGrant::from_management(
                observer.target.clone(), state.snapshot().unwrap(), Vec::new(),
            ).map_err(|_| Error::with_message(Errno::EINVAL, "invalid initial CPU binding"))?);
        }
        // All allocation precedes the owner lock. Membership serialization
        // excludes replacing the owner while the bounded grants are installed.
        let _membership = CgroupMembership::write_lock();
        if !Arc::ptr_eq(&observer.node.controller().cpu.read().get(), &observer.owner) {
            return_errno_with_message!(Errno::ESTALE, "initial CPU owner was replaced")
        }
        {
            let control = observer.owner.inner.as_ref().unwrap().control()?;
            let mut state = control.max.lock();
            if state.is_detached || state.trusted_management.is_some()
                || state.native.as_ref().is_none_or(|native| native.is_fenced())
            {
                return_errno_with_message!(Errno::ESTALE, "initial CPU management is closed")
            }
            if state.max.quota_ns() != MAX_INITIAL_CAP_NS || state.max.period_ns() != CPU_PERIOD_NS {
                return_errno_with_message!(Errno::EINVAL, "initial recovery requires the prebound CPU limit")
            }
            state.trusted_management = Some(TrustedCpuManagement {
                grants, manager_expires_ns: expires_ns, restore_cap_ns: state.max.quota_ns(),
                manager_closed: ManagerClosure::Open, budget_cause: BudgetCause::Bootstrap,
                recovery_consumed: false, watchdog: WatchdogState::new(),
            });
        }
        drop(_membership);
        let recovery = snapshots.pop().unwrap();
        let manager = snapshots.pop().unwrap();
        Ok([
            Arc::new(Self { observer: observer.clone(), grant: manager, index: 0, issued_ns, expires_ns }),
            Arc::new(Self { observer, grant: recovery, index: 1, issued_ns, expires_ns: recovery_expires_ns }),
        ])
    }

    pub(crate) fn grant(&self) -> NativeGrant {
        self.grant.clone()
    }

    pub(crate) fn publisher(&self) -> PublisherId {
        self.grant.principal()
    }

    pub(crate) fn read_usage(&self) -> core::result::Result<UsageSnapshot, CpuUsageError> {
        if ostd::cpu::all_cpus().count() != 1 {
            return Err(CpuUsageError::UnsupportedProfile);
        }
        crate::sched::with_current_cpu_bandwidth_settled(|now| self.read_usage_at(now))
    }

    fn read_usage_at(&self, now: Option<u64>) -> core::result::Result<UsageSnapshot, CpuUsageError> {
        let now = now.ok_or(CpuUsageError::ClockUnavailable)?;
        if now < self.issued_ns { return Err(CpuUsageError::Indeterminate); }
        if now >= self.expires_ns { return Err(CpuUsageError::Expired); }
        let current = self.observer.node.controller().cpu.read();
        if !Arc::ptr_eq(&current.get(), &self.observer.owner) {
            return Err(CpuUsageError::Closed);
        }
        let control = self.observer.owner.inner.as_ref().and_then(|cpu| cpu.control.as_ref())
            .ok_or(CpuUsageError::Closed)?;
        let mut state = control.max.lock();
        state.trusted_management.as_ref().ok_or(CpuUsageError::Closed)?
            .recovery_phase(self.index, now).map_err(|status| match status {
                DeliveryStatus::Revoked => CpuUsageError::Expired,
                _ => CpuUsageError::Indeterminate,
            })?;
        state.sample_usage(now)
    }

    /// Only the associated canonical delegation is closed; saved results,
    /// the workload quota and the other recovery delegation are preserved.
    /// Call after releasing Process, TaskSet and VMAR locks.
    pub(crate) fn revoke(&self) {
        if ostd::cpu::all_cpus().count() == 1 {
            crate::sched::with_current_cpu_bandwidth_settled(|now| self.revoke_at(now));
        } else {
            self.revoke_at(None);
        }
    }

    fn revoke_at(&self, now: Option<u64>) {
        if let Some(control) = self.observer.owner.inner.as_ref().and_then(|cpu| cpu.control.as_ref()) {
            let mut state = control.max.lock();
            let reliable_cut = now.filter(|cut| *cut >= self.issued_ns && *cut >= state.max.last_observed_ns);
            if let Some(policy) = state.trusted_management.as_mut() {
                if self.index == 0 && !policy.grants[0].is_revoked() {
                    policy.manager_closed = match reliable_cut {
                        Some(cut) => ManagerClosure::At(cut),
                        None => ManagerClosure::ClockUnavailable,
                    };
                }
                policy.grants[self.index].revoke();
            }
        }
    }

    pub(crate) fn execute<B: LockBackend>(
        &self,
        core: &ControlCoreWith<B>,
        token: &ReserveTokenWith<B>,
    ) -> core::result::Result<DeliveryObservation, DeliveryError> {
        core.execute_native_reserved::<SubController<CpuController>, _>(
            token, self.publisher(), |execution| self.apply(execution),
        )
    }

    fn apply(&self, execution: NativeExecution<'_, SubController<CpuController>>) -> PublishOutcome {
        let failure = |status| PublishOutcome::Failure { status };
        if ostd::cpu::all_cpus().count() != 1 {
            return failure(DeliveryStatus::Indeterminate);
        }
        crate::sched::with_current_cpu_bandwidth_settled(|now| self.apply_at(execution, now))
    }

    /// Production callers have settled the local runqueue with IRQs disabled.
    /// Ktests use the same owner checks with explicit clock-cut fixtures.
    fn apply_at(
        &self,
        execution: NativeExecution<'_, SubController<CpuController>>,
        now: Option<u64>,
    ) -> PublishOutcome {
        let failure = |status| PublishOutcome::Failure { status };
        let Some(now) = now else { return failure(DeliveryStatus::Indeterminate); };
        if now < self.issued_ns {
            return failure(DeliveryStatus::Indeterminate);
        }
        if now >= self.expires_ns {
            return failure(DeliveryStatus::Revoked);
        }
        let current = self.observer.node.controller().cpu.read();
        if !Arc::ptr_eq(&current.get(), &self.observer.owner)
            || !core::ptr::eq(execution.owner(), self.observer.owner.as_ref())
        {
            return failure(DeliveryStatus::Revoked);
        }
        let Some(control) = execution.owner().inner.as_ref().and_then(|cpu| cpu.control.as_ref()) else {
            return failure(DeliveryStatus::Revoked);
        };
        let mut state = control.max.lock();
        state.apply_trusted(self.index, execution, now)
    }
}

#[cfg(ktest)]
mod tests;

impl CpuBandwidthState {
    fn apply_trusted(
        &mut self,
        index: usize,
        execution: NativeExecution<'_, SubController<CpuController>>,
        now: u64,
    ) -> PublishOutcome {
        let failure = |status| PublishOutcome::Failure { status };
        if self.is_detached {
            return failure(DeliveryStatus::Revoked);
        }
        let Some(snapshot) = execution.management_snapshot() else {
            return failure(DeliveryStatus::PermissionDenied);
        };
        let Some(policy) = self.trusted_management.as_ref() else {
            return failure(DeliveryStatus::Revoked);
        };
        if !execution.ancestor_epochs().is_empty() {
            return failure(DeliveryStatus::PermissionDenied);
        }
        if let Err(error) = policy.grants[index].check(snapshot, execution.binding(), now) {
            return failure(error.delivery_status());
        }
        let recovering = match policy.recovery_phase(index, now) {
            Ok(recovering) => recovering,
            Err(status) => return failure(status),
        };
        if recovering && !policy.recovery_budget_allowed(self.max.quota_ns(), execution.binding().cap_ns) {
            return failure(DeliveryStatus::PermissionDenied);
        }
        let usage = match self.sample_usage(now) {
            Ok(usage) => usage,
            Err(CpuUsageError::Unbound | CpuUsageError::Closed | CpuUsageError::Expired) => {
                return failure(DeliveryStatus::Revoked);
            }
            Err(_) => return failure(DeliveryStatus::Indeterminate),
        };
        let update = NativeResourceUpdate::from(execution.binding());
        let native = self.native.as_mut().unwrap();
        let max = &mut self.max;
        let policy = self.trusted_management.as_mut().unwrap();
        match native.apply(update, now, usage.window_consumed_ns, &mut || {
            max.reconfigure_native(update.cap_ns, now);
            policy.applied(index, update.cap_ns, recovering);
        }) {
            Ok(receipt) => receipt.into_publish_outcome(),
            Err(error) => failure(error.delivery_status()),
        }
    }
}
