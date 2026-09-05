use std::collections::{HashSet, VecDeque};

use hepta_session_core::{
    ControlSource, ControlState, DEFAULT_HUMAN_LEASE_TTL_MS, SessionEvent, SessionMachine,
    SessionPhase,
};
use trillionnium_contract_core::LeaseId;

const MAX_DEPTH: usize = 7;

fn lease(value: &str) -> LeaseId {
    LeaseId::parse("lease_id", value).expect("bounded test lease")
}

fn event_corpus() -> Vec<SessionEvent> {
    let primary = lease("state-space-primary");
    let foreign = lease("state-space-foreign");
    vec![
        SessionEvent::BeginAgentObservation,
        SessionEvent::EndAgentObservation,
        SessionEvent::BeginAgentMutation,
        SessionEvent::EndAgentMutation,
        SessionEvent::HumanFocusGained {
            lease_id: primary.clone(),
            ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
        },
        SessionEvent::HumanFocusGained {
            lease_id: foreign.clone(),
            ttl_ms: 25,
        },
        SessionEvent::HumanInput {
            lease_id: primary.clone(),
            extend_by_ms: 15,
        },
        SessionEvent::HumanInput {
            lease_id: foreign.clone(),
            extend_by_ms: 15,
        },
        SessionEvent::HumanFocusReleased {
            lease_id: primary.clone(),
        },
        SessionEvent::HumanFocusReleased {
            lease_id: foreign.clone(),
        },
        SessionEvent::ImeStarted {
            lease_id: primary.clone(),
        },
        SessionEvent::ImeStarted {
            lease_id: foreign.clone(),
        },
        SessionEvent::ImeEnded { lease_id: primary },
        SessionEvent::ImeEnded { lease_id: foreign },
        SessionEvent::DomCommitted,
        SessionEvent::SemanticSnapshotPublished,
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
    ]
}

fn public_state_key(machine: &SessionMachine) -> String {
    format!("{:?}", machine.snapshot())
}

fn behavioral_signature(machine: &SessionMachine, now_ms: u64) -> Vec<String> {
    let probe_lease = lease("state-space-primary");
    [
        SessionEvent::NavigationCommitted,
        SessionEvent::NavigationFailed,
        SessionEvent::CancelRequested,
        SessionEvent::CancelCompleted,
        SessionEvent::HumanFocusReleased {
            lease_id: probe_lease,
        },
        SessionEvent::BeginAgentMutation,
        SessionEvent::Tick,
        SessionEvent::Close,
    ]
    .into_iter()
    .map(|event| {
        let mut candidate = machine.clone();
        let outcome = candidate.apply(event, now_ms);
        format!("{outcome:?}|{:?}", candidate.snapshot())
    })
    .collect()
}

fn assert_public_invariants(machine: &SessionMachine) {
    let snapshot = machine.snapshot();

    if snapshot.human_lease.is_some() {
        assert!(
            !matches!(
                snapshot.control,
                ControlState::AgentObserving
                    | ControlState::AgentMutating
                    | ControlState::AgentNavigating
            ),
            "human lease overlapped Agent ownership: {snapshot:?}"
        );
    }

    if matches!(
        snapshot.control,
        ControlState::HumanActive | ControlState::HumanImeComposing
    ) {
        assert!(
            snapshot.human_lease.is_some(),
            "human control had no lease: {snapshot:?}"
        );
    }

    if snapshot.control == ControlState::AgentNavigating {
        assert!(
            matches!(
                snapshot.phase,
                SessionPhase::NavigationPending | SessionPhase::Cancelling
            ),
            "Agent navigation survived its phase: {snapshot:?}"
        );
        assert!(
            snapshot.human_lease.is_none(),
            "Agent navigation retained a human lease: {snapshot:?}"
        );
    }

    if matches!(
        snapshot.phase,
        SessionPhase::Recovering | SessionPhase::Closed
    ) {
        assert_eq!(snapshot.control, ControlState::Idle, "{snapshot:?}");
        assert!(snapshot.human_lease.is_none(), "{snapshot:?}");
    }
}

#[test]
fn bounded_event_space_preserves_arbitration_and_transactionality() {
    let events = event_corpus();
    let initial = SessionMachine::new();
    let mut seen = HashSet::from([public_state_key(&initial)]);
    let mut queue = VecDeque::from([(initial, 0_usize)]);
    let mut attempted_transitions = 0_usize;
    let mut rejected_transitions = 0_usize;

    while let Some((machine, depth)) = queue.pop_front() {
        assert_public_invariants(&machine);
        let now_ms = (depth as u64).saturating_mul(10).saturating_add(1);

        for event in events.iter().cloned() {
            attempted_transitions += 1;
            let before_snapshot = machine.snapshot();
            let before_signature = behavioral_signature(&machine, now_ms.saturating_add(1));
            let mut candidate = machine.clone();

            match candidate.apply(event, now_ms) {
                Ok(_effects) => {
                    assert_public_invariants(&candidate);
                    if depth < MAX_DEPTH {
                        let key = public_state_key(&candidate);
                        if seen.insert(key) {
                            queue.push_back((candidate, depth + 1));
                        }
                    }
                }
                Err(_error) => {
                    rejected_transitions += 1;
                    assert_eq!(
                        candidate.snapshot(),
                        before_snapshot,
                        "rejected transition changed public state"
                    );
                    assert_eq!(
                        behavioral_signature(&candidate, now_ms.saturating_add(1)),
                        before_signature,
                        "rejected transition changed hidden behavior"
                    );
                }
            }
        }
    }

    assert!(
        seen.len() >= 100,
        "state exploration was unexpectedly shallow"
    );
    assert!(seen.len() < 100_000, "state exploration escaped its bound");
    assert!(attempted_transitions >= seen.len() * events.len());
    assert!(rejected_transitions > attempted_transitions / 3);
}
