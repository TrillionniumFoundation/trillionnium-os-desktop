//! Session state, event, effect, and error types.

use std::error::Error;
use std::fmt;

use trillionnium_contract_core::LeaseId;

pub const DEFAULT_HUMAN_LEASE_TTL_MS: u64 = 5_000;
pub const MAX_HUMAN_LEASE_TTL_MS: u64 = 30_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ControlState {
    Idle,
    AgentObserving,
    AgentMutating,
    HumanActive,
    HumanImeComposing,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SessionPhase {
    Ready,
    NavigationPending,
    ModalBlocked,
    CapabilityPending,
    Cancelling,
    Recovering,
    Closed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ControlSource {
    Agent,
    Human,
    System,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HumanLease {
    pub lease_id: LeaseId,
    pub acquired_at_ms: u64,
    pub expires_at_ms: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SessionEvent {
    BeginAgentObservation,
    EndAgentObservation,
    BeginAgentMutation,
    EndAgentMutation,
    HumanFocusGained { lease_id: LeaseId, ttl_ms: u64 },
    HumanInput { lease_id: LeaseId, extend_by_ms: u64 },
    HumanFocusReleased { lease_id: LeaseId },
    ImeStarted { lease_id: LeaseId },
    ImeEnded { lease_id: LeaseId },
    DomCommitted,
    SemanticSnapshotPublished,
    NavigationStarted { source: ControlSource },
    NavigationCommitted,
    NavigationFailed,
    ModalOpened,
    ModalClosed,
    CapabilityRequested,
    CapabilityResolved,
    CancelRequested,
    CancelCompleted,
    BrowserCrashed,
    Recovered,
    Tick,
    Close,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SessionEffect {
    InterruptAgentWork,
    HumanLeaseGranted,
    HumanLeaseExtended,
    HumanLeaseReleased,
    HumanLeaseExpired,
    MutationEpochAdvanced,
    SemanticSnapshotAdvanced,
    DocumentGenerationAdvanced,
    AllReferencesInvalidated,
    SessionClosed,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TransitionError {
    Closed,
    InvalidLeaseTtl,
    LeaseMismatch,
    HumanLeaseRequired,
    PhaseConflict(SessionPhase),
    ControlConflict(ControlState),
    InvalidTransition(&'static str),
}

impl fmt::Display for TransitionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Closed => formatter.write_str("session is closed"),
            Self::InvalidLeaseTtl => formatter.write_str("human lease ttl is invalid"),
            Self::LeaseMismatch => formatter.write_str("human lease id does not match"),
            Self::HumanLeaseRequired => formatter.write_str("an active human lease is required"),
            Self::PhaseConflict(phase) => write!(formatter, "session phase conflict: {phase:?}"),
            Self::ControlConflict(control) => {
                write!(formatter, "session control conflict: {control:?}")
            }
            Self::InvalidTransition(message) => formatter.write_str(message),
        }
    }
}

impl Error for TransitionError {}
