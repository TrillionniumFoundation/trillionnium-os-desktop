use super::*;
use serde_json::json;

fn target() -> CalculatorTargetIdentity {
    CalculatorTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 2,
        incarnation: "2".repeat(32),
    }
}
fn request(id: &str, revision: u64) -> Vec<u8> {
    serde_json::to_vec(&CalculatorEvaluate {
        schema_version: 1,
        action: CalculatorEvaluateAction::Evaluate,
        operation_id: id.into(),
        destination_id: target().destination_id(),
        target: target(),
        expected_revision: revision,
        left: "12".into(),
        operator: CalculatorOperator::Add,
        right: "30".into(),
    })
    .unwrap()
}
fn observe(document: &mut CalculatorDocument, id: &str, payload: &[u8]) -> CalculatorResponse {
    let raw = serde_json::to_vec(&CalculatorObserve {
        schema_version: 1,
        action: CalculatorObserveAction::Observe,
        target: target(),
        operation_id: id.into(),
        payload_sha256: sha256_hex(payload),
    })
    .unwrap();
    CalculatorResponse::parse_exact(&document.recovery_exact(&raw).unwrap()).unwrap()
}
fn acknowledge(receipt: &CalculatorResponse) -> Vec<u8> {
    serde_json::to_vec(&CalculatorAcknowledge {
        schema_version: 1,
        action: CalculatorAcknowledgeAction::Acknowledge,
        target: target(),
        operation_id: receipt.operation_id.clone(),
        payload_sha256: receipt.payload_sha256.clone(),
        receipt_sha256: sha256_hex(&serde_json::to_vec(receipt).unwrap()),
    })
    .unwrap()
}
fn refusal(response: CalculatorResponse, reason: CalculatorNotAppliedReason) {
    assert!(
        matches!(response.result, CalculatorResult::NotApplied { reason: actual, .. } if actual == reason)
    );
}

#[test]
fn checked_integer_profile_has_explicit_non_effects() {
    use CalculatorNotAppliedReason::*;
    use CalculatorOperator::*;
    for (a, op, b, expected) in [
        ("12", Add, "30", "42"),
        ("-12", Subtract, "30", "-42"),
        ("-6", Multiply, "7", "-42"),
        ("-84", Divide, "2", "-42"),
    ] {
        assert_eq!(checked_calculation(a, op, b).unwrap(), expected);
    }
    for operand in [
        "+1",
        "01",
        "-0",
        " 1",
        "1 ",
        "1.0",
        "NaN",
        "9223372036854775808",
    ] {
        assert_eq!(checked_calculation(operand, Add, "0"), Err(InvalidOperand));
    }
    assert_eq!(
        checked_calculation("9223372036854775807", Add, "1"),
        Err(Overflow)
    );
    assert_eq!(
        checked_calculation("-9223372036854775808", Divide, "-1"),
        Err(Overflow)
    );
    assert_eq!(
        checked_calculation("3", Divide, "2"),
        Err(NonIntegralDivision)
    );
    assert_eq!(checked_calculation("1", Divide, "0"), Err(DivisionByZero));
}

#[test]
fn actual_model_mutation_and_independent_readback_bind_exact_bytes() {
    let mut document = CalculatorDocument::new(target()).unwrap();
    let raw = request("original-1", 0);
    let receipt = document.apply_exact(&raw).unwrap();
    assert_eq!(document.state().result, "42");
    assert_eq!(document.revision(), 1);
    assert_eq!(receipt.payload_sha256, sha256_hex(&raw));
    assert_eq!(
        CalculatorResponse::parse_exact(&serde_json::to_vec(&receipt).unwrap()).unwrap(),
        receipt
    );
    let query = json!({"schema_version":1,"action":"read_calculator","target":target(),"observation_id":"3".repeat(32)});
    let state: CalculatorStateObservation = serde_json::from_slice(
        &document
            .recovery_exact(&serde_json::to_vec(&query).unwrap())
            .unwrap(),
    )
    .unwrap();
    assert_eq!(state.state, *document.state());
    assert_eq!(state.state_sha256, document.state().sha256());
    assert_eq!(state.observation_id, "3".repeat(32));
    assert!(state.receipt_pending);
    assert_eq!(observe(&mut document, "original-1", &raw), receipt);
}

#[test]
fn local_edits_share_revision_but_preserve_original_causal_receipt() {
    let mut document = CalculatorDocument::new(target()).unwrap();
    let raw = request("original-1", 0);
    let receipt = document.apply_exact(&raw).unwrap();
    document
        .local_edit(CalculatorValueState {
            left: "99".into(),
            ..document.state().clone()
        })
        .unwrap();
    assert_eq!(document.revision(), 2);
    assert_eq!(document.apply_exact(&raw).unwrap(), receipt);
    assert_eq!(document.state().left, "99");
    assert_eq!(observe(&mut document, "original-1", &raw), receipt);
    refusal(
        document.apply_exact(&request("original-2", 1)).unwrap(),
        CalculatorNotAppliedReason::RevisionConflict,
    );
    refusal(
        document.apply_exact(&request("original-2", 2)).unwrap(),
        CalculatorNotAppliedReason::ReceiptPending,
    );
}

#[test]
fn pending_receipt_is_retired_only_by_exact_original_identity() {
    let mut document = CalculatorDocument::new(target()).unwrap();
    let raw = request("original-1", 0);
    let receipt = document.apply_exact(&raw).unwrap();
    let ack = acknowledge(&receipt);
    let mut wrong: serde_json::Value = serde_json::from_slice(&ack).unwrap();
    wrong["receipt_sha256"] = json!("0".repeat(64));
    let response: CalculatorAcknowledged = serde_json::from_slice(
        &document
            .recovery_exact(&serde_json::to_vec(&wrong).unwrap())
            .unwrap(),
    )
    .unwrap();
    assert_eq!(response.status, CalculatorAcknowledgementStatus::NotRetired);
    assert!(document.receipt_pending());
    let response: CalculatorAcknowledged =
        serde_json::from_slice(&document.recovery_exact(&ack).unwrap()).unwrap();
    assert_eq!(response.status, CalculatorAcknowledgementStatus::Retired);
    assert!(!document.receipt_pending());
    let response: CalculatorAcknowledged =
        serde_json::from_slice(&document.recovery_exact(&ack).unwrap()).unwrap();
    assert_eq!(
        response.status,
        CalculatorAcknowledgementStatus::AlreadyRetired
    );
    assert!(matches!(
        observe(&mut document, "original-1", &raw).result,
        CalculatorResult::Unknown {
            current_revision: 1
        }
    ));
    refusal(
        document.apply_exact(&request("original-1", 1)).unwrap(),
        CalculatorNotAppliedReason::OperationConflict,
    );
    assert!(matches!(
        document
            .apply_exact(&request("original-2", 1))
            .unwrap()
            .result,
        CalculatorResult::Applied { revision: 2, .. }
    ));
}

#[test]
fn semantically_equal_new_serialization_is_not_original_payload() {
    let mut document = CalculatorDocument::new(target()).unwrap();
    let raw = request("original-1", 0);
    document.apply_exact(&raw).unwrap();
    let pretty =
        serde_json::to_vec_pretty(&serde_json::from_slice::<serde_json::Value>(&raw).unwrap())
            .unwrap();
    assert_ne!(sha256_hex(&raw), sha256_hex(&pretty));
    refusal(
        document.apply_exact(&pretty).unwrap(),
        CalculatorNotAppliedReason::OperationConflict,
    );
    assert_eq!(document.revision(), 1);
}

#[test]
fn recovery_lane_rejects_effect_and_never_infers_receipt_from_result() {
    let mut document = CalculatorDocument::new(target()).unwrap();
    let raw = request("never-entered", 0);
    assert_eq!(
        document.recovery_exact(&raw),
        Err(CalculatorProtocolError::Schema)
    );
    document
        .local_edit(CalculatorValueState {
            left: "12".into(),
            operator: Some(CalculatorOperator::Add),
            right: "30".into(),
            result: "42".into(),
        })
        .unwrap();
    assert!(matches!(
        observe(&mut document, "never-entered", &raw).result,
        CalculatorResult::Unknown { .. }
    ));
    assert!(!document.receipt_pending());
}

#[test]
fn new_incarnation_cannot_receive_old_effect_or_readback() {
    let mut other = target();
    other.incarnation = "4".repeat(32);
    assert_ne!(other.scope_sha256(), target().scope_sha256());
    let mut document = CalculatorDocument::new(other).unwrap();
    refusal(
        document.apply_exact(&request("old", 0)).unwrap(),
        CalculatorNotAppliedReason::TargetMismatch,
    );
    let query = json!({"schema_version":1,"action":"read_calculator","target":target(),"observation_id":"3".repeat(32)});
    assert_eq!(
        document.recovery_exact(&serde_json::to_vec(&query).unwrap()),
        Err(CalculatorProtocolError::Target)
    );
    assert_eq!(document.revision(), 0);
}

#[test]
fn bounded_schema_and_observation_nonce_are_checked_before_mutation() {
    let mut raw: serde_json::Value = serde_json::from_slice(&request("one", 0)).unwrap();
    raw["extra"] = json!(true);
    assert_eq!(
        CalculatorEvaluate::parse_exact(&serde_json::to_vec(&raw).unwrap()),
        Err(CalculatorProtocolError::Schema)
    );
    assert_eq!(
        CalculatorEvaluate::parse_exact(&vec![b' '; 4097]),
        Err(CalculatorProtocolError::FrameBound)
    );
    let mut document = CalculatorDocument::new(target()).unwrap();
    let query = json!({"schema_version":1,"action":"read_calculator","target":target(),"observation_id":"0".repeat(32)});
    assert_eq!(
        document.recovery_exact(&serde_json::to_vec(&query).unwrap()),
        Err(CalculatorProtocolError::Digest)
    );
    assert_eq!(document.revision(), 0);
}

#[test]
fn deadline_and_arithmetic_refusals_leave_app_state_unmodified() {
    let mut document = CalculatorDocument::new(target()).unwrap();
    let raw = request("late", 0);
    refusal(
        document.deadline_refusal(&raw).unwrap(),
        CalculatorNotAppliedReason::UiDeadlineElapsed,
    );
    let mut invalid: serde_json::Value = serde_json::from_slice(&raw).unwrap();
    invalid["right"] = json!("not-a-number");
    refusal(
        document
            .apply_exact(&serde_json::to_vec(&invalid).unwrap())
            .unwrap(),
        CalculatorNotAppliedReason::InvalidOperand,
    );
    assert_eq!(document.revision(), 0);
    assert_eq!(*document.state(), CalculatorValueState::default());
    assert!(!document.receipt_pending());
}

#[test]
fn expired_duplicate_preserves_known_applied_and_retired_becomes_unknown() {
    let mut document = CalculatorDocument::new(target()).unwrap();
    let raw = request("original-1", 0);
    let receipt = document.apply_exact(&raw).unwrap();
    document
        .local_edit(CalculatorValueState {
            left: "99".into(),
            ..document.state().clone()
        })
        .unwrap();
    assert_eq!(document.deadline_refusal(&raw).unwrap(), receipt);
    assert_eq!(document.state().left, "99");
    refusal(
        document
            .deadline_refusal(&request("original-1", 2))
            .unwrap(),
        CalculatorNotAppliedReason::OperationConflict,
    );
    let ack = acknowledge(&receipt);
    document.recovery_exact(&ack).unwrap();
    assert!(matches!(
        document.deadline_refusal(&raw).unwrap().result,
        CalculatorResult::Unknown { .. }
    ));
    assert!(matches!(
        document.apply_exact(&raw).unwrap().result,
        CalculatorResult::Unknown { .. }
    ));
    refusal(
        document
            .deadline_refusal(&request("original-2", 2))
            .unwrap(),
        CalculatorNotAppliedReason::UiDeadlineElapsed,
    );
    let second = document.apply_exact(&request("original-2", 2)).unwrap();
    let old: CalculatorAcknowledged =
        serde_json::from_slice(&document.recovery_exact(&ack).unwrap()).unwrap();
    assert_eq!(old.status, CalculatorAcknowledgementStatus::AlreadyRetired);
    assert!(document.receipt_pending());
    assert_eq!(
        observe(&mut document, "original-2", &request("original-2", 2)),
        second
    );
}

#[test]
fn revision_exhaustion_is_atomic_and_applied_response_is_validated() {
    let mut document = CalculatorDocument::new(target()).unwrap();
    document.revision = u64::MAX;
    refusal(
        document.apply_exact(&request("last", u64::MAX)).unwrap(),
        CalculatorNotAppliedReason::RevisionExhausted,
    );
    assert!(document
        .local_edit(CalculatorValueState {
            left: "1".into(),
            ..Default::default()
        })
        .is_err());
    assert_eq!(*document.state(), CalculatorValueState::default());
    let mut other = CalculatorDocument::new(target()).unwrap();
    let receipt = other.apply_exact(&request("ok", 0)).unwrap();
    let mut value = serde_json::to_value(receipt).unwrap();
    value["result"]["state"]["result"] = json!("43");
    assert_eq!(
        CalculatorResponse::parse_exact(&serde_json::to_vec(&value).unwrap()),
        Err(CalculatorProtocolError::Receipt)
    );
}

#[test]
fn emit_cross_repository_wire_fixture_from_app_serialization() {
    let mut document = CalculatorDocument::new(target()).unwrap();
    let payload = request("original-1", 0);
    let receipt = document.apply_exact(&payload).unwrap();
    let applied = serde_json::to_vec(&receipt).unwrap();
    let read = serde_json::to_vec(&CalculatorRead {
        schema_version: 1,
        action: CalculatorReadAction::ReadCalculator,
        target: target(),
        observation_id: "3".repeat(32),
    })
    .unwrap();
    let readback = document.recovery_exact(&read).unwrap();
    let ack = acknowledge(&receipt);
    let acknowledged = document.recovery_exact(&ack).unwrap();
    let fixture = json!({
        "schema":"trill.calculator.wire-fixture.v1",
        "scope":"MODEL_SERIALIZATION_ONLY; not real GUI or original-owner acceptance",
        "target":target(),
        "scope_sha256":target().scope_sha256(),
        "predecessor_sha256":target().predecessor_sha256(0),
        "state_sha256":document.state().sha256(),
        "request_sha256":sha256_hex(&payload),
        "receipt_sha256":sha256_hex(&applied),
        "request_bytes":String::from_utf8(payload).unwrap(),
        "applied_bytes":String::from_utf8(applied).unwrap(),
        "read_request_bytes":String::from_utf8(read).unwrap(),
        "readback_bytes":String::from_utf8(readback).unwrap(),
        "acknowledge_request_bytes":String::from_utf8(ack).unwrap(),
        "acknowledged_bytes":String::from_utf8(acknowledged).unwrap()
    });
    println!("CALCULATOR_WIRE_FIXTURE_V1 {fixture}");
}
