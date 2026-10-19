// SPDX-License-Identifier: MPL-2.0

//! Shared metadata for the actual cgroup CPU bandwidth owner.
//!
//! `CpuControl::max` protects this state with its existing IRQ-disabling lock.
//! Binding and detachment follow membership -> bandwidth lock order. There is
//! no grant, delivery namespace or second resource ledger here.

use alloc::sync::Arc;

use aster_systree::{Error, Result};
use os_control::{
    CPU_PERIOD_NS, NativeResourceError, NativeResourceState, NativeTarget, ResourceDomainId,
    StableObjectId, UsageSnapshot,
};

use super::{
    super::{Controller, SubController},
    CpuController, CpuMax,
    max_config::CpuMaxConfig,
};
use crate::fs::cgroupfs::CgroupMembership;

pub(super) struct CpuBandwidthState {
    pub(super) max: CpuMax,
    native: Option<NativeResourceState>,
    // An unbound old Arc must not become bindable after replacement or deletion.
    is_detached: bool,
}

/// Internal observation failures; this is not a new public HOS2 operation.
#[derive(Debug, Eq, PartialEq)]
pub(super) enum CpuUsageError {
    Unbound,
    Closed,
    Indeterminate,
    ClockUnavailable,
    UnsupportedProfile,
    InconsistentAccounting,
}

impl CpuBandwidthState {
    pub(super) fn new(max: CpuMax) -> Self {
        Self {
            max,
            native: None,
            is_detached: false,
        }
    }

    pub(super) fn reconfigure(&mut self, config: CpuMaxConfig, now: u64) -> Result<()> {
        if self.is_detached {
            return Err(Error::IsDead);
        }
        let next_period = config.period_usec.unwrap_or(self.max.period_usec);
        let mutation_fn = &mut || self.max.reconfigure(config.quota_usec, next_period, now);
        if let Some(native) = &mut self.native {
            native
                .apply_owner_configuration(mutation_fn)
                .map_err(configuration_error)?;
        } else {
            mutation_fn();
        }
        Ok(())
    }

    /// Applies Linux configuration after the original local running settlement.
    pub(super) fn reconfigure_at(&mut self, config: CpuMaxConfig, now: Option<u64>) -> Result<()> {
        if self.is_detached {
            return Err(Error::IsDead);
        }
        let now = match now {
            Some(now) if now >= self.max.last_observed_ns || ostd::cpu::all_cpus().count() != 1 => {
                now
            }
            _ => {
                // In N0, local IRQ exclusion makes an older owner observation
                // a real rollback. SMP lock arrival order alone cannot prove
                // that; the shared CpuMax instead preserves its high-water cut.
                self.max.accounting_fault = true;
                // Removing a Linux limit remains available for local recovery.
                // Retain the endpoint and fault; do not manufacture a current
                // native receipt or successful usage observation.
                self.max.last_observed_ns
            }
        };
        if self.max.accounting_fault && config.quota_usec != u64::MAX {
            return Err(Error::ResourceUnavailable);
        }
        self.reconfigure(config, now)
    }

    /// Copies one revision and the actual settled owner accounting under its lock.
    ///
    /// The caller has settled the local scheduler through this exact endpoint
    /// and has established the single-CPU N0 profile. No userspace copy occurs.
    fn sample_usage(&mut self, now: u64) -> core::result::Result<UsageSnapshot, CpuUsageError> {
        let native = self.native.as_ref().ok_or(CpuUsageError::Unbound)?;
        if native.is_indeterminate() {
            return Err(CpuUsageError::Indeterminate);
        }
        if self.is_detached || native.is_invalidated() {
            return Err(CpuUsageError::Closed);
        }
        let max = &mut self.max;
        if now < max.last_observed_ns {
            max.accounting_fault = true;
        }
        if max.accounting_fault {
            return Err(CpuUsageError::InconsistentAccounting);
        }
        if max.period_ns() != CPU_PERIOD_NS
            || max.quota_usec > CPU_PERIOD_NS / 1_000
            || !max
                .native_window_valid_from_ns
                .is_some_and(|start| now >= start)
        {
            return Err(CpuUsageError::UnsupportedProfile);
        }
        max.advance(now);
        let Some(elapsed) = now.checked_sub(max.window_start_ns) else {
            max.accounting_fault = true;
            return Err(CpuUsageError::InconsistentAccounting);
        };
        if max.used_ns > elapsed
            || max.used_ns > max.cumulative_ns
            || max.cumulative_ns > now
            || max.cumulative_ns - max.used_ns > max.window_start_ns
        {
            max.accounting_fault = true;
            return Err(CpuUsageError::InconsistentAccounting);
        }
        Ok(UsageSnapshot {
            stable_object_id: native.stable_object_id(),
            revision: native.revision(),
            sample_boottime_ns: now,
            cumulative_cpu_ns: max.cumulative_ns,
            window_start_ns: max.window_start_ns,
            window_consumed_ns: max.used_ns,
            active_cap_ns: CpuMax::us_to_ns(max.quota_usec),
            active_period_ns: max.period_ns(),
            // This slice has no native event producer or explicit pause owner.
            // Configuration revisions and timer ticks are not event sequences.
            event_sequence: 0,
            dropped_events: 0,
            user_paused: false,
        })
    }

    pub(super) fn detach(&mut self) {
        self.is_detached = true;
        if let Some(native) = &mut self.native {
            native.invalidate();
        }
    }
}

fn configuration_error(error: NativeResourceError) -> Error {
    match error {
        NativeResourceError::Overflow => Error::Overflow,
        NativeResourceError::Invalidated => Error::IsDead,
        NativeResourceError::Indeterminate => Error::ResourceUnavailable,
        _ => Error::InvalidOperation,
    }
}

impl Controller {
    /// Observes a bound current incarnation after its actual local settlement.
    ///
    /// This private G1-b seam does not authenticate or grant observation rights.
    /// G1-c must supply trusted admission before any native syscall can use it.
    #[cfg_attr(not(ktest), expect(dead_code))]
    fn read_native_cpu_usage_for_owner(
        &self,
        owner: &Arc<SubController<CpuController>>,
    ) -> core::result::Result<UsageSnapshot, CpuUsageError> {
        if ostd::cpu::all_cpus().count() != 1 {
            return Err(CpuUsageError::UnsupportedProfile);
        }
        crate::sched::with_current_cpu_bandwidth_settled(|now| {
            let now = now.ok_or(CpuUsageError::ClockUnavailable)?;
            // Local IRQ exclusion serializes N0 publication with this check and
            // the owner snapshot. This is not a remote-CPU rendezvous.
            let current = self.cpu.read();
            if !Arc::ptr_eq(&current.get(), owner) {
                return Err(CpuUsageError::Closed);
            }
            let control = owner
                .inner
                .as_ref()
                .ok_or(CpuUsageError::Closed)?
                .control
                .as_ref()
                .ok_or(CpuUsageError::UnsupportedProfile)?;
            control.max.lock().sample_usage(now)
        })
    }

    /// Binds trusted identities once to the currently installed, active CPU owner.
    ///
    /// The membership writer excludes replacement and deletion until metadata
    /// installation completes. Production bootstrap does not call this seam yet.
    #[cfg_attr(not(ktest), expect(dead_code))]
    fn bind_native_cpu_once_for_owner(
        &self,
        owner: &Arc<SubController<CpuController>>,
        id: ResourceDomainId,
        stable_object_id: StableObjectId,
        _membership: &mut CgroupMembership,
    ) -> Result<NativeTarget> {
        if !Arc::ptr_eq(&self.cpu.read().get(), owner) {
            return Err(Error::IsDead);
        }
        let control = owner.inner.as_ref().ok_or(Error::IsDead)?.control()?;
        let metadata =
            NativeResourceState::new(id, stable_object_id).map_err(configuration_error)?;
        let target = NativeTarget::from_owner(owner.clone(), id, stable_object_id)
            .map_err(|_| Error::InvalidOperation)?;
        let mut state = control.max.lock();
        if state.is_detached {
            return Err(Error::IsDead);
        }
        if state.native.is_some() {
            return Err(Error::AlreadyExists);
        }
        state.native = Some(metadata);
        Ok(target)
    }
}

#[cfg(ktest)]
mod tests;

#[cfg(ktest)]
mod usage_tests;
