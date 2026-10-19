// SPDX-License-Identifier: MPL-2.0

//! Shared metadata for the actual cgroup CPU bandwidth owner.
//!
//! `CpuControl::max` protects this state with its existing IRQ-disabling lock.
//! Binding and detachment follow membership -> bandwidth lock order. There is
//! no native execution, clock conversion, grant or delivery namespace here.

use alloc::sync::Arc;

use aster_systree::{Error, Result};
use os_control::{
    NativeResourceError, NativeResourceState, NativeTarget, ResourceDomainId, StableObjectId,
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
