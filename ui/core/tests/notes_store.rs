#![cfg(target_os = "linux")]

use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::{symlink, PermissionsExt};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;
use trill_ui_core::notes::*;
use trill_ui_core::notes_recovery::*;
use trill_ui_core::notes_store::{NotesStore, MAX_SAVED_NOTES};

struct Directory(PathBuf);

impl Directory {
    fn new() -> Self {
        let mut random = [0_u8; 16];
        fs::File::open("/dev/urandom")
            .unwrap()
            .read_exact(&mut random)
            .unwrap();
        let suffix = random
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        let path = std::env::temp_dir().join(format!("trill-notes-store-{suffix}"));
        fs::create_dir(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        Self(path)
    }
}

impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn target() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "a".repeat(32),
        task_id: 1,
        incarnation: "b".repeat(32),
    }
}

fn request() -> Vec<u8> {
    let target = target();
    serde_json::to_vec(&NotesReplace {
        schema_version: NOTES_SCHEMA_VERSION,
        action: NotesReplaceAction::ReplaceNote,
        operation_id: "original-writer-operation".into(),
        destination_id: target.destination_id(),
        target,
        expected_revision: 0,
        text: "重启后仍可核对的原始效果".into(),
    })
    .unwrap()
}

fn query() -> Vec<u8> {
    serde_json::to_vec(&NotesObserve {
        schema_version: NOTES_SCHEMA_VERSION,
        action: NotesObserveAction::Observe,
        target: target(),
        operation_id: "original-writer-operation".into(),
        payload_sha256: sha256_hex(&request()),
    })
    .unwrap()
}

fn document_directory(root: &Directory) -> PathBuf {
    root.0
        .join(format!("{}-1-{}", "a".repeat(32), "b".repeat(32)))
}

fn reopened_target() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "c".repeat(32),
        task_id: 2,
        incarnation: "d".repeat(32),
    }
}

fn read_state(store: &mut NotesStore, identity: &NotesTargetIdentity) -> serde_json::Value {
    let raw = serde_json::to_vec(&serde_json::json!({
        "schema_version": 1, "action": "read_document_state", "target": identity,
        "request_id": "e".repeat(32),
    })).unwrap();
    serde_json::from_slice(&store.recovery_exact(&raw).unwrap()).unwrap()
}

#[test]
fn saved_text_opens_under_new_identity_without_receipts_or_old_effect_capability() {
    let root = Directory::new();
    let mut original = NotesStore::create(&root.0, target()).unwrap();
    let original_receipt = original.apply_exact(&request()).unwrap();
    original.local_edit("用户继续编辑的笔记\n第二行".into()).unwrap();
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
    assert_eq!(state["target"], serde_json::to_value(reopened_target()).unwrap());
    assert_eq!(state["receipt_pending"], false);
    assert!(matches!(reopened.apply_exact(&request()).unwrap().result,
        NotesResult::NotApplied { reason: NotesNotAppliedReason::TargetMismatch, .. }));
    assert!(reopened.recovery_exact(&query()).is_err());
    assert_eq!(fs::read(&old_path).unwrap(), old_bytes);
    drop(reopened);
    let mut saved_copy = NotesStore::recover(&root.0, &reopened_target()).unwrap();
    assert_eq!(saved_copy.text(), "用户继续编辑的笔记\n第二行");
    assert_eq!(read_state(&mut saved_copy, &reopened_target())["receipt_pending"], false);
    let mut original_recovery = NotesStore::recover(&root.0, &target()).unwrap();
    assert_eq!(NotesResponse::parse_exact(&original_recovery.recovery_exact(&query()).unwrap()).unwrap(), original_receipt);
}

#[test]
fn changed_source_and_intervening_current_edits_are_not_overwritten() {
    let root = Directory::new();
    let mut original = NotesStore::create(&root.0, target()).unwrap();
    original.local_edit("first saved text".into()).unwrap();
    drop(original);
    let mut reopened = NotesStore::create(&root.0, reopened_target()).unwrap();
    let selected = NotesStore::saved_documents(&root.0, &reopened_target()).unwrap().documents.remove(0);
    // A valid but newer source snapshot replaces the one displayed by the picker.
    let path = document_directory(&root).join("document.json");
    let mut newer = NotesDocument::restore_checkpoint(&fs::read(&path).unwrap(), &target()).unwrap();
    newer.local_edit("changed after selection".into()).unwrap();
    fs::write(&path, newer.checkpoint().unwrap()).unwrap();
    assert!(reopened.restore_saved_text(&root.0, &selected, 0).is_err());
    assert_eq!(reopened.text(), "");
    assert_eq!(reopened.revision(), 0);
    assert!(!reopened.is_frozen());
    let refreshed = NotesStore::saved_documents(&root.0, &reopened_target()).unwrap().documents.remove(0);
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
    let selected = NotesStore::saved_documents(&root.0, &reopened_target()).unwrap().documents.remove(0);
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
    assert!(NotesStore::saved_documents(&root.0, &reopened_target()).unwrap().documents.is_empty());
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
    let selected = NotesStore::saved_documents(&root.0, &reopened_target()).unwrap().documents.remove(0);
    let next = root.0.join(format!("{}-2-{}", "c".repeat(32), "d".repeat(32))).join("next.json");
    symlink(&old_path, next).unwrap();
    assert!(reopened.restore_saved_text(&root.0, &selected, 0).is_err());
    assert!(reopened.is_frozen());
    assert!(reopened.local_edit("no retry".into()).is_err());
    assert_eq!(fs::read(&old_path).unwrap(), old_bytes);
    drop(reopened);
    let mut recovered = NotesStore::recover(&root.0, &reopened_target()).unwrap();
    assert_eq!(recovered.text(), "");
    assert_eq!(recovered.revision(), 0);
    assert_eq!(read_state(&mut recovered, &reopened_target())["receipt_pending"], false);
}

#[test]
fn saved_picker_is_bounded_and_keeps_utf8_previews_intact() {
    let root = Directory::new();
    for index in 1..=MAX_SAVED_NOTES + 1 {
        let identity = NotesTargetIdentity {
            session_instance: "a".repeat(32), task_id: index as u64,
            incarnation: format!("{index:032x}"),
        };
        let mut original = NotesStore::create(&root.0, identity).unwrap();
        original.local_edit(format!("{} {index}", "中".repeat(100))).unwrap();
    }
    let listing = NotesStore::saved_documents(&root.0, &reopened_target()).unwrap();
    assert!(listing.truncated);
    assert_eq!(listing.documents.len(), MAX_SAVED_NOTES);
    assert!(listing.documents.iter().all(|entry| entry.preview == "中".repeat(80)));
    assert_eq!(listing.unavailable, 0);
}

#[test]
fn restored_copy_survives_process_death_while_original_receipt_remains_recoverable() {
    let root = Directory::new();
    let mut original = NotesStore::create(&root.0, target()).unwrap();
    let receipt = original.apply_exact(&request()).unwrap();
    drop(original);
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "restore_then_wait_fixture", "--nocapture"])
        .env("TRILL_NOTES_RESTORE_TEST_CHILD_ROOT", &root.0)
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn().unwrap();
    let output = child.stdout.take().unwrap();
    let (send, receive) = mpsc::channel();
    let reader = std::thread::spawn(move || {
        for line in BufReader::new(output).lines() {
            if line.is_ok_and(|line| line == "NOTES_RESTORED_BEFORE_EXIT") {
                let _ = send.send(());
                return;
            }
        }
    });
    let committed = receive.recv_timeout(Duration::from_secs(10));
    let _ = child.kill();
    let status = child.wait().unwrap();
    reader.join().unwrap();
    assert!(committed.is_ok(), "restoring child did not persist within the deadline");
    assert!(!status.success());
    let mut restored = NotesStore::recover(&root.0, &reopened_target()).unwrap();
    assert_eq!(restored.text(), "重启后仍可核对的原始效果");
    assert_eq!(restored.revision(), 1);
    assert_eq!(read_state(&mut restored, &reopened_target())["receipt_pending"], false);
    assert!(restored.apply_exact(&request()).is_err());
    let mut original = NotesStore::recover(&root.0, &target()).unwrap();
    assert_eq!(NotesResponse::parse_exact(&original.recovery_exact(&query()).unwrap()).unwrap(), receipt);
}

#[test]
fn restore_then_wait_fixture() {
    let Some(root) = std::env::var_os("TRILL_NOTES_RESTORE_TEST_CHILD_ROOT") else { return; };
    let root = PathBuf::from(root);
    let mut copy = NotesStore::create(&root, reopened_target()).unwrap();
    let selected = NotesStore::saved_documents(&root, &reopened_target()).unwrap().documents.remove(0);
    copy.restore_saved_text(&root, &selected, 0).unwrap();
    println!("NOTES_RESTORED_BEFORE_EXIT");
    std::io::stdout().flush().unwrap();
    let mut one = [0_u8; 1];
    let _ = std::io::stdin().read(&mut one);
    drop(copy);
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

#[test]
fn durable_receipt_survives_sigkill_before_delivery() {
    let root = Directory::new();
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "persist_then_wait_fixture", "--nocapture"])
        .env("TRILL_NOTES_TEST_CHILD_ROOT", &root.0)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let output = child.stdout.take().unwrap();
    let (send, receive) = mpsc::channel();
    let reader = std::thread::spawn(move || {
        for line in BufReader::new(output).lines() {
            if line.is_ok_and(|line| line == "NOTES_DURABLE_BEFORE_REPLY") {
                let _ = send.send(());
                return;
            }
        }
    });
    let committed = receive.recv_timeout(Duration::from_secs(10));
    let _ = child.kill();
    let status = child.wait().unwrap();
    reader.join().unwrap();
    assert!(
        committed.is_ok(),
        "child did not persist before the bounded deadline"
    );
    assert!(!status.success());
    let mut recovered = NotesStore::recover(&root.0, &target()).unwrap();
    let observed =
        NotesResponse::parse_exact(&recovered.recovery_exact(&query()).unwrap()).unwrap();
    let mut expected = NotesDocument::new(target()).unwrap();
    assert_eq!(observed, expected.apply_exact(&request()).unwrap());
    assert_eq!(recovered.text(), "重启后仍可核对的原始效果");
    assert_eq!(recovered.revision(), 1);
    assert!(recovered.apply_exact(&request()).is_err());
}

#[test]
fn persist_then_wait_fixture() {
    let Some(root) = std::env::var_os("TRILL_NOTES_TEST_CHILD_ROOT") else {
        return;
    };
    let mut store = NotesStore::create(&PathBuf::from(root), target()).unwrap();
    store.apply_exact(&request()).unwrap();
    // No effect receipt is delivered. The parent kills this real process
    // while it still holds the incarnation lock, then opens recovery alone.
    println!("NOTES_DURABLE_BEFORE_REPLY");
    std::io::stdout().flush().unwrap();
    let mut one = [0_u8; 1];
    let _ = std::io::stdin().read(&mut one);
    drop(store);
}
