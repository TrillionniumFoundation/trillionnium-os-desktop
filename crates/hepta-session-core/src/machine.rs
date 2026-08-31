//! Deterministic session ownership, revision, and Agent/human arbitration.

use hepta_browser_contracts::{BrowserErrorCode, ElementRef, error_for_freshness};
use trillionnium_contract_core::{LeaseId, RevisionClock};

use crate::types::{
    ControlSource, ControlState, HumanLease, MAX_HUMAN_LEASE_TTL_MS, SessionEffect, SessionEvent,
    SessionPhase, TransitionError,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SessionSnapshot {
    pub control: ControlState,
    pub phase: SessionPhase,
    pub revisions: RevisionClock,
    pub human_lease: Option<HumanLease>,
}

#[derive(Debug, Clone)]
pub struct SessionMachine {
    control: ControlState,
    phase: SessionPhase,
    pending_navigation_source: Option<ControlSource>,
    revisions: RevisionClock,
    human_lease: Option<HumanLease>,
}

impl Default for SessionMachine {
    fn default() -> Self {
        Self::new()
    }
}

impl SessionMachine {
    pub const fn new() -> Self {
        Self {
            control: ControlState::Idle,
            phase: SessionPhase::Ready,
            pending_navigation_source: None,
            revisions: RevisionClock::new(),
            human_lease: None,
        }
    }

    pub fn snapshot(&self) -> SessionSnapshot {
        SessionSnapshot {
            control: self.control,
            phase: self.phase,
            revisions: self.revisions,
            human_lease: self.human_lease.clone(),
        }
    }

    #[cfg(test)]
    pub(crate) fn revisions_mut_for_test(&mut self) -> &mut RevisionClock {
        &mut self.revisions
    }

    pub fn validate_element_ref(&self, element: &ElementRef) -> Result<(), BrowserErrorCode> {
        match error_for_freshness(element.freshness(self.revisions)) {
            Some(error) => Err(error),
            None => Ok(()),
        }
    }

    /// Apply one event transactionally.
    ///
    /// No rejected event may leave a partially updated ownership, phase, lease,
    /// navigation, or revision state behind. This is especially important for
    /// revision exhaustion and adapter events that arrive after cancellation.
    pub fn apply(
        &mut self,
        event: SessionEvent,
        now_ms: u64,
    ) -> Result<Vec<SessionEffect>, TransitionError> {
        let mut candidate = self.clone();
        let effects = candidate.apply_inner(event, now_ms)?;
        candidate.validate_invariants()?;
        *self = candidate;
        Ok(effects)
    }

    fn apply_inner(
        &mut self,
        event: SessionEvent,
        now_ms: u64,
    ) -> Result<Vec<SessionEffect>, TransitionError> {
        if self.phase == SessionPhase::Closed && event != SessionEvent::Close {
            return Err(TransitionError::Closed);
        }

        let mut effects = Vec::new();
        match event {
            SessionEvent::BeginAgentObservation => {
                self.require_agent_control_available()?;
                self.control = ControlState::AgentObserving;
            }
            SessionEvent::EndAgentObservation => {
                if self.control != ControlState::AgentObserving {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.control = ControlState::Idle;
            }
            SessionEvent::BeginAgentMutation => {
                self.require_agent_control_available()?;
                self.control = ControlState::AgentMutating;
            }
            SessionEvent::EndAgentMutation => {
                if self.control != ControlState::AgentMutating {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.control = ControlState::Idle;
            }
            SessionEvent::HumanFocusGained { lease_id, ttl_ms } => {
                // Cancellation owns the session until reconciliation finishes.
                // Do not allow a new human lease to be acquired after the
                // current lease has been revoked by `CancelRequested`.
                self.require_human_interaction_allowed()?;
                if ttl_ms == 0 || ttl_ms > MAX_HUMAN_LEASE_TTL_MS {
                    return Err(TransitionError::InvalidLeaseTtl);
                }
                let expires_at_ms =
                    now_ms
                        .checked_add(ttl_ms)
                        .ok_or(TransitionError::InvalidTransition(
                            "human lease expiration overflowed",
                        ))?;
                if matches!(
                    self.control,
                    ControlState::AgentObserving | ControlState::AgentMutating
                ) {
                    effects.push(SessionEffect::InterruptAgentWork);
                }
                self.control = ControlState::HumanActive;
                self.human_lease = Some(HumanLease {
                    lease_id,
                    acquired_at_ms: now_ms,
                    expires_at_ms,
                });
                effects.push(SessionEffect::HumanLeaseGranted);
            }
            SessionEvent::HumanInput {
                lease_id,
                extend_by_ms,
            } => {
                self.require_human_interaction_allowed()?;
                let expired = {
                    let lease = self
                        .human_lease
                        .as_ref()
                        .ok_or(TransitionError::HumanLeaseRequired)?;
                    if lease.lease_id != lease_id {
                        return Err(TransitionError::LeaseMismatch);
                    }
                    // Adapter-owned human/system navigation may return the
                    // machine to `Idle` while retaining a lease for focus
                    // cleanup. A lease alone must never authorize input.
                    if self.control != ControlState::HumanActive {
                        return Err(TransitionError::ControlConflict(self.control));
                    }
                    now_ms >= lease.expires_at_ms
                };
                if expired {
                    self.control = ControlState::Idle;
                    self.human_lease = None;
                    effects.push(SessionEffect::HumanLeaseExpired);
                } else {
                    let extension = extend_by_ms.min(MAX_HUMAN_LEASE_TTL_MS);
                    let expires_at_ms =
                        now_ms
                            .checked_add(extension)
                            .ok_or(TransitionError::InvalidTransition(
                                "human lease expiration overflowed",
                            ))?;
                    let lease = self.require_matching_lease(&lease_id)?;
                    lease.expires_at_ms = expires_at_ms;
                    effects.push(SessionEffect::HumanLeaseExtended);
                }
            }
            SessionEvent::HumanFocusReleased { lease_id } => {
                self.require_human_interaction_allowed()?;
                self.require_matching_lease(&lease_id)?;
                self.human_lease = None;
                self.control = ControlState::Idle;
                effects.push(SessionEffect::HumanLeaseReleased);
            }
            SessionEvent::ImeStarted { lease_id } => {
                self.require_human_interaction_allowed()?;
                self.require_matching_lease(&lease_id)?;
                if self.control != ControlState::HumanActive {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.control = ControlState::HumanImeComposing;
            }
            SessionEvent::ImeEnded { lease_id } => {
                self.require_human_interaction_allowed()?;
                self.require_matching_lease(&lease_id)?;
                if self.control != ControlState::HumanImeComposing {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.control = ControlState::HumanActive;
            }
            SessionEvent::DomCommitted => {
                self.revisions
                    .try_on_dom_commit()
                    .map_err(|_error| TransitionError::RevisionExhausted)?;
                effects.push(SessionEffect::MutationEpochAdvanced);
            }
            SessionEvent::SemanticSnapshotPublished => {
                self.revisions
                    .try_on_semantic_snapshot()
                    .map_err(|_error| TransitionError::RevisionExhausted)?;
                effects.push(SessionEffect::SemanticSnapshotAdvanced);
            }
            SessionEvent::NavigationStarted { source } => {
                self.require_ready()?;
                match source {
                    ControlSource::Agent => {
                        // Agent navigation is an active operation and must
                        // acquire the same exclusive control as page actions.
                        // An idle control marker with a retained human lease is
                        // not sufficient: the lease must be explicitly
                        // released or expire before Agent admission.
                        self.require_agent_control_available()?;
                        self.control = ControlState::AgentNavigating;
                    }
                    ControlSource::Human => {
                        if self.control != ControlState::HumanActive {
                            return Err(TransitionError::ControlConflict(self.control));
                        }
                        if self.human_lease.is_none() {
                            return Err(TransitionError::HumanLeaseRequired);
                        }
                    }
                    ControlSource::System => {
                        // System adapters may navigate an idle or human-owned
                        // page, but may not relabel active Agent work or an IME
                        // composition as a system navigation.
                        if matches!(
                            self.control,
                            ControlState::AgentObserving
                                | ControlState::AgentMutating
                                | ControlState::AgentNavigating
                                | ControlState::HumanImeComposing
                        ) {
                            return Err(TransitionError::ControlConflict(self.control));
                        }
                    }
                }
                self.pending_navigation_source = Some(source);
                self.phase = SessionPhase::NavigationPending;
            }
            SessionEvent::NavigationCommitted => {
                self.require_pending_navigation()?;
                if self.pending_navigation_source == Some(ControlSource::Agent)
                    && self.control != ControlState::AgentNavigating
                {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.revisions
                    .try_on_navigation_commit()
                    .map_err(|_error| TransitionError::RevisionExhausted)?;
                self.finish_navigation();
                effects.push(SessionEffect::DocumentGenerationAdvanced);
            }
            SessionEvent::NavigationFailed => {
                self.require_pending_navigation()?;
                if self.pending_navigation_source == Some(ControlSource::Agent)
                    && self.control != ControlState::AgentNavigating
                {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.finish_navigation();
            }
            SessionEvent::ModalOpened => {
                self.require_ready()?;
                self.phase = SessionPhase::ModalBlocked;
            }
            SessionEvent::ModalClosed => {
                if self.phase != SessionPhase::ModalBlocked {
                    return Err(TransitionError::PhaseConflict(self.phase));
                }
                self.phase = SessionPhase::Ready;
            }
            SessionEvent::CapabilityRequested => {
                self.require_ready()?;
                self.phase = SessionPhase::CapabilityPending;
            }
            SessionEvent::CapabilityResolved => {
                if self.phase != SessionPhase::CapabilityPending {
                    return Err(TransitionError::PhaseConflict(self.phase));
                }
                self.phase = SessionPhase::Ready;
            }
            SessionEvent::CancelRequested => {
                if matches!(self.phase, SessionPhase::Recovering | SessionPhase::Closed) {
                    return Err(TransitionError::PhaseConflict(self.phase));
                }
                self.phase = SessionPhase::Cancelling;
                // Any pending navigation is now being reconciled under the
                // cancellation boundary; its terminal adapter event must not
                // be able to resurrect the old ownership marker.
                self.pending_navigation_source = None;
                // Cancellation is a hard ownership boundary. Revoke a human
                // lease immediately so an already-issued lease cannot continue
                // sending input while an Agent operation is reconciled. Keep
                // Agent control intact until `CancelCompleted` so adapters can
                // finish the in-flight operation's cleanup path.
                self.revoke_human_lease();
            }
            SessionEvent::CancelCompleted => {
                if self.phase != SessionPhase::Cancelling {
                    return Err(TransitionError::PhaseConflict(self.phase));
                }
                self.phase = SessionPhase::Ready;
                self.control = ControlState::Idle;
                self.pending_navigation_source = None;
                // Defensive cleanup keeps this transition fail closed even if
                // a future adapter populated a lease during reconciliation.
                self.revoke_human_lease();
            }
            SessionEvent::BrowserCrashed => {
                self.revisions
                    .try_on_process_recovery()
                    .map_err(|_error| TransitionError::RevisionExhausted)?;
                self.phase = SessionPhase::Recovering;
                self.control = ControlState::Idle;
                self.pending_navigation_source = None;
                self.human_lease = None;
                effects.push(SessionEffect::AllReferencesInvalidated);
            }
            SessionEvent::Recovered => {
                if self.phase != SessionPhase::Recovering {
                    return Err(TransitionError::PhaseConflict(self.phase));
                }
                self.phase = SessionPhase::Ready;
            }
            SessionEvent::Tick => {
                let expired = self
                    .human_lease
                    .as_ref()
                    .is_some_and(|lease| now_ms >= lease.expires_at_ms);
                if expired {
                    self.human_lease = None;
                    if matches!(
                        self.control,
                        ControlState::HumanActive | ControlState::HumanImeComposing
                    ) {
                        self.control = ControlState::Idle;
                    }
                    effects.push(SessionEffect::HumanLeaseExpired);
                }
            }
            SessionEvent::Close => {
                self.phase = SessionPhase::Closed;
                self.control = ControlState::Idle;
                self.pending_navigation_source = None;
                self.human_lease = None;
                effects.push(SessionEffect::SessionClosed);
            }
        }
        Ok(effects)
    }

    fn require_ready(&self) -> Result<(), TransitionError> {
        if self.phase == SessionPhase::Ready {
            Ok(())
        } else {
            Err(TransitionError::PhaseConflict(self.phase))
        }
    }

    fn require_idle(&self) -> Result<(), TransitionError> {
        if self.control == ControlState::Idle {
            Ok(())
        } else {
            Err(TransitionError::ControlConflict(self.control))
        }
    }

    fn require_agent_control_available(&self) -> Result<(), TransitionError> {
        self.require_ready()?;
        self.require_idle()?;
        if self.human_lease.is_some() {
            Err(TransitionError::InvalidTransition(
                "active human lease blocks Agent control",
            ))
        } else {
            Ok(())
        }
    }

    fn require_pending_navigation(&self) -> Result<(), TransitionError> {
        if self.phase != SessionPhase::NavigationPending {
            return Err(TransitionError::PhaseConflict(self.phase));
        }
        if self.pending_navigation_source.is_none() {
            return Err(TransitionError::InvalidTransition(
                "navigation phase has no source owner",
            ));
        }
        Ok(())
    }

    fn finish_navigation(&mut self) {
        self.phase = SessionPhase::Ready;
        self.control = ControlState::Idle;
        self.pending_navigation_source = None;
    }

    fn require_human_interaction_allowed(&self) -> Result<(), TransitionError> {
        if self.phase == SessionPhase::Cancelling {
            Err(TransitionError::PhaseConflict(self.phase))
        } else if self.pending_navigation_source == Some(ControlSource::Agent) {
            Err(TransitionError::PhaseConflict(
                SessionPhase::NavigationPending,
            ))
        } else {
            Ok(())
        }
    }

    fn revoke_human_lease(&mut self) {
        self.human_lease = None;
        if matches!(
            self.control,
            ControlState::HumanActive | ControlState::HumanImeComposing
        ) {
            self.control = ControlState::Idle;
        }
    }

    fn require_matching_lease(
        &mut self,
        lease_id: &LeaseId,
    ) -> Result<&mut HumanLease, TransitionError> {
        let lease = self
            .human_lease
            .as_mut()
            .ok_or(TransitionError::HumanLeaseRequired)?;
        if &lease.lease_id != lease_id {
            return Err(TransitionError::LeaseMismatch);
        }
        Ok(lease)
    }

    fn validate_invariants(&self) -> Result<(), TransitionError> {
        if self.human_lease.is_some()
            && matches!(
                self.control,
                ControlState::AgentObserving
                    | ControlState::AgentMutating
                    | ControlState::AgentNavigating
            )
        {
            return Err(TransitionError::InvalidTransition(
                "human lease overlaps Agent control",
            ));
        }
        if matches!(
            self.control,
            ControlState::HumanActive | ControlState::HumanImeComposing
        ) && self.human_lease.is_none()
        {
            return Err(TransitionError::InvalidTransition(
                "human control has no active lease",
            ));
        }
        if self.phase == SessionPhase::NavigationPending
            && self.pending_navigation_source.is_none()
        {
            return Err(TransitionError::InvalidTransition(
                "navigation phase has no source owner",
            ));
        }
        if self.phase != SessionPhase::NavigationPending
            && self.pending_navigation_source.is_some()
        {
            return Err(TransitionError::InvalidTransition(
                "navigation owner survived its phase",
            ));
        }
        if self.pending_navigation_source == Some(ControlSource::Agent)
            && self.control != ControlState::AgentNavigating
        {
            return Err(TransitionError::InvalidTransition(
                "Agent navigation has no exclusive control",
            ));
        }
        if self.control == ControlState::AgentNavigating
            && !matches!(
                self.phase,
                SessionPhase::NavigationPending | SessionPhase::Cancelling
            )
        {
            return Err(TransitionError::InvalidTransition(
                "Agent navigation control survived its phase",
            ));
        }
        if matches!(self.phase, SessionPhase::Recovering | SessionPhase::Closed)
            && (self.control != ControlState::Idle || self.human_lease.is_some())
        {
            return Err(TransitionError::InvalidTransition(
                "terminal recovery state retains page ownership",
            ));
        }
        Ok(())
    }
}

#[cfg(test)]
mod invariant_tests {
    use super::*;
    use crate::types::DEFAULT_HUMAN_LEASE_TTL_MS;

    fn lease() -> LeaseId {
        LeaseId::parse("lease_id", "machine-invariant-lease").expect("lease")
    }

    fn retained_lease_after_human_navigation() -> SessionMachine {
        let mut machine = SessionMachine::new();
        machine
            .apply(
                SessionEvent::HumanFocusGained {
                    lease_id: lease(),
                    ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
                },
                0,
            )
            .expect("focus");
        machine
            .apply(
                SessionEvent::NavigationStarted {
                    source: ControlSource::Human,
                },
                1,
            )
            .expect("human navigation");
        machine
            .apply(SessionEvent::NavigationCommitted, 2)
            .expect("commit");
        assert_eq!(machine.snapshot().control, ControlState::Idle);
        assert!(machine.snapshot().human_lease.is_some());
        machine
    }

    #[test]
    fn retained_human_lease_blocks_every_agent_admission_path() {
        let mut machine = retained_lease_after_human_navigation();
        let before = machine.snapshot();
        assert_eq!(
            machine.apply(SessionEvent::BeginAgentObservation, 3),
            Err(TransitionError::InvalidTransition(
                "active human lease blocks Agent control"
            ))
        );
        assert_eq!(machine.snapshot(), before);
        assert_eq!(
            machine.apply(SessionEvent::BeginAgentMutation, 3),
            Err(TransitionError::InvalidTransition(
                "active human lease blocks Agent control"
            ))
        );
        assert_eq!(machine.snapshot(), before);
        assert_eq!(
            machine.apply(
                SessionEvent::NavigationStarted {
                    source: ControlSource::Agent,
                },
                3,
            ),
            Err(TransitionError::InvalidTransition(
                "active human lease blocks Agent control"
            ))
        );
        assert_eq!(machine.snapshot(), before);

        machine
            .apply(SessionEvent::HumanFocusReleased { lease_id: lease() }, 4)
            .expect("lease release");
        machine
            .apply(SessionEvent::BeginAgentMutation, 5)
            .expect("Agent admitted after explicit release");
    }

    #[test]
    fn source_labels_cannot_relabel_active_page_control() {
        let mut machine = SessionMachine::new();
        machine
            .apply(SessionEvent::BeginAgentMutation, 0)
            .expect("Agent mutation");
        let before = machine.snapshot();
        assert_eq!(
            machine.apply(
                SessionEvent::NavigationStarted {
                    source: ControlSource::Human,
                },
                1,
            ),
            Err(TransitionError::ControlConflict(
                ControlState::AgentMutating
            ))
        );
        assert_eq!(machine.snapshot(), before);
        assert_eq!(
            machine.apply(
                SessionEvent::NavigationStarted {
                    source: ControlSource::System,
                },
                1,
            ),
            Err(TransitionError::ControlConflict(
                ControlState::AgentMutating
            ))
        );
        assert_eq!(machine.snapshot(), before);
    }

    #[test]
    fn rejected_events_are_transactional() {
        let mut machine = SessionMachine::new();
        machine
            .apply(
                SessionEvent::NavigationStarted {
                    source: ControlSource::Agent,
                },
                0,
            )
            .expect("Agent navigation");
        let before = machine.snapshot();
        assert_eq!(
            machine.apply(
                SessionEvent::HumanFocusGained {
                    lease_id: lease(),
                    ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
                },
                1,
            ),
            Err(TransitionError::PhaseConflict(
                SessionPhase::NavigationPending
            ))
        );
        assert_eq!(machine.snapshot(), before);
    }
}
