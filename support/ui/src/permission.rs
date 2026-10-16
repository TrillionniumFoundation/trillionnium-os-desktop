//! Consumer-side permission observations for the desktop shell.
//!
//! A05 owns authenticated process identity, workspace/trust-domain scope,
//! portal prompts and grant lifetime.  This module deliberately models only
//! the state that a UI may safely consume after an authoritative observation
//! has crossed that boundary.  It does not issue a request, mint a grant,
//! persist a capability or define an on-wire representation.

use std::collections::BTreeMap;

/// User-facing capabilities whose access must be observed from the trusted
/// portal/session owner.  A missing observation is never treated as allowed.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub enum PermissionKind {
    FileSelection,
    Clipboard,
    DragAndDrop,
    Screenshot,
    ScreenShare,
    Microphone,
    Camera,
    Notifications,
    GlobalKeyboard,
}

/// A decision observed from the trusted owner.
///
/// Every value, including `Granted`, is subject to the observation revision.
/// The UI must not infer a decision from assistant text, a local workspace
/// label or the fact that an application is running.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PermissionDecision {
    Unknown,
    Denied,
    Granted,
    Revoked,
    Expired,
}

impl PermissionDecision {
    /// Only an explicit current grant can authorize a UI action.
    pub const fn allows(self) -> bool {
        matches!(self, Self::Granted)
    }
}

/// An opaque monotonic revision supplied by the trusted owner alongside a
/// decision.  It is intentionally not a grant token or an authentication
/// credential.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PermissionObservation {
    decision: PermissionDecision,
    revision: u64,
}

impl PermissionObservation {
    /// Construct an observation.  Revision zero is reserved for "no
    /// observation" and is rejected so a fabricated default cannot authorize
    /// an action.
    pub const fn new(decision: PermissionDecision, revision: u64) -> Option<Self> {
        if revision == 0 {
            None
        } else {
            Some(Self { decision, revision })
        }
    }

    pub const fn decision(self) -> PermissionDecision {
        self.decision
    }

    pub const fn revision(self) -> u64 {
        self.revision
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PermissionObservationError {
    InvalidRevision,
    StaleRevision,
    ConflictingRevision,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PermissionObservationUpdate {
    Inserted,
    Updated,
    Unchanged,
}

/// A UI cache of the latest observation per capability.
///
/// The cache has no method that changes an observation based on a local user
/// action.  A portal implementation can feed an observation through
/// [`Self::observe`]; until then all capabilities remain `Unknown` and are
/// denied by [`Self::allows`].
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct PermissionState {
    observations: BTreeMap<PermissionKind, PermissionObservation>,
}

impl PermissionState {
    pub const fn new() -> Self {
        Self {
            observations: BTreeMap::new(),
        }
    }

    /// Apply an observation from the trusted owner.
    ///
    /// Revisions are compared per capability.  Older observations cannot
    /// resurrect a revoked or expired capability, and two different
    /// decisions with one revision are rejected as an ambiguous stream.
    pub fn observe(
        &mut self,
        kind: PermissionKind,
        decision: PermissionDecision,
        revision: u64,
    ) -> Result<PermissionObservationUpdate, PermissionObservationError> {
        let incoming = PermissionObservation::new(decision, revision)
            .ok_or(PermissionObservationError::InvalidRevision)?;

        match self.observations.get(&kind).copied() {
            None => {
                self.observations.insert(kind, incoming);
                Ok(PermissionObservationUpdate::Inserted)
            }
            Some(current) if revision < current.revision => {
                Err(PermissionObservationError::StaleRevision)
            }
            Some(current) if revision == current.revision && decision == current.decision => {
                Ok(PermissionObservationUpdate::Unchanged)
            }
            Some(current) if revision == current.revision => {
                debug_assert_ne!(current.decision, decision);
                Err(PermissionObservationError::ConflictingRevision)
            }
            Some(_) => {
                self.observations.insert(kind, incoming);
                Ok(PermissionObservationUpdate::Updated)
            }
        }
    }

    /// Return the latest observation, if one has been received.
    pub fn observation(&self, kind: PermissionKind) -> Option<PermissionObservation> {
        self.observations.get(&kind).copied()
    }

    /// Return the latest decision, defaulting to `Unknown` when no trusted
    /// observation exists.
    pub fn decision(&self, kind: PermissionKind) -> PermissionDecision {
        self.observation(kind)
            .map(PermissionObservation::decision)
            .unwrap_or(PermissionDecision::Unknown)
    }

    /// Whether the shell may proceed with a capability-dependent action.
    pub fn allows(&self, kind: PermissionKind) -> bool {
        self.decision(kind).allows()
    }

    /// Local UI code cannot grant access.  It must hand this outcome to the
    /// A05 portal/session integration once that owner exists.
    pub fn request(&self, kind: PermissionKind) -> PermissionRequest {
        PermissionRequest::NeedsAuthoritativePortal {
            kind,
            current: self.decision(kind),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PermissionRequest {
    NeedsAuthoritativePortal {
        kind: PermissionKind,
        current: PermissionDecision,
    },
}

#[cfg(test)]
mod tests {
    use super::*;

    const ALL_KINDS: [PermissionKind; 9] = [
        PermissionKind::FileSelection,
        PermissionKind::Clipboard,
        PermissionKind::DragAndDrop,
        PermissionKind::Screenshot,
        PermissionKind::ScreenShare,
        PermissionKind::Microphone,
        PermissionKind::Camera,
        PermissionKind::Notifications,
        PermissionKind::GlobalKeyboard,
    ];

    #[test]
    fn empty_state_is_unknown_and_denied_for_every_capability() {
        let state = PermissionState::new();
        for kind in ALL_KINDS {
            assert_eq!(state.decision(kind), PermissionDecision::Unknown);
            assert!(!state.allows(kind));
        }
    }

    #[test]
    fn zero_revision_cannot_be_constructed_or_observed() {
        assert_eq!(
            PermissionObservation::new(PermissionDecision::Granted, 0),
            None
        );
        let mut state = PermissionState::new();
        assert_eq!(
            state.observe(PermissionKind::Clipboard, PermissionDecision::Granted, 0),
            Err(PermissionObservationError::InvalidRevision)
        );
        assert_eq!(
            state.decision(PermissionKind::Clipboard),
            PermissionDecision::Unknown
        );
    }

    #[test]
    fn local_request_does_not_promote_unknown_to_granted() {
        let state = PermissionState::new();
        assert_eq!(
            state.request(PermissionKind::ScreenShare),
            PermissionRequest::NeedsAuthoritativePortal {
                kind: PermissionKind::ScreenShare,
                current: PermissionDecision::Unknown,
            }
        );
        assert!(!state.allows(PermissionKind::ScreenShare));
    }

    #[test]
    fn stale_grant_cannot_resurrect_revoked_capability() {
        let mut state = PermissionState::new();
        assert_eq!(
            state.observe(PermissionKind::Microphone, PermissionDecision::Granted, 4),
            Ok(PermissionObservationUpdate::Inserted)
        );
        assert_eq!(
            state.observe(PermissionKind::Microphone, PermissionDecision::Revoked, 5),
            Ok(PermissionObservationUpdate::Updated)
        );
        assert!(!state.allows(PermissionKind::Microphone));
        assert_eq!(
            state.observe(PermissionKind::Microphone, PermissionDecision::Granted, 4),
            Err(PermissionObservationError::StaleRevision)
        );
        assert_eq!(
            state.decision(PermissionKind::Microphone),
            PermissionDecision::Revoked
        );
    }

    #[test]
    fn conflicting_decisions_with_one_revision_are_rejected() {
        let mut state = PermissionState::new();
        assert_eq!(
            state.observe(PermissionKind::Camera, PermissionDecision::Denied, 9),
            Ok(PermissionObservationUpdate::Inserted)
        );
        assert_eq!(
            state.observe(PermissionKind::Camera, PermissionDecision::Granted, 9),
            Err(PermissionObservationError::ConflictingRevision)
        );
        assert_eq!(
            state.decision(PermissionKind::Camera),
            PermissionDecision::Denied
        );
    }

    #[test]
    fn same_observation_is_idempotent() {
        let mut state = PermissionState::new();
        assert_eq!(
            state.observe(
                PermissionKind::Notifications,
                PermissionDecision::Granted,
                2
            ),
            Ok(PermissionObservationUpdate::Inserted)
        );
        assert_eq!(
            state.observe(
                PermissionKind::Notifications,
                PermissionDecision::Granted,
                2
            ),
            Ok(PermissionObservationUpdate::Unchanged)
        );
        assert!(state.allows(PermissionKind::Notifications));
    }

    #[test]
    fn unknown_observation_is_not_an_implicit_grant() {
        let mut state = PermissionState::new();
        state
            .observe(
                PermissionKind::GlobalKeyboard,
                PermissionDecision::Unknown,
                1,
            )
            .unwrap();
        assert!(!state.allows(PermissionKind::GlobalKeyboard));
        state
            .observe(
                PermissionKind::GlobalKeyboard,
                PermissionDecision::Granted,
                2,
            )
            .unwrap();
        assert!(state.allows(PermissionKind::GlobalKeyboard));
        state
            .observe(
                PermissionKind::GlobalKeyboard,
                PermissionDecision::Expired,
                3,
            )
            .unwrap();
        assert!(!state.allows(PermissionKind::GlobalKeyboard));
    }
}
