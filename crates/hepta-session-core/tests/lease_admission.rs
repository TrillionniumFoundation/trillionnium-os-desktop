use hepta_session_core::{
    ControlSource, ControlState, SessionEffect, SessionEvent, SessionMachine, SessionPhase,
    TransitionError,
};
use trillionnium_contract_core::LeaseId;

const LEASE_START_MS: u64 = 100;
const LEASE_TTL_MS: u64 = 10;
const LEASE_EXPIRY_MS: u64 = LEASE_START_MS + LEASE_TTL_MS;

fn lease(name: &str) -> LeaseId {
    LeaseId::parse("lease_id", name).expect("valid test lease")
}

fn focus(machine: &mut SessionMachine, lease_id: LeaseId) {
    machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id,
                ttl_ms: LEASE_TTL_MS,
            },
            LEASE_START_MS,
        )
        .expect("focus admission");
}

fn modal_blocked() -> SessionMachine {
    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::ModalOpened, LEASE_START_MS)
        .expect("modal open");
    machine
}

fn capability_pending() -> SessionMachine {
    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::CapabilityRequested, LEASE_START_MS)
        .expect("capability request");
    machine
}

fn recovering() -> SessionMachine {
    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::BrowserCrashed, LEASE_START_MS)
        .expect("browser crash");
    machine
}

fn cancelling() -> SessionMachine {
    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::CancelRequested, LEASE_START_MS)
        .expect("cancellation request");
    machine
}

fn closed() -> SessionMachine {
    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::Close, LEASE_START_MS)
        .expect("close");
    machine
}

fn system_navigation_pending() -> SessionMachine {
    let mut machine = SessionMachine::new();
    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::System,
            },
            LEASE_START_MS,
        )
        .expect("system navigation");
    machine
}

fn human_navigation_pending() -> SessionMachine {
    let mut machine = SessionMachine::new();
    focus(&mut machine, lease("phase-human-navigation"));
    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Human,
            },
            LEASE_START_MS + 1,
        )
        .expect("human navigation");
    machine
}

fn agent_navigation_pending() -> SessionMachine {
    let mut machine = SessionMachine::new();
    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Agent,
            },
            LEASE_START_MS,
        )
        .expect("agent navigation");
    machine
}

fn human_events() -> Vec<SessionEvent> {
    let lease_id = lease("phase-event");
    vec![
        SessionEvent::HumanFocusGained {
            lease_id: lease_id.clone(),
            ttl_ms: LEASE_TTL_MS,
        },
        SessionEvent::HumanInput {
            lease_id: lease_id.clone(),
            extend_by_ms: 1,
        },
        SessionEvent::HumanFocusReleased {
            lease_id: lease_id.clone(),
        },
        SessionEvent::ImeStarted {
            lease_id: lease_id.clone(),
        },
        SessionEvent::ImeEnded { lease_id },
    ]
}

#[test]
fn every_human_interaction_is_rejected_transactionally_outside_ready() {
    let non_ready = [
        modal_blocked(),
        capability_pending(),
        recovering(),
        cancelling(),
        system_navigation_pending(),
        human_navigation_pending(),
        agent_navigation_pending(),
    ];

    for baseline in non_ready {
        let phase = baseline.snapshot().phase;
        assert_ne!(phase, SessionPhase::Ready);
        for event in human_events() {
            let mut machine = baseline.clone();
            let before = machine.snapshot();
            assert_eq!(
                machine.apply(event, LEASE_START_MS + 2),
                Err(TransitionError::PhaseConflict(phase))
            );
            assert_eq!(machine.snapshot(), before);
        }
    }

    let baseline = closed();
    for event in human_events() {
        let mut machine = baseline.clone();
        let before = machine.snapshot();
        assert_eq!(
            machine.apply(event, LEASE_START_MS + 2),
            Err(TransitionError::Closed)
        );
        assert_eq!(machine.snapshot(), before);
    }
}

#[test]
fn expired_lease_cannot_authorize_human_input_ime_or_navigation() {
    let lease_id = lease("expired-human-authority");

    let mut machine = SessionMachine::new();
    focus(&mut machine, lease_id.clone());
    for event in [
        SessionEvent::HumanInput {
            lease_id: lease_id.clone(),
            extend_by_ms: 1,
        },
        SessionEvent::ImeStarted {
            lease_id: lease_id.clone(),
        },
        SessionEvent::NavigationStarted {
            source: ControlSource::Human,
        },
    ] {
        let before = machine.snapshot();
        assert_eq!(
            machine.apply(event, LEASE_EXPIRY_MS),
            Err(TransitionError::InvalidTransition("human lease expired"))
        );
        assert_eq!(machine.snapshot(), before);
    }

    machine
        .apply(
            SessionEvent::ImeStarted {
                lease_id: lease_id.clone(),
            },
            LEASE_EXPIRY_MS - 1,
        )
        .expect("IME starts while lease is live");
    let before = machine.snapshot();
    assert_eq!(
        machine.apply(SessionEvent::ImeEnded { lease_id }, LEASE_EXPIRY_MS),
        Err(TransitionError::InvalidTransition("human lease expired"))
    );
    assert_eq!(machine.snapshot(), before);
}

fn expired_human_machine(name: &str) -> SessionMachine {
    let mut machine = SessionMachine::new();
    focus(&mut machine, lease(name));
    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Human,
            },
            LEASE_START_MS + 1,
        )
        .expect("human navigation starts while lease is live");
    machine
        .apply(SessionEvent::NavigationCommitted, LEASE_START_MS + 2)
        .expect("human navigation commits");
    assert_eq!(machine.snapshot().control, ControlState::Idle);
    assert!(machine.snapshot().human_lease.is_some());
    machine
}

#[test]
fn every_agent_admission_atomically_reaps_an_expired_lease() {
    let cases = [
        (
            SessionEvent::BeginAgentObservation,
            ControlState::AgentObserving,
            SessionPhase::Ready,
        ),
        (
            SessionEvent::BeginAgentMutation,
            ControlState::AgentMutating,
            SessionPhase::Ready,
        ),
        (
            SessionEvent::NavigationStarted {
                source: ControlSource::Agent,
            },
            ControlState::AgentNavigating,
            SessionPhase::NavigationPending,
        ),
    ];

    for (index, (event, expected_control, expected_phase)) in cases.into_iter().enumerate() {
        let mut machine = expired_human_machine(&format!("expired-agent-{index}"));
        let effects = machine
            .apply(event, LEASE_EXPIRY_MS)
            .expect("expired lease must not deny Agent admission");
        assert_eq!(
            effects
                .iter()
                .filter(|effect| **effect == SessionEffect::HumanLeaseExpired)
                .count(),
            1
        );
        let snapshot = machine.snapshot();
        assert!(snapshot.human_lease.is_none());
        assert_eq!(snapshot.control, expected_control);
        assert_eq!(snapshot.phase, expected_phase);
    }
}

#[test]
fn live_lease_still_blocks_agent_admission_without_mutation() {
    let mut machine = SessionMachine::new();
    let lease_id = lease("live-agent-denial");
    focus(&mut machine, lease_id);
    let before = machine.snapshot();

    for event in [
        SessionEvent::BeginAgentObservation,
        SessionEvent::BeginAgentMutation,
        SessionEvent::NavigationStarted {
            source: ControlSource::Agent,
        },
    ] {
        assert!(machine.apply(event, LEASE_EXPIRY_MS - 1).is_err());
        assert_eq!(machine.snapshot(), before);
    }
}

#[test]
fn regressed_human_event_time_never_consumes_a_lease() {
    let mut machine = SessionMachine::new();
    let lease_id = lease("regressed-human-time");
    focus(&mut machine, lease_id.clone());
    let before = machine.snapshot();
    assert_eq!(
        machine.apply(SessionEvent::ImeStarted { lease_id }, LEASE_START_MS - 1,),
        Err(TransitionError::InvalidTransition(
            "human lease event time precedes acquisition"
        ))
    );
    assert_eq!(machine.snapshot(), before);
}
