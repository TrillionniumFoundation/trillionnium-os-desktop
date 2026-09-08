use hepta_session_core::{
    ControlState, SessionEvent, SessionMachine, SessionPhase, TransitionError,
};
use trillionnium_contract_core::LeaseId;

fn lease(value: &str) -> LeaseId {
    LeaseId::parse("lease_id", value).unwrap()
}

#[test]
fn lease_acquisition_overflow_is_rejected_without_state_change() {
    let mut machine = SessionMachine::new();
    let before = machine.snapshot();

    let result = machine.apply(
        SessionEvent::HumanFocusGained {
            lease_id: lease("lease-acquisition-overflow"),
            ttl_ms: 1,
        },
        u64::MAX,
    );

    assert_eq!(result, Err(TransitionError::TimeOverflow));
    assert_eq!(machine.snapshot(), before);
    assert_eq!(machine.snapshot().control, ControlState::Idle);
    assert_eq!(machine.snapshot().phase, SessionPhase::Ready);
}

#[test]
fn lease_extension_overflow_is_rejected_without_state_change() {
    let mut machine = SessionMachine::new();
    let lease_id = lease("lease-extension-overflow");
    machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease_id.clone(),
                ttl_ms: 20,
            },
            u64::MAX - 20,
        )
        .unwrap();

    let before = machine.snapshot();
    assert_eq!(before.control, ControlState::HumanActive);
    assert_eq!(
        before.human_lease.as_ref().map(|value| value.expires_at_ms),
        Some(u64::MAX)
    );

    let result = machine.apply(
        SessionEvent::HumanInput {
            lease_id,
            extend_by_ms: 2,
        },
        u64::MAX - 1,
    );

    assert_eq!(result, Err(TransitionError::TimeOverflow));
    assert_eq!(machine.snapshot(), before);
}
