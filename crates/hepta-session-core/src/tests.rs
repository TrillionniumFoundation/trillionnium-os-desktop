use super::*;
use trillionnium_contract_core::LeaseId;

fn lease() -> LeaseId {
    LeaseId::parse("lease_id", "lease-fixture").unwrap()
}

#[test]
fn human_focus_preempts_agent_work_and_blocks_new_mutation() {
    let mut machine = SessionMachine::new();
    machine.apply(SessionEvent::BeginAgentMutation, 0).unwrap();
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
    assert!(machine.apply(SessionEvent::BeginAgentMutation, 11).is_err());
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
    assert_eq!(machine.snapshot().control, ControlState::HumanImeComposing);
    assert!(machine.apply(SessionEvent::BeginAgentMutation, 2).is_err());
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
    machine.apply(SessionEvent::NavigationCommitted, 2).unwrap();
    let navigated = machine.snapshot().revisions;
    assert_eq!(navigated.session_generation, original.session_generation);
    assert!(navigated.document_generation > original.document_generation);

    machine.apply(SessionEvent::BrowserCrashed, 3).unwrap();
    let crashed = machine.snapshot().revisions;
    assert!(crashed.session_generation > original.session_generation);
    assert_eq!(machine.snapshot().phase, SessionPhase::Recovering);
}

#[test]
fn revision_exhaustion_fails_closed_without_partial_session_transition() {
    let mut machine = SessionMachine::new();
    machine.revisions_mut_for_test().mutation_epoch = u64::MAX;
    let before = machine.snapshot();
    assert_eq!(
        machine.apply(SessionEvent::DomCommitted, 0),
        Err(TransitionError::RevisionExhausted)
    );
    assert_eq!(machine.snapshot(), before);

    let mut machine = SessionMachine::new();
    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Agent,
            },
            0,
        )
        .unwrap();
    machine.revisions_mut_for_test().document_generation = u64::MAX;
    let before = machine.snapshot();
    assert_eq!(
        machine.apply(SessionEvent::NavigationCommitted, 1),
        Err(TransitionError::RevisionExhausted)
    );
    assert_eq!(machine.snapshot(), before);

    let mut machine = SessionMachine::new();
    machine.revisions_mut_for_test().session_generation = u64::MAX;
    let before = machine.snapshot();
    assert_eq!(
        machine.apply(SessionEvent::BrowserCrashed, 0),
        Err(TransitionError::RevisionExhausted)
    );
    assert_eq!(machine.snapshot(), before);
}

#[test]
fn agent_navigation_requires_idle_control_but_human_navigation_is_preserved() {
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
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Human,
            },
            1,
        )
        .expect("human navigation remains an adapter-owned transition");
    assert_eq!(machine.snapshot().phase, SessionPhase::NavigationPending);

    let mut machine = SessionMachine::new();
    machine
        .apply(SessionEvent::BeginAgentObservation, 0)
        .unwrap();
    assert_eq!(
        machine.apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Agent,
            },
            1,
        ),
        Err(TransitionError::ControlConflict(
            ControlState::AgentObserving
        ))
    );
    assert_eq!(machine.snapshot().phase, SessionPhase::Ready);
}

#[test]
fn human_input_requires_human_control_after_adapter_navigation() {
    let mut machine = SessionMachine::new();
    machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
            },
            0,
        )
        .expect("human focus");
    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Human,
            },
            1,
        )
        .expect("adapter-owned human navigation");
    machine
        .apply(SessionEvent::NavigationCommitted, 2)
        .expect("navigation commit");

    let snapshot = machine.snapshot();
    assert_eq!(snapshot.control, ControlState::Idle);
    assert!(snapshot.human_lease.is_some());
    assert_eq!(
        machine.apply(
            SessionEvent::HumanInput {
                lease_id: lease(),
                extend_by_ms: 100,
            },
            3,
        ),
        Err(TransitionError::ControlConflict(ControlState::Idle))
    );
    // The stale lease remains available for an adapter's explicit focus
    // release, but it cannot be used to extend or authorize input.
    machine
        .apply(SessionEvent::HumanFocusReleased { lease_id: lease() }, 4)
        .expect("adapter can release the retained lease");
    assert!(machine.snapshot().human_lease.is_none());
}

#[test]
fn agent_navigation_owns_control_until_terminal_event() {
    let mut machine = SessionMachine::new();
    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Agent,
            },
            0,
        )
        .expect("Agent navigation starts from idle");
    assert_eq!(machine.snapshot().control, ControlState::AgentNavigating);
    assert_eq!(machine.snapshot().phase, SessionPhase::NavigationPending);

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
    assert_eq!(
        machine.apply(SessionEvent::BeginAgentObservation, 1),
        Err(TransitionError::PhaseConflict(
            SessionPhase::NavigationPending
        ))
    );
    assert_eq!(
        machine.apply(
            SessionEvent::HumanInput {
                lease_id: lease(),
                extend_by_ms: 100,
            },
            1,
        ),
        Err(TransitionError::PhaseConflict(
            SessionPhase::NavigationPending
        ))
    );

    machine
        .apply(SessionEvent::NavigationCommitted, 2)
        .expect("navigation commit");
    assert_eq!(machine.snapshot().control, ControlState::Idle);
    assert_eq!(machine.snapshot().phase, SessionPhase::Ready);
    machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
            },
            3,
        )
        .expect("human focus is admitted after navigation completes");
}

#[test]
fn cancelled_agent_navigation_rejects_late_terminal_event() {
    let mut machine = SessionMachine::new();
    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Agent,
            },
            0,
        )
        .expect("Agent navigation starts");
    machine
        .apply(SessionEvent::CancelRequested, 1)
        .expect("cancellation starts");
    assert_eq!(machine.snapshot().phase, SessionPhase::Cancelling);
    assert_eq!(machine.snapshot().control, ControlState::AgentNavigating);

    assert_eq!(
        machine.apply(SessionEvent::NavigationFailed, 2),
        Err(TransitionError::PhaseConflict(SessionPhase::Cancelling))
    );
    assert_eq!(
        machine.apply(SessionEvent::NavigationCommitted, 2),
        Err(TransitionError::PhaseConflict(SessionPhase::Cancelling))
    );
    machine
        .apply(SessionEvent::CancelCompleted, 3)
        .expect("cancellation completes");
    assert_eq!(machine.snapshot().phase, SessionPhase::Ready);
    assert_eq!(machine.snapshot().control, ControlState::Idle);
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
fn human_lease_expiration_overflow_fails_closed() {
    let mut machine = SessionMachine::new();
    assert_eq!(
        machine.apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
            },
            u64::MAX - 1,
        ),
        Err(TransitionError::InvalidTransition(
            "human lease expiration overflowed",
        ))
    );
    assert_eq!(machine.snapshot().control, ControlState::Idle);
    assert!(machine.snapshot().human_lease.is_none());

    machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: 5,
            },
            u64::MAX - 10,
        )
        .expect("lease before the boundary");
    let before = machine.snapshot();
    assert_eq!(
        machine.apply(
            SessionEvent::HumanInput {
                lease_id: lease(),
                extend_by_ms: 11,
            },
            u64::MAX - 10,
        ),
        Err(TransitionError::InvalidTransition(
            "human lease expiration overflowed",
        ))
    );
    assert_eq!(machine.snapshot(), before);
}

#[test]
fn cancellation_revokes_human_lease_and_blocks_new_human_input() {
    let mut machine = SessionMachine::new();
    machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
            },
            10,
        )
        .unwrap();

    machine.apply(SessionEvent::CancelRequested, 11).unwrap();
    let cancelling = machine.snapshot();
    assert_eq!(cancelling.phase, SessionPhase::Cancelling);
    assert_eq!(cancelling.control, ControlState::Idle);
    assert!(cancelling.human_lease.is_none());

    assert_eq!(
        machine.apply(
            SessionEvent::HumanInput {
                lease_id: lease(),
                extend_by_ms: 100,
            },
            12,
        ),
        Err(TransitionError::PhaseConflict(SessionPhase::Cancelling))
    );
    assert_eq!(
        machine.apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease(),
                ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
            },
            12,
        ),
        Err(TransitionError::PhaseConflict(SessionPhase::Cancelling))
    );
    assert_eq!(
        machine.apply(SessionEvent::HumanFocusReleased { lease_id: lease() }, 12,),
        Err(TransitionError::PhaseConflict(SessionPhase::Cancelling))
    );
    assert_eq!(
        machine.apply(SessionEvent::ImeStarted { lease_id: lease() }, 12),
        Err(TransitionError::PhaseConflict(SessionPhase::Cancelling))
    );

    machine.apply(SessionEvent::CancelCompleted, 13).unwrap();
    assert_eq!(machine.snapshot().phase, SessionPhase::Ready);
    assert_eq!(machine.snapshot().control, ControlState::Idle);
    assert!(machine.snapshot().human_lease.is_none());
    assert_eq!(
        machine.apply(
            SessionEvent::HumanInput {
                lease_id: lease(),
                extend_by_ms: 100,
            },
            14,
        ),
        Err(TransitionError::HumanLeaseRequired)
    );
}

#[test]
fn cancellation_revokes_ime_lease_and_completes_idle() {
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

    machine.apply(SessionEvent::CancelRequested, 2).unwrap();
    assert_eq!(machine.snapshot().control, ControlState::Idle);
    assert!(machine.snapshot().human_lease.is_none());
    machine.apply(SessionEvent::CancelCompleted, 3).unwrap();
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
