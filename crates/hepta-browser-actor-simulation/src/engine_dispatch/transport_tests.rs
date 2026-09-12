//! Real AF_UNIX + canonical codec + actor + engine-thread queue + disk journal.
//! The engine and semantic principal's unit/executable facts are test fixtures;
//! this is NOT Servo, systemd activation or exact-image qualification.
use super::*;
use crate::{
    BrowserActor, DeterministicLocalRuntime, MechanismIdentity, PrincipalBinding, TaskFlowPrincipal,
};
use hepta_agent_port::serve_one_with_observer;
use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserResponse, JsonObject, ObservationField, ProfileSpec, decode_response,
};
use hepta_session_core::{
    JournalId, ReceiptJournal, ReceiptLifecycleState, SessionPhase, inspect_receipt_journal,
};
use std::cell::RefCell;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicU64;
use std::time::Instant;

const BUDGET: Duration = Duration::from_secs(5);
static DIRECTORY_ID: AtomicU64 = AtomicU64::new(0);
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "hepta-engine-dispatch-{}-{}",
            std::process::id(),
            DIRECTORY_ID.fetch_add(1, Ordering::SeqCst)
        ));
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
fn binding(peer: PeerIdentity) -> PrincipalBinding {
    PrincipalBinding::bind(
        TaskFlowPrincipal {
            principal_id: "fixture-principal".to_owned(),
            expected_uid: peer.uid,
            expected_gid: peer.gid,
            expected_systemd_unit: "fixture.service".to_owned(),
            expected_cgroup_v2_path: "/fixture".to_owned(),
            expected_executable_sha256: "1".repeat(64),
        },
        MechanismIdentity {
            peer,
            systemd_unit: "fixture.service".to_owned(),
            cgroup_v2_path: "/fixture".to_owned(),
            executable_sha256: "1".repeat(64),
        },
    )
    .unwrap()
}
fn invoke(stream: UnixStream, request: BrowserRequest) -> BrowserResponse {
    let peer = PeerIdentity::from_stream(&stream).unwrap();
    let mut client = ClientConnection::connect(stream, PeerPolicy::exact(peer), BUDGET).unwrap();
    let seq = client
        .send_request(encode_request(&request).unwrap(), BUDGET)
        .unwrap();
    let response = decode_response(&client.receive_response(seq, BUDGET).unwrap())
        .unwrap()
        .value;
    assert_eq!(response.request_id, request.request_id);
    assert_eq!(response.session_id, request.session_id);
    assert_eq!(response.session_generation, request.session_generation);
    response
}
fn req(id: &str, session: Option<&str>, operation: BrowserOperation) -> BrowserRequest {
    BrowserRequest {
        request_id: id.to_owned(),
        session_id: session.map(str::to_owned),
        session_generation: session.map(|_| 1),
        deadline_unix_ms: None,
        operation,
    }
}
fn create() -> BrowserRequest {
    req(
        "create",
        None,
        BrowserOperation::SessionCreate {
            profile: ProfileSpec {
                profile_id: "ephemeral".to_owned(),
                persistence: ProfilePersistence::Ephemeral,
            },
            ui_mode: "headed".to_owned(),
        },
    )
}
fn text(object: &JsonObject, key: &str) -> String {
    let Some(JsonValue::String(value)) = object.get(key) else {
        panic!("missing {key}")
    };
    value.clone()
}
fn number(object: &JsonObject, key: &str) -> u64 {
    let Some(JsonValue::Integer(value)) = object.get(key) else {
        panic!("missing {key}")
    };
    (*value).try_into().unwrap()
}
fn sockets(count: usize) -> (Vec<UnixStream>, Vec<UnixStream>) {
    (0..count).map(|_| UnixStream::pair().unwrap()).unzip()
}
fn check_dispatched(path: &Path, control: &RequestControl) {
    let report = inspect_receipt_journal(path).unwrap();
    let recent: Vec<_> = report.records.iter().rev().take(2).collect();
    assert_eq!(recent[0].event.receipt_id, control.request_id);
    assert_eq!(recent[0].event.lifecycle, ReceiptLifecycleState::Dispatched);
    assert_eq!(recent[1].event.lifecycle, ReceiptLifecycleState::Requested);
}

struct FixtureEngine {
    inner: DeterministicLocalRuntime,
    journal: PathBuf,
    retained: Option<ElementReference>,
    effects: Rc<RefCell<usize>>,
    calls: Rc<RefCell<Vec<String>>>,
}
impl PageRuntime for FixtureEngine {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        check_dispatched(&self.journal, control);
        self.calls.borrow_mut().push(control.request_id.clone());
        let observe = matches!(message, BrowserActorMessage::Observe { .. });
        let mut result = self.inner.dispatch(owner, message, control)?;
        if observe {
            let page = owner.unwrap();
            let rev = page.session.revisions;
            self.retained = Some(ElementReference {
                session_generation: rev.session_generation,
                document_generation: rev.document_generation,
                semantic_snapshot_revision: rev.semantic_snapshot_revision + 1,
                frame_id: "main".to_owned(),
                backend_node_key: Some("fixture-button".to_owned()),
                role: Some("button".to_owned()),
                accessible_name_sha256: Some("a".repeat(64)),
                structural_fingerprint: "b".repeat(64),
            });
            result
                .result
                .insert("fixture_only".to_owned(), JsonValue::Bool(true));
        }
        Ok(result)
    }
    fn dispatch_page_act(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        target: ElementReference,
        action: PageAction,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        check_dispatched(&self.journal, control);
        self.calls.borrow_mut().push(control.request_id.clone());
        control.ensure_active()?;
        if self.retained.as_ref() != Some(&target) || action != PageAction::Click {
            return Err(RuntimeFailure::PolicyDenied(
                "fixture target missing, changed or consumed",
            ));
        }
        self.retained = None;
        *self.effects.borrow_mut() += 1;
        Ok(RuntimeReply {
            result: JsonObject::new(),
            current_url: None,
        })
    }
}

#[test]
fn connected_transport_actor_engine_and_durable_receipts_form_one_host_chain() {
    let directory = Directory::new();
    let path = directory.0.join("receipts.hjr");
    let journal = ReceiptJournal::create(&path, JournalId([91; 16]), 1).unwrap();
    let effects = Rc::new(RefCell::new(0));
    let calls = Rc::new(RefCell::new(Vec::new()));
    let (wake, events) = mpsc::channel();
    let (port, mut engine) = engine_thread_pair(
        FixtureEngine {
            inner: DeterministicLocalRuntime::default(),
            journal: path.clone(),
            retained: None,
            effects: effects.clone(),
            calls: calls.clone(),
        },
        Arc::new(move || {
            wake.send(()).unwrap();
        }),
    );
    let (server_streams, client_streams) = sockets(6);
    let peer = PeerIdentity::from_stream(&server_streams[0]).unwrap();
    let server = thread::spawn(move || {
        let mut actor = BrowserActor::new(binding(peer), port);
        let mut observer = actor.receipt_observer(journal, "host-engine-fixture");
        let mut evidence = Vec::new();
        for stream in server_streams {
            evidence.push(
                serve_one_with_observer(
                    stream,
                    PeerPolicy::exact(peer),
                    BUDGET,
                    &mut actor,
                    &mut observer,
                )
                .unwrap(),
            );
        }
        assert!(actor.page_owner().is_none());
        let report = observer.inspect().unwrap();
        (evidence, report)
    });
    let client = thread::spawn(move || {
        let mut streams = client_streams.into_iter();
        let created = invoke(streams.next().unwrap(), create());
        let session = text(created.outcome.as_ref().unwrap(), "session_id");
        let observed = invoke(
            streams.next().unwrap(),
            req(
                "observe",
                Some(&session),
                BrowserOperation::PageObserve {
                    fields: vec![ObservationField::Role],
                },
            ),
        );
        let fields = observed.outcome.as_ref().unwrap();
        let target = ElementReference {
            session_generation: number(fields, "session_generation"),
            document_generation: number(fields, "document_generation"),
            semantic_snapshot_revision: number(fields, "semantic_snapshot_revision"),
            frame_id: "main".to_owned(),
            backend_node_key: Some("fixture-button".to_owned()),
            role: Some("button".to_owned()),
            accessible_name_sha256: Some("a".repeat(64)),
            structural_fingerprint: "b".repeat(64),
        };
        assert!(
            invoke(
                streams.next().unwrap(),
                req(
                    "act",
                    Some(&session),
                    BrowserOperation::PageAct {
                        target: target.clone(),
                        action: PageAction::Click
                    }
                )
            )
            .outcome
            .is_ok()
        );
        let denied = invoke(
            streams.next().unwrap(),
            req(
                "consumed-target",
                Some(&session),
                BrowserOperation::PageAct {
                    target,
                    action: PageAction::Click,
                },
            ),
        );
        assert!(matches!(denied.outcome,Err(e) if e.code==BrowserErrorCode::PolicyDenied));
        let foreign = invoke(
            streams.next().unwrap(),
            req(
                "foreign-session",
                Some("foreign"),
                BrowserOperation::SessionSnapshot,
            ),
        );
        assert!(matches!(foreign.outcome,Err(e) if e.code==BrowserErrorCode::StaleSession));
        assert!(
            invoke(
                streams.next().unwrap(),
                req("close", Some(&session), BrowserOperation::SessionClose)
            )
            .outcome
            .is_ok()
        );
    });
    let deadline = Instant::now() + Duration::from_secs(15);
    while !server.is_finished() {
        assert!(Instant::now() < deadline, "host chain stuck");
        if events.recv_timeout(Duration::from_millis(10)).is_ok() {
            match engine.pump_one() {
                EnginePumpResult::Replied => {}
                EnginePumpResult::Closed => {
                    // The actor's normal Drop wakes retirement after all five
                    // engine operations. It is not a sixth dispatch.
                    assert_eq!(calls.borrow().len(), 5);
                    break;
                }
                state => panic!("unexpected pump state: {state:?}"),
            }
        }
    }
    client.join().unwrap();
    let (evidence, report) = server.join().unwrap();
    assert_eq!(*effects.borrow(), 1);
    assert_eq!(
        &*calls.borrow(),
        &["create", "observe", "act", "consumed-target", "close"]
    );
    assert_eq!(evidence.len(), 6);
    assert!(evidence.iter().all(|e| e.response_committed));
    assert_eq!(report.records.len(), 18);
    assert!(report.unresolved.is_empty());
    for (rows, proof) in report.records.chunks_exact(3).zip(&evidence) {
        assert_eq!(rows[0].event.lifecycle, ReceiptLifecycleState::Requested);
        assert_eq!(rows[1].event.lifecycle, ReceiptLifecycleState::Dispatched);
        assert_eq!(rows[2].event.lifecycle, ReceiptLifecycleState::Completed);
        assert_eq!(
            hepta_session_core::hex_digest(rows[2].event.response_sha256.unwrap()),
            proof.response_sha256
        );
    }
}

struct SlowNavigation {
    inner: DeterministicLocalRuntime,
    journal: PathBuf,
    release: Receiver<()>,
    effects: Rc<RefCell<usize>>,
}
impl PageRuntime for SlowNavigation {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        check_dispatched(&self.journal, control);
        if matches!(message, BrowserActorMessage::Navigate { .. }) {
            *self.effects.borrow_mut() += 1;
            self.release.recv_timeout(BUDGET).unwrap();
            return Ok(RuntimeReply {
                result: JsonObject::new(),
                current_url: Some("http://127.0.0.1:8000/late".to_owned()),
            });
        }
        self.inner.dispatch(owner, message, control)
    }
}
#[test]
fn timed_out_running_navigation_has_no_response_and_retains_indeterminate_receipt() {
    let directory = Directory::new();
    let path = directory.0.join("receipts.hjr");
    let journal = ReceiptJournal::create(&path, JournalId([92; 16]), 1).unwrap();
    let effects = Rc::new(RefCell::new(0));
    let (release, blocked) = mpsc::channel();
    let (wake, events) = mpsc::channel();
    let (port, mut engine) = engine_thread_pair(
        SlowNavigation {
            inner: DeterministicLocalRuntime::default(),
            journal: path.clone(),
            release: blocked,
            effects: effects.clone(),
        },
        Arc::new(move || {
            wake.send(()).unwrap();
        }),
    );
    let (server_streams, client_streams) = sockets(2);
    let peer = PeerIdentity::from_stream(&server_streams[0]).unwrap();
    let server = thread::spawn(move || {
        let mut streams = server_streams.into_iter();
        let mut actor = BrowserActor::new(binding(peer), port);
        let mut observer = actor.receipt_observer(journal, "host-timeout-fixture");
        serve_one_with_observer(
            streams.next().unwrap(),
            PeerPolicy::exact(peer),
            BUDGET,
            &mut actor,
            &mut observer,
        )
        .unwrap();
        let result = serve_one_with_observer(
            streams.next().unwrap(),
            PeerPolicy::exact(peer),
            Duration::from_secs(1),
            &mut actor,
            &mut observer,
        );
        release.send(()).unwrap();
        assert!(result.is_err());
        assert_eq!(
            actor.page_owner().unwrap().session.phase,
            SessionPhase::Recovering
        );
        observer.inspect().unwrap()
    });
    let client = thread::spawn(move || {
        let mut streams = client_streams.into_iter();
        let created = invoke(streams.next().unwrap(), create());
        let session = text(created.outcome.as_ref().unwrap(), "session_id");
        let stream = streams.next().unwrap();
        let peer = PeerIdentity::from_stream(&stream).unwrap();
        let mut client =
            ClientConnection::connect(stream, PeerPolicy::exact(peer), BUDGET).unwrap();
        let request = req(
            "late-navigate",
            Some(&session),
            BrowserOperation::PageNavigate {
                target: NavigationTarget::LocalHttpFixture {
                    url: "http://127.0.0.1:8000/late".to_owned(),
                },
                expected_document_generation: 1,
            },
        );
        let seq = client
            .send_request(encode_request(&request).unwrap(), BUDGET)
            .unwrap();
        assert!(client.receive_response(seq, BUDGET).is_err());
    });
    events.recv_timeout(BUDGET).unwrap();
    assert_eq!(engine.pump_one(), EnginePumpResult::Replied);
    events.recv_timeout(BUDGET).unwrap();
    assert_eq!(engine.pump_one(), EnginePumpResult::Discarded);
    client.join().unwrap();
    let report = server.join().unwrap();
    assert_eq!(*effects.borrow(), 1);
    assert_eq!(report.records.len(), 6);
    let last = &report.records[5].event;
    assert_eq!(last.receipt_id, "late-navigate");
    assert_eq!(last.lifecycle, ReceiptLifecycleState::Indeterminate);
    assert!(last.response_sha256.is_none());
    assert!(report.unresolved.is_empty());
}

#[test]
fn actual_transport_peer_mismatch_to_fixture_principal_never_reaches_engine() {
    let directory = Directory::new();
    let path = directory.0.join("receipts.hjr");
    let journal = ReceiptJournal::create(&path, JournalId([93; 16]), 1).unwrap();
    let (wake, events) = mpsc::channel();
    let (port, mut engine) = engine_thread_pair(
        DeterministicLocalRuntime::default(),
        Arc::new(move || {
            wake.send(()).unwrap();
        }),
    );
    let (server_stream, client_stream) = UnixStream::pair().unwrap();
    let peer = PeerIdentity::from_stream(&server_stream).unwrap();
    let wrong_peer = PeerIdentity {
        uid: peer.uid.wrapping_add(1),
        ..peer
    };
    let server = thread::spawn(move || {
        let mut actor = BrowserActor::new(binding(wrong_peer), port);
        let mut observer = actor.receipt_observer(journal, "principal-negative-fixture");
        let evidence = serve_one_with_observer(
            server_stream,
            PeerPolicy::exact(peer),
            BUDGET,
            &mut actor,
            &mut observer,
        )
        .unwrap();
        assert!(!evidence.response_ok);
        observer.inspect().unwrap()
    });
    let response = invoke(
        client_stream,
        req("wrong-principal", None, BrowserOperation::Health),
    );
    assert!(matches!(response.outcome,Err(e) if e.code==BrowserErrorCode::PolicyDenied));
    let report = server.join().unwrap();
    assert_eq!(report.records.len(), 3);
    // The rejected actor is dropped: one retirement wake, no queued call.
    events.recv_timeout(BUDGET).unwrap();
    assert!(engine.receiver.try_recv().is_err());
    assert_eq!(engine.pump_one(), EnginePumpResult::Closed);
}
