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

#[test]
fn durable_reopen_uses_the_original_worker_and_rejects_stale_local_edits() {
    use std::fs;
    use std::io::Read;
    use std::os::unix::fs::DirBuilderExt;
    let mut random = [0_u8; 16];
    fs::File::open("/dev/urandom")
        .unwrap()
        .read_exact(&mut random)
        .unwrap();
    let suffix: String = random.iter().map(|byte| format!("{byte:02x}")).collect();
    let root = std::env::temp_dir().join(format!("trill-notes-reopen-worker-{suffix}"));
    fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
    let mut old_target = identity();
    old_target.incarnation = "9".repeat(32);
    let mut old = NotesStore::create(&root, old_target).unwrap();
    old.local_edit("原始保存的笔记".into()).unwrap();
    drop(old);
    let store = NotesStore::create(&root, identity()).unwrap();
    let source = store.saved_notes().unwrap().entries.remove(0);
    let (sender, receiver) = mpsc::sync_channel(4);
    let output = Arc::new(Mutex::new(Projection::default()));
    let worker_output = output.clone();
    let handle = std::thread::spawn(move || {
        run(
            Document::Durable(store),
            receiver,
            worker_output,
            egui::Context::default(),
        )
    });
    sender
        .send(Command::ReopenSaved {
            id: 4,
            revision: 0,
            source,
        })
        .unwrap();
    let observed = observe(&sender);
    assert_eq!(observed["revision"], 1);
    assert_eq!(observed["receipt_pending"], false);
    assert_eq!(
        observed["text_sha256"],
        sha256_hex("原始保存的笔记".as_bytes())
    );
    assert!(output
        .lock()
        .unwrap()
        .reopen_result
        .as_ref()
        .unwrap()
        .1
        .is_ok());
    sender
        .send(Command::LocalEdit {
            id: 5,
            revision: 0,
            text: "stale typed text".into(),
        })
        .unwrap();
    assert_eq!(observe(&sender)["revision"], 1);
    assert_eq!(output.lock().unwrap().local_result, Some((5, false, 1)));
    sender
        .send(Command::LocalEdit {
            id: 6,
            revision: 1,
            text: "继续编辑".into(),
        })
        .unwrap();
    assert_eq!(observe(&sender)["revision"], 2);
    drop(sender);
    handle.join().unwrap();
    let saved = NotesStore::recover(&root, &identity()).unwrap();
    assert_eq!(saved.text(), "继续编辑");
    drop(saved);
    fs::remove_dir_all(root).unwrap();
}
