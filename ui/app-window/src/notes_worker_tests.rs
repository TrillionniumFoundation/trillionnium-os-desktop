use super::*;
use std::time::Duration;
use std::fs;
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
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
            None,
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

struct SavedDocumentFixture(PathBuf);

impl SavedDocumentFixture {
    fn new() -> Self {
        let mut random = [0_u8; 16];
        fs::File::open("/dev/urandom").unwrap().read_exact(&mut random).unwrap();
        let suffix = random.iter().map(|byte| format!("{byte:02x}")).collect::<String>();
        let root = std::env::temp_dir().join(format!("trill-notes-worker-restore-{suffix}"));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let mut saved = NotesStore::create(&root, NotesTargetIdentity {
            session_instance: "4".repeat(32), task_id: 2, incarnation: "5".repeat(32),
        }).unwrap();
        saved.local_edit("previous user document".into()).unwrap();
        Self(root)
    }

    fn worker(&self) -> (mpsc::SyncSender<Command>, Arc<Mutex<Projection>>, std::thread::JoinHandle<()>) {
        let document = NotesStore::create(&self.0, identity()).unwrap();
        let root = self.0.clone();
        let (sender, receiver) = mpsc::sync_channel(4);
        let output = Arc::new(Mutex::new(Projection::default()));
        let projection = output.clone();
        let thread = std::thread::spawn(move || run(Document::Durable(document), Some(root),
            receiver, projection, egui::Context::default()));
        (sender, output, thread)
    }
}

impl Drop for SavedDocumentFixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn selected_document(sender: &mpsc::SyncSender<Command>, output: &Arc<Mutex<Projection>>) -> SavedNotesDocument {
    sender.send(Command::ListSaved { id: 17 }).unwrap();
    observe(sender); // A later serialized command is the bounded completion barrier.
    let snapshot = output.lock().unwrap();
    let (id, listing) = snapshot.saved_documents.as_ref().unwrap();
    assert_eq!(*id, 17);
    let listing = listing.as_ref().unwrap();
    assert_eq!(listing.documents.len(), 1);
    listing.documents[0].clone()
}

#[test]
fn saved_document_is_restored_on_the_worker_as_a_new_local_revision() {
    let fixture = SavedDocumentFixture::new();
    let (sender, output, handle) = fixture.worker();
    let selected = selected_document(&sender, &output);
    sender.send(Command::RestoreSaved { id: 18, revision: 0, source: selected }).unwrap();
    let state = observe(&sender);
    assert_eq!(state["revision"], 1);
    assert_eq!(state["text_sha256"], sha256_hex(b"previous user document"));
    assert_eq!(state["receipt_pending"], false);
    assert_eq!(output.lock().unwrap().restore_result, Some((18, Ok(()))));
    let result = exchange(&sender, mutation(), false, Instant::now() + Duration::from_secs(2)).unwrap();
    assert!(matches!(NotesResponse::parse_exact(&result).unwrap().result,
        NotesResult::NotApplied { reason: NotesNotAppliedReason::RevisionConflict, .. }));
    drop(sender);
    handle.join().unwrap();
    let persisted = NotesStore::recover(&fixture.0, &identity()).unwrap();
    assert_eq!(persisted.text(), "previous user document");
    assert_eq!(persisted.revision(), 1);
}

#[test]
fn external_effect_between_picker_and_restore_wins_without_being_overwritten() {
    let fixture = SavedDocumentFixture::new();
    let (sender, output, handle) = fixture.worker();
    let selected = selected_document(&sender, &output);
    let raw = exchange(&sender, mutation(), false, Instant::now() + Duration::from_secs(2)).unwrap();
    assert!(matches!(NotesResponse::parse_exact(&raw).unwrap().result, NotesResult::Applied { .. }));
    sender.send(Command::RestoreSaved { id: 18, revision: 0, source: selected }).unwrap();
    let state = observe(&sender);
    assert_eq!(state["text_sha256"], sha256_hex(b"original effect"));
    assert_eq!(state["revision"], 1);
    assert_eq!(state["receipt_pending"], true);
    assert!(output.lock().unwrap().restore_result.as_ref().unwrap().1.is_err());
    drop(sender);
    handle.join().unwrap();
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
