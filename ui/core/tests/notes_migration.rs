#![cfg(target_os = "linux")]

use std::fs;
use std::io::Read;
use std::os::unix::fs::{DirBuilderExt, MetadataExt};
use std::path::PathBuf;
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
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let path = std::env::temp_dir().join(format!("trill-notes-migration-{suffix}"));
        fs::DirBuilder::new().mode(0o700).create(&path).unwrap();
        Self(path)
    }

    fn document(&self, target: &NotesTargetIdentity) -> PathBuf {
        self.0
            .join(format!(
                "{}-{}-{}",
                target.session_instance, target.task_id, target.incarnation
            ))
            .join("document.json")
    }
}

impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn fixture() -> (serde_json::Value, NotesTargetIdentity) {
    let value: serde_json::Value =
        serde_json::from_str(include_str!("../../../tests/ui/notes-model-v1.json")).unwrap();
    let identity = serde_json::from_value(value["target"].clone()).unwrap();
    (value, identity)
}

#[test]
fn legacy_open_is_read_only_and_retirement_upgrades_without_transferring_identity() {
    let root = Directory::new();
    let (fixture, target) = fixture();
    let mut app = NotesStore::create(&root.0, target.clone()).unwrap();
    let request = fixture["wire"]["request_utf8"].as_str().unwrap().as_bytes();
    let receipt = app.apply_exact(request).unwrap();
    drop(app);
    let path = root.document(&target);
    let legacy = fixture["checkpoint"]["legacy_utf8"]
        .as_str()
        .unwrap()
        .as_bytes();
    fs::write(&path, legacy).unwrap();
    let before = fs::metadata(&path).unwrap();
    let mut recovered = NotesStore::recover(&root.0, &target).unwrap();
    let observe = serde_json::to_vec(&NotesObserve {
        schema_version: 1,
        action: NotesObserveAction::Observe,
        target: target.clone(),
        operation_id: receipt.operation_id.clone(),
        payload_sha256: receipt.payload_sha256.clone(),
    })
    .unwrap();
    assert_eq!(
        NotesResponse::parse_exact(&recovered.recovery_exact(&observe).unwrap()).unwrap(),
        receipt
    );
    assert_eq!(fs::read(&path).unwrap(), legacy);
    let after = fs::metadata(&path).unwrap();
    assert_eq!(
        (before.ino(), before.mtime(), before.mtime_nsec()),
        (after.ino(), after.mtime(), after.mtime_nsec())
    );
    assert!(recovered.apply_exact(request).is_err());
    assert!(recovered
        .local_edit("not a recovered capability".into())
        .is_err());
    let ack = serde_json::to_vec(&NotesAcknowledge {
        schema_version: 1,
        action: NotesAcknowledgeAction::AcknowledgeTerminal,
        target: target.clone(),
        operation_id: receipt.operation_id.clone(),
        payload_sha256: receipt.payload_sha256.clone(),
        receipt_sha256: sha256_hex(&serde_json::to_vec(&receipt).unwrap()),
    })
    .unwrap();
    let response: NotesRetirementResponse =
        serde_json::from_slice(&recovered.recovery_exact(&ack).unwrap()).unwrap();
    assert_eq!(response.status, NotesRetirementStatus::Released);
    drop(recovered);
    let original = fs::read(&path).unwrap();
    let upgraded: serde_json::Value = serde_json::from_slice(&original).unwrap();
    assert_eq!(upgraded["format"], "trill.notes.checkpoint");
    assert_eq!(upgraded["schema_version"], 2);
    assert_eq!(upgraded["target"], serde_json::to_value(&target).unwrap());
    assert_eq!(upgraded["revision"], 1);
    assert_eq!(
        upgraded["retired_receipt"],
        serde_json::from_slice::<serde_json::Value>(&ack).unwrap()
    );
    let mut again = NotesStore::recover(&root.0, &target).unwrap();
    let response: NotesRetirementResponse =
        serde_json::from_slice(&again.recovery_exact(&ack).unwrap()).unwrap();
    assert_eq!(response.status, NotesRetirementStatus::AlreadyReleased);
    drop(again);
    let current = NotesTargetIdentity {
        session_instance: "4".repeat(32),
        task_id: 2,
        incarnation: "5".repeat(32),
    };
    let mut copy = NotesStore::create(&root.0, current.clone()).unwrap();
    let selected = NotesStore::saved_documents(&root.0, &current)
        .unwrap()
        .documents
        .into_iter()
        .find(|entry| entry.target == target)
        .unwrap();
    copy.restore_saved_text(&root.0, &selected, 0).unwrap();
    let copied: serde_json::Value =
        serde_json::from_slice(&fs::read(root.document(&current)).unwrap()).unwrap();
    assert_eq!(copied["target"], serde_json::to_value(&current).unwrap());
    assert_eq!(copied["text"], upgraded["text"]);
    assert_eq!(copied["revision"], 1);
    assert!(copied["pending_receipt"].is_null());
    assert!(copied["retired_receipt"].is_null());
    assert_eq!(fs::read(&path).unwrap(), original);
}

#[test]
fn invalid_or_mixed_legacy_file_is_rejected_without_rewriting_it() {
    let root = Directory::new();
    let (fixture, target) = fixture();
    drop(NotesStore::create(&root.0, target.clone()).unwrap());
    let path = root.document(&target);
    let legacy: serde_json::Value =
        serde_json::from_str(fixture["checkpoint"]["legacy_utf8"].as_str().unwrap()).unwrap();
    for field in ["format", "schema_version", "pending_receipt"] {
        let mut changed = legacy.clone();
        match field {
            "format" => changed["format"] = serde_json::json!("trill.notes.checkpoint"),
            "schema_version" => changed["schema_version"] = serde_json::json!(3),
            _ => {
                changed.as_object_mut().unwrap().remove(field);
            }
        }
        let bytes = serde_json::to_vec(&changed).unwrap();
        fs::write(&path, &bytes).unwrap();
        assert!(NotesStore::recover(&root.0, &target).is_err());
        assert_eq!(fs::read(&path).unwrap(), bytes);
    }
}
