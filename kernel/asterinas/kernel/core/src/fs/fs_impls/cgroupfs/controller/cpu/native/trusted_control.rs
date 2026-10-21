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

pub(crate) const MAX_INITIAL_CAP_NS: u64 = 50_000_000;
pub(crate) const INITIAL_LEASE_NS: u64 = 300_000_000_000;

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
        let make_state = |publisher: PublisherId| {
            ManagementGrantState::new(ManagementGrantConfig {
                id: ManagementGrantId::new(publisher.bytes()),
                publisher,
                target: observer.target.id(),
                stable_object_id: observer.target.stable_object_id(),
                epoch: 1,
                issued_at_ns: issued_ns,
                expires_at_ns: expires_ns,
                max_cap_ns: MAX_INITIAL_CAP_NS,
            }).map_err(|_| Error::with_message(Errno::EINVAL, "invalid initial delegation"))
        };
        let grants = [make_state(publishers[0])?, make_state(publishers[1])?];
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
            state.trusted_management = Some(grants);
        }
        drop(_membership);
        let recovery = snapshots.pop().unwrap();
        let manager = snapshots.pop().unwrap();
        Ok([
            Arc::new(Self { observer: observer.clone(), grant: manager, index: 0, issued_ns, expires_ns }),
            Arc::new(Self { observer, grant: recovery, index: 1, issued_ns, expires_ns }),
        ])
    }

    pub(crate) fn grant(&self) -> NativeGrant {
        self.grant.clone()
    }

    pub(crate) fn publisher(&self) -> PublisherId {
        self.grant.principal()
    }

    pub(crate) fn read_usage(&self) -> core::result::Result<UsageSnapshot, CpuUsageError> {
        self.observer.read_usage_during(self.issued_ns, self.expires_ns)
    }

    /// Only the associated canonical delegation is closed; saved results,
    /// the workload quota and the other recovery delegation are preserved.
    /// Call after releasing Process, TaskSet and VMAR locks.
    pub(crate) fn revoke(&self) {
        if let Some(control) = self.observer.owner.inner.as_ref().and_then(|cpu| cpu.control.as_ref()) {
            let mut state = control.max.lock();
            if let Some(grants) = state.trusted_management.as_mut() {
                grants[self.index].revoke();
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
        let Some(grants) = self.trusted_management.as_ref() else {
            return failure(DeliveryStatus::Revoked);
        };
        if !execution.ancestor_epochs().is_empty() {
            return failure(DeliveryStatus::PermissionDenied);
        }
        if let Err(error) = grants[index].check(snapshot, execution.binding(), now) {
            return failure(error.delivery_status());
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
        match native.apply(update, now, usage.window_consumed_ns, &mut || {
            max.reconfigure_native(update.cap_ns, now);
        }) {
            Ok(receipt) => receipt.into_publish_outcome(),
            Err(error) => failure(error.delivery_status()),
        }
    }
}
