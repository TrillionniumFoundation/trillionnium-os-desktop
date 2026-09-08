//! Boundary regressions use real pidfds and threads, with explicitly synthetic
//! procfs unit/executable facts. They are not Servo or systemd qualification.
use super::*;
use crate::{BrowserActor, PrincipalBinding, TaskFlowPrincipal};
use hepta_agent_port::{DispatchContext, HandlerOutcome};
use hepta_agent_transport::PeerIdentity;
use hepta_browser_codec::{EffectClass, JsonObject};
use hepta_peer_attestation::{AttestedPeer, PeerRuntimePolicy, ProcfsPeerAttestor};
use std::cell::{Cell, RefCell};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::sync::atomic::AtomicU64;
use std::time::Instant;

static NEXT: AtomicU64 = AtomicU64::new(0);
const BUDGET: Duration = Duration::from_secs(5);
pub(super) struct Fixture {
    pub(super) root: PathBuf,
    pub(super) process: PathBuf,
    pub(super) peer: PeerIdentity,
    pub(super) attestor: ProcfsPeerAttestor,
    pub(super) attested: AttestedPeer,
    pub(super) binding: PrincipalBinding,
}
impl Fixture {
    pub(super) fn new() -> Self {
        let (stream, _other) = UnixStream::pair().unwrap();
        let peer = PeerIdentity::from_stream(&stream).unwrap();
        let pid = peer.pid.unwrap();
        let root = std::env::temp_dir().join(format!(
            "hepta-authority-{pid}-{}",
            NEXT.fetch_add(1, Ordering::SeqCst)
        ));
        let process = root.join(pid.to_string());
        fs::create_dir_all(&process).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        fs::write(
            process.join("status"),
            format!(
                "Uid:\t{0}\t{0}\t{0}\t{0}\nGid:\t{1}\t{1}\t{1}\t{1}\n",
                peer.uid, peer.gid
            ),
        )
        .unwrap();
        let mut fields = vec!["S"; 20];
        fields[19] = "987654";
        fs::write(
            process.join("stat"),
            format!("{pid} (fixture) {}\n", fields.join(" ")),
        )
        .unwrap();
        fs::write(process.join("cgroup"), "0::/system.slice/fixture.service\n").unwrap();
        fs::write(process.join("exe"), b"bounded-fixture-executable").unwrap();
        let attestor = ProcfsPeerAttestor::new(&root);
        let snapshot = attestor.read_snapshot(pid).unwrap();
        let attested = attestor
            .attest(peer, &PeerRuntimePolicy::exact(&snapshot))
            .unwrap();
        let binding = PrincipalBinding::bind_attested(
            TaskFlowPrincipal {
                principal_id: "fixture-task".to_owned(),
                expected_uid: peer.uid,
                expected_gid: peer.gid,
                expected_systemd_unit: snapshot.systemd_unit.clone().unwrap(),
                expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
                expected_executable_sha256: snapshot.executable_sha256.clone(),
            },
            peer,
            &snapshot,
        )
        .unwrap();
        Self {
            root,
            process,
            peer,
            attestor,
            attested,
            binding,
        }
    }
    fn context(&self) -> DispatchContext {
        let accepted_at = Instant::now();
        DispatchContext {
            peer: self.peer,
            transport_sequence: 1,
            canonical_request_sha256: "2".repeat(64),
            effect_class: EffectClass::Observation,
            accepted_at,
            effective_deadline: accepted_at + BUDGET,
        }
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}
fn health() -> BrowserRequest {
    BrowserRequest {
        request_id: "guard-health".to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    }
}
struct Counter(Rc<Cell<usize>>);
impl PageRuntime for Counter {
    fn dispatch(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        _: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        self.0.set(self.0.get() + 1);
        Ok(RuntimeReply {
            result: JsonObject::new(),
            current_url: None,
        })
    }
}

fn changed_queued_identity_is_refused(file: &str, replacement: &str) {
    let fixture = Fixture::new();
    let path = fixture.process.join(file);
    let calls = Rc::new(Cell::new(0));
    let (wake, events) = mpsc::sync_channel(1);
    let (port, mut engine) = engine_thread_pair(
        Counter(calls.clone()),
        Arc::new(move || wake.try_send(()).unwrap()),
    );
    let worker = thread::spawn(move || {
        let mut actor = BrowserActor::new(fixture.binding.clone(), port);
        let outcome = actor
            .handle_attested(
                &fixture.context(),
                &health(),
                &fixture.attestor,
                &fixture.attested,
            )
            .unwrap();
        (outcome, fixture)
    });
    events.recv_timeout(BUDGET).unwrap();
    fs::write(path, replacement).unwrap();
    engine.pump_one();
    let (outcome, _fixture) = worker.join().unwrap();
    assert_eq!(calls.get(), 0, "changed queued peer must not reach backend");
    assert!(matches!(outcome, HandlerOutcome::Failure(_)));
}

#[test]
fn queued_request_rechecks_cgroup_at_engine_boundary() {
    changed_queued_identity_is_refused("cgroup", "0::/system.slice/replaced.service\n");
}
#[test]
fn queued_request_rechecks_executable_at_engine_boundary() {
    changed_queued_identity_is_refused("exe", "changed-fixture-executable");
}

#[test]
fn queued_request_rechecks_process_birth_at_engine_boundary() {
    let pid = std::process::id();
    let mut fields = vec!["S"; 20];
    fields[19] = "987655";
    changed_queued_identity_is_refused("stat", &format!("{pid} (fixture) {}\n", fields.join(" ")));
}

#[test]
fn queued_request_rechecks_peer_credentials_at_engine_boundary() {
    changed_queued_identity_is_refused(
        "status",
        "Uid:\t1234\t1234\t1234\t1234\nGid:\t1234\t1234\t1234\t1234\n",
    );
}

struct Capture {
    controls: Rc<RefCell<Vec<RequestControl>>>,
    panic: bool,
    change: Option<PathBuf>,
}
impl PageRuntime for Capture {
    fn dispatch(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        control.ensure_current_peer()?;
        self.controls.borrow_mut().push(control.clone());
        if self.panic {
            panic!("deliberate fixture unwind");
        }
        if let Some(path) = &self.change {
            fs::write(path, "0::/system.slice/changed.service\n").unwrap();
        }
        Ok(RuntimeReply {
            result: JsonObject::new(),
            current_url: None,
        })
    }
}
#[test]
fn attested_success_revokes_retained_control_and_next_request_gets_fresh_custody() {
    let f = Fixture::new();
    let controls = Rc::new(RefCell::new(Vec::new()));
    let mut actor = BrowserActor::new(
        f.binding.clone(),
        Capture {
            controls: controls.clone(),
            panic: false,
            change: None,
        },
    );
    for _ in 0..2 {
        let outcome = actor
            .handle_attested(&f.context(), &health(), &f.attestor, &f.attested)
            .unwrap();
        assert!(matches!(outcome, HandlerOutcome::Success(_)));
        assert!(actor.request_authority.borrow().is_none());
        for c in controls.borrow().iter() {
            assert!(matches!(
                c.ensure_active(),
                Err(RuntimeFailure::PeerIdentityRevoked)
            ));
        }
    }
    assert_eq!(controls.borrow().len(), 2);
}
#[test]
fn direct_backend_identity_drift_never_becomes_confirmed_success() {
    let f = Fixture::new();
    let controls = Rc::new(RefCell::new(Vec::new()));
    let mut actor = BrowserActor::new(
        f.binding.clone(),
        Capture {
            controls: controls.clone(),
            panic: false,
            change: Some(f.process.join("cgroup")),
        },
    );
    let outcome = actor
        .handle_attested(&f.context(), &health(), &f.attestor, &f.attested)
        .unwrap();
    let HandlerOutcome::Failure(error) = outcome else {
        panic!("stale success");
    };
    assert_eq!(
        error.code,
        hepta_browser_codec::BrowserErrorCode::Indeterminate
    );
    assert!(actor.runtime_unavailable);
    assert!(actor.request_authority.borrow().is_none());
    assert_eq!(controls.borrow().len(), 1);
}
#[test]
fn unwinding_request_revokes_retained_control_and_clears_authority_slot() {
    let f = Fixture::new();
    let controls = Rc::new(RefCell::new(Vec::new()));
    let mut actor = BrowserActor::new(
        f.binding.clone(),
        Capture {
            controls: controls.clone(),
            panic: true,
            change: None,
        },
    );
    assert!(
        catch_unwind(AssertUnwindSafe(|| actor.handle_attested(
            &f.context(),
            &health(),
            &f.attestor,
            &f.attested
        )))
        .is_err()
    );
    assert!(actor.request_authority.borrow().is_none());
    assert!(matches!(
        controls.borrow()[0].ensure_current_peer(),
        Err(RuntimeFailure::PeerIdentityRevoked)
    ));
    // Caller must retire an actor after an arbitrary backend unwind; this test
    // proves guard cleanup only, not successful actor reconstruction.
}
#[test]
fn cancelled_attested_request_never_calls_backend_or_leaks_scope() {
    let f = Fixture::new();
    let controls = Rc::new(RefCell::new(Vec::new()));
    let mut actor = BrowserActor::new(
        f.binding.clone(),
        Capture {
            controls: controls.clone(),
            panic: false,
            change: None,
        },
    );
    actor.cancel_request(health().request_id);
    assert!(matches!(
        actor
            .handle_attested(&f.context(), &health(), &f.attestor, &f.attested)
            .unwrap(),
        HandlerOutcome::Failure(_)
    ));
    assert!(controls.borrow().is_empty());
    assert!(actor.request_authority.borrow().is_none());
}
#[test]
fn expired_attested_request_does_not_start_identity_io() {
    let f = Fixture::new();
    let controls = Rc::new(RefCell::new(Vec::new()));
    let mut actor = BrowserActor::new(
        f.binding.clone(),
        Capture {
            controls: controls.clone(),
            panic: false,
            change: None,
        },
    );
    let mut context = f.context();
    context.effective_deadline = context.accepted_at;
    fs::remove_file(f.process.join("exe")).unwrap();
    assert!(matches!(
        actor.handle_attested(&context, &health(), &f.attestor, &f.attested),
        Err(hepta_agent_port::AgentPortError::DeadlineExceeded)
    ));
    assert!(controls.borrow().is_empty());
    assert!(actor.request_authority.borrow().is_none());
}
#[test]
fn unattested_compatibility_call_is_explicitly_not_a_peer_custody_claim() {
    use hepta_agent_port::BrowserRequestHandler;
    let f = Fixture::new();
    let controls = Rc::new(RefCell::new(Vec::new()));
    let mut actor = BrowserActor::new(
        f.binding.clone(),
        Capture {
            controls: controls.clone(),
            panic: false,
            change: None,
        },
    );
    assert!(matches!(
        actor.handle(&f.context(), &health()).unwrap(),
        HandlerOutcome::Success(_)
    ));
    assert!(controls.borrow()[0].authority.is_none());
}

struct WireAttested<'a> {
    actor: &'a mut BrowserActor<EngineThreadRuntime>,
    fixture: &'a Fixture,
}
impl hepta_agent_port::BrowserRequestHandler for WireAttested<'_> {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, hepta_agent_port::AgentPortError> {
        self.actor.handle_attested(
            context,
            request,
            &self.fixture.attestor,
            &self.fixture.attested,
        )
    }
}
fn wire_call(stream: UnixStream, request: BrowserRequest) -> hepta_browser_codec::BrowserResponse {
    use hepta_agent_transport::{ClientConnection, PeerPolicy};
    let peer = PeerIdentity::from_stream(&stream).unwrap();
    let mut c = ClientConnection::connect(stream, PeerPolicy::exact(peer), BUDGET).unwrap();
    let seq = c
        .send_request(encode_request(&request).unwrap(), BUDGET)
        .unwrap();
    hepta_browser_codec::decode_response(&c.receive_response(seq, BUDGET).unwrap())
        .unwrap()
        .value
}
struct ChangeAfterNavigate {
    inner: crate::DeterministicLocalRuntime,
    cgroup: PathBuf,
    journal: PathBuf,
    effects: Rc<Cell<usize>>,
}
impl PageRuntime for ChangeAfterNavigate {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        let report = hepta_session_core::inspect_receipt_journal(&self.journal).unwrap();
        let last = report.records.last().unwrap();
        assert_eq!(last.event.receipt_id, control.request_id);
        assert_eq!(
            last.event.lifecycle,
            hepta_session_core::ReceiptLifecycleState::Dispatched
        );
        let change = matches!(message, BrowserActorMessage::Navigate { .. });
        let reply = self.inner.dispatch(owner, message, control)?;
        if change {
            self.effects.set(self.effects.get() + 1);
            fs::write(&self.cgroup, "0::/system.slice/changed.service\n").unwrap();
        }
        Ok(reply)
    }
}
#[test]
fn attested_socket_navigation_drift_records_indeterminate_without_success_digest() {
    use hepta_agent_transport::PeerPolicy;
    use hepta_browser_codec::{BrowserErrorCode, ProfileSpec};
    use hepta_session_core::{
        JournalId, ReceiptJournal, ReceiptLifecycleState, SessionPhase, inspect_receipt_journal,
    };
    let fixture = Fixture::new();
    let path = fixture.root.join("receipts.hjr");
    let journal = ReceiptJournal::create(&path, JournalId([94; 16]), 1).unwrap();
    let effects = Rc::new(Cell::new(0));
    let (wake, events) = mpsc::sync_channel(1);
    let (port, mut engine) = engine_thread_pair(
        ChangeAfterNavigate {
            inner: crate::DeterministicLocalRuntime::default(),
            cgroup: fixture.process.join("cgroup"),
            journal: path.clone(),
            effects: effects.clone(),
        },
        Arc::new(move || wake.try_send(()).unwrap()),
    );
    let (server1, client1) = UnixStream::pair().unwrap();
    let (server2, client2) = UnixStream::pair().unwrap();
    let worker = thread::spawn(move || {
        let mut actor = BrowserActor::new(fixture.binding.clone(), port);
        let mut observer = actor.receipt_observer(journal, "fixture-image");
        for s in [server1, server2] {
            let mut handler = WireAttested {
                actor: &mut actor,
                fixture: &fixture,
            };
            hepta_agent_port::serve_one_with_observer(
                s,
                PeerPolicy::exact(fixture.peer),
                BUDGET,
                &mut handler,
                &mut observer,
            )
            .unwrap();
        }
        (
            actor.page_owner().unwrap(),
            actor.runtime_unavailable,
            fixture,
        )
    });
    let client = thread::spawn(move || {
        let mut create = health();
        create.operation = BrowserOperation::SessionCreate {
            profile: ProfileSpec {
                profile_id: "fixture".to_owned(),
                persistence: ProfilePersistence::Ephemeral,
            },
            ui_mode: "headed".to_owned(),
        };
        let result = wire_call(client1, create).outcome.unwrap();
        let Some(JsonValue::String(session)) = result.get("session_id") else {
            panic!("missing session")
        };
        let nav = BrowserRequest {
            request_id: "guard-nav".to_owned(),
            session_id: Some(session.clone()),
            session_generation: Some(1),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageNavigate {
                target: NavigationTarget::LocalHttpFixture {
                    url: "http://127.0.0.1:8000/fixture".to_owned(),
                },
                expected_document_generation: 1,
            },
        };
        let error = wire_call(client2, nav).outcome.unwrap_err();
        assert_eq!(error.code, BrowserErrorCode::Indeterminate);
        assert_eq!(error.retry_policy(), "never_automatic");
    });
    for _ in 0..2 {
        events.recv_timeout(BUDGET).unwrap();
        engine.pump_one();
    }
    let (owner, unavailable, _fixture) = worker.join().unwrap();
    client.join().unwrap();
    assert!(unavailable);
    assert_eq!(owner.session.phase, SessionPhase::Recovering);
    assert_eq!(effects.get(), 1);
    let report = inspect_receipt_journal(&path).unwrap();
    assert_eq!(report.records.len(), 6);
    let last = &report.records.last().unwrap().event;
    assert_eq!(last.lifecycle, ReceiptLifecycleState::Indeterminate);
    assert!(last.outcome.is_none());
    assert!(last.response_sha256.is_none());
}
