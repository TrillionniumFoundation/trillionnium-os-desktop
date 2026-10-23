//! Real disposable UDS transport with scripted responses and a test-only owner.
//! The expired all-zero-signature original wire fixture is not a credential.
//! These tests do not qualify original authentication or crash durability.

#![cfg(all(target_os = "linux", feature = "objective-submission"))]

use hepta_os_observer::objective::history::{
    HistoryAnchor, HistoryAttempt, HistoryIssue, HistoryStatus, ObjectiveHistoryClient,
    OwnerUnknownReason,
};
use hepta_os_observer::objective::{
    ObjectiveTransport, ProvidedObjective, SubmissionAttempt, SubmissionIdentity, SubmissionStatus,
};
use hepta_os_observer::{EndpointConfig, MAX_FRAME_BYTES};
use serde_json::{json, Value};
use std::fs::{self, DirBuilder};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, PermissionsExt};
use std::os::unix::net::UnixListener;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use trill_session::objective_submission::{
    LocalSubmissionPhase, ObjectiveSubmission, OriginalObjectiveRequestOwner, RequestOwnerIssue,
    SubmissionAdapterError,
};

const AGENT: &str = "11111111-1111-4111-8111-111111111111";
const SPAWN: u64 = 3;
const REQUEST: u64 = 41;
const HISTORY_SPAWN: u64 = 7;
const HISTORY_REQUEST: u64 = 91;
static NEXT: AtomicU64 = AtomicU64::new(1);

fn raw() -> String {
    include_str!(
        "../../../services/hepta-os/tests/fixtures/objective_ingress_original_wire_only.json"
    )
    .trim_end_matches('\n')
    .replace("\"body\":{", "\"body\": {  ")
}

#[derive(Default)]
struct OwnerState {
    original: Option<String>,
    identity: Option<SubmissionIdentity>,
    events: Vec<&'static str>,
    refuse_pending: bool,
    refuse_start: bool,
    send_started: bool,
    fail_submission: bool,
    fail_history: bool,
    fail_cancellation: bool,
}

#[derive(Clone, Default)]
struct TestOwner(Arc<Mutex<OwnerState>>);

impl TestOwner {
    fn seeded(identity: SubmissionIdentity) -> Self {
        Self(Arc::new(Mutex::new(OwnerState {
            original: Some(raw()),
            identity: Some(identity),
            ..OwnerState::default()
        })))
    }
}

impl OriginalObjectiveRequestOwner for TestOwner {
    type Pending = u8;

    fn retain_before_send(
        &mut self,
        identity: &SubmissionIdentity,
        original: &[u8],
    ) -> Result<u8, RequestOwnerIssue> {
        let mut state = self.0.lock().unwrap();
        if state.refuse_pending {
            return Err(RequestOwnerIssue::PersistenceUnknown);
        }
        if state.identity.is_some() {
            return Err(RequestOwnerIssue::AlreadyRetained);
        }
        state.original = Some(String::from_utf8(original.to_vec()).unwrap());
        state.identity = Some(identity.clone());
        state.events.push("pending");
        Ok(1)
    }

    fn recover_pending(
        &mut self,
        identity: &SubmissionIdentity,
        original: &[u8],
    ) -> Result<u8, RequestOwnerIssue> {
        let mut state = self.0.lock().unwrap();
        if state.identity.as_ref() != Some(identity)
            || state.original.as_deref().map(str::as_bytes) != Some(original)
        {
            return Err(RequestOwnerIssue::IdentityMismatch);
        }
        state.events.push("recovered");
        Ok(1)
    }

    fn retain_submission_attempt(
        &mut self,
        ticket: &u8,
        attempt: &SubmissionAttempt,
    ) -> Result<(), RequestOwnerIssue> {
        assert_eq!(*ticket, 1);
        let mut state = self.0.lock().unwrap();
        assert!(state.send_started, "owner start must precede transport");
        assert_eq!(Some(attempt.identity()), state.identity.as_ref());
        assert!(attempt.matches_original_json(state.original.as_ref().unwrap().as_bytes()));
        state.events.push("submission_observed");
        if state.fail_submission {
            return Err(RequestOwnerIssue::PersistenceUnknown);
        }
        state.events.push("submission_retained");
        Ok(())
    }

    fn mark_send_started(&mut self, ticket: &u8) -> Result<(), RequestOwnerIssue> {
        assert_eq!(*ticket, 1);
        let mut state = self.0.lock().unwrap();
        assert!(!state.send_started);
        if state.refuse_start {
            state.events.push("send_start_refused");
            return Err(RequestOwnerIssue::Refused);
        }
        state.send_started = true;
        state.events.push("send_started");
        Ok(())
    }

    fn retained_history_anchor(
        &mut self,
        ticket: &u8,
    ) -> Result<Option<HistoryAnchor>, RequestOwnerIssue> {
        assert_eq!(*ticket, 1);
        self.0.lock().unwrap().events.push("anchor_read");
        // The admission response has no sequence. Do not invent an anchor.
        Ok(None)
    }

    fn retain_history_attempt(
        &mut self,
        ticket: &u8,
        attempt: &HistoryAttempt,
    ) -> Result<(), RequestOwnerIssue> {
        assert_eq!(*ticket, 1);
        let mut state = self.0.lock().unwrap();
        assert!(attempt.matches_original_json(state.original.as_ref().unwrap().as_bytes()));
        state.events.push("history_observed");
        if state.fail_history {
            return Err(RequestOwnerIssue::PersistenceUnknown);
        }
        state.events.push("history_retained");
        Ok(())
    }

    fn retain_local_cancellation(
        &mut self,
        ticket: &u8,
        identity: &SubmissionIdentity,
    ) -> Result<(), RequestOwnerIssue> {
        assert_eq!(*ticket, 1);
        let mut state = self.0.lock().unwrap();
        assert_eq!(Some(identity), state.identity.as_ref());
        state.events.push("local_cancel_observed");
        if state.fail_cancellation {
            return Err(RequestOwnerIssue::PersistenceUnknown);
        }
        state.events.push("local_cancel_retained");
        Ok(())
    }
}

struct Socket {
    directory: PathBuf,
    path: PathBuf,
    listener: Option<UnixListener>,
    uid: u32,
}

impl Socket {
    fn new() -> Self {
        let directory = PathBuf::from(format!(
            "/tmp/trill-objective-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        DirBuilder::new().mode(0o700).create(&directory).unwrap();
        let path = directory.join("control.sock");
        let listener = UnixListener::bind(&path).unwrap();
        listener.set_nonblocking(true).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        let uid = fs::metadata(&directory).unwrap().uid();
        Self {
            directory,
            path,
            listener: Some(listener),
            uid,
        }
    }

    fn config(&self, agent: &str, spawn: u64) -> EndpointConfig {
        EndpointConfig::new(self.path.clone(), agent.into(), spawn, self.uid).unwrap()
    }

    fn transport(&self) -> ObjectiveTransport {
        ObjectiveTransport::new(self.config(AGENT, SPAWN), std::process::id(), REQUEST).unwrap()
    }

    fn identity(&self) -> SubmissionIdentity {
        self.transport()
            .submission_identity(&ProvidedObjective::parse_json(raw()).unwrap())
    }

    fn history(&self, agent: &str) -> ObjectiveHistoryClient {
        ObjectiveHistoryClient::new(
            self.config(agent, HISTORY_SPAWN),
            std::process::id(),
            HISTORY_REQUEST,
        )
        .unwrap()
    }

    fn assert_no_connection(&self) {
        assert!(matches!(self.listener.as_ref().unwrap().accept(), Err(e)
            if e.kind() == std::io::ErrorKind::WouldBlock));
    }

    fn serve(
        &mut self,
        owner: TestOwner,
        reply: Option<Value>,
        history: bool,
    ) -> (mpsc::Sender<()>, thread::JoinHandle<Vec<u8>>) {
        let listener = self.listener.take().unwrap();
        let (done, finished) = mpsc::channel();
        let server = thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(8);
            let (mut stream, _) = loop {
                match listener.accept() {
                    Ok(pair) => break pair,
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        assert!(Instant::now() < deadline, "missing fixture connection");
                        thread::sleep(Duration::from_millis(2));
                    }
                    Err(e) => panic!("{e}"),
                }
            };
            let original = {
                let mut state = owner.0.lock().unwrap();
                assert!(state.identity.is_some(), "retention must precede connect");
                if !history {
                    assert!(state.send_started, "owner start must precede connect");
                }
                state.events.push("socket_connected");
                state.original.clone().unwrap()
            };
            stream
                .set_read_timeout(Some(Duration::from_secs(8)))
                .unwrap();
            stream
                .set_write_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            let mut reader = BufReader::new(stream.try_clone().unwrap());
            let mut received = Vec::new();
            (&mut reader)
                .take(MAX_FRAME_BYTES + 1)
                .read_until(b'\n', &mut received)
                .unwrap();
            assert!(received.ends_with(b"\n") && received.len() as u64 <= MAX_FRAME_BYTES);
            assert!(reader.buffer().is_empty());
            let expected = if history {
                format!("{{\"schema_version\":2,\"request_id\":{HISTORY_REQUEST},\"spawn_generation\":{HISTORY_SPAWN},\"method\":{{\"type\":\"objective_admission\",\"query\":{{\"request\":{original},\"anchor\":null}}}}}}\n")
            } else {
                format!("{{\"schema_version\":2,\"request_id\":{REQUEST},\"spawn_generation\":{SPAWN},\"method\":{{\"type\":\"objective_start\",\"request\":{original}}}}}\n")
            };
            assert_eq!(received, expected.as_bytes(), "exact original bytes");
            if let Some(reply) = reply {
                let mut bytes = serde_json::to_vec(&reply).unwrap();
                bytes.push(b'\n');
                stream.write_all(&bytes).unwrap();
            }
            drop(reader);
            drop(stream);
            finished.recv_timeout(Duration::from_secs(8)).unwrap();
            assert!(
                matches!(listener.accept(), Err(e)
                if e.kind() == std::io::ErrorKind::WouldBlock),
                "no repeat connection"
            );
            received
        });
        (done, server)
    }
}

impl Drop for Socket {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.directory);
    }
}

fn admitted() -> Value {
    json!({"schema_version":2,"request_id":REQUEST,"agent_id":AGENT,
        "spawn_generation":SPAWN,"current_generation":SPAWN+1,
        "payload":{"type":"objective_run","run_id":"run.objective.1",
        "objective_digest":"1".repeat(64),"hard_constraint_digest":"2".repeat(64),
        "publication_digest":"3".repeat(64),"chain_digest":"4".repeat(64),
        "disposition":"compiled","idempotent":false}})
}

fn history_reply(published: bool) -> Value {
    let request: Value = serde_json::from_str(&raw()).unwrap();
    let outcome = if published {
        json!({"type":"published","publication":{
            "run_id":request["body"]["run_id"],"original_spawn_generation":SPAWN,
            "issuer_id":request["issuer_id"],"key_epoch":request["key_epoch"],
            "message_id":request["message_id"],"message_sequence":request["sequence"],
            "expires_at_ms":request["expires_at_ms"],"signed_body_digest":"1".repeat(64),
            "profile_digest":"2".repeat(64),"publication_sequence":2,
            "publication_digest":"3".repeat(64),"chain_digest":"4".repeat(64),
            "outcome":{"type":"compiled","objective_digest":"5".repeat(64),
            "hard_constraint_digest":"6".repeat(64)}}})
    } else {
        json!({"type":"unknown","reason":"no_matching_publication"})
    };
    json!({"schema_version":2,"request_id":HISTORY_REQUEST,"agent_id":AGENT,
        "spawn_generation":HISTORY_SPAWN,"current_generation":HISTORY_SPAWN+1,
        "payload":{"type":"objective_admission","outcome":outcome}})
}

fn complete(done: mpsc::Sender<()>, server: thread::JoinHandle<Vec<u8>>) {
    done.send(()).unwrap();
    assert!(!server.join().unwrap().is_empty());
}

#[test]
fn rejected_retention_or_invalid_input_never_connects() {
    let socket = Socket::new();
    let owner = TestOwner::default();
    owner.0.lock().unwrap().refuse_pending = true;
    assert!(matches!(
        ObjectiveSubmission::prepare(owner.clone(), socket.transport(), raw()),
        Err(SubmissionAdapterError::Owner(
            RequestOwnerIssue::PersistenceUnknown
        ))
    ));
    assert!(matches!(
        ObjectiveSubmission::prepare(owner.clone(), socket.transport(), "{}".into()),
        Err(SubmissionAdapterError::Envelope(_))
    ));
    let mismatched =
        ObjectiveTransport::new(socket.config(AGENT, SPAWN + 1), std::process::id(), REQUEST)
            .unwrap();
    assert!(matches!(
        ObjectiveSubmission::prepare(owner.clone(), mismatched, raw()),
        Err(SubmissionAdapterError::GenerationFenced)
    ));
    assert!(owner.0.lock().unwrap().events.is_empty());
    socket.assert_no_connection();
}

#[test]
fn exact_pending_identity_precedes_original_send_and_receipt() {
    let mut socket = Socket::new();
    let owner = TestOwner::default();
    let identity = socket.identity();
    let mut submission =
        ObjectiveSubmission::prepare(owner.clone(), socket.transport(), raw()).unwrap();
    assert_eq!(submission.view().identity, identity);
    assert_eq!(
        submission.view().phase,
        LocalSubmissionPhase::PendingRetained
    );
    socket.assert_no_connection();
    let (done, server) = socket.serve(owner.clone(), Some(admitted()), false);
    submission.submit_once().unwrap();
    let view = submission.view();
    assert!(matches!(
        view.observed_submission,
        Some(SubmissionStatus::Admitted(_))
    ));
    assert!(view.submission_recorded);
    assert_eq!(
        submission.submit_once(),
        Err(SubmissionAdapterError::SendPermissionConsumed)
    );
    complete(done, server);
    assert_eq!(
        owner.0.lock().unwrap().events,
        [
            "pending",
            "send_started",
            "socket_connected",
            "submission_observed",
            "submission_retained"
        ]
    );
}

#[test]
fn original_owner_start_refusal_consumes_permission_without_connecting() {
    let socket = Socket::new();
    let owner = TestOwner::default();
    owner.0.lock().unwrap().refuse_start = true;
    let mut submission =
        ObjectiveSubmission::prepare(owner.clone(), socket.transport(), raw()).unwrap();
    assert_eq!(
        submission.submit_once(),
        Err(SubmissionAdapterError::Owner(RequestOwnerIssue::Refused))
    );
    assert_eq!(
        submission.view().phase,
        LocalSubmissionPhase::SubmissionStartedOrUnknown
    );
    assert!(submission.view().observed_submission.is_none());
    assert_eq!(
        submission.submit_once(),
        Err(SubmissionAdapterError::SendPermissionConsumed)
    );
    assert_eq!(
        submission.cancel_before_send(),
        Err(SubmissionAdapterError::OriginalOwnerCancellationRequired)
    );
    assert_eq!(
        owner.0.lock().unwrap().events,
        ["pending", "send_start_refused"]
    );
    socket.assert_no_connection();
}

#[test]
fn lost_reply_is_unknown_and_never_becomes_a_retry_or_run_cancel() {
    let mut socket = Socket::new();
    let owner = TestOwner::default();
    let mut submission =
        ObjectiveSubmission::prepare(owner.clone(), socket.transport(), raw()).unwrap();
    let (done, server) = socket.serve(owner, None, false);
    submission.submit_once().unwrap();
    assert!(matches!(
        submission.view().observed_submission,
        Some(SubmissionStatus::SubmitUnknown(_))
    ));
    assert_eq!(
        submission.submit_once(),
        Err(SubmissionAdapterError::SendPermissionConsumed)
    );
    assert_eq!(
        submission.cancel_before_send(),
        Err(SubmissionAdapterError::OriginalOwnerCancellationRequired)
    );
    complete(done, server);
}

#[test]
fn failed_submission_handoff_keeps_result_and_retries_only_retention() {
    let mut socket = Socket::new();
    let owner = TestOwner::default();
    owner.0.lock().unwrap().fail_submission = true;
    let mut submission =
        ObjectiveSubmission::prepare(owner.clone(), socket.transport(), raw()).unwrap();
    let (done, server) = socket.serve(owner.clone(), Some(admitted()), false);
    assert_eq!(
        submission.submit_once(),
        Err(SubmissionAdapterError::Owner(
            RequestOwnerIssue::PersistenceUnknown
        ))
    );
    let view = submission.view();
    assert!(matches!(
        view.observed_submission,
        Some(SubmissionStatus::Admitted(_))
    ));
    assert!(!view.submission_recorded);
    assert_eq!(view.phase, LocalSubmissionPhase::SubmissionStartedOrUnknown);
    assert_eq!(
        submission.submit_once(),
        Err(SubmissionAdapterError::SendPermissionConsumed)
    );
    owner.0.lock().unwrap().fail_submission = false;
    submission.retain_observed_submission().unwrap();
    assert!(submission.view().submission_recorded);
    complete(done, server);
}

#[test]
fn local_cancel_consumes_only_an_unused_permission_even_if_handoff_fails() {
    let socket = Socket::new();
    let owner = TestOwner::default();
    owner.0.lock().unwrap().fail_cancellation = true;
    let mut submission =
        ObjectiveSubmission::prepare(owner.clone(), socket.transport(), raw()).unwrap();
    assert_eq!(
        submission.cancel_before_send(),
        Err(SubmissionAdapterError::Owner(
            RequestOwnerIssue::PersistenceUnknown
        ))
    );
    assert_eq!(
        submission.view().phase,
        LocalSubmissionPhase::LocalSendCancelled
    );
    assert!(!submission.view().local_cancellation_recorded);
    assert_eq!(
        submission.submit_once(),
        Err(SubmissionAdapterError::SendPermissionConsumed)
    );
    owner.0.lock().unwrap().fail_cancellation = false;
    submission.retain_local_cancellation().unwrap();
    assert!(submission.view().local_cancellation_recorded);
    assert_eq!(
        submission.reconcile_once(socket.history(AGENT)),
        Err(SubmissionAdapterError::HistoryBeforeSubmission)
    );
    socket.assert_no_connection();
}

#[test]
fn original_owner_duplicate_fence_blocks_a_fresh_facade() {
    let socket = Socket::new();
    let owner = TestOwner::default();
    let _first = ObjectiveSubmission::prepare(owner.clone(), socket.transport(), raw()).unwrap();
    assert!(matches!(
        ObjectiveSubmission::prepare(owner, socket.transport(), raw()),
        Err(SubmissionAdapterError::Owner(
            RequestOwnerIssue::AlreadyRetained
        ))
    ));
    socket.assert_no_connection();
}

#[test]
fn recovered_pending_has_no_transport_and_rejects_changed_original_metadata() {
    let socket = Socket::new();
    let identity = socket.identity();
    let owner = TestOwner::seeded(identity.clone());
    let mut recovered =
        ObjectiveSubmission::recover_unknown(owner.clone(), identity.clone(), raw()).unwrap();
    assert_eq!(
        recovered.submit_once(),
        Err(SubmissionAdapterError::SendPermissionConsumed)
    );
    assert_eq!(
        recovered.cancel_before_send(),
        Err(SubmissionAdapterError::OriginalOwnerCancellationRequired)
    );
    let mut changed = identity;
    changed.objective.message_id.push_str(".changed");
    assert!(matches!(
        ObjectiveSubmission::recover_unknown(owner, changed, raw()),
        Err(SubmissionAdapterError::RetainedIdentityMismatch)
    ));
    socket.assert_no_connection();
}

#[test]
fn history_requires_started_intent_and_the_same_agent_before_connecting() {
    let socket = Socket::new();
    let owner = TestOwner::default();
    let mut pending =
        ObjectiveSubmission::prepare(owner.clone(), socket.transport(), raw()).unwrap();
    assert_eq!(
        pending.reconcile_once(socket.history(AGENT)),
        Err(SubmissionAdapterError::HistoryBeforeSubmission)
    );
    let mut recovered =
        ObjectiveSubmission::recover_unknown(owner, pending.view().identity, raw()).unwrap();
    let other = "22222222-2222-4222-8222-222222222222";
    assert_eq!(
        recovered.reconcile_once(socket.history(other)),
        Err(SubmissionAdapterError::HistoryOwnerMismatch)
    );
    socket.assert_no_connection();
}

#[test]
fn unknown_history_preserves_admission_and_an_earlier_original_publication() {
    let mut socket = Socket::new();
    let owner = TestOwner::default();
    let mut submission =
        ObjectiveSubmission::prepare(owner.clone(), socket.transport(), raw()).unwrap();
    let (done, server) = socket.serve(owner.clone(), Some(admitted()), false);
    submission.submit_once().unwrap();
    complete(done, server);
    for published in [true, false] {
        let mut history_socket = Socket::new();
        let client = history_socket.history(AGENT);
        let (done, server) =
            history_socket.serve(owner.clone(), Some(history_reply(published)), true);
        submission.reconcile_once(client).unwrap();
        complete(done, server);
    }
    let view = submission.view();
    assert!(matches!(
        view.observed_submission,
        Some(SubmissionStatus::Admitted(_))
    ));
    assert!(matches!(
        view.first_observed_publication,
        Some(HistoryStatus::HistoricalPublication { .. })
    ));
    assert_eq!(
        view.last_history,
        Some(HistoryStatus::Unknown(HistoryIssue::Owner(
            OwnerUnknownReason::NoMatchingPublication
        )))
    );
    assert_eq!(
        submission.submit_once(),
        Err(SubmissionAdapterError::SendPermissionConsumed)
    );
}

#[test]
fn failed_history_handoff_cannot_be_overwritten_by_another_query() {
    let socket = Socket::new();
    let identity = socket.identity();
    let owner = TestOwner::seeded(identity.clone());
    owner.0.lock().unwrap().fail_history = true;
    let mut submission =
        ObjectiveSubmission::recover_unknown(owner.clone(), identity, raw()).unwrap();
    let mut history_socket = Socket::new();
    let client = history_socket.history(AGENT);
    let (done, server) = history_socket.serve(owner.clone(), Some(history_reply(true)), true);
    assert_eq!(
        submission.reconcile_once(client),
        Err(SubmissionAdapterError::Owner(
            RequestOwnerIssue::PersistenceUnknown
        ))
    );
    complete(done, server);
    assert!(submission.view().first_observed_publication.is_some());
    assert!(!submission.view().history_recorded);
    assert_eq!(
        submission.reconcile_once(socket.history(AGENT)),
        Err(SubmissionAdapterError::UnretainedHistoryResult)
    );
    socket.assert_no_connection();
    owner.0.lock().unwrap().fail_history = false;
    submission.retain_observed_history().unwrap();
    assert!(submission.view().history_recorded);
}
