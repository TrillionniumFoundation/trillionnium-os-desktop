//! Deterministic session ownership, revision, and Agent/human arbitration.

use hepta_browser_contracts::{BrowserErrorCode, ElementRef, error_for_freshness};
use trillionnium_contract_core::{LeaseId, RevisionClock};

use crate::types::{
    ControlState, HumanLease, MAX_HUMAN_LEASE_TTL_MS, SessionEffect, SessionEvent, SessionPhase,
    TransitionError,
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

    pub fn validate_element_ref(&self, element: &ElementRef) -> Result<(), BrowserErrorCode> {
        match error_for_freshness(element.freshness(self.revisions)) {
            Some(error) => Err(error),
            None => Ok(()),
        }
    }

    pub fn apply(
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
                self.require_ready()?;
                self.require_idle()?;
                self.control = ControlState::AgentObserving;
            }
            SessionEvent::EndAgentObservation => {
                if self.control != ControlState::AgentObserving {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.control = ControlState::Idle;
            }
            SessionEvent::BeginAgentMutation => {
                self.require_ready()?;
                self.require_idle()?;
                self.control = ControlState::AgentMutating;
            }
            SessionEvent::EndAgentMutation => {
                if self.control != ControlState::AgentMutating {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.control = ControlState::Idle;
            }
            SessionEvent::HumanFocusGained { lease_id, ttl_ms } => {
                if ttl_ms == 0 || ttl_ms > MAX_HUMAN_LEASE_TTL_MS {
                    return Err(TransitionError::InvalidLeaseTtl);
                }
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
                    expires_at_ms: now_ms.saturating_add(ttl_ms),
                });
                effects.push(SessionEffect::HumanLeaseGranted);
            }
            SessionEvent::HumanInput {
                lease_id,
                extend_by_ms,
            } => {
                let expired = {
                    let lease = self.require_matching_lease(&lease_id)?;
                    now_ms >= lease.expires_at_ms
                };
                if expired {
                    self.control = ControlState::Idle;
                    self.human_lease = None;
                    effects.push(SessionEffect::HumanLeaseExpired);
                } else {
                    let extension = extend_by_ms.min(MAX_HUMAN_LEASE_TTL_MS);
                    let lease = self.require_matching_lease(&lease_id)?;
                    lease.expires_at_ms = now_ms.saturating_add(extension);
                    effects.push(SessionEffect::HumanLeaseExtended);
                }
            }
            SessionEvent::HumanFocusReleased { lease_id } => {
                self.require_matching_lease(&lease_id)?;
                self.human_lease = None;
                self.control = ControlState::Idle;
                effects.push(SessionEffect::HumanLeaseReleased);
            }
            SessionEvent::ImeStarted { lease_id } => {
                self.require_matching_lease(&lease_id)?;
                if self.control != ControlState::HumanActive {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.control = ControlState::HumanImeComposing;
            }
            SessionEvent::ImeEnded { lease_id } => {
                self.require_matching_lease(&lease_id)?;
                if self.control != ControlState::HumanImeComposing {
                    return Err(TransitionError::ControlConflict(self.control));
                }
                self.control = ControlState::HumanActive;
            }
            SessionEvent::DomCommitted => {
                self.revisions.on_dom_commit();
                effects.push(SessionEffect::MutationEpochAdvanced);
            }
            SessionEvent::SemanticSnapshotPublished => {
                self.revisions.on_semantic_snapshot();
                effects.push(SessionEffect::SemanticSnapshotAdvanced);
            }
            SessionEvent::NavigationStarted { .. } => {
                self.require_ready()?;
                self.phase = SessionPhase::NavigationPending;
            }
            SessionEvent::NavigationCommitted => {
                if self.phase != SessionPhase::NavigationPending {
                    return Err(TransitionError::PhaseConflict(self.phase));
                }
                self.revisions.on_navigation_commit();
                self.phase = SessionPhase::Ready;
                self.control = ControlState::Idle;
                effects.push(SessionEffect::DocumentGenerationAdvanced);
            }
            SessionEvent::NavigationFailed => {
                if self.phase != SessionPhase::NavigationPending {
                    return Err(TransitionError::PhaseConflict(self.phase));
                }
                self.phase = SessionPhase::Ready;
                self.control = ControlState::Idle;
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
            }
            SessionEvent::CancelCompleted => {
                if self.phase != SessionPhase::Cancelling {
                    return Err(TransitionError::PhaseConflict(self.phase));
                }
                self.phase = SessionPhase::Ready;
                self.control = ControlState::Idle;
            }
            SessionEvent::BrowserCrashed => {
                self.revisions.on_process_recovery();
                self.phase = SessionPhase::Recovering;
                self.control = ControlState::Idle;
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
}
