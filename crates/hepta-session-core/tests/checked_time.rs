use hepta_session_core::{
    ControlState, SessionEvent, SessionMachine, SessionPhase, TransitionError,
};
use trillionnium_contract_core::LeaseId;

#[test]
fn lease_deadline_overflow_is_rejected_without_state_change() {
    let mut machine = SessionMachine::new();
    let before = machine.snapshot();

    let result = machine.apply(
        SessionEvent::HumanFocusGained {
            lease_id: LeaseId::parse("lease_id", "lease-overflow").unwrap(),
            ttl_ms: 1,
        },
        u64::MAX,
    );

    assert_eq!(result, Err(TransitionError::TimeOverflow));
    let after = machine.snapshot();
    assert_eq!(after.control, ControlState::Idle);
    assert_eq!(after.phase, SessionPhase::Ready);
    assert_eq!(after, before);
}
