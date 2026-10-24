use super::*;
use std::time::Duration;
use trill_ui_core::notes::*;

fn identity() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 1,
        incarnation: "2".repeat(32),
    }
}

fn start_worker() -> (
    mpsc::SyncSender<Command>,
    Arc<Mutex<Projection>>,
    std::thread::JoinHandle<()>,
) {
    let (sender, receiver) = mpsc::sync_channel(4);
    let output = Arc::new(Mutex::new(Projection::default()));
    let output_clone = output.clone();
    let handle = std::thread::spawn(move || {
        run(
            Document::Memory(NotesDocument::new(identity()).unwrap()),
            receiver,
            output_clone,
            egui::Context::default(),
        )
    });
    (sender, output, handle)
}

fn exchange(
    sender: &mpsc::SyncSender<Command>,
    raw: Vec<u8>,
    recovery: bool,
    expires_at: Instant,
) -> Option<Vec<u8>> {
    let (reply, response) = mpsc::sync_channel(1);
    sender
        .send(Command::Protocol(Pending {
            bytes: raw,
            expires_at,
            recovery,
            reply,
        }))
        .unwrap();
    response.recv_timeout(Duration::from_secs(2)).unwrap()
}

fn mutation() -> Vec<u8> {
    serde_json::to_vec(&NotesReplace {
        schema_version: 1,
        action: NotesReplaceAction::ReplaceNote,
        operation_id: "worker-effect".into(),
        destination_id: identity().destination_id(),
        target: identity(),
        expected_revision: 0,
        text: "original effect".into(),
    })
    .unwrap()
}

fn observe(sender: &mpsc::SyncSender<Command>) -> serde_json::Value {
    let query = serde_json::to_vec(&serde_json::json!({
        "schema_version": 1, "action": "read_document_state", "target": identity(),
        "request_id": "3".repeat(32),
    }))
    .unwrap();
    serde_json::from_slice(
        &exchange(sender, query, true, Instant::now() + Duration::from_secs(2)).unwrap(),
    )
    .unwrap()
}

#[test]
fn delayed_local_typing_cannot_overwrite_an_intervening_external_effect() {
    let (sender, output, handle) = start_worker();
    let raw = exchange(
        &sender,
        mutation(),
        false,
        Instant::now() + Duration::from_secs(2),
    )
    .unwrap();
    assert!(matches!(
        NotesResponse::parse_exact(&raw).unwrap().result,
        NotesResult::Applied { revision: 1, .. }
    ));
    sender
        .send(Command::LocalEdit {
            id: 1,
            revision: 0,
            text: "stale local draft".into(),
        })
        .unwrap();
    let observed = observe(&sender);
    assert_eq!(observed["revision"], 1);
    assert_eq!(observed["text_sha256"], sha256_hex(b"original effect"));
    assert_eq!(output.lock().unwrap().local_result, Some((1, false, 1)));
    drop(sender);
    handle.join().unwrap();
}

#[test]
fn expired_handoff_never_mutates_while_fresh_local_edits_share_the_same_revision() {
    let (sender, output, handle) = start_worker();
    assert!(exchange(
        &sender,
        mutation(),
        false,
        Instant::now() - Duration::from_secs(1)
    )
    .is_none());
    sender
        .send(Command::LocalEdit {
            id: 7,
            revision: 0,
            text: "current local edit".into(),
        })
        .unwrap();
    let observed = observe(&sender);
    assert_eq!(observed["revision"], 1);
    assert_eq!(observed["receipt_pending"], false);
    assert_eq!(observed["text_sha256"], sha256_hex(b"current local edit"));
    assert_eq!(output.lock().unwrap().local_result, Some((7, true, 1)));
    drop(sender);
    handle.join().unwrap();
}
