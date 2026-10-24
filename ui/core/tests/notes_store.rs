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
use trill_ui_core::notes_store::NotesStore;

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
