use std::fs;
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use trill_ui_core::notes::*;
use trill_ui_core::notes_store::NotesStore;

pub(super) struct Directory(pub(super) PathBuf);

impl Directory {
    pub(super) fn new() -> Self {
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

pub(super) fn target() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "a".repeat(32),
        task_id: 1,
        incarnation: "b".repeat(32),
    }
}

pub(super) fn request() -> Vec<u8> {
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

pub(super) fn query() -> Vec<u8> {
    serde_json::to_vec(&NotesObserve {
        schema_version: NOTES_SCHEMA_VERSION,
        action: NotesObserveAction::Observe,
        target: target(),
        operation_id: "original-writer-operation".into(),
        payload_sha256: sha256_hex(&request()),
    })
    .unwrap()
}

pub(super) fn reopened_target() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "c".repeat(32),
        task_id: 2,
        incarnation: "d".repeat(32),
    }
}

pub(super) fn read_state(store: &mut NotesStore, identity: &NotesTargetIdentity) -> serde_json::Value {
    let raw = serde_json::to_vec(&serde_json::json!({
        "schema_version": 1, "action": "read_document_state", "target": identity,
        "request_id": "e".repeat(32),
    }))
    .unwrap();
    serde_json::from_slice(&store.recovery_exact(&raw).unwrap()).unwrap()
}
