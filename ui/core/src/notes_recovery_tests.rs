use super::*;
use crate::notes_recovery::{
    NotesAcknowledge, NotesAcknowledgeAction, NotesRetirementResponse, NotesRetirementStatus,
};

fn fixture() -> serde_json::Value {
    serde_json::from_str(include_str!("../../../tests/ui/notes-target-v1.json")).unwrap()
}

#[test]
fn pending_receipt_survives_new_effects_and_only_exact_ack_releases_capacity() {
    let fixture = fixture();
    let raw = fixture["request_utf8"].as_str().unwrap().as_bytes();
    let request = NotesReplace::parse_exact(raw).unwrap();
    let mut document = NotesDocument::new(request.target.clone()).unwrap();
    let receipt = document.apply_exact(raw).unwrap();
    let mut next = request.clone();
    next.operation_id = "next-operation".into();
    next.expected_revision = 1;
    next.text = "next document".into();
    let next_raw = serde_json::to_vec(&next).unwrap();
    assert!(matches!(
        document.apply_exact(&next_raw).unwrap().result,
        NotesResult::NotApplied {
            reason: NotesNotAppliedReason::ReceiptPending,
            ..
        }
    ));
    assert_eq!(document.revision(), 1);
    assert!(document.recovery_exact(&next_raw).is_err());
    assert_eq!(
        document.revision(),
        1,
        "recovery lane rejects effects at the receiver"
    );
    let mut ack = NotesAcknowledge {
        schema_version: NOTES_SCHEMA_VERSION,
        action: NotesAcknowledgeAction::AcknowledgeTerminal,
        target: request.target,
        operation_id: request.operation_id,
        payload_sha256: sha256_hex(raw),
        receipt_sha256: "0".repeat(64),
    };
    let response: NotesRetirementResponse = serde_json::from_slice(
        &document
            .recovery_exact(&serde_json::to_vec(&ack).unwrap())
            .unwrap(),
    )
    .unwrap();
    assert_eq!(response.status, NotesRetirementStatus::Unknown);
    assert_eq!(document.apply_exact(raw).unwrap(), receipt);
    ack.receipt_sha256 = sha256_hex(&serde_json::to_vec(&receipt).unwrap());
    for expected in [
        NotesRetirementStatus::Released,
        NotesRetirementStatus::AlreadyReleased,
    ] {
        let response: NotesRetirementResponse = serde_json::from_slice(
            &document
                .recovery_exact(&serde_json::to_vec(&ack).unwrap())
                .unwrap(),
        )
        .unwrap();
        assert_eq!(response.status, expected);
        assert_eq!(
            document.revision(),
            1,
            "receipt retirement never edits the document"
        );
    }
    assert!(matches!(
        document.apply_exact(&next_raw).unwrap().result,
        NotesResult::Applied { revision: 2, .. }
    ));
    // A late retry of the previous ACK cannot discard the next pending receipt.
    document
        .recovery_exact(&serde_json::to_vec(&ack).unwrap())
        .unwrap();
    assert_eq!(
        document.apply_exact(&next_raw).unwrap().result,
        NotesResult::Applied {
            previous_revision: 1,
            revision: 2,
            text_sha256: sha256_hex(next.text.as_bytes())
        }
    );
}

#[test]
fn recovery_golden_matches_exact_receipt_and_ack_bytes() {
    let target_fixture = fixture();
    let recovery: serde_json::Value =
        serde_json::from_str(include_str!("../../../tests/ui/notes-recovery-v1.json")).unwrap();
    let raw = target_fixture["request_utf8"].as_str().unwrap().as_bytes();
    let request = NotesReplace::parse_exact(raw).unwrap();
    let mut document = NotesDocument::new(request.target).unwrap();
    document.apply_exact(raw).unwrap();
    let query = recovery["observe_utf8"].as_str().unwrap().as_bytes();
    assert_eq!(
        document.recovery_exact(query).unwrap(),
        target_fixture["application_response_utf8"]
            .as_str()
            .unwrap()
            .as_bytes()
    );
    let ack = recovery["acknowledge_utf8"].as_str().unwrap().as_bytes();
    assert_eq!(
        document.recovery_exact(ack).unwrap(),
        recovery["released_utf8"].as_str().unwrap().as_bytes()
    );
    assert_eq!(
        document.recovery_exact(ack).unwrap(),
        recovery["already_released_utf8"]
            .as_str()
            .unwrap()
            .as_bytes()
    );
}
