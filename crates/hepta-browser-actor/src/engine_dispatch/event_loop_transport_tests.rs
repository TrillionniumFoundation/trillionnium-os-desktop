//! Real host socket/handshake/actor/journal with deferred fixture callbacks.
//! The event-loop driver, engine and procfs unit/executable material are fixtures,
//! not winit, Servo, systemd, an installed image, or external network effects.
use super::super::authority_tests::Fixture;
use super::*;
use crate::{BrowserActor, DeterministicLocalRuntime, PageRuntime};
use hepta_agent_port::{
    BrowserRequestHandler, DispatchContext, HandlerOutcome, serve_one_with_observer,
};
use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserRequest, BrowserResponse, JsonValue, NavigationTarget,
    ProfilePersistence, ProfileSpec, decode_response, encode_request,
};
use hepta_session_core::{
    JournalId, ReceiptJournal, ReceiptLifecycleState, SessionPhase, inspect_receipt_journal,
};
use std::cell::RefCell;
use std::collections::VecDeque;
use std::fs;
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::time::Duration;

const BUDGET: Duration = Duration::from_secs(5);
struct NativeOperation {
    owner: Option<PageOwnerSnapshot>,
    message: BrowserActorMessage,
    completion: EngineCompletion,
}
#[derive(Default)]
struct NativeEvents {
    queue: VecDeque<NativeOperation>,
    started: Vec<String>,
    retired: usize,
}
struct Adapter(Rc<RefCell<NativeEvents>>);
impl CallbackPageRuntime for Adapter {
    fn start(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        completion: EngineCompletion,
    ) {
        let mut events = self.0.borrow_mut();
        events.started.push(completion.request_id().to_owned());
        events.queue.push_back(NativeOperation {
            owner: owner.cloned(),
            message,
            completion,
        });
    }
    fn retire(&mut self) {
        let mut events = self.0.borrow_mut();
        events.retired += 1;
        events.queue.clear();
    }
}
struct AttestedHandler<'a> {
    actor: &'a mut BrowserActor<EngineThreadRuntime>,
    fixture: &'a Fixture,
}
impl BrowserRequestHandler for AttestedHandler<'_> {
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
fn request(id: &str, session: Option<&str>, operation: BrowserOperation) -> BrowserRequest {
    BrowserRequest {
        request_id: id.to_owned(),
        session_id: session.map(str::to_owned),
        session_generation: session.map(|_| 1),
        deadline_unix_ms: None,
        operation,
    }
}
fn call(stream: UnixStream, request: BrowserRequest) -> BrowserResponse {
    let peer = PeerIdentity::from_stream(&stream).unwrap();
    let mut client = ClientConnection::connect(stream, PeerPolicy::exact(peer), BUDGET).unwrap();
    let sequence = client
        .send_request(encode_request(&request).unwrap(), BUDGET)
        .unwrap();
    let response = decode_response(&client.receive_response(sequence, BUDGET).unwrap())
        .unwrap()
        .value;
    assert_eq!(response.request_id, request.request_id);
    assert_eq!(response.session_id, request.session_id);
    response
}
fn next_native_event(
    events: &Rc<RefCell<NativeEvents>>,
    runtime: &mut DeterministicLocalRuntime,
    journal: &PathBuf,
    corrupt_after_navigation: Option<&PathBuf>,
    ticks: &mut usize,
) -> bool {
    let Some(operation) = events.borrow_mut().queue.pop_front() else {
        return false;
    };
    // This work runs only on a later native-event turn, after pump_one returned.
    *ticks += 1;
    let report = inspect_receipt_journal(journal).unwrap();
    let rows = &report.records[report.records.len() - 2..];
    assert_eq!(rows[0].event.lifecycle, ReceiptLifecycleState::Requested);
    assert_eq!(rows[1].event.lifecycle, ReceiptLifecycleState::Dispatched);
    assert_eq!(rows[1].event.receipt_id, operation.completion.request_id());
    operation.completion.ensure_current_peer().unwrap();
    let is_navigation = matches!(operation.message, BrowserActorMessage::Navigate { .. });
    let result = runtime.dispatch(
        operation.owner.as_ref(),
        operation.message,
        &operation.completion.control,
    );
    if is_navigation && let Some(path) = corrupt_after_navigation {
        fs::write(path, b"different-fixture-executable").unwrap();
    }
    assert_eq!(
        operation.completion.complete(result),
        CompletionDelivery::Queued
    );
    true
}

fn exercise(corrupt: bool) {
    let fixture = Fixture::new();
    let path = fixture.root.join("callback-receipts.hjr");
    let executable = fixture.process.join("exe");
    let journal = ReceiptJournal::create(&path, JournalId([98; 16]), 1).unwrap();
    let events = Rc::new(RefCell::new(NativeEvents::default()));
    let (wake, wakes) = mpsc::channel();
    let (port, mut engine) = callback_engine_pair(
        Adapter(events.clone()),
        Arc::new(move || {
            let _ = wake.send(());
        }),
    );
    let count = if corrupt { 2 } else { 4 };
    let (servers, clients): (Vec<_>, Vec<_>) =
        (0..count).map(|_| UnixStream::pair().unwrap()).unzip();
    let server = thread::spawn(move || {
        let mut actor = BrowserActor::new(fixture.binding.clone(), port);
        let mut observer = actor.receipt_observer(journal, "callback-fixture-image");
        let mut proofs = Vec::new();
        for socket in servers {
            let mut handler = AttestedHandler {
                actor: &mut actor,
                fixture: &fixture,
            };
            proofs.push(
                serve_one_with_observer(
                    socket,
                    PeerPolicy::exact(fixture.peer),
                    BUDGET,
                    &mut handler,
                    &mut observer,
                )
                .unwrap(),
            );
        }
        (
            proofs,
            observer.inspect().unwrap(),
            actor.page_owner(),
            actor.runtime_unavailable,
            fixture,
        )
    });
    let client = thread::spawn(move || {
        let mut streams = clients.into_iter();
        let created = call(
            streams.next().unwrap(),
            request(
                "cb-create",
                None,
                BrowserOperation::SessionCreate {
                    profile: ProfileSpec {
                        profile_id: "callback-fixture".to_owned(),
                        persistence: ProfilePersistence::Ephemeral,
                    },
                    ui_mode: "headed".to_owned(),
                },
            ),
        );
        let result = created.outcome.unwrap();
        let Some(JsonValue::String(session)) = result.get("session_id") else {
            panic!("missing session");
        };
        let nav = call(
            streams.next().unwrap(),
            request(
                "cb-navigate",
                Some(session),
                BrowserOperation::PageNavigate {
                    target: NavigationTarget::LocalHttpFixture {
                        url: "http://127.0.0.1:8080/callback-fixture".to_owned(),
                    },
                    expected_document_generation: 1,
                },
            ),
        );
        if corrupt {
            let error = nav.outcome.unwrap_err();
            assert_eq!(error.code, BrowserErrorCode::Indeterminate);
            assert_eq!(error.retry_policy(), "never_automatic");
            return;
        }
        assert!(nav.outcome.is_ok());
        assert!(
            call(
                streams.next().unwrap(),
                request(
                    "cb-snapshot",
                    Some(session),
                    BrowserOperation::SessionSnapshot
                )
            )
            .outcome
            .is_ok()
        );
        assert!(
            call(
                streams.next().unwrap(),
                request("cb-close", Some(session), BrowserOperation::SessionClose)
            )
            .outcome
            .is_ok()
        );
    });
    let limit = Instant::now() + Duration::from_secs(15);
    let mut local_runtime = DeterministicLocalRuntime::default();
    let mut native_ticks = 0;
    let mut pending_turns = 0;
    while !server.is_finished() {
        assert!(Instant::now() < limit, "callback host chain stuck");
        // Process an event from a previous iteration, never wait inside start.
        next_native_event(
            &events,
            &mut local_runtime,
            &path,
            corrupt.then_some(&executable),
            &mut native_ticks,
        );
        let timeout = engine
            .next_wake_deadline()
            .map(|at| at.saturating_duration_since(Instant::now()))
            .unwrap_or(Duration::from_millis(10));
        let _ = wakes.recv_timeout(timeout.min(Duration::from_millis(10)));
        match engine.pump_one() {
            CallbackPumpResult::Pending => pending_turns += 1,
            CallbackPumpResult::Idle
            | CallbackPumpResult::Replied
            | CallbackPumpResult::Retired => {}
        }
    }
    client.join().unwrap();
    let (proofs, report, owner, unavailable, _fixture) = server.join().unwrap();
    assert_eq!(native_ticks, count);
    assert!(pending_turns >= count);
    assert_eq!(events.borrow().started.len(), count);
    assert!(events.borrow().queue.is_empty());
    assert_eq!(report.records.len(), count * 3);
    for (index, (rows, proof)) in report.records.chunks_exact(3).zip(proofs).enumerate() {
        assert_eq!(rows[0].event.lifecycle, ReceiptLifecycleState::Requested);
        assert_eq!(rows[1].event.lifecycle, ReceiptLifecycleState::Dispatched);
        if corrupt && index == 1 {
            assert_eq!(
                rows[2].event.lifecycle,
                ReceiptLifecycleState::Indeterminate
            );
            assert!(rows[2].event.outcome.is_none());
            assert!(rows[2].event.response_sha256.is_none());
        } else {
            assert_eq!(rows[2].event.lifecycle, ReceiptLifecycleState::Completed);
            assert_eq!(
                hepta_session_core::hex_digest(rows[2].event.response_sha256.unwrap()),
                proof.response_sha256
            );
        }
    }
    if corrupt {
        assert!(unavailable);
        assert_eq!(owner.unwrap().session.phase, SessionPhase::Recovering);
    } else {
        assert!(!unavailable);
        assert!(owner.is_none());
    }
    engine.retire();
    drop(engine);
    assert_eq!(events.borrow().retired, 1);
}

#[test]
fn attested_host_chain_yields_for_native_callbacks_and_preserves_twelve_receipts() {
    exercise(false);
}
#[test]
fn attested_deferred_navigation_identity_loss_is_indeterminate_not_success() {
    exercise(true);
}
