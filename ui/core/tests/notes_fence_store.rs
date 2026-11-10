#![cfg(target_os = "linux")]

use std::fs;
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use trill_ui_core::notes::*;
use trill_ui_core::notes_store::NotesStore;

#[test]
fn notes_fence_receipt_and_revision_survive_disk_recovery_without_effect_authority() {
    let mut random = [0_u8; 16];
    fs::File::open("/dev/urandom").unwrap().read_exact(&mut random).unwrap();
    let suffix: String = random.iter().map(|b| format!("{b:02x}")).collect();
    let directory = std::env::temp_dir().join(format!("trill-notes-fence-{suffix}"));
    fs::create_dir(&directory).unwrap();
    fs::set_permissions(&directory, fs::Permissions::from_mode(0o700)).unwrap();
    let target = NotesTargetIdentity { session_instance: "a".repeat(32), task_id: 1, incarnation: "b".repeat(32) };
    let original = serde_json::to_vec(&NotesReplace { schema_version: 1, action: NotesReplaceAction::ReplaceNote,
        operation_id: "original".into(), destination_id: target.destination_id(), target: target.clone(),
        expected_revision: 0, text: "late write".into(),
    }).unwrap();
    let cancel = serde_json::to_vec(&NotesFence { schema_version: 1, action: NotesFenceAction::FenceNoteOperation,
        operation_id: "cancel".into(), destination_id: target.destination_id(), target: target.clone(),
        original_operation_id: "original".into(), original_payload_sha256: sha256_hex(&original), expected_revision: 0,
    }).unwrap();
    let mut application = NotesStore::create(&directory, target.clone()).unwrap();
    let receipt = application.fence_exact(&cancel).unwrap();
    assert_eq!(application.revision(), 1);
    assert_eq!(application.text(), "");
    assert!(matches!(application.apply_exact(&original).unwrap().result,
        NotesResult::NotApplied { reason: NotesNotAppliedReason::RevisionConflict, .. }));
    drop(application);
    let mut recovered = NotesStore::recover(&directory, &target).unwrap();
    let query = serde_json::json!({"schema_version":1,"action":"observe_fence","target":target,
        "operation_id":"cancel","payload_sha256":sha256_hex(&cancel)});
    assert_eq!(NotesFenceResponse::parse_exact(&recovered.recovery_exact(&serde_json::to_vec(&query).unwrap()).unwrap()).unwrap(), receipt);
    assert!(recovered.fence_exact(&cancel).is_err());
    assert!(recovered.apply_exact(&original).is_err());
    assert!(recovered.recovery_exact(&cancel).is_err());
    drop(recovered);
    fs::remove_dir_all(directory).unwrap();
}
