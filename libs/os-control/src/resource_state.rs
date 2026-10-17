//! Resource identity and revision admission for an existing resource owner.
//!
//! This state has no lock, allocation, budget, runtime counter, grant registry,
//! or clock. Embed exactly one instance in the actual owner's mutation state
//! and use that owner's existing lock. Every configuration writer, including
//! Linux compatibility and lifecycle paths, must advance this same revision.
//! Trusted bootstrap assigns the identities; this constructor neither mints
//! credentials nor checks global identity uniqueness.

use crate::{
    DeliveryStatus, PublishOutcome, RequestBinding, ResourceDomainId, StableObjectId, CPU_PERIOD_NS,
};

/// Only the resource fields needed for a native InstallBudget mutation.
/// This carries no delivery identity, publisher, or proof of authority.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NativeResourceUpdate {
    pub target: ResourceDomainId,
    pub stable_object_id: StableObjectId,
    pub expected_revision: u64,
    pub period_ns: u64,
    pub cap_ns: u64,
}

impl From<RequestBinding> for NativeResourceUpdate {
    fn from(binding: RequestBinding) -> Self {
        Self {
            target: binding.target,
            stable_object_id: binding.stable_object_id,
            expected_revision: binding.expected_revision,
            period_ns: binding.period_ns,
            cap_ns: binding.cap_ns,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NativeResourceError {
    InvalidIdentity,
    BindingMismatch,
    InvalidRevision,
    RevisionConflict { expected: u64, actual: u64 },
    InvalidBudget,
    InconsistentAccounting,
    Invalidated,
    Indeterminate,
    Overflow,
}

impl NativeResourceError {
    /// Existing HOS2 status for a reserved mutation rejected by this state.
    /// These checks do not replace authentication or the owner's policy checks.
    pub const fn delivery_status(self) -> DeliveryStatus {
        match self {
            Self::InvalidIdentity | Self::InvalidRevision | Self::InvalidBudget => {
                DeliveryStatus::InvalidInput
            }
            Self::BindingMismatch => DeliveryStatus::PermissionDenied,
            Self::RevisionConflict { .. } => DeliveryStatus::Conflict,
            Self::Invalidated => DeliveryStatus::Revoked,
            Self::InconsistentAccounting | Self::Indeterminate => DeliveryStatus::Indeterminate,
            Self::Overflow => DeliveryStatus::ResourceExhausted,
        }
    }
}

/// A completed revision transition. The owner cannot alter these fields.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NativeRevisionChange {
    previous_revision: u64,
    revision: u64,
}

impl NativeRevisionChange {
    pub const fn previous_revision(&self) -> u64 {
        self.previous_revision
    }

    pub const fn revision(&self) -> u64 {
        self.revision
    }
}

/// A prevalidated successful native receipt, created only after mutation returns.
/// Reusing this value is not permission to perform another effect.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NativeResourceReceipt {
    stable_object_id: StableObjectId,
    change: NativeRevisionChange,
    effective_boottime_ns: u64,
    consumed_at_apply_ns: u64,
}

impl NativeResourceReceipt {
    pub const fn stable_object_id(&self) -> StableObjectId {
        self.stable_object_id
    }

    pub const fn previous_revision(&self) -> u64 {
        self.change.previous_revision
    }

    pub const fn revision(&self) -> u64 {
        self.change.revision
    }

    pub const fn effective_boottime_ns(&self) -> u64 {
        self.effective_boottime_ns
    }

    pub const fn consumed_at_apply_ns(&self) -> u64 {
        self.consumed_at_apply_ns
    }

    /// Conversion cannot fail after the resource effect has occurred.
    pub const fn into_publish_outcome(self) -> PublishOutcome {
        PublishOutcome::Success {
            stable_object_id: self.stable_object_id,
            previous_revision: self.change.previous_revision,
            saved_revision: self.change.revision,
            effective_ns: self.effective_boottime_ns,
            consumed_ns: self.consumed_at_apply_ns,
        }
    }
}

/// Canonical metadata embedded beside the real owner's sole accounting state.
/// It cannot be cloned into a second mutable revision authority.
#[derive(Debug)]
pub struct NativeResourceState {
    id: ResourceDomainId,
    stable_object_id: StableObjectId,
    revision: u64,
    fence: Option<NativeResourceFence>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum NativeResourceFence {
    Invalidated,
    Indeterminate,
}

impl NativeResourceState {
    /// Initialize a new, trusted resource instance at revision one.
    /// Replacing a live instance or resetting its revision is not supported.
    pub fn new(
        id: ResourceDomainId,
        stable_object_id: StableObjectId,
    ) -> Result<Self, NativeResourceError> {
        if !id.is_nonzero() || !stable_object_id.is_nonzero() {
            return Err(NativeResourceError::InvalidIdentity);
        }
        Ok(Self {
            id,
            stable_object_id,
            revision: 1,
            fence: None,
        })
    }

    pub const fn id(&self) -> ResourceDomainId {
        self.id
    }

    pub const fn stable_object_id(&self) -> StableObjectId {
        self.stable_object_id
    }

    pub const fn revision(&self) -> u64 {
        self.revision
    }

    pub const fn is_fenced(&self) -> bool {
        self.fence.is_some()
    }

    pub const fn is_invalidated(&self) -> bool {
        matches!(self.fence, Some(NativeResourceFence::Invalidated))
    }

    pub const fn is_indeterminate(&self) -> bool {
        matches!(self.fence, Some(NativeResourceFence::Indeterminate))
    }

    /// Permanently close a known detached or destroyed resource instance.
    ///
    /// The owner must invalidate its old metadata under the old mutation lock
    /// as part of its actual lifecycle transition, before an old pinned owner
    /// can admit another configuration. This does not perform that transition,
    /// prove hardware quiescence, revoke another grant, or change any budget,
    /// accounting, revision or saved delivery result. Repeated calls are inert.
    /// An ambiguous effect stays indeterminate rather than becoming a known
    /// lifecycle refusal. There is no reactivation API.
    pub fn invalidate(&mut self) {
        if self.fence.is_none() {
            self.fence = Some(NativeResourceFence::Invalidated);
        }
    }

    /// Validate a native update and receipt before one infallible mutation.
    ///
    /// The caller holds the actual owner's mutation lock, has already checked
    /// authority, ancestors and policy, and has settled its sole runtime state
    /// using the real boot clock. The timestamp is an input, not a new clock;
    /// this state cannot detect clock rollback or settle runtime itself.
    /// All fallible work must precede this method's callback. The callback is
    /// borrowed and called once: prepare owning captures before taking the
    /// owner lock and destroy them after unlocking, or only borrow owner fields.
    /// Explicit destruction or allocation inside the callback remains the
    /// caller's responsibility.
    ///
    /// A panic leaves a permanent indeterminate fence, including when the
    /// caller recovers a poisoned host lock. No new D may retry that effect
    /// through this state. There is deliberately no reset or recovery API.
    pub fn apply<F: FnMut() + ?Sized>(
        &mut self,
        update: NativeResourceUpdate,
        effective_ns: u64,
        consumed_ns: u64,
        mutation: &mut F,
    ) -> Result<NativeResourceReceipt, NativeResourceError> {
        self.check_active()?;
        if update.target != self.id || update.stable_object_id != self.stable_object_id {
            return Err(NativeResourceError::BindingMismatch);
        }
        if update.expected_revision == 0 || update.expected_revision == u64::MAX {
            return Err(NativeResourceError::InvalidRevision);
        }
        if update.expected_revision != self.revision {
            return Err(NativeResourceError::RevisionConflict {
                expected: update.expected_revision,
                actual: self.revision,
            });
        }
        if update.period_ns != CPU_PERIOD_NS || update.cap_ns > CPU_PERIOD_NS {
            return Err(NativeResourceError::InvalidBudget);
        }
        if consumed_ns > effective_ns % CPU_PERIOD_NS {
            return Err(NativeResourceError::InconsistentAccounting);
        }
        let change = self.next_change()?;
        // Construct the complete wire-valid outcome before entering an effect.
        let receipt = NativeResourceReceipt {
            stable_object_id: self.stable_object_id,
            change,
            effective_boottime_ns: effective_ns,
            consumed_at_apply_ns: consumed_ns,
        };
        self.mutate(change, mutation);
        Ok(receipt)
    }

    /// Advance the same revision for a trusted ordinary-owner configuration.
    ///
    /// Linux compatibility or lifecycle writes may use unlimited quota or a
    /// period other than HOS2's fixed period, so this path has no HOS2 budget
    /// assumptions and fabricates no D or publisher. The actual owner checks
    /// those inputs and its existing permissions before calling this method,
    /// under the same lock as native updates. The borrowed callback and panic
    /// fence obey the same rules as apply.
    pub fn apply_owner_configuration<F: FnMut() + ?Sized>(
        &mut self,
        mutation: &mut F,
    ) -> Result<NativeRevisionChange, NativeResourceError> {
        self.check_active()?;
        let change = self.next_change()?;
        self.mutate(change, mutation);
        Ok(change)
    }

    fn check_active(&self) -> Result<(), NativeResourceError> {
        match self.fence {
            Some(NativeResourceFence::Invalidated) => Err(NativeResourceError::Invalidated),
            Some(NativeResourceFence::Indeterminate) => Err(NativeResourceError::Indeterminate),
            None => Ok(()),
        }
    }

    fn next_change(&self) -> Result<NativeRevisionChange, NativeResourceError> {
        Ok(NativeRevisionChange {
            previous_revision: self.revision,
            revision: self
                .revision
                .checked_add(1)
                .ok_or(NativeResourceError::Overflow)?,
        })
    }

    fn mutate<F: FnMut() + ?Sized>(&mut self, change: NativeRevisionChange, mutation: &mut F) {
        // No unwinding guard clears this sentinel. An ambiguous effect cannot
        // regain admission merely because its old revision still compares equal.
        self.fence = Some(NativeResourceFence::Indeterminate);
        mutation();
        self.revision = change.revision;
        self.fence = None;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn last_native_revision_succeeds_then_every_owner_write_is_exhausted() {
        let mut state =
            NativeResourceState::new(ResourceDomainId::from_u128(1), StableObjectId::from_u128(2))
                .unwrap();
        // A private unit setup exercises exhaustion without exposing revision
        // restoration or reset to adapters.
        state.revision = u64::MAX - 1;
        let update = NativeResourceUpdate {
            target: state.id(),
            stable_object_id: state.stable_object_id(),
            expected_revision: u64::MAX - 1,
            period_ns: CPU_PERIOD_NS,
            cap_ns: 0,
        };
        let mut effects = 0;
        let receipt = state.apply(update, 0, 0, &mut || effects += 1).unwrap();
        assert_eq!(receipt.previous_revision(), u64::MAX - 1);
        assert_eq!(receipt.revision(), u64::MAX);
        assert_eq!(state.revision(), u64::MAX);
        assert!(!state.is_fenced());
        assert_eq!(
            state.apply_owner_configuration(&mut || effects += 1),
            Err(NativeResourceError::Overflow)
        );
        assert_eq!(effects, 1);
        assert_eq!(state.revision(), u64::MAX);
        assert!(!state.is_fenced());
    }

    #[test]
    fn max_expected_revision_is_invalid_before_any_callback() {
        let mut state =
            NativeResourceState::new(ResourceDomainId::from_u128(1), StableObjectId::from_u128(2))
                .unwrap();
        let update = NativeResourceUpdate {
            target: state.id(),
            stable_object_id: state.stable_object_id(),
            expected_revision: u64::MAX,
            period_ns: CPU_PERIOD_NS,
            cap_ns: 0,
        };
        let mut effects = 0;
        assert_eq!(
            state.apply(update, 0, 0, &mut || effects += 1),
            Err(NativeResourceError::InvalidRevision)
        );
        assert_eq!(effects, 0);
        assert_eq!(state.revision(), 1);
        assert!(!state.is_fenced());
    }
}
