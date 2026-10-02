use hepta_session_core::{
    ControlSource, ControlState, SessionEvent, SessionMachine, SessionPhase, TransitionError,
};
use trillionnium_contract_core::LeaseId;

fn lease() -> LeaseId {
    LeaseId::parse("lease_id", "human-custody").expect("valid lease")
}

fn focus(machine: &mut SessionMachine) {
    machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: 100,
            },
            0,
        )
        .expect("human focus");
}

#[test]
fn focus_is_rejected_in_every_unavailable_phase_without_changing_state() {
    for event in [
        SessionEvent::NavigationStarted {
            source: ControlSource::System,
        },
        SessionEvent::ModalOpened,
        SessionEvent::CapabilityRequested,
        SessionEvent::CancelRequested,
        SessionEvent::BrowserCrashed,
    ] {
        let mut machine = SessionMachine::new();
        machine.apply(event, 0).expect("enter blocked phase");
        let before = machine.snapshot();
        assert_eq!(
            machine.apply(
                SessionEvent::HumanFocusGained {
                    lease_id: lease(),
                    ttl_ms: 100
                },
                1
            ),
            Err(TransitionError::PhaseConflict(before.phase))
        );
        assert_eq!(machine.snapshot(), before);
    }
}

#[test]
fn agent_and_system_navigation_cannot_steal_human_or_agent_control() {
    for control_event in [
        SessionEvent::BeginAgentObservation,
        SessionEvent::BeginAgentMutation,
        SessionEvent::HumanFocusGained {
            lease_id: lease(),
            ttl_ms: 100,
        },
    ] {
        for source in [ControlSource::Agent, ControlSource::System] {
            let mut machine = SessionMachine::new();
            machine
                .apply(control_event.clone(), 0)
                .expect("acquire control");
            let before = machine.snapshot();
            assert_eq!(
                machine.apply(SessionEvent::NavigationStarted { source }, 1),
                Err(TransitionError::ControlConflict(before.control))
            );
            assert_eq!(machine.snapshot(), before);
        }
    }
}

#[test]
fn human_navigation_requires_live_noncomposing_custody() {
    let mut machine = SessionMachine::new();
    assert!(
        machine
            .apply(
                SessionEvent::NavigationStarted {
                    source: ControlSource::Human
                },
                0
            )
            .is_err()
    );
    focus(&mut machine);
    machine
        .apply(SessionEvent::ImeStarted { lease_id: lease() }, 1)
        .expect("start IME");
    assert_eq!(
        machine.apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Human
            },
            2
        ),
        Err(TransitionError::ControlConflict(
            ControlState::HumanImeComposing
        ))
    );
    machine
        .apply(SessionEvent::ImeEnded { lease_id: lease() }, 3)
        .expect("end IME");
    let before = machine.snapshot();
    assert_eq!(
        machine.apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Human
            },
            100
        ),
        Err(TransitionError::HumanLeaseRequired)
    );
    assert_eq!(machine.snapshot(), before);
}

#[test]
fn human_navigation_completion_preserves_lease_and_mutation_exclusion() {
    for completion in [
        SessionEvent::NavigationCommitted,
        SessionEvent::NavigationFailed,
    ] {
        let mut machine = SessionMachine::new();
        focus(&mut machine);
        machine
            .apply(
                SessionEvent::NavigationStarted {
                    source: ControlSource::Human,
                },
                1,
            )
            .expect("human navigation");
        machine.apply(completion, 2).expect("complete navigation");
        let after = machine.snapshot();
        assert_eq!(after.phase, SessionPhase::Ready);
        assert_eq!(after.control, ControlState::HumanActive);
        assert!(after.human_lease.is_some());
        assert_eq!(
            machine.apply(SessionEvent::BeginAgentMutation, 3),
            Err(TransitionError::ControlConflict(ControlState::HumanActive))
        );
    }
}

#[test]
fn cancelling_preserves_active_human_and_ime_control() {
    for composing in [false, true] {
        let mut machine = SessionMachine::new();
        focus(&mut machine);
        if composing {
            machine
                .apply(SessionEvent::ImeStarted { lease_id: lease() }, 1)
                .expect("start IME");
        }
        let before = machine.snapshot();
        machine
            .apply(SessionEvent::CancelRequested, 2)
            .expect("start cancellation");
        machine
            .apply(SessionEvent::CancelCompleted, 3)
            .expect("complete cancellation");
        assert_eq!(machine.snapshot(), before);
        assert!(machine.apply(SessionEvent::BeginAgentMutation, 4).is_err());
    }
}

#[test]
fn blocked_phases_cannot_accept_content_input_or_ime() {
    for phase_event in [
        SessionEvent::ModalOpened,
        SessionEvent::CapabilityRequested,
        SessionEvent::CancelRequested,
    ] {
        for input in [
            SessionEvent::HumanInput {
                lease_id: lease(),
                extend_by_ms: 100,
            },
            SessionEvent::ImeStarted { lease_id: lease() },
        ] {
            let mut machine = SessionMachine::new();
            focus(&mut machine);
            machine.apply(phase_event.clone(), 1).expect("block phase");
            let before = machine.snapshot();
            assert_eq!(
                machine.apply(input, 2),
                Err(TransitionError::PhaseConflict(before.phase))
            );
            assert_eq!(machine.snapshot(), before);
        }
    }
}

#[test]
fn ime_cannot_begin_or_end_after_lease_expiry_without_a_tick() {
    for composing in [false, true] {
        let mut machine = SessionMachine::new();
        focus(&mut machine);
        if composing {
            machine
                .apply(SessionEvent::ImeStarted { lease_id: lease() }, 1)
                .expect("start IME");
        }
        let before = machine.snapshot();
        let event = if composing {
            SessionEvent::ImeEnded { lease_id: lease() }
        } else {
            SessionEvent::ImeStarted { lease_id: lease() }
        };
        assert_eq!(
            machine.apply(event, 100),
            Err(TransitionError::HumanLeaseRequired)
        );
        assert_eq!(machine.snapshot(), before);
    }
}

#[test]
fn crashed_content_cannot_publish_fresh_revisions_before_recovery() {
    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::BrowserCrashed, 0)
        .expect("crash");
    let crashed = machine.snapshot();
    for event in [
        SessionEvent::DomCommitted,
        SessionEvent::SemanticSnapshotPublished,
    ] {
        assert_eq!(
            machine.apply(event, 1),
            Err(TransitionError::PhaseConflict(SessionPhase::Recovering))
        );
        assert_eq!(machine.snapshot(), crashed);
    }
    machine
        .apply(SessionEvent::Recovered, 2)
        .expect("explicit recovery");
    machine
        .apply(SessionEvent::DomCommitted, 3)
        .expect("current content commit");
    machine
        .apply(SessionEvent::SemanticSnapshotPublished, 4)
        .expect("current snapshot");
}

#[test]
fn hostile_event_sequences_keep_custody_consistent_and_rejections_atomic() {
    fn explore(machine: SessionMachine, depth: u64) {
        let snapshot = machine.snapshot();
        let human_control = matches!(
            snapshot.control,
            ControlState::HumanActive | ControlState::HumanImeComposing
        );
        assert_eq!(snapshot.human_lease.is_some(), human_control);
        if matches!(
            snapshot.phase,
            SessionPhase::Recovering | SessionPhase::Closed
        ) {
            assert_eq!(snapshot.control, ControlState::Idle);
        }
        if depth == 4 {
            return;
        }
        for event in [
            SessionEvent::BeginAgentObservation,
            SessionEvent::EndAgentObservation,
            SessionEvent::BeginAgentMutation,
            SessionEvent::EndAgentMutation,
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: 2,
            },
            SessionEvent::HumanInput {
                lease_id: lease(),
                extend_by_ms: 2,
            },
            SessionEvent::HumanFocusReleased { lease_id: lease() },
            SessionEvent::ImeStarted { lease_id: lease() },
            SessionEvent::ImeEnded { lease_id: lease() },
            SessionEvent::NavigationStarted {
                source: ControlSource::Agent,
            },
            SessionEvent::NavigationStarted {
                source: ControlSource::Human,
            },
            SessionEvent::NavigationStarted {
                source: ControlSource::System,
            },
            SessionEvent::NavigationCommitted,
            SessionEvent::NavigationFailed,
            SessionEvent::ModalOpened,
            SessionEvent::ModalClosed,
            SessionEvent::CapabilityRequested,
            SessionEvent::CapabilityResolved,
            SessionEvent::CancelRequested,
            SessionEvent::CancelCompleted,
            SessionEvent::BrowserCrashed,
            SessionEvent::Recovered,
            SessionEvent::Tick,
            SessionEvent::Close,
        ] {
            let mut candidate = machine.clone();
            let result = candidate.apply(event.clone(), depth);
            if result.is_err() {
                assert_eq!(candidate.snapshot(), snapshot, "rejected event {event:?}");
            } else {
                explore(candidate, depth + 1);
            }
        }
    }
    explore(SessionMachine::new(), 0);
}
