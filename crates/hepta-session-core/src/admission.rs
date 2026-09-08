//! Public transactional admission boundary for the session reducer.
//!
//! The inner machine owns deterministic phase/control transitions. This
//! facade adds the time-bearing authority checks that must happen before an
//! event is reduced: Human/IME interaction is Ready-only, every Human
//! authority use requires a live lease, and every Agent admission atomically
//! reaps an expired Human lease before acquiring control.

use hepta_browser_contracts::{BrowserErrorCode, ElementRef};
use trillionnium_contract_core::LeaseId;
#[cfg(test)]
use trillionnium_contract_core::RevisionClock;

use crate::machine::{SessionMachine as Reducer, SessionSnapshot};
use crate::types::{ControlSource, SessionEffect, SessionEvent, SessionPhase, TransitionError};

#[derive(Debug, Clone)]
pub struct SessionMachine {
    reducer: Reducer,
}

impl Default for SessionMachine {
    fn default() -> Self {
        Self::new()
    }
}

impl SessionMachine {
    pub const fn new() -> Self {
        Self {
            reducer: Reducer::new(),
        }
    }

    pub fn snapshot(&self) -> SessionSnapshot {
        self.reducer.snapshot()
    }

    #[cfg(test)]
    pub(crate) fn revisions_mut_for_test(&mut self) -> &mut RevisionClock {
        self.reducer.revisions_mut_for_test()
    }

    pub fn validate_element_ref(&self, element: &ElementRef) -> Result<(), BrowserErrorCode> {
        self.reducer.validate_element_ref(element)
    }

    /// Apply one event under the public phase and lease-authority contract.
    ///
    /// The reducer is cloned before any time normalization. If either expiry
    /// reconciliation or the requested transition fails, the original machine
    /// remains byte-for-byte unchanged. Successful Agent admission includes a
    /// `HumanLeaseExpired` effect when it atomically reaps a stale lease.
    pub fn apply(
        &mut self,
        event: SessionEvent,
        now_ms: u64,
    ) -> Result<Vec<SessionEffect>, TransitionError> {
        self.require_admission(&event, now_ms)?;

        let mut candidate = self.reducer.clone();
        let mut effects = Vec::new();
        if is_agent_admission(&event) {
            effects.extend(candidate.apply(SessionEvent::Tick, now_ms)?);
        }
        effects.extend(candidate.apply(event, now_ms)?);
        self.reducer = candidate;
        Ok(effects)
    }

    fn require_admission(&self, event: &SessionEvent, now_ms: u64) -> Result<(), TransitionError> {
        let snapshot = self.reducer.snapshot();
        if snapshot.phase == SessionPhase::Closed && !matches!(event, SessionEvent::Close) {
            return Err(TransitionError::Closed);
        }

        if is_human_interaction(event) && snapshot.phase != SessionPhase::Ready {
            return Err(TransitionError::PhaseConflict(snapshot.phase));
        }

        match event {
            SessionEvent::HumanInput { lease_id, .. }
            | SessionEvent::ImeStarted { lease_id }
            | SessionEvent::ImeEnded { lease_id } => {
                require_active_matching_lease(&snapshot, lease_id, now_ms)?;
            }
            SessionEvent::NavigationStarted {
                source: ControlSource::Human,
            } => {
                require_active_lease(&snapshot, now_ms)?;
            }
            _ => {}
        }
        Ok(())
    }
}

fn is_agent_admission(event: &SessionEvent) -> bool {
    matches!(
        event,
        SessionEvent::BeginAgentObservation
            | SessionEvent::BeginAgentMutation
            | SessionEvent::NavigationStarted {
                source: ControlSource::Agent
            }
    )
}

fn is_human_interaction(event: &SessionEvent) -> bool {
    matches!(
        event,
        SessionEvent::HumanFocusGained { .. }
            | SessionEvent::HumanInput { .. }
            | SessionEvent::HumanFocusReleased { .. }
            | SessionEvent::ImeStarted { .. }
            | SessionEvent::ImeEnded { .. }
    )
}

fn require_active_matching_lease(
    snapshot: &SessionSnapshot,
    lease_id: &LeaseId,
    now_ms: u64,
) -> Result<(), TransitionError> {
    let lease = snapshot
        .human_lease
        .as_ref()
        .ok_or(TransitionError::HumanLeaseRequired)?;
    if &lease.lease_id != lease_id {
        return Err(TransitionError::LeaseMismatch);
    }
    require_live_timestamp(lease.acquired_at_ms, lease.expires_at_ms, now_ms)
}

fn require_active_lease(snapshot: &SessionSnapshot, now_ms: u64) -> Result<(), TransitionError> {
    let lease = snapshot
        .human_lease
        .as_ref()
        .ok_or(TransitionError::HumanLeaseRequired)?;
    require_live_timestamp(lease.acquired_at_ms, lease.expires_at_ms, now_ms)
}

fn require_live_timestamp(
    acquired_at_ms: u64,
    expires_at_ms: u64,
    now_ms: u64,
) -> Result<(), TransitionError> {
    if now_ms < acquired_at_ms {
        return Err(TransitionError::InvalidTransition(
            "human lease event time precedes acquisition",
        ));
    }
    if now_ms >= expires_at_ms {
        return Err(TransitionError::InvalidTransition("human lease expired"));
    }
    Ok(())
}
