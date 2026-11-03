//! Management-delegation state for embedding in an existing resource owner.
//!
//! This module has no locks, registry, budget, runtime counter or durable
//! ledger. The owner must access it under the same mutation lock used for
//! resource admission and effects. Constructors receive trusted resolver
//! values; they do not authenticate a publisher or establish a kernel lease.

use alloc::sync::Arc;

use crate::{
    DeliveryStatus, ManagementGrantId, PublisherId, RequestBinding, ResourceDomainId,
    StableObjectId, CPU_PERIOD_NS,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ManagementGrantConfig {
    pub id: ManagementGrantId,
    pub publisher: PublisherId,
    pub target: ResourceDomainId,
    pub stable_object_id: StableObjectId,
    pub epoch: u64,
    pub issued_at_ns: u64,
    pub expires_at_ns: u64,
    pub max_cap_ns: u64,
}

/// Immutable authority terms captured before reserving a delivery.
/// Clones remain snapshots and never become current rights by themselves.
/// The private origin tag also prevents a new state with identical public
/// configuration from accepting an earlier delegation's saved snapshot.
#[derive(Clone, Debug)]
pub struct ManagementGrantSnapshot {
    config: ManagementGrantConfig,
    origin: Arc<()>,
}

impl PartialEq for ManagementGrantSnapshot {
    fn eq(&self, other: &Self) -> bool {
        self.config == other.config && Arc::ptr_eq(&self.origin, &other.origin)
    }
}

impl Eq for ManagementGrantSnapshot {}

impl ManagementGrantSnapshot {
    pub const fn id(&self) -> ManagementGrantId {
        self.config.id
    }

    pub const fn publisher(&self) -> PublisherId {
        self.config.publisher
    }

    pub const fn target(&self) -> ResourceDomainId {
        self.config.target
    }

    pub const fn stable_object_id(&self) -> StableObjectId {
        self.config.stable_object_id
    }

    pub const fn epoch(&self) -> u64 {
        self.config.epoch
    }

    pub const fn issued_at_ns(&self) -> u64 {
        self.config.issued_at_ns
    }

    pub const fn expires_at_ns(&self) -> u64 {
        self.config.expires_at_ns
    }

    pub const fn max_cap_ns(&self) -> u64 {
        self.config.max_cap_ns
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ManagementError {
    InvalidIdentity,
    InvalidLease,
    InvalidBudget,
    Revoked,
    Expired,
    NotYetValid,
    SnapshotMismatch,
    BindingMismatch,
    CapLimit,
}

impl ManagementError {
    /// Existing HOS2 refusal status for a reserved semantic authority check.
    /// Structural errors still belong on A05's pre-reservation error path.
    pub const fn delivery_status(self) -> DeliveryStatus {
        match self {
            Self::Revoked | Self::Expired | Self::NotYetValid | Self::SnapshotMismatch => {
                DeliveryStatus::Revoked
            }
            Self::BindingMismatch | Self::CapLimit => DeliveryStatus::PermissionDenied,
            Self::InvalidIdentity | Self::InvalidLease | Self::InvalidBudget => {
                DeliveryStatus::InvalidInput
            }
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ManagementRevokeReceipt {
    pub id: ManagementGrantId,
    pub previous_epoch: u64,
    pub epoch: u64,
}

/// One management delegation, owned by the existing resource owner.
/// This state deliberately cannot be cloned into another live authority.
#[derive(Debug)]
pub struct ManagementGrantState {
    config: ManagementGrantConfig,
    revoked: Option<ManagementRevokeReceipt>,
    // Identity only: no second liveness/epoch state or authority registry.
    origin: Arc<()>,
}

impl ManagementGrantState {
    pub fn new(config: ManagementGrantConfig) -> Result<Self, ManagementError> {
        if !config.id.is_nonzero()
            || !config.publisher.is_nonzero()
            || !config.target.is_nonzero()
            || !config.stable_object_id.is_nonzero()
            || config.epoch == 0
        {
            return Err(ManagementError::InvalidIdentity);
        }
        if config.expires_at_ns <= config.issued_at_ns {
            return Err(ManagementError::InvalidLease);
        }
        if config.max_cap_ns > CPU_PERIOD_NS {
            return Err(ManagementError::InvalidBudget);
        }
        Ok(Self {
            config,
            revoked: None,
            origin: Arc::new(()),
        })
    }

    /// Capture terms, without claiming that the lease is valid at any time.
    /// A resource mutation must call check again with actual boot-clock time.
    pub fn snapshot(&self) -> Result<ManagementGrantSnapshot, ManagementError> {
        if self.is_revoked() {
            return Err(ManagementError::Revoked);
        }
        Ok(ManagementGrantSnapshot {
            config: self.config,
            origin: Arc::clone(&self.origin),
        })
    }

    /// Whether a saved snapshot came from this exact state allocation.
    ///
    /// This remains true after revocation and proves identity only, never
    /// current rights or lease validity. Existing owners use it to fence
    /// delayed lifecycle and timer work before touching a replacement state.
    /// Equal public configuration in a new state cannot satisfy this check.
    pub fn owns_snapshot(&self, snapshot: &ManagementGrantSnapshot) -> bool {
        Arc::ptr_eq(&snapshot.origin, &self.origin)
    }

    /// Revoke only the original delegation selected by a retained snapshot.
    /// The resource owner must hold its original mutation lock. An old image
    /// cannot revoke a replacement that happens to occupy the same array slot.
    /// Repeating closure of this same instance retains the first receipt.
    pub fn revoke_for_snapshot(
        &mut self,
        snapshot: &ManagementGrantSnapshot,
    ) -> Result<ManagementRevokeReceipt, ManagementError> {
        if !self.owns_snapshot(snapshot) {
            return Err(ManagementError::SnapshotMismatch);
        }
        Ok(self.revoke())
    }

    /// Check the saved delegation inside the original owner's mutation lock.
    /// The owner supplies real BOOTTIME, prevents clock rollback and settles
    /// actual runtime. This pure value does not create another clock domain.
    pub fn check(
        &self,
        snapshot: &ManagementGrantSnapshot,
        binding: RequestBinding,
        now_ns: u64,
    ) -> Result<(), ManagementError> {
        if self.is_revoked() {
            return Err(ManagementError::Revoked);
        }
        if snapshot.config != self.config || !Arc::ptr_eq(&snapshot.origin, &self.origin) {
            return Err(ManagementError::SnapshotMismatch);
        }
        if binding.publisher != self.config.publisher
            || binding.target != self.config.target
            || binding.stable_object_id != self.config.stable_object_id
            || binding.grant_epoch != self.config.epoch
            || binding.period_ns != CPU_PERIOD_NS
        {
            return Err(ManagementError::BindingMismatch);
        }
        if now_ns < self.config.issued_at_ns {
            return Err(ManagementError::NotYetValid);
        }
        if now_ns >= self.config.expires_at_ns {
            return Err(ManagementError::Expired);
        }
        if binding.cap_ns > self.config.max_cap_ns {
            return Err(ManagementError::CapLimit);
        }
        Ok(())
    }

    /// Close only this delegation. Its resource, other grants, admitted
    /// budgets and accounting are owned elsewhere and remain untouched.
    /// Repeated revocation returns the identical first receipt. At MAX the
    /// epoch saturates while revocation remains permanent and fail-closed.
    pub fn revoke(&mut self) -> ManagementRevokeReceipt {
        if let Some(receipt) = self.revoked {
            return receipt;
        }
        let receipt = ManagementRevokeReceipt {
            id: self.config.id,
            previous_epoch: self.config.epoch,
            epoch: self.config.epoch.saturating_add(1),
        };
        self.config.epoch = receipt.epoch;
        self.revoked = Some(receipt);
        receipt
    }

    pub const fn current_epoch(&self) -> u64 {
        self.config.epoch
    }

    pub const fn is_revoked(&self) -> bool {
        self.revoked.is_some()
    }
}
