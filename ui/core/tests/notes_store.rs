#![cfg(target_os = "linux")]

use std::fs;
use std::os::unix::fs::symlink;
use std::path::PathBuf;
#[path = "common/notes_store.rs"]
mod common;
use common::*;
use trill_ui_core::notes::*;
use trill_ui_core::notes_recovery::*;
use trill_ui_core::notes_store::{NotesStore, MAX_SAVED_NOTES};

fn document_directory(root: &Directory) -> PathBuf {
    root.0
        .join(format!("{}-1-{}", "a".repeat(32), "b".repeat(32)))
}

#[test]
fn saved_text_opens_under_new_identity_without_receipts_or_old_effect_capability() {
    let root = Directory::new();
    let mut original = NotesStore::create(&root.0, target()).unwrap();
    let original_receipt = original.apply_exact(&request()).unwrap();
    original
        .local_edit("用户继续编辑的笔记\n第二行".into())
        .unwrap();
    drop(original);
    let old_path = document_directory(&root).join("document.json");
    let old_bytes = fs::read(&old_path).unwrap();
    let mut reopened = NotesStore::create(&root.0, reopened_target()).unwrap();
    let listing = NotesStore::saved_documents(&root.0, &reopened_target()).unwrap();
    assert_eq!(listing.documents.len(), 1);
    let selected = &listing.documents[0];
    assert_eq!(selected.target, target());
    assert_eq!(selected.revision, 2);
    assert_eq!(selected.preview, "用户继续编辑的笔记");
    reopened.restore_saved_text(&root.0, selected, 0).unwrap();
    assert_eq!(reopened.text(), "用户继续编辑的笔记\n第二行");
    assert_eq!(reopened.revision(), 1);
    let state = read_state(&mut reopened, &reopened_target());
    assert_eq!(
        state["target"],
        serde_json::to_value(reopened_target()).unwrap()
    );
    assert_eq!(state["receipt_pending"], false);
    assert!(matches!(
        reopened.apply_exact(&request()).unwrap().result,
        NotesResult::NotApplied {
            reason: NotesNotAppliedReason::TargetMismatch,
            ..
        }
    ));
    assert!(reopened.recovery_exact(&query()).is_err());
    assert_eq!(fs::read(&old_path).unwrap(), old_bytes);
    drop(reopened);
    let mut saved_copy = NotesStore::recover(&root.0, &reopened_target()).unwrap();
    assert_eq!(saved_copy.text(), "用户继续编辑的笔记\n第二行");
    assert_eq!(
        read_state(&mut saved_copy, &reopened_target())["receipt_pending"],
        false
    );
    let mut original_recovery = NotesStore::recover(&root.0, &target()).unwrap();
    assert_eq!(
        NotesResponse::parse_exact(&original_recovery.recovery_exact(&query()).unwrap()).unwrap(),
        original_receipt
    );
}

#[test]
fn changed_source_and_intervening_current_edits_are_not_overwritten() {
    let root = Directory::new();
    let mut original = NotesStore::create(&root.0, target()).unwrap();
    original.local_edit("first saved text".into()).unwrap();
    drop(original);
    let mut reopened = NotesStore::create(&root.0, reopened_target()).unwrap();
    let selected = NotesStore::saved_documents(&root.0, &reopened_target())
        .unwrap()
        .documents
        .remove(0);
    // A valid but newer source snapshot replaces the one displayed by the picker.
    let path = document_directory(&root).join("document.json");
    let mut newer =
        NotesDocument::restore_checkpoint(&fs::read(&path).unwrap(), &target()).unwrap();
    newer.local_edit("changed after selection".into()).unwrap();
    fs::write(&path, newer.checkpoint().unwrap()).unwrap();
    assert!(reopened.restore_saved_text(&root.0, &selected, 0).is_err());
    assert_eq!(reopened.text(), "");
    assert_eq!(reopened.revision(), 0);
    assert!(!reopened.is_frozen());
    let refreshed = NotesStore::saved_documents(&root.0, &reopened_target())
        .unwrap()
        .documents
        .remove(0);
    reopened.local_edit("keep my new edits".into()).unwrap();
    assert!(reopened.restore_saved_text(&root.0, &refreshed, 0).is_err());
    assert!(reopened.restore_saved_text(&root.0, &refreshed, 1).is_err());
    assert_eq!(reopened.text(), "keep my new edits");
    assert_eq!(reopened.revision(), 1);
}

#[test]
fn saved_picker_and_restore_refuse_locked_or_symlinked_sources() {
    let root = Directory::new();
    let mut original = NotesStore::create(&root.0, target()).unwrap();
    original.local_edit("private saved text".into()).unwrap();
    drop(original);
    let mut reopened = NotesStore::create(&root.0, reopened_target()).unwrap();
    let selected = NotesStore::saved_documents(&root.0, &reopened_target())
        .unwrap()
        .documents
        .remove(0);
    let original_owner = NotesStore::recover(&root.0, &target()).unwrap();
    assert!(reopened.restore_saved_text(&root.0, &selected, 0).is_err());
    let busy = NotesStore::saved_documents(&root.0, &reopened_target()).unwrap();
    assert!(busy.documents.is_empty());
    assert_eq!(busy.unavailable, 1);
    drop(original_owner);
    let path = document_directory(&root).join("document.json");
    let outside = root.0.join("do-not-follow.json");
    fs::rename(&path, &outside).unwrap();
    let before = fs::read(&outside).unwrap();
    symlink(&outside, &path).unwrap();
    assert!(reopened.restore_saved_text(&root.0, &selected, 0).is_err());
    assert!(NotesStore::saved_documents(&root.0, &reopened_target())
        .unwrap()
        .documents
        .is_empty());
    assert_eq!(fs::read(&outside).unwrap(), before);
    assert_eq!(reopened.revision(), 0);
    assert!(!reopened.is_frozen());
}

#[test]
fn failed_restore_write_freezes_only_the_new_incarnation_and_retains_original() {
    let root = Directory::new();
    let mut original = NotesStore::create(&root.0, target()).unwrap();
    original.apply_exact(&request()).unwrap();
    drop(original);
    let old_path = document_directory(&root).join("document.json");
    let old_bytes = fs::read(&old_path).unwrap();
    let mut reopened = NotesStore::create(&root.0, reopened_target()).unwrap();
    let selected = NotesStore::saved_documents(&root.0, &reopened_target())
        .unwrap()
        .documents
        .remove(0);
    let next = root
        .0
        .join(format!("{}-2-{}", "c".repeat(32), "d".repeat(32)))
        .join("next.json");
    symlink(&old_path, next).unwrap();
    assert!(reopened.restore_saved_text(&root.0, &selected, 0).is_err());
    assert!(reopened.is_frozen());
    assert!(reopened.local_edit("no retry".into()).is_err());
    assert_eq!(fs::read(&old_path).unwrap(), old_bytes);
    drop(reopened);
    let mut recovered = NotesStore::recover(&root.0, &reopened_target()).unwrap();
    assert_eq!(recovered.text(), "");
    assert_eq!(recovered.revision(), 0);
    assert_eq!(
        read_state(&mut recovered, &reopened_target())["receipt_pending"],
        false
    );
}

#[test]
fn saved_picker_is_bounded_and_keeps_utf8_previews_intact() {
    let root = Directory::new();
    for index in 1..=MAX_SAVED_NOTES + 1 {
        let identity = NotesTargetIdentity {
            session_instance: "a".repeat(32),
            task_id: index as u64,
            incarnation: format!("{index:032x}"),
        };
        let mut original = NotesStore::create(&root.0, identity).unwrap();
        original
            .local_edit(format!("{} {index}", "中".repeat(100)))
            .unwrap();
    }
    let listing = NotesStore::saved_documents(&root.0, &reopened_target()).unwrap();
    assert!(listing.truncated);
    assert_eq!(listing.documents.len(), MAX_SAVED_NOTES);
    assert!(listing
        .documents
        .iter()
        .all(|entry| entry.preview == "中".repeat(80)));
    assert_eq!(listing.unavailable, 0);
}

#[test]
fn recovery_preserves_exact_receipt_and_retirement_without_restoring_effects() {
    let root = Directory::new();
    let mut app = NotesStore::create(&root.0, target()).unwrap();
    let receipt = app.apply_exact(&request()).unwrap();
    assert!(NotesStore::recover(&root.0, &target()).is_err());
    assert!(NotesStore::create(&root.0, target()).is_err());
    app.local_edit("local edit after the original effect".into())
        .unwrap();
    drop(app);
    let mut recovered = NotesStore::recover(&root.0, &target()).unwrap();
    assert_eq!(recovered.revision(), 2);
    assert_eq!(recovered.text(), "local edit after the original effect");
    assert_eq!(
        NotesResponse::parse_exact(&recovered.recovery_exact(&query()).unwrap()).unwrap(),
        receipt
    );
    assert!(recovered.apply_exact(&request()).is_err());
    assert!(recovered.local_edit("must not apply".into()).is_err());
    assert!(recovered.recovery_exact(&request()).is_err());
    let ack = serde_json::to_vec(&NotesAcknowledge {
        schema_version: NOTES_SCHEMA_VERSION,
        action: NotesAcknowledgeAction::AcknowledgeTerminal,
        target: target(),
        operation_id: receipt.operation_id.clone(),
        payload_sha256: receipt.payload_sha256.clone(),
        receipt_sha256: sha256_hex(&serde_json::to_vec(&receipt).unwrap()),
    })
    .unwrap();
    let first: NotesRetirementResponse =
        serde_json::from_slice(&recovered.recovery_exact(&ack).unwrap()).unwrap();
    assert_eq!(first.status, NotesRetirementStatus::Released);
    drop(recovered);
    let mut again = NotesStore::recover(&root.0, &target()).unwrap();
    let second: NotesRetirementResponse =
        serde_json::from_slice(&again.recovery_exact(&ack).unwrap()).unwrap();
    assert_eq!(second.status, NotesRetirementStatus::AlreadyReleased);
    assert_eq!(again.revision(), 2);
}

#[test]
fn corrupt_or_rebound_checkpoints_are_rejected() {
    let root = Directory::new();
    let mut store = NotesStore::create(&root.0, target()).unwrap();
    store.apply_exact(&request()).unwrap();
    drop(store);
    let path = document_directory(&root).join("document.json");
    let original = fs::read(&path).unwrap();
    let mut value: serde_json::Value = serde_json::from_slice(&original).unwrap();
    value["text"] = "different effect".into();
    fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
    assert!(NotesStore::recover(&root.0, &target()).is_err());
    fs::write(&path, &original).unwrap();
    let mut other = target();
    other.incarnation = "c".repeat(32);
    assert!(NotesDocument::restore_checkpoint(&original, &other).is_err());
    fs::remove_file(&path).unwrap();
    let elsewhere = root.0.join("other.json");
    fs::write(&elsewhere, &original).unwrap();
    symlink(&elsewhere, &path).unwrap();
    assert!(NotesStore::recover(&root.0, &target()).is_err());
}

#[test]
fn original_hepta_read_contract_is_correlated_and_reflects_pending_receipt() {
    let root = Directory::new();
    let mut store = NotesStore::create(&root.0, target()).unwrap();
    let query = serde_json::json!({
        "schema_version": 1, "action": "read_document_state", "target": target(),
        "request_id": "d".repeat(32),
    });
    let raw = serde_json::to_vec(&query).unwrap();
    let initial: serde_json::Value =
        serde_json::from_slice(&store.recovery_exact(&raw).unwrap()).unwrap();
    assert_eq!(
        initial,
        serde_json::json!({
            "schema_version":1, "action":"document_state", "target":target(),
            "request_id":"d".repeat(32), "revision":0, "text_sha256":sha256_hex(b""),
            "receipt_pending":false,
        })
    );
    store.apply_exact(&request()).unwrap();
    let applied: serde_json::Value =
        serde_json::from_slice(&store.recovery_exact(&raw).unwrap()).unwrap();
    assert_eq!(
        applied,
        serde_json::json!({
            "schema_version":1, "action":"document_state", "target":target(),
            "request_id":"d".repeat(32), "revision":1,
            "text_sha256":sha256_hex("重启后仍可核对的原始效果".as_bytes()), "receipt_pending":true,
        })
    );
    let mut invalid = query;
    invalid["request_id"] = "nonce is not valid".into();
    assert!(store
        .recovery_exact(&serde_json::to_vec(&invalid).unwrap())
        .is_err());
    assert_eq!(store.revision(), 1);
}

#[test]
fn failed_storage_freezes_effects_until_independent_recovery() {
    let root = Directory::new();
    let mut store = NotesStore::create(&root.0, target()).unwrap();
    let foreign = root.0.join("foreign");
    fs::write(&foreign, b"do not touch").unwrap();
    symlink(&foreign, document_directory(&root).join("next.json")).unwrap();
    assert!(store.apply_exact(&request()).is_err());
    assert!(store
        .local_edit("no retry after storage ambiguity".into())
        .is_err());
    assert!(store.recovery_exact(&query()).is_err());
    assert_eq!(fs::read(&foreign).unwrap(), b"do not touch");
    drop(store);
    let mut recovered = NotesStore::recover(&root.0, &target()).unwrap();
    assert_eq!(recovered.revision(), 0);
    assert!(matches!(
        NotesResponse::parse_exact(&recovered.recovery_exact(&query()).unwrap())
            .unwrap()
            .result,
        NotesResult::Unknown {
            current_revision: 0
        }
    ));
}
