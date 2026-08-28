use super::*;
use trillionnium_contract_core::LeaseId;

fn lease() -> LeaseId {
    LeaseId::parse("lease_id", "lease-fixture").unwrap()
}

#[test]
fn human_focus_preempts_agent_work_and_blocks_new_mutation() {
    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::BeginAgentMutation, 0)
        .unwrap();
    let effects = machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
            },
            10,
        )
        .unwrap();
    assert!(effects.contains(&SessionEffect::InterruptAgentWork));
    assert_eq!(machine.snapshot().control, ControlState::HumanActive);
    assert!(
        machine
            .apply(SessionEvent::BeginAgentMutation, 11)
            .is_err()
    );
}

#[test]
fn ime_composition_is_an_explicit_control_state() {
    let mut machine = SessionMachine::new();
    machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
            },
            0,
        )
        .unwrap();
    machine
        .apply(SessionEvent::ImeStarted { lease_id: lease() }, 1)
        .unwrap();
    assert_eq!(
        machine.snapshot().control,
        ControlState::HumanImeComposing
    );
    assert!(
        machine
            .apply(SessionEvent::BeginAgentMutation, 2)
            .is_err()
    );
    machine
        .apply(SessionEvent::ImeEnded { lease_id: lease() }, 3)
        .unwrap();
    assert_eq!(machine.snapshot().control, ControlState::HumanActive);
}

#[test]
fn dom_commits_do_not_globally_invalidate_semantic_refs() {
    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::SemanticSnapshotPublished, 0)
        .unwrap();
    let before = machine.snapshot().revisions;
    machine.apply(SessionEvent::DomCommitted, 1).unwrap();
    let after = machine.snapshot().revisions;
    assert_eq!(after.document_generation, before.document_generation);
    assert_eq!(
        after.semantic_snapshot_revision,
        before.semantic_snapshot_revision
    );
    assert_eq!(after.mutation_epoch, before.mutation_epoch + 1);
}

#[test]
fn navigation_and_crash_invalidate_different_revision_layers() {
    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::SemanticSnapshotPublished, 0)
        .unwrap();
    let original = machine.snapshot().revisions;
    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Agent,
            },
            1,
        )
        .unwrap();
    machine
        .apply(SessionEvent::NavigationCommitted, 2)
        .unwrap();
    let navigated = machine.snapshot().revisions;
    assert_eq!(navigated.session_generation, original.session_generation);
    assert!(navigated.document_generation > original.document_generation);

    machine.apply(SessionEvent::BrowserCrashed, 3).unwrap();
    let crashed = machine.snapshot().revisions;
    assert!(crashed.session_generation > original.session_generation);
    assert_eq!(machine.snapshot().phase, SessionPhase::Recovering);
}

#[test]
fn human_lease_expiry_is_monotonic_and_releases_control() {
    let mut machine = SessionMachine::new();
    machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: 100,
            },
            10,
        )
        .unwrap();
    let effects = machine.apply(SessionEvent::Tick, 110).unwrap();
    assert!(effects.contains(&SessionEffect::HumanLeaseExpired));
    assert_eq!(machine.snapshot().control, ControlState::Idle);
    assert!(machine.snapshot().human_lease.is_none());
}

#[test]
fn bounded_queue_fails_closed_at_capacity() {
    let mut queue = ArbiterQueue::new(2).unwrap();
    queue.push(1).unwrap();
    queue.push(2).unwrap();
    assert_eq!(queue.push(3), Err(QueueError::Full { capacity: 2 }));
    assert_eq!(queue.pop(), Some(1));
    assert_eq!(queue.pop(), Some(2));
}

#[test]
fn close_is_terminal() {
    let mut machine = SessionMachine::new();
    machine.apply(SessionEvent::Close, 0).unwrap();
    assert_eq!(machine.snapshot().phase, SessionPhase::Closed);
    assert_eq!(
        machine.apply(SessionEvent::BeginAgentObservation, 1),
        Err(TransitionError::Closed)
    );
}
