//! Consumer-side permission observations for the desktop shell.
//!
//! A05 owns authenticated process identity, workspace/trust-domain scope,
//! portal prompts and grant lifetime.  This module deliberately models only
//! the state that a UI may safely consume after an authoritative observation
//! has crossed that boundary.  It does not issue a request, mint a grant,
//! persist a capability or define an on-wire representation.

use std::collections::BTreeMap;

/// Bound the consumer-only cache. Exhaustion never silently evicts previous
/// grants or revocations, and must never imply authorization success.
pub const MAX_PERMISSION_OBSERVATIONS: usize = 1024;

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

/// Opaque scope supplied by the trusted A05 owner.
///
/// The shell never derives this value from a workspace label, PID, UID or
/// assistant message. It only uses the value to keep observations from one
/// owner/workspace/trust-domain scope from authorizing another scope.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct PermissionScopeId(u128);

impl PermissionScopeId {
    /// Construct a scope identifier. Zero is reserved for "no trusted
    /// scope" and cannot be used to authorize an action.
    pub const fn new(value: u128) -> Option<Self> {
        if value == 0 {
            None
        } else {
            Some(Self(value))
        }
    }

    pub const fn get(self) -> u128 {
        self.0
    }
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
/// decision. It is intentionally not a grant token or an authentication
/// credential.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PermissionObservation {
    decision: PermissionDecision,
    revision: u64,
}

impl PermissionObservation {
    /// Construct an observation. Revision zero is reserved for "no
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
    CapacityExceeded,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PermissionObservationUpdate {
    Inserted,
    Updated,
    Unchanged,
}

/// A UI cache of the latest observation per capability and trusted scope.
///
/// Scope is an opaque owner-supplied identity. Requiring it at every lookup
/// makes cross-workspace reuse impossible by construction. The cache has no
/// method that changes an observation based on a local user action. A portal
/// implementation can feed an observation through [`Self::observe`]; until
/// then all capabilities remain `Unknown` and are denied by [`Self::allows`].
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct PermissionState {
    observations: BTreeMap<(PermissionScopeId, PermissionKind), PermissionObservation>,
}

impl PermissionState {
    pub const fn new() -> Self {
        Self {
            observations: BTreeMap::new(),
        }
    }

    /// Apply an observation from the trusted owner.
    ///
    /// Revisions are compared per scope and capability. Older observations
    /// cannot resurrect a revoked or expired capability, and two different
    /// decisions with one revision are rejected as an ambiguous stream.
    pub fn observe(
        &mut self,
        scope: PermissionScopeId,
        kind: PermissionKind,
        decision: PermissionDecision,
        revision: u64,
    ) -> Result<PermissionObservationUpdate, PermissionObservationError> {
        let incoming = PermissionObservation::new(decision, revision)
            .ok_or(PermissionObservationError::InvalidRevision)?;

        match self.observations.get(&(scope, kind)).copied() {
            None => {
                if self.observations.len() >= MAX_PERMISSION_OBSERVATIONS {
                    return Err(PermissionObservationError::CapacityExceeded);
                }
                self.observations.insert((scope, kind), incoming);
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
                // A previously granted permission cannot remain usable after
                // two contradictory claims at the SAME owner revision.
                // Poison this cache entry to Unknown. Neither replay of the
                // old grant nor the conflicting decision can restore access
                // without a strictly newer authenticated observation.
                self.observations.insert(
                    (scope, kind),
                    PermissionObservation {
                        decision: PermissionDecision::Unknown,
                        revision,
                    },
                );
                Err(PermissionObservationError::ConflictingRevision)
            }
            Some(_) => {
                self.observations.insert((scope, kind), incoming);
                Ok(PermissionObservationUpdate::Updated)
            }
        }
    }

    /// Invalidate cached decisions when the authoritative stream is lost.
    /// Preserve revision tombstones so a replay of a pre-disconnect grant
    /// cannot be accepted as a newly observed authorization. This is a local
    /// UI guard, NOT a revoke or owner-authentication protocol.
    pub fn invalidate_all(&mut self) {
        for observation in self.observations.values_mut() {
            observation.decision = PermissionDecision::Unknown;
        }
    }

    /// Invalidate only one owner's scope, preserving its last revision.
    /// To reset owner generations, the future trusted A05 bridge must create
    /// a NEW consumer cache after identity/revision reconciliation.
    pub fn invalidate_scope(&mut self, scope: PermissionScopeId) {
        for ((observed_scope, _), observation) in &mut self.observations {
            if *observed_scope == scope {
                observation.decision = PermissionDecision::Unknown;
            }
        }
    }

    /// Return the latest observation, if one has been received for this
    /// trusted scope and capability.
    pub fn observation(
        &self,
        scope: PermissionScopeId,
        kind: PermissionKind,
    ) -> Option<PermissionObservation> {
        self.observations.get(&(scope, kind)).copied()
    }

    /// Return the latest decision, defaulting to `Unknown` when no trusted
    /// observation exists for this scope.
    pub fn decision(&self, scope: PermissionScopeId, kind: PermissionKind) -> PermissionDecision {
        self.observation(scope, kind)
            .map(PermissionObservation::decision)
            .unwrap_or(PermissionDecision::Unknown)
    }

    /// Whether the shell may proceed with a capability-dependent action in
    /// this trusted scope.
    pub fn allows(&self, scope: PermissionScopeId, kind: PermissionKind) -> bool {
        self.decision(scope, kind).allows()
    }

    /// Local UI code cannot grant access. It must hand this outcome to the
    /// A05 portal/session integration once that owner exists.
    pub fn request(&self, scope: PermissionScopeId, kind: PermissionKind) -> PermissionRequest {
        PermissionRequest::NeedsAuthoritativePortal {
            scope,
            kind,
            current: self.decision(scope, kind),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PermissionRequest {
    NeedsAuthoritativePortal {
        scope: PermissionScopeId,
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

    const PERSONAL: PermissionScopeId = PermissionScopeId(1);
    const WORK: PermissionScopeId = PermissionScopeId(2);

    #[test]
    fn owner_disconnect_invalidates_cached_grants() {
        let mut state = PermissionState::new();
        for scope in [PERSONAL, WORK] {
            state
                .observe(
                    scope,
                    PermissionKind::Clipboard,
                    PermissionDecision::Granted,
                    2,
                )
                .unwrap();
            assert!(state.allows(scope, PermissionKind::Clipboard));
        }
        state.invalidate_all();
        for scope in [PERSONAL, WORK] {
            assert_eq!(
                state.decision(scope, PermissionKind::Clipboard),
                PermissionDecision::Unknown
            );
            assert!(!state.allows(scope, PermissionKind::Clipboard));
        }
    }

    #[test]
    fn old_grant_cannot_resurrect_after_disconnection_invalidation() {
        let mut state = PermissionState::new();
        state
            .observe(
                PERSONAL,
                PermissionKind::Microphone,
                PermissionDecision::Granted,
                41,
            )
            .unwrap();
        state.invalidate_all();
        assert_eq!(
            state.decision(PERSONAL, PermissionKind::Microphone),
            PermissionDecision::Unknown
        );
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Microphone,
                PermissionDecision::Granted,
                41,
            ),
            Err(PermissionObservationError::ConflictingRevision)
        );
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Microphone,
                PermissionDecision::Granted,
                40,
            ),
            Err(PermissionObservationError::StaleRevision)
        );
        assert!(!state.allows(PERSONAL, PermissionKind::Microphone));
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Microphone,
                PermissionDecision::Denied,
                42,
            ),
            Ok(PermissionObservationUpdate::Updated)
        );
        assert!(!state.allows(PERSONAL, PermissionKind::Microphone));
    }

    #[test]
    fn invalidating_one_scope_does_not_clear_unrelated_grants() {
        let mut state = PermissionState::new();
        for scope in [PERSONAL, WORK] {
            state
                .observe(
                    scope,
                    PermissionKind::Camera,
                    PermissionDecision::Granted,
                    1,
                )
                .unwrap();
        }
        state.invalidate_scope(PERSONAL);
        assert!(!state.allows(PERSONAL, PermissionKind::Camera));
        assert!(state.allows(WORK, PermissionKind::Camera));
    }

    #[test]
    fn capacity_failure_never_prevents_revoking_an_existing_grant() {
        let mut state = PermissionState::new();
        for value in 1..=MAX_PERMISSION_OBSERVATIONS as u128 {
            let scope = PermissionScopeId::new(value).unwrap();
            state
                .observe(
                    scope,
                    PermissionKind::Microphone,
                    PermissionDecision::Granted,
                    1,
                )
                .unwrap();
        }
        let next = PermissionScopeId::new(MAX_PERMISSION_OBSERVATIONS as u128 + 1).unwrap();
        assert_eq!(
            state.observe(
                next,
                PermissionKind::Microphone,
                PermissionDecision::Granted,
                1,
            ),
            Err(PermissionObservationError::CapacityExceeded)
        );
        assert!(!state.allows(next, PermissionKind::Microphone));
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Microphone,
                PermissionDecision::Revoked,
                2,
            ),
            Ok(PermissionObservationUpdate::Updated)
        );
        assert!(!state.allows(PERSONAL, PermissionKind::Microphone));
    }

    #[test]
    fn zero_scope_cannot_be_constructed() {
        assert_eq!(PermissionScopeId::new(0), None);
        assert_eq!(
            PermissionScopeId::new(7).map(PermissionScopeId::get),
            Some(7)
        );
    }

    #[test]
    fn empty_state_is_unknown_and_denied_for_every_capability() {
        let state = PermissionState::new();
        for kind in ALL_KINDS {
            assert_eq!(state.decision(PERSONAL, kind), PermissionDecision::Unknown);
            assert!(!state.allows(PERSONAL, kind));
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
            state.observe(
                PERSONAL,
                PermissionKind::Clipboard,
                PermissionDecision::Granted,
                0
            ),
            Err(PermissionObservationError::InvalidRevision)
        );
        assert_eq!(
            state.decision(PERSONAL, PermissionKind::Clipboard),
            PermissionDecision::Unknown
        );
    }

    #[test]
    fn local_request_does_not_promote_unknown_to_granted() {
        let state = PermissionState::new();
        assert_eq!(
            state.request(PERSONAL, PermissionKind::ScreenShare),
            PermissionRequest::NeedsAuthoritativePortal {
                scope: PERSONAL,
                kind: PermissionKind::ScreenShare,
                current: PermissionDecision::Unknown,
            }
        );
        assert!(!state.allows(PERSONAL, PermissionKind::ScreenShare));
    }

    #[test]
    fn stale_grant_cannot_resurrect_revoked_capability() {
        let mut state = PermissionState::new();
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Microphone,
                PermissionDecision::Granted,
                4
            ),
            Ok(PermissionObservationUpdate::Inserted)
        );
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Microphone,
                PermissionDecision::Revoked,
                5
            ),
            Ok(PermissionObservationUpdate::Updated)
        );
        assert!(!state.allows(PERSONAL, PermissionKind::Microphone));
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Microphone,
                PermissionDecision::Granted,
                4
            ),
            Err(PermissionObservationError::StaleRevision)
        );
        assert_eq!(
            state.decision(PERSONAL, PermissionKind::Microphone),
            PermissionDecision::Revoked
        );
    }

    #[test]
    fn conflicting_decisions_with_one_revision_are_rejected() {
        let mut state = PermissionState::new();
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Camera,
                PermissionDecision::Denied,
                9
            ),
            Ok(PermissionObservationUpdate::Inserted)
        );
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Camera,
                PermissionDecision::Granted,
                9
            ),
            Err(PermissionObservationError::ConflictingRevision)
        );
        assert_eq!(
            state.decision(PERSONAL, PermissionKind::Camera),
            PermissionDecision::Unknown
        );
        assert!(!state.allows(PERSONAL, PermissionKind::Camera));
    }

    #[test]
    fn same_revision_conflict_poisoned_grant_cannot_replay_as_allowed() {
        let mut state = PermissionState::new();
        state
            .observe(
                PERSONAL,
                PermissionKind::ScreenShare,
                PermissionDecision::Granted,
                7,
            )
            .unwrap();
        assert!(state.allows(PERSONAL, PermissionKind::ScreenShare));

        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::ScreenShare,
                PermissionDecision::Revoked,
                7,
            ),
            Err(PermissionObservationError::ConflictingRevision)
        );
        assert_eq!(
            state.decision(PERSONAL, PermissionKind::ScreenShare),
            PermissionDecision::Unknown
        );
        assert!(!state.allows(PERSONAL, PermissionKind::ScreenShare));

        // A duplicate earlier grant at that revision must not repair the
        // conflicted observation or restore screen capture.
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::ScreenShare,
                PermissionDecision::Granted,
                7,
            ),
            Err(PermissionObservationError::ConflictingRevision)
        );
        assert!(!state.allows(PERSONAL, PermissionKind::ScreenShare));
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::ScreenShare,
                PermissionDecision::Granted,
                6,
            ),
            Err(PermissionObservationError::StaleRevision)
        );
        assert!(!state.allows(PERSONAL, PermissionKind::ScreenShare));

        // A genuinely newer owner revision may authorize the action.
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::ScreenShare,
                PermissionDecision::Granted,
                8,
            ),
            Ok(PermissionObservationUpdate::Updated)
        );
        assert!(state.allows(PERSONAL, PermissionKind::ScreenShare));
    }

    #[test]
    fn same_observation_is_idempotent() {
        let mut state = PermissionState::new();
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Notifications,
                PermissionDecision::Granted,
                2
            ),
            Ok(PermissionObservationUpdate::Inserted)
        );
        assert_eq!(
            state.observe(
                PERSONAL,
                PermissionKind::Notifications,
                PermissionDecision::Granted,
                2
            ),
            Ok(PermissionObservationUpdate::Unchanged)
        );
        assert!(state.allows(PERSONAL, PermissionKind::Notifications));
    }

    #[test]
    fn unknown_observation_is_not_an_implicit_grant() {
        let mut state = PermissionState::new();
        state
            .observe(
                PERSONAL,
                PermissionKind::GlobalKeyboard,
                PermissionDecision::Unknown,
                1,
            )
            .unwrap();
        assert!(!state.allows(PERSONAL, PermissionKind::GlobalKeyboard));
        state
            .observe(
                PERSONAL,
                PermissionKind::GlobalKeyboard,
                PermissionDecision::Granted,
                2,
            )
            .unwrap();
        assert!(state.allows(PERSONAL, PermissionKind::GlobalKeyboard));
        state
            .observe(
                PERSONAL,
                PermissionKind::GlobalKeyboard,
                PermissionDecision::Expired,
                3,
            )
            .unwrap();
        assert!(!state.allows(PERSONAL, PermissionKind::GlobalKeyboard));
    }

    #[test]
    fn grant_in_one_scope_never_authorizes_another_scope() {
        let mut state = PermissionState::new();
        state
            .observe(
                PERSONAL,
                PermissionKind::Clipboard,
                PermissionDecision::Granted,
                1,
            )
            .unwrap();
        assert!(state.allows(PERSONAL, PermissionKind::Clipboard));
        assert!(!state.allows(WORK, PermissionKind::Clipboard));
        assert_eq!(
            state.decision(WORK, PermissionKind::Clipboard),
            PermissionDecision::Unknown
        );
    }
}
