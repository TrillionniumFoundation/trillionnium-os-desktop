use super::*;
use crate::{CancellationToken, DeterministicLocalRuntime};
use hepta_browser_codec::{JsonObject, ObservationField, ProfileSpec, WaitCondition};
use hepta_session_core::SessionMachine;
use std::cell::RefCell;
use std::time::Instant;

const TEST_BUDGET: Duration = Duration::from_secs(5);

fn control(id: &str) -> RequestControl {
    RequestControl {
        request_id: id.to_owned(),
        deadline: Instant::now() + TEST_BUDGET,
        cancelled: false,
        cancellation: CancellationToken::new(),
        authority: None,
    }
}
pub(super) fn owner() -> PageOwnerSnapshot {
    PageOwnerSnapshot {
        session_id: "session-1".to_owned(),
        webview_token: "view-1".to_owned(),
        current_url: "http://127.0.0.1:8000/fixture".to_owned(),
        local_fixture_only: true,
        session: SessionMachine::new().snapshot(),
    }
}
pub(super) fn target() -> ElementReference {
    ElementReference {
        session_generation: 1,
        document_generation: 1,
        semantic_snapshot_revision: 1,
        frame_id: "frame-main".to_owned(),
        backend_node_key: Some("button-1".to_owned()),
        role: Some("button".to_owned()),
        accessible_name_sha256: Some("1".repeat(64)),
        structural_fingerprint: "2".repeat(64),
    }
}
fn reply() -> RuntimeReply {
    RuntimeReply {
        result: JsonObject::new(),
        current_url: None,
    }
}
#[derive(Default)]
struct Calls {
    ordinary: usize,
    atomic: usize,
    threads: Vec<ThreadId>,
    owners: Vec<Option<PageOwnerSnapshot>>,
}
struct NonSendEngine(Rc<RefCell<Calls>>);
impl PageRuntime for NonSendEngine {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        control.ensure_active()?;
        assert!(!matches!(message, BrowserActorMessage::Act { .. }));
        let mut calls = self.0.borrow_mut();
        calls.ordinary += 1;
        calls.threads.push(thread::current().id());
        calls.owners.push(owner.cloned());
        let mut result = reply();
        result.result.insert(
            "id".to_owned(),
            JsonValue::String(control.request_id.clone()),
        );
        Ok(result)
    }
    fn dispatch_page_act(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        got: ElementReference,
        action: PageAction,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        control.ensure_active()?;
        assert_eq!(got, target());
        assert_eq!(action, PageAction::Click);
        let mut calls = self.0.borrow_mut();
        calls.atomic += 1;
        calls.threads.push(thread::current().id());
        calls.owners.push(owner.cloned());
        Ok(reply())
    }
}
fn pair<R: PageRuntime>(engine: R) -> (EngineThreadRuntime, EngineThreadOwner<R>, Receiver<()>) {
    let (wake, events) = mpsc::channel();
    let (port, owner) = engine_thread_pair(
        engine,
        Arc::new(move || {
            wake.send(()).unwrap();
        }),
    );
    (port, owner, events)
}
fn pump<R: PageRuntime>(
    owner: &mut EngineThreadOwner<R>,
    events: &Receiver<()>,
) -> EnginePumpResult {
    events.recv_timeout(TEST_BUDGET).expect("engine wake");
    owner.pump_one()
}

#[test]
fn engine_runtime_endpoint_is_send_but_backend_can_be_rc_owned() {
    fn is_send<T: Send>() {}
    is_send::<EngineThreadRuntime>();
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, mut engine, events) = pair(NonSendEngine(calls.clone()));
    let owner_thread = thread::current().id();
    let worker = thread::spawn(move || {
        let result = port.dispatch(None, BrowserActorMessage::Health, &control("health"));
        (port, result)
    });
    assert_eq!(pump(&mut engine, &events), EnginePumpResult::Replied);
    let (_port, result) = worker.join().unwrap();
    assert!(result.is_ok());
    assert_eq!(calls.borrow().ordinary, 1);
    assert_eq!(calls.borrow().threads, vec![owner_thread]);
}

#[test]
fn pump_is_nonblocking_and_does_not_create_hidden_work() {
    let (_port, mut engine, events) = pair(DeterministicLocalRuntime::default());
    assert_eq!(engine.pump_one(), EnginePumpResult::Idle);
    assert!(events.try_recv().is_err());
}

#[test]
fn owner_thread_self_dispatch_is_rejected_without_poison_or_enqueue() {
    let (mut port, mut engine, events) = pair(DeterministicLocalRuntime::default());
    assert!(matches!(
        port.dispatch(None, BrowserActorMessage::Health, &control("same")),
        Err(RuntimeFailure::PolicyDenied(_))
    ));
    assert!(!port.closed.load(Ordering::SeqCst));
    assert_eq!(engine.pump_one(), EnginePumpResult::Idle);
    assert!(events.try_recv().is_err());
}

#[test]
fn generic_act_never_reaches_engine_or_atomic_hook() {
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, mut engine, events) = pair(NonSendEngine(calls.clone()));
    let worker = thread::spawn(move || {
        let result = port.dispatch(
            Some(&owner()),
            BrowserActorMessage::Act {
                target: target(),
                action: PageAction::Click,
            },
            &control("bad-act"),
        );
        (port, result)
    });
    let (_port, result) = worker.join().unwrap();
    assert!(matches!(result, Err(RuntimeFailure::Unsupported(_))));
    assert_eq!(engine.pump_one(), EnginePumpResult::Idle);
    assert!(events.try_recv().is_err());
    assert_eq!(calls.borrow().ordinary + calls.borrow().atomic, 0);
}

#[test]
fn page_act_uses_only_atomic_hook_and_preserves_full_owner_snapshot() {
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, mut engine, events) = pair(NonSendEngine(calls.clone()));
    let original = owner();
    let forwarded = original.clone();
    let worker = thread::spawn(move || {
        let result = port.dispatch_page_act(
            Some(&forwarded),
            target(),
            PageAction::Click,
            &control("act"),
        );
        (port, result)
    });
    assert_eq!(pump(&mut engine, &events), EnginePumpResult::Replied);
    let (_port, result) = worker.join().unwrap();
    assert!(result.is_ok());
    assert_eq!(calls.borrow().ordinary, 0);
    assert_eq!(calls.borrow().atomic, 1);
    assert_eq!(calls.borrow().owners, vec![Some(original)]);
}

#[test]
fn absent_semantic_backend_remains_unsupported() {
    let (mut port, mut engine, events) = pair(DeterministicLocalRuntime::default());
    let worker = thread::spawn(move || {
        let result = port.dispatch_page_act(
            Some(&owner()),
            target(),
            PageAction::Click,
            &control("unsupported"),
        );
        (port, result)
    });
    pump(&mut engine, &events);
    let (port, result) = worker.join().unwrap();
    assert!(matches!(result, Err(RuntimeFailure::Unsupported(_))));
    assert!(!port.closed.load(Ordering::SeqCst));
}

#[test]
fn queued_cancel_revokes_work_before_later_pump() {
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, mut engine, events) = pair(NonSendEngine(calls.clone()));
    let ctl = control("cancel-queued");
    let token = ctl.cancellation_token();
    let worker = thread::spawn(move || {
        let result = port.dispatch(None, BrowserActorMessage::Health, &ctl);
        (port, result)
    });
    events.recv_timeout(TEST_BUDGET).unwrap();
    token.cancel();
    let (port, result) = worker.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::Cancelled));
    assert!(port.closed.load(Ordering::SeqCst));
    assert_eq!(engine.pump_one(), EnginePumpResult::Closed);
    assert_eq!(calls.borrow().ordinary, 0);
}

#[test]
fn queued_timeout_revokes_work_and_pair_is_not_reusable() {
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, mut engine, events) = pair(NonSendEngine(calls.clone()));
    let worker = thread::spawn(move || {
        let mut ctl = control("expire");
        ctl.deadline = Instant::now() + Duration::from_millis(100);
        let result = port.dispatch(None, BrowserActorMessage::Health, &ctl);
        let next = port.dispatch(None, BrowserActorMessage::Health, &control("not-replayed"));
        (port, result, next)
    });
    events.recv_timeout(TEST_BUDGET).unwrap();
    let (_port, result, next) = worker.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::DeadlineExceeded));
    assert_eq!(next, Err(RuntimeFailure::BrowserCrashed));
    assert_eq!(engine.pump_one(), EnginePumpResult::Closed);
    assert_eq!(calls.borrow().ordinary, 0);
}

#[test]
fn already_cancelled_request_is_harmless_preflight_failure() {
    let (mut port, mut engine, events) = pair(DeterministicLocalRuntime::default());
    let worker = thread::spawn(move || {
        let ctl = control("preflight");
        ctl.cancel();
        let result = port.dispatch(None, BrowserActorMessage::Health, &ctl);
        (port, result)
    });
    let (port, result) = worker.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::Cancelled));
    assert!(!port.closed.load(Ordering::SeqCst));
    assert_eq!(engine.pump_one(), EnginePumpResult::Idle);
    assert!(events.try_recv().is_err());
}

#[test]
fn owner_loss_terminates_queued_wait_without_executing_backend() {
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, engine, events) = pair(NonSendEngine(calls.clone()));
    let worker = thread::spawn(move || {
        let result = port.dispatch(None, BrowserActorMessage::Health, &control("owner-loss"));
        (port, result)
    });
    events.recv_timeout(TEST_BUDGET).unwrap();
    drop(engine);
    let (port, result) = worker.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::BrowserCrashed));
    assert!(port.closed.load(Ordering::SeqCst));
    assert_eq!(calls.borrow().ordinary, 0);
}

#[test]
fn dropping_client_closes_idle_owner() {
    let (port, mut engine, _) = pair(DeterministicLocalRuntime::default());
    drop(port);
    assert_eq!(engine.pump_one(), EnginePumpResult::Closed);
}

struct Stubborn {
    release: Receiver<()>,
    seen: Rc<RefCell<usize>>,
}
impl PageRuntime for Stubborn {
    fn dispatch(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        _: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        *self.seen.borrow_mut() += 1;
        self.release.recv_timeout(TEST_BUDGET).unwrap();
        Ok(reply())
    }
}
#[test]
fn late_running_reply_is_discarded_without_second_execution() {
    let (release, wait) = mpsc::channel();
    let seen = Rc::new(RefCell::new(0));
    let (mut port, mut engine, events) = pair(Stubborn {
        release: wait,
        seen: seen.clone(),
    });
    let worker = thread::spawn(move || {
        let mut ctl = control("late");
        ctl.deadline = Instant::now() + Duration::from_millis(200);
        let result = port.dispatch(None, BrowserActorMessage::Health, &ctl);
        release.send(()).unwrap();
        let next = port.dispatch(None, BrowserActorMessage::Health, &control("after-late"));
        (port, result, next)
    });
    assert_eq!(pump(&mut engine, &events), EnginePumpResult::Discarded);
    let (_port, result, next) = worker.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::DeadlineExceeded));
    assert_eq!(next, Err(RuntimeFailure::BrowserCrashed));
    assert_eq!(*seen.borrow(), 1);
    assert_eq!(engine.pump_one(), EnginePumpResult::Closed);
}

struct PanicEngine;
impl PageRuntime for PanicEngine {
    fn dispatch(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        _: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        panic!("deliberate engine test panic")
    }
}
#[test]
fn backend_panic_permanently_poisoned_not_retried() {
    let (mut port, mut engine, events) = pair(PanicEngine);
    let worker = thread::spawn(move || {
        let result = port.dispatch(None, BrowserActorMessage::Health, &control("panic"));
        let next = port.dispatch(None, BrowserActorMessage::Health, &control("next"));
        (port, result, next)
    });
    pump(&mut engine, &events);
    let (_port, result, next) = worker.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::BrowserCrashed));
    assert_eq!(next, Err(RuntimeFailure::BrowserCrashed));
    assert_eq!(engine.pump_one(), EnginePumpResult::Closed);
}

#[test]
fn waker_panic_cancels_enqueued_work() {
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, mut engine) = engine_thread_pair(
        NonSendEngine(calls.clone()),
        Arc::new(|| panic!("deliberate wake test panic")),
    );
    let worker = thread::spawn(move || {
        let result = port.dispatch(None, BrowserActorMessage::Health, &control("wake-panic"));
        (port, result)
    });
    let (_port, result) = worker.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::BrowserCrashed));
    assert_eq!(engine.pump_one(), EnginePumpResult::Closed);
    assert_eq!(calls.borrow().ordinary, 0);
}

#[test]
fn policy_failure_does_not_poison_safe_followup() {
    struct DenyOnce(bool);
    impl PageRuntime for DenyOnce {
        fn dispatch(
            &mut self,
            _: Option<&PageOwnerSnapshot>,
            _: BrowserActorMessage,
            _: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            if !self.0 {
                self.0 = true;
                Err(RuntimeFailure::PolicyDenied("fixture denial"))
            } else {
                Ok(reply())
            }
        }
    }
    let (mut port, mut engine, events) = pair(DenyOnce(false));
    let worker = thread::spawn(move || {
        let first = port.dispatch(None, BrowserActorMessage::Health, &control("deny"));
        let second = port.dispatch(None, BrowserActorMessage::Health, &control("allow"));
        (port, first, second)
    });
    pump(&mut engine, &events);
    pump(&mut engine, &events);
    let (_port, first, second) = worker.join().unwrap();
    assert!(matches!(first, Err(RuntimeFailure::PolicyDenied(_))));
    assert!(second.is_ok());
}

#[test]
fn invalid_inputs_never_wake_or_reach_engine() {
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, mut engine, events) = pair(NonSendEngine(calls.clone()));
    let worker = thread::spawn(move || {
        let mut nonlocal = owner();
        nonlocal.local_fixture_only = false;
        let mut oversized = owner();
        oversized.webview_token = "x".repeat(129);
        let cases = [
            (Some(nonlocal), BrowserActorMessage::Snapshot),
            (Some(oversized), BrowserActorMessage::Snapshot),
            (None, BrowserActorMessage::Snapshot),
            (
                Some(owner()),
                BrowserActorMessage::Navigate {
                    url: "https://example.com/".to_owned(),
                    expected_document_generation: 1,
                },
            ),
            (
                Some(owner()),
                BrowserActorMessage::Observe {
                    fields: vec![ObservationField::Role; 6],
                },
            ),
            (
                Some(owner()),
                BrowserActorMessage::Extract {
                    schema_id: "s".repeat(129),
                },
            ),
            (
                Some(owner()),
                BrowserActorMessage::Wait {
                    condition: WaitCondition::DocumentReady,
                    timeout: Duration::from_nanos(1),
                },
            ),
            (
                None,
                BrowserActorMessage::CreateSession {
                    session_id: "create".to_owned(),
                    profile: ProfileSpec {
                        profile_id: "profile".to_owned(),
                        persistence: ProfilePersistence::Persistent,
                    },
                },
            ),
            (
                None,
                BrowserActorMessage::CreateSession {
                    session_id: "x".repeat(129),
                    profile: ProfileSpec {
                        profile_id: "profile".to_owned(),
                        persistence: ProfilePersistence::Ephemeral,
                    },
                },
            ),
        ];
        for (owner, message) in cases {
            assert!(matches!(
                port.dispatch(owner.as_ref(), message, &control("invalid")),
                Err(RuntimeFailure::PolicyDenied(_))
            ));
        }
        port
    });
    let port = worker.join().unwrap();
    assert!(!port.closed.load(Ordering::SeqCst));
    assert_eq!(engine.pump_one(), EnginePumpResult::Idle);
    assert!(events.try_recv().is_err());
    assert_eq!(calls.borrow().ordinary, 0);
}

#[test]
fn invalid_reply_closes_pair_instead_of_publishing_success() {
    struct Oversized;
    impl PageRuntime for Oversized {
        fn dispatch(
            &mut self,
            _: Option<&PageOwnerSnapshot>,
            _: BrowserActorMessage,
            _: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            let mut r = reply();
            r.result.insert(
                "too-big".to_owned(),
                JsonValue::String("x".repeat(hepta_browser_codec::MAX_JSON_STRING_BYTES + 1)),
            );
            Ok(r)
        }
    }
    let (mut port, mut engine, events) = pair(Oversized);
    let worker = thread::spawn(move || {
        let result = port.dispatch(
            None,
            BrowserActorMessage::Health,
            &control("oversized-reply"),
        );
        (port, result)
    });
    pump(&mut engine, &events);
    let (port, result) = worker.join().unwrap();
    assert!(matches!(result, Err(RuntimeFailure::Internal(_))));
    assert!(port.closed.load(Ordering::SeqCst));
}

#[test]
fn external_url_reply_is_not_accepted_as_local_owner() {
    struct Redirect;
    impl PageRuntime for Redirect {
        fn dispatch(
            &mut self,
            _: Option<&PageOwnerSnapshot>,
            _: BrowserActorMessage,
            _: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            Ok(RuntimeReply {
                result: JsonObject::new(),
                current_url: Some("https://example.com/".to_owned()),
            })
        }
    }
    let (mut port, mut engine, events) = pair(Redirect);
    let worker = thread::spawn(move || {
        let result = port.dispatch(None, BrowserActorMessage::Health, &control("redirect"));
        (port, result)
    });
    pump(&mut engine, &events);
    let (port, result) = worker.join().unwrap();
    assert!(matches!(result, Err(RuntimeFailure::Internal(_))));
    assert!(port.closed.load(Ordering::SeqCst));
}

#[test]
fn request_scoped_replies_do_not_cross_reused_request_identifiers() {
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, mut engine, events) = pair(NonSendEngine(calls.clone()));
    let worker = thread::spawn(move || {
        for _ in 0..3 {
            let result = port.dispatch(None, BrowserActorMessage::Health, &control("same-id"))?;
            assert_eq!(
                result.result.get("id"),
                Some(&JsonValue::String("same-id".to_owned()))
            );
        }
        Ok::<_, RuntimeFailure>(port)
    });
    for _ in 0..3 {
        pump(&mut engine, &events);
    }
    let _port = worker.join().unwrap().unwrap();
    assert_eq!(calls.borrow().ordinary, 3);
}

#[test]
fn internal_engine_diagnostics_do_not_escape_into_actor_results() {
    struct SecretError;
    impl PageRuntime for SecretError {
        fn dispatch(
            &mut self,
            _: Option<&PageOwnerSnapshot>,
            _: BrowserActorMessage,
            _: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            Err(RuntimeFailure::Internal(
                "private-page-content".repeat(100_000),
            ))
        }
    }
    let (mut port, mut engine, events) = pair(SecretError);
    let worker = thread::spawn(move || {
        let result = port.dispatch(None, BrowserActorMessage::Health, &control("private"));
        (port, result)
    });
    pump(&mut engine, &events);
    let (port, result) = worker.join().unwrap();
    assert_eq!(
        result,
        Err(RuntimeFailure::Internal(
            "engine dispatch failed; runtime retired".to_owned()
        ))
    );
    assert!(port.closed.load(Ordering::SeqCst));
}

#[test]
fn invalid_control_identity_is_rejected_before_wake() {
    let (mut port, mut engine, events) = pair(DeterministicLocalRuntime::default());
    let worker = thread::spawn(move || {
        for id in ["x".repeat(129), "bad\nrequest".to_owned(), String::new()] {
            assert!(matches!(
                port.dispatch(None, BrowserActorMessage::Health, &control(&id)),
                Err(RuntimeFailure::PolicyDenied(_))
            ));
        }
        port
    });
    let _port = worker.join().unwrap();
    assert_eq!(engine.pump_one(), EnginePumpResult::Idle);
    assert!(events.try_recv().is_err());
}

#[test]
fn unexpected_full_queue_never_waits_or_retries() {
    let calls = Rc::new(RefCell::new(Calls::default()));
    let (mut port, mut engine, events) = pair(NonSendEngine(calls.clone()));
    let (reply, _receiver) = mpsc::sync_channel(1);
    let original = control("orphan");
    port.sender
        .try_send(PendingCall {
            request: request(None, BrowserOperation::Health, &original),
            create_session_id: None,
            owner: None,
            control: original,
            reply,
        })
        .ok()
        .unwrap();
    let worker = thread::spawn(move || {
        let result = port.dispatch(None, BrowserActorMessage::Health, &control("overflow"));
        (port, result)
    });
    let (port, result) = worker.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::BrowserCrashed));
    assert!(port.closed.load(Ordering::SeqCst));
    // Closing a full queue now emits a retirement wake, not a dispatch.
    events.recv_timeout(TEST_BUDGET).unwrap();
    assert_eq!(engine.pump_one(), EnginePumpResult::Closed);
    assert_eq!(calls.borrow().ordinary, 0);
}

#[test]
fn endpoint_retirement_wakes_a_dormant_owner() {
    let (port, _engine, events) = pair(DeterministicLocalRuntime::default());
    drop(port);
    events
        .recv_timeout(Duration::from_millis(100))
        .expect("retirement must wake an event-driven owner");
}

#[test]
fn abandoned_wait_wakes_owner_after_the_enqueue_wake_was_consumed() {
    let (mut port, _engine, events) = pair(DeterministicLocalRuntime::default());
    let ctl = control("retire-wake");
    let cancellation = ctl.cancellation_token();
    let worker = thread::spawn(move || {
        let result = port.dispatch(None, BrowserActorMessage::Health, &ctl);
        (port, result)
    });
    events.recv_timeout(TEST_BUDGET).unwrap();
    cancellation.cancel();
    let (_port, result) = worker.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::Cancelled));
    events
        .recv_timeout(Duration::from_millis(100))
        .expect("abandoning an in-flight wait must wake the owner");
}
