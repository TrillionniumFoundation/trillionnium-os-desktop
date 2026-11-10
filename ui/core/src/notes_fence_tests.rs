use super::*;
use crate::notes_recovery::{NotesAcknowledge, NotesAcknowledgeAction};

fn identity() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "a".repeat(32),
        task_id: 1,
        incarnation: "b".repeat(32),
    }
}

fn replace(id: &str, revision: u64) -> Vec<u8> {
    serde_json::to_vec(&NotesReplace {
        schema_version: 1,
        action: NotesReplaceAction::ReplaceNote,
        operation_id: id.into(),
        destination_id: identity().destination_id(),
        target: identity(),
        expected_revision: revision,
        text: "original goal".into(),
    })
    .unwrap()
}

fn fence(original: &[u8], id: &str) -> Vec<u8> {
    let original_request = NotesReplace::parse_exact(original).unwrap();
    serde_json::to_vec(&NotesFence {
        schema_version: 1,
        action: NotesFenceAction::FenceNoteOperation,
        operation_id: id.into(),
        destination_id: identity().destination_id(),
        target: identity(),
        original_operation_id: original_request.operation_id,
        original_payload_sha256: sha256_hex(original),
        expected_revision: original_request.expected_revision,
    })
    .unwrap()
}

fn ack(receipt: &NotesFenceResponse) -> Vec<u8> {
    serde_json::to_vec(&NotesAcknowledge {
        schema_version: 1,
        action: NotesAcknowledgeAction::AcknowledgeTerminal,
        target: identity(),
        operation_id: receipt.operation_id.clone(),
        payload_sha256: receipt.payload_sha256.clone(),
        receipt_sha256: sha256_hex(&serde_json::to_vec(receipt).unwrap()),
    })
    .unwrap()
}

#[test]
fn fence_first_excludes_late_original_after_restore_and_retirement() {
    let original = replace("original", 0);
    let cancel = fence(&original, "cancel");
    let mut document = NotesDocument::new(identity()).unwrap();
    assert!(document.recovery_exact(&cancel).is_err());
    assert_eq!(document.revision(), 0);
    let receipt = document.fence_exact(&cancel).unwrap();
    assert!(matches!(
        receipt.result,
        NotesFenceResult::Fenced {
            previous_revision: 0,
            revision: 1,
            ..
        }
    ));
    assert_eq!(document.text(), "");
    assert_eq!(document.fence_exact(&cancel).unwrap(), receipt);
    let bytes = document.checkpoint().unwrap();
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&bytes).unwrap()["schema_version"],
        3
    );
    let mut restored = NotesDocument::restore_checkpoint(&bytes, &identity()).unwrap();
    let query = serde_json::json!({"schema_version":1,"action":"observe_fence","target":identity(),
        "operation_id":"cancel","payload_sha256":sha256_hex(&cancel)});
    assert_eq!(
        NotesFenceResponse::parse_exact(
            &restored
                .recovery_exact(&serde_json::to_vec(&query).unwrap())
                .unwrap()
        )
        .unwrap(),
        receipt
    );
    assert!(matches!(
        restored.apply_exact(&original).unwrap().result,
        NotesResult::NotApplied {
            reason: NotesNotAppliedReason::RevisionConflict,
            ..
        }
    ));
    let mut wrong = serde_json::from_slice::<serde_json::Value>(&ack(&receipt)).unwrap();
    wrong["receipt_sha256"] = serde_json::json!("0".repeat(64));
    restored
        .recovery_exact(&serde_json::to_vec(&wrong).unwrap())
        .unwrap();
    assert!(matches!(
        restored.apply_exact(&replace("next", 1)).unwrap().result,
        NotesResult::NotApplied {
            reason: NotesNotAppliedReason::ReceiptPending,
            ..
        }
    ));
    restored.recovery_exact(&ack(&receipt)).unwrap();
    let after_ack = restored.checkpoint().unwrap();
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&after_ack).unwrap()["schema_version"],
        3
    );
    let mut recovered = NotesDocument::restore_checkpoint(&after_ack, &identity()).unwrap();
    assert!(matches!(
        recovered.apply_exact(&original).unwrap().result,
        NotesResult::NotApplied {
            reason: NotesNotAppliedReason::RevisionConflict,
            ..
        }
    ));
    assert!(matches!(
        recovered.apply_exact(&replace("next", 1)).unwrap().result,
        NotesResult::Applied { revision: 2, .. }
    ));
}

#[test]
fn apply_first_is_preserved_and_never_reported_as_fenced() {
    let original = replace("original", 0);
    let cancel = fence(&original, "cancel");
    let mut document = NotesDocument::new(identity()).unwrap();
    let applied = document.apply_exact(&original).unwrap();
    assert!(matches!(
        document.fence_exact(&cancel).unwrap().result,
        NotesFenceResult::NotFenced {
            reason: NotesNotAppliedReason::RevisionConflict,
            current_revision: 1
        }
    ));
    assert_eq!(document.apply_exact(&original).unwrap(), applied);
    assert_eq!(document.text(), "original goal");
    assert_eq!(document.revision(), 1);
}

#[test]
fn fence_checkpoint_rejects_missing_or_conflicting_facts() {
    let mut document = NotesDocument::new(identity()).unwrap();
    document
        .fence_exact(&fence(&replace("original", 0), "cancel"))
        .unwrap();
    let checkpoint: serde_json::Value =
        serde_json::from_slice(&document.checkpoint().unwrap()).unwrap();
    for field in [
        "pending_fence_receipt",
        "pending_receipt",
        "retired_receipt",
    ] {
        let mut bad = checkpoint.clone();
        bad.as_object_mut().unwrap().remove(field);
        assert!(
            NotesDocument::restore_checkpoint(&serde_json::to_vec(&bad).unwrap(), &identity())
                .is_err()
        );
    }
    let mut bad = checkpoint;
    bad["pending_fence_receipt"]["result"]["text_sha256"] = serde_json::json!("0".repeat(64));
    assert!(
        NotesDocument::restore_checkpoint(&serde_json::to_vec(&bad).unwrap(), &identity()).is_err()
    );
}
