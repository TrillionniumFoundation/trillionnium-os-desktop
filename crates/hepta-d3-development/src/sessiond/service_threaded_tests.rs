//! Actual daemon SessionState/runner tests. Unit/cgroup identity facts are fixtures;
//! these tests do not exercise systemd activation or a Servo adapter.
use super::*;
use hepta_browser_actor::{
    BrowserActorMessage, MechanismIdentity, PageOwnerSnapshot, PageRuntime, RequestControl,
    RuntimeFailure, RuntimeReply,
};
use std::cell::RefCell;
use std::rc::Rc;
struct CheckedFixture {
    runtime: AtomicFixtureRuntime,
    journal: PathBuf,
    threads: Rc<RefCell<Vec<std::thread::ThreadId>>>,
}
impl CheckedFixture {
    fn before(&self, control: &RequestControl) {
        self.threads.borrow_mut().push(std::thread::current().id());
        let report = hepta_session_core::inspect_receipt_journal(&self.journal).unwrap();
        let event = &report.records.last().unwrap().event;
        assert_eq!(event.receipt_id, control.request_id);
        assert_eq!(
            event.lifecycle,
            hepta_session_core::ReceiptLifecycleState::Dispatched
        );
    }
}
impl PageRuntime for CheckedFixture {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        self.before(control);
        self.runtime.dispatch(owner, message, control)
    }
    fn dispatch_page_act(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        target: hepta_browser_codec::ElementReference,
        action: hepta_browser_codec::PageAction,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        self.before(control);
        self.runtime
            .dispatch_page_act(owner, target, action, control)
    }
}
use hepta_browser_actor::engine_dispatch::engine_thread_pair;
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

static UNIQUE: AtomicU64 = AtomicU64::new(0);
struct Store(PathBuf);
impl Store {
    fn new() -> Self {
        Self(std::env::temp_dir().join(format!(
            "d3-threaded-state-{}-{}",
            std::process::id(),
            UNIQUE.fetch_add(1, Ordering::Relaxed)
        )))
    }
}
impl Drop for Store {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn snapshot(peer: PeerIdentity) -> PeerRuntimeSnapshot {
    PeerRuntimeSnapshot {
        pid: peer.pid.unwrap(),
        uid: peer.uid,
        gid: peer.gid,
        start_time_ticks: 123,
        systemd_unit: Some(PEER_UNIT.into()),
        cgroup_v2_path: format!("/system.slice/{PEER_UNIT}"),
        executable_sha256: "1".repeat(64),
    }
}
fn binding(peer: PeerIdentity) -> PrincipalBinding {
    PrincipalBinding::bind(
        TaskFlowPrincipal {
            principal_id: "fixture-principal".into(),
            expected_uid: peer.uid,
            expected_gid: peer.gid,
            expected_systemd_unit: PEER_UNIT.into(),
            expected_cgroup_v2_path: format!("/system.slice/{PEER_UNIT}"),
            expected_executable_sha256: "1".repeat(64),
        },
        MechanismIdentity {
            peer,
            systemd_unit: PEER_UNIT.into(),
            cgroup_v2_path: format!("/system.slice/{PEER_UNIT}"),
            executable_sha256: "1".repeat(64),
        },
    )
    .unwrap()
}
fn state(path: &std::path::Path, peer: PeerIdentity, runtime: EngineThreadRuntime) -> SessionState {
    attach_session(
        peer,
        snapshot(peer),
        binding(peer),
        runtime,
        storage::open_or_create_managed(path).unwrap(),
        "threaded-fixture".into(),
    )
}

#[test]
fn persistent_session_rejects_recycled_pid_with_new_process_birth() {
    let store = Store::new();
    let (runtime, _owner) = engine_thread_pair(AtomicFixtureRuntime::default(), Arc::new(|| {}));
    let peer = PeerIdentity {
        pid: Some(82),
        uid: 1000,
        gid: 1001,
    };
    let current = state(&store.0, peer, runtime);
    let mut next = snapshot(peer);
    assert!(verify_continuity(&current, peer, &next).is_ok());
    next.start_time_ticks += 1;
    assert!(
        same_peer(current.peer, peer),
        "this tuple check alone used to pass"
    );
    assert!(verify_continuity(&current, peer, &next).is_err());
    assert_eq!(current.peer_snapshot.start_time_ticks, 123);
    assert!(current.actor.page_owner().is_none());
}

#[test]
fn persistent_session_rejects_every_attested_snapshot_drift() {
    let store = Store::new();
    let (runtime, _owner) = engine_thread_pair(AtomicFixtureRuntime::default(), Arc::new(|| {}));
    let peer = PeerIdentity {
        pid: Some(82),
        uid: 1000,
        gid: 1001,
    };
    let current = state(&store.0, peer, runtime);
    for field in 0..7 {
        let mut next = snapshot(peer);
        match field {
            0 => next.pid += 1,
            1 => next.uid += 1,
            2 => next.gid += 1,
            3 => next.start_time_ticks += 1,
            4 => next.cgroup_v2_path = "/other".into(),
            5 => next.systemd_unit = Some("other.service".into()),
            _ => next.executable_sha256 = "2".repeat(64),
        }
        assert!(
            verify_continuity(&current, peer, &next).is_err(),
            "field {field}"
        );
    }
    let changed_peer = PeerIdentity {
        pid: Some(83),
        ..peer
    };
    assert!(verify_continuity(&current, changed_peer, &snapshot(peer)).is_err());
    assert!(verify_continuity(&current, peer, &snapshot(peer)).is_ok());
}

#[test]
fn actual_fixture_runs_through_service_owner_and_preserves_sequential_state() {
    exercise_fixture_service(false);
}

#[test]
fn deferred_fixture_uses_actual_callback_runner_and_preserves_fifteen_receipts() {
    exercise_fixture_service(true);
}

fn exercise_fixture_service(deferred: bool) {
    use hepta_agent_transport::ClientConnection;
    use hepta_browser_codec::{
        BrowserOperation, BrowserResponse, JsonValue, ObservationField, PageAction,
        ProfilePersistence, ProfileSpec, decode_response, encode_request,
    };
    use hepta_session_core::ReceiptLifecycleState;
    use std::thread;
    use std::time::Duration;
    let store = Store::new();
    let (servers, clients): (Vec<_>, Vec<_>) = (0..5).map(|_| UnixStream::pair().unwrap()).unzip();
    let budget = Duration::from_secs(5);
    let owner_id = thread::current().id();
    let client = thread::spawn(move || {
        let mut session = None;
        let mut target = None;
        for (index, stream) in clients.into_iter().enumerate() {
            let operation = match index {
                0 => BrowserOperation::SessionCreate {
                    profile: ProfileSpec {
                        profile_id: "ephemeral".into(),
                        persistence: ProfilePersistence::Ephemeral,
                    },
                    ui_mode: "headed".into(),
                },
                1 => BrowserOperation::PageObserve {
                    fields: vec![ObservationField::Role],
                },
                2 | 3 => BrowserOperation::PageAct {
                    target: target.clone().unwrap(),
                    action: PageAction::Click,
                },
                _ => BrowserOperation::SessionClose,
            };
            let request = BrowserRequest {
                request_id: format!("threaded-{index}"),
                session_id: session.clone(),
                session_generation: session.as_ref().map(|_| 1),
                deadline_unix_ms: None,
                operation,
            };
            let peer = PeerIdentity::from_stream(&stream).unwrap();
            let mut connection =
                ClientConnection::connect(stream, PeerPolicy::exact(peer), budget).unwrap();
            let seq = connection
                .send_request(encode_request(&request).unwrap(), budget)
                .unwrap();
            let response: BrowserResponse =
                decode_response(&connection.receive_response(seq, budget).unwrap())
                    .unwrap()
                    .value;
            assert_eq!(response.request_id, request.request_id);
            assert_eq!(
                response.outcome.is_ok(),
                index != 3,
                "stale observation must be rejected"
            );
            if index == 0 {
                let Some(JsonValue::String(value)) =
                    response.outcome.as_ref().unwrap().get("session_id")
                else {
                    panic!("session missing")
                };
                session = Some(value.clone());
            }
            if index == 1 {
                let result = response.outcome.as_ref().unwrap();
                let value = result.get("semantic_target").unwrap().clone();
                target = Some(reference(value));
            }
        }
    });
    let threads = Rc::new(RefCell::new(Vec::new()));
    let checked = CheckedFixture {
        runtime: AtomicFixtureRuntime::default(),
        journal: store.0.join("segment-0000000000000001.journal"),
        threads: threads.clone(),
    };
    let work = |runtime, stop: &engine::ServiceStop| {
        assert_ne!(thread::current().id(), owner_id);
        let peer = PeerIdentity::from_stream(&servers[0])?;
        let mut state = state(&store.0, peer, runtime);
        let mut evidence = Vec::new();
        for stream in servers {
            stop.ensure_active()?;
            verify_continuity(&state, PeerIdentity::from_stream(&stream)?, &snapshot(peer))?;
            evidence.push(serve_one_with_observer(
                stream,
                PeerPolicy::exact(peer),
                budget,
                &mut state.actor,
                &mut state.observer,
            )?);
        }
        assert!(state.actor.page_owner().is_none());
        Ok((state.observer.inspect()?, evidence))
    };
    let deferred_events = Rc::new(RefCell::new(DeferredEvents::default()));
    let result = if deferred {
        let events = deferred_events.clone();
        let mut bridge =
            hepta_browser_actor::engine_dispatch::event_loop::ImmediateCallbacks::new(checked);
        engine::run_callback_on_owner(
            DeferredFixture(events.clone()),
            move || {
                // A later driver turn, never re-enter the owner from start().
                let next = events.borrow_mut().pending.take();
                if let Some(next) = next {
                    events.borrow_mut().completed += 1;
                    next.execute(&mut bridge);
                }
                Ok(None)
            },
            work,
        )
    } else {
        engine::run_on_owner(checked, work)
    };
    let (mut observations, evidence) = result.unwrap();
    if deferred {
        let events = deferred_events.borrow();
        assert_eq!(events.started, threads.borrow().len());
        assert_eq!(events.completed, events.started);
        assert_eq!(events.retired, 1);
        assert!(events.pending.is_none());
    }
    client.join().unwrap();
    assert_eq!(observations.records.len(), 15);
    assert!(!threads.borrow().is_empty());
    assert!(threads.borrow().iter().all(|id| *id == owner_id));
    for (group, evidence) in observations.records.chunks_mut(3).zip(evidence) {
        assert_eq!(group[0].event.lifecycle, ReceiptLifecycleState::Requested);
        assert_eq!(group[1].event.lifecycle, ReceiptLifecycleState::Dispatched);
        assert!(group[2].event.lifecycle.is_terminal());
        assert_eq!(
            hepta_session_core::hex_digest(group[2].event.response_sha256.unwrap()),
            evidence.response_sha256
        );
    }
}

fn reference(value: hepta_browser_codec::JsonValue) -> hepta_browser_codec::ElementReference {
    use hepta_browser_codec::JsonValue;
    let JsonValue::Object(object) = value else {
        panic!("reference missing")
    };
    let text = |key: &str| match object.get(key).unwrap() {
        JsonValue::String(s) => s.clone(),
        _ => panic!("text"),
    };
    let num = |key: &str| match object.get(key).unwrap() {
        JsonValue::Integer(i) => u64::try_from(*i).unwrap(),
        _ => panic!("number"),
    };
    hepta_browser_codec::ElementReference {
        session_generation: num("session_generation"),
        document_generation: num("document_generation"),
        semantic_snapshot_revision: num("semantic_snapshot_revision"),
        frame_id: text("frame_id"),
        backend_node_key: Some(text("backend_node_key")),
        role: Some(text("role")),
        accessible_name_sha256: Some(text("accessible_name_sha256")),
        structural_fingerprint: text("structural_fingerprint"),
    }
}

#[test]
fn recreated_service_reopens_journal_but_rejects_old_session_and_reparented_target() {
    // Real UnixStream/SO_PEERCRED/codec/thread runner/journal; engine and unit
    // facts remain fixtures. This reconstructs a service in one process, not
    // a systemd/QEMU/physical restart qualification.
    use hepta_agent_transport::ClientConnection;
    use hepta_browser_codec::{
        BrowserErrorCode, BrowserOperation, JsonValue, ObservationField, PageAction,
        ProfilePersistence, ProfileSpec, decode_response, encode_request,
    };
    use std::thread;
    use std::time::Duration;
    let store = Store::new();
    let mut prior: Option<(String, hepta_browser_codec::ElementReference)> = None;
    let mut all_evidence = Vec::new();
    let mut report = None;
    let owner_id = thread::current().id();
    let threads = Rc::new(RefCell::new(Vec::new()));
    let budget = Duration::from_secs(5);
    for phase in 0..2 {
        let count = if phase == 0 { 2 } else { 6 };
        let (servers, clients): (Vec<_>, Vec<_>) =
            (0..count).map(|_| UnixStream::pair().unwrap()).unzip();
        let previous = prior.clone();
        let client = thread::spawn(move || {
            let mut session = None;
            let mut target = None;
            for (index, stream) in clients.into_iter().enumerate() {
                let operation = match index {
                    0 => BrowserOperation::SessionCreate {
                        profile: ProfileSpec {
                            profile_id: "restart-ephemeral".into(),
                            persistence: ProfilePersistence::Ephemeral,
                        },
                        ui_mode: "headed".into(),
                    },
                    1 => BrowserOperation::PageObserve {
                        fields: vec![ObservationField::Role],
                    },
                    2 | 3 => BrowserOperation::PageAct {
                        target: previous.as_ref().unwrap().1.clone(),
                        action: PageAction::Click,
                    },
                    4 => BrowserOperation::PageAct {
                        target: target.clone().unwrap(),
                        action: PageAction::Click,
                    },
                    _ => BrowserOperation::SessionClose,
                };
                let envelope_session = if index == 2 {
                    Some(previous.as_ref().unwrap().0.clone())
                } else {
                    session.clone()
                };
                let request = BrowserRequest {
                    request_id: format!("incarnation-{phase}-{index}"),
                    session_id: envelope_session.clone(),
                    session_generation: envelope_session.map(|_| 1),
                    deadline_unix_ms: None,
                    operation,
                };
                let peer = PeerIdentity::from_stream(&stream).unwrap();
                let mut connection =
                    ClientConnection::connect(stream, PeerPolicy::exact(peer), budget).unwrap();
                let sequence = connection
                    .send_request(encode_request(&request).unwrap(), budget)
                    .unwrap();
                let response =
                    decode_response(&connection.receive_response(sequence, budget).unwrap())
                        .unwrap()
                        .value;
                assert_eq!(response.request_id, request.request_id);
                if index == 2 || index == 3 {
                    assert_eq!(
                        response.outcome.as_ref().unwrap_err().code,
                        if index == 2 {
                            BrowserErrorCode::StaleSession
                        } else {
                            BrowserErrorCode::PolicyDenied
                        }
                    );
                } else {
                    let result = response.outcome.as_ref().unwrap();
                    if index == 0 {
                        let JsonValue::String(id) = &result["session_id"] else {
                            panic!("missing session")
                        };
                        if let Some(old) = &previous {
                            assert_ne!(&old.0, id);
                        }
                        session = Some(id.clone());
                    }
                    if index == 1 {
                        target = Some(reference(result["semantic_target"].clone()));
                        if let Some(old) = &previous {
                            assert_ne!(old.1.frame_id, target.as_ref().unwrap().frame_id);
                        }
                    }
                    if index == 4 {
                        assert_eq!(result["action_count"], JsonValue::Integer(1));
                        assert_eq!(result["servo_adapter_exercised"], JsonValue::Bool(false));
                    }
                }
            }
            (session.unwrap(), target.unwrap())
        });
        let checked = CheckedFixture {
            runtime: AtomicFixtureRuntime::default(),
            journal: store.0.join("segment-0000000000000001.journal"),
            threads: threads.clone(),
        };
        let (records, evidence) = engine::run_on_owner(checked, |runtime, stop| {
            let peer = PeerIdentity::from_stream(&servers[0])?;
            let mut current = state(&store.0, peer, runtime);
            let mut evidence = Vec::new();
            for stream in servers {
                stop.ensure_active()?;
                verify_continuity(
                    &current,
                    PeerIdentity::from_stream(&stream)?,
                    &snapshot(peer),
                )?;
                evidence.push(serve_one_with_observer(
                    stream,
                    PeerPolicy::exact(peer),
                    budget,
                    &mut current.actor,
                    &mut current.observer,
                )?);
            }
            Ok((current.observer.inspect()?, evidence))
        })
        .unwrap();
        prior = Some(client.join().unwrap());
        assert_eq!(records.records.len(), if phase == 0 { 6 } else { 24 });
        all_evidence.extend(evidence);
        report = Some(records);
    }
    let records = report.unwrap().records;
    assert_eq!(
        threads.borrow().len(),
        7,
        "old outer session must not enter the backend; reparented target is refused inside fixture"
    );
    assert!(threads.borrow().iter().all(|t| *t == owner_id));
    assert_eq!(records.len(), 24);
    for (group, evidence) in records.chunks(3).zip(all_evidence) {
        assert_eq!(
            group[0].event.lifecycle,
            hepta_session_core::ReceiptLifecycleState::Requested
        );
        assert_eq!(
            group[1].event.lifecycle,
            hepta_session_core::ReceiptLifecycleState::Dispatched
        );
        assert!(group[2].event.lifecycle.is_terminal());
        assert_eq!(
            hepta_session_core::hex_digest(group[2].event.response_sha256.unwrap()),
            evidence.response_sha256
        );
        assert_eq!(group[0].event.receipt_id, evidence.request_id);
    }
}

// Deferred fixture event registrations contain the original one-shot token.
// The driver invokes the immediate bridge only on a subsequent event turn.
use hepta_browser_actor::engine_dispatch::event_loop::{CallbackPageRuntime, EngineCompletion};
#[derive(Default)]
struct DeferredEvents {
    pending: Option<DeferredOperation>,
    started: usize,
    completed: usize,
    retired: usize,
}
enum DeferredOperation {
    Ordinary(
        Option<PageOwnerSnapshot>,
        BrowserActorMessage,
        EngineCompletion,
    ),
    Atomic(
        Option<PageOwnerSnapshot>,
        hepta_browser_codec::ElementReference,
        hepta_browser_codec::PageAction,
        EngineCompletion,
    ),
}
impl DeferredOperation {
    fn execute(self, bridge: &mut impl CallbackPageRuntime) {
        match self {
            Self::Ordinary(owner, message, done) => bridge.start(owner.as_ref(), message, done),
            Self::Atomic(owner, target, action, done) => {
                bridge.start_page_act(owner.as_ref(), target, action, done)
            }
        }
    }
}
struct DeferredFixture(Rc<RefCell<DeferredEvents>>);
impl CallbackPageRuntime for DeferredFixture {
    fn start(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        done: EngineCompletion,
    ) {
        let mut e = self.0.borrow_mut();
        assert!(e.pending.is_none());
        e.started += 1;
        e.pending = Some(DeferredOperation::Ordinary(owner.cloned(), message, done));
    }
    fn start_page_act(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        target: hepta_browser_codec::ElementReference,
        action: hepta_browser_codec::PageAction,
        done: EngineCompletion,
    ) {
        let mut e = self.0.borrow_mut();
        assert!(e.pending.is_none());
        e.started += 1;
        e.pending = Some(DeferredOperation::Atomic(
            owner.cloned(),
            target,
            action,
            done,
        ));
    }
    fn retire(&mut self) {
        let mut e = self.0.borrow_mut();
        e.retired += 1;
        e.pending.take();
    }
}
