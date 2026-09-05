use super::*;
use crate::{CancellationToken, PageRuntime};
use hepta_browser_codec::{JsonObject, JsonValue};
use std::cell::RefCell;
use std::time::Duration;

const BUDGET: Duration = Duration::from_secs(5);

fn control(id: &str) -> RequestControl {
    RequestControl {
        request_id: id.to_owned(),
        deadline: Instant::now() + BUDGET,
        cancelled: false,
        cancellation: CancellationToken::new(),
        authority: None,
    }
}
fn reply(id: &str) -> RuntimeReply {
    RuntimeReply {
        result: JsonObject::from([("id".to_owned(), JsonValue::String(id.to_owned()))]),
        current_url: None,
    }
}
fn owner() -> PageOwnerSnapshot {
    super::super::tests::owner()
}
fn target() -> ElementReference {
    super::super::tests::target()
}

#[derive(Default)]
struct NativeState {
    started: Vec<String>,
    ordinary: usize,
    atomic: usize,
    cleanups: usize,
    threads: Vec<ThreadId>,
    owners: Vec<Option<PageOwnerSnapshot>>,
    callbacks: Vec<EngineCompletion>,
    drop_thread: Option<ThreadId>,
}
struct DelayedBackend(Rc<RefCell<NativeState>>);
impl CallbackPageRuntime for DelayedBackend {
    fn start(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        done: EngineCompletion,
    ) {
        assert!(!matches!(message, BrowserActorMessage::Act { .. }));
        done.ensure_current_peer().unwrap();
        let mut state = self.0.borrow_mut();
        state.ordinary += 1;
        state.started.push(done.request_id().to_owned());
        state.threads.push(thread::current().id());
        state.owners.push(owner.cloned());
        state.callbacks.push(done);
    }
    fn start_page_act(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        got: ElementReference,
        action: PageAction,
        done: EngineCompletion,
    ) {
        assert_eq!(got, target());
        assert_eq!(action, PageAction::Click);
        done.ensure_current_peer().unwrap();
        let mut state = self.0.borrow_mut();
        state.atomic += 1;
        state.started.push(done.request_id().to_owned());
        state.threads.push(thread::current().id());
        state.owners.push(owner.cloned());
        state.callbacks.push(done);
    }
    fn retire(&mut self) {
        let mut state = self.0.borrow_mut();
        state.cleanups += 1;
        state.threads.push(thread::current().id());
        state.callbacks.clear();
    }
}
impl Drop for DelayedBackend {
    fn drop(&mut self) {
        self.0.borrow_mut().drop_thread = Some(thread::current().id());
    }
}
fn pair<R: CallbackPageRuntime>(
    runtime: R,
) -> (EngineThreadRuntime, CallbackEngineOwner<R>, Receiver<()>) {
    let (wake, events) = mpsc::channel();
    let (port, owner) = callback_engine_pair(
        runtime,
        Arc::new(move || {
            let _ = wake.send(());
        }),
    );
    (port, owner, events)
}
fn wait(events: &Receiver<()>) {
    events.recv_timeout(BUDGET).expect("native loop wake");
}
fn worker(
    mut port: EngineThreadRuntime,
    ctl: RequestControl,
) -> thread::JoinHandle<(EngineThreadRuntime, Result<RuntimeReply, RuntimeFailure>)> {
    thread::spawn(move || {
        let answer = port.dispatch(None, BrowserActorMessage::Health, &ctl);
        (port, answer)
    })
}

#[test]
fn owner_yields_until_native_callback_and_never_restarts_the_operation() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    assert_eq!(engine.pump_one(), CallbackPumpResult::Idle);
    assert!(engine.next_wake_deadline().is_none());
    let ctl = control("deferred");
    let original_deadline = ctl.deadline;
    let work = worker(port, ctl);
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
    // These iterations represent unrelated native event processing. No callback
    // result exists yet, but the main thread remains able to process them.
    let mut native_events = 0;
    for _ in 0..32 {
        native_events += 1;
        assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
        assert_eq!(state.borrow().started.len(), 1);
    }
    assert_eq!(native_events, 32);
    assert!(engine.next_wake_deadline().unwrap() <= original_deadline);
    let done = state.borrow_mut().callbacks.pop().unwrap();
    assert_eq!(done.deadline(), original_deadline);
    assert_eq!(
        done.complete(Ok(reply("deferred"))),
        CompletionDelivery::Queued
    );
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Replied);
    assert!(engine.next_wake_deadline().is_none());
    let (_port, result) = work.join().unwrap();
    assert_eq!(result, Ok(reply("deferred")));
    assert_eq!(state.borrow().threads, vec![thread::current().id()]);
}

struct InlineBackend;
impl CallbackPageRuntime for InlineBackend {
    fn start(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        done: EngineCompletion,
    ) {
        let id = done.request_id().to_owned();
        assert_eq!(done.complete(Ok(reply(&id))), CompletionDelivery::Queued);
    }
    fn retire(&mut self) {}
}

#[test]
fn synchronous_callback_is_safe_after_active_state_was_installed() {
    let (port, mut engine, events) = pair(InlineBackend);
    let work = worker(port, control("inline"));
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Replied);
    assert_eq!(work.join().unwrap().1, Ok(reply("inline")));
}

#[test]
fn callback_can_complete_cross_thread_without_moving_native_backend() {
    fn is_send<T: Send>() {}
    is_send::<EngineCompletion>();
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let work = worker(port, control("cross-thread"));
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
    let done = state.borrow_mut().callbacks.pop().unwrap();
    let other = thread::spawn(move || done.complete(Ok(reply("cross-thread"))));
    assert_eq!(other.join().unwrap(), CompletionDelivery::Queued);
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Replied);
    assert_eq!(work.join().unwrap().1, Ok(reply("cross-thread")));
    assert_eq!(state.borrow().threads, vec![thread::current().id()]);
}

#[test]
fn cancellation_while_callback_pending_retires_once_and_rejects_late_token() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let ctl = control("cancel");
    let cancel = ctl.cancellation_token();
    let work = worker(port, ctl);
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
    let late = state.borrow_mut().callbacks.pop().unwrap();
    cancel.cancel();
    let (mut port, result) = work.join().unwrap();
    assert_eq!(result, Err(RuntimeFailure::Cancelled));
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert!(late.ensure_active().is_err());
    assert!(late.ensure_current_peer().is_err());
    assert_eq!(
        late.complete(Ok(reply("late"))),
        CompletionDelivery::Retired
    );
    engine.retire();
    drop(engine);
    assert_eq!(state.borrow().cleanups, 1);
    assert_eq!(state.borrow().drop_thread, Some(thread::current().id()));
    let next =
        thread::spawn(move || port.dispatch(None, BrowserActorMessage::Health, &control("next")));
    assert_eq!(next.join().unwrap(), Err(RuntimeFailure::BrowserCrashed));
}

#[test]
fn queued_cancel_never_calls_backend_start() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let ctl = control("queued-cancel");
    let cancel = ctl.cancellation_token();
    let work = worker(port, ctl);
    wait(&events);
    cancel.cancel();
    assert_eq!(work.join().unwrap().1, Err(RuntimeFailure::Cancelled));
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert_eq!(state.borrow().ordinary, 0);
}

#[test]
fn callback_timer_keeps_original_deadline_and_refuses_late_success() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let mut ctl = control("expire");
    ctl.deadline = Instant::now() + Duration::from_millis(150);
    let deadline = ctl.deadline;
    let work = worker(port, ctl);
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
    let late = state.borrow_mut().callbacks.pop().unwrap();
    assert_eq!(late.deadline(), deadline);
    let wake = engine.next_wake_deadline().unwrap();
    assert!(wake <= deadline && wake <= Instant::now() + ENGINE_CANCEL_POLL);
    assert_eq!(
        work.join().unwrap().1,
        Err(RuntimeFailure::DeadlineExceeded)
    );
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert_eq!(
        late.complete(Ok(reply("expired"))),
        CompletionDelivery::Retired
    );
}

#[test]
fn dropping_uncompleted_callback_is_failure_not_empty_success() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let work = worker(port, control("lost"));
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
    drop(state.borrow_mut().callbacks.pop().unwrap());
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert_eq!(work.join().unwrap().1, Err(RuntimeFailure::BrowserCrashed));
    assert_eq!(state.borrow().cleanups, 1);
}

#[test]
fn owner_drop_revokes_callback_and_wakes_waiter_on_original_thread() {
    let main_thread = thread::current().id();
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let work = worker(port, control("owner-drop"));
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
    let late = state.borrow_mut().callbacks.pop().unwrap();
    drop(engine);
    assert!(work.join().unwrap().1.is_err());
    assert_eq!(
        late.complete(Ok(reply("late"))),
        CompletionDelivery::Retired
    );
    assert_eq!(state.borrow().threads, vec![main_thread, main_thread]);
    assert_eq!(state.borrow().drop_thread, Some(main_thread));
}

#[test]
fn generic_act_is_never_routed_to_callback_backend() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (mut port, mut engine, _events) = pair(DelayedBackend(state.clone()));
    let work = thread::spawn(move || {
        let got = port.dispatch(
            Some(&owner()),
            BrowserActorMessage::Act {
                target: target(),
                action: PageAction::Click,
            },
            &control("ordinary-act"),
        );
        (port, got)
    });
    let (_port, result) = work.join().unwrap();
    assert!(matches!(result, Err(RuntimeFailure::Unsupported(_))));
    assert_eq!(engine.pump_one(), CallbackPumpResult::Idle);
    assert_eq!(state.borrow().atomic + state.borrow().ordinary, 0);
}

#[test]
fn semantic_act_uses_distinct_callback_hook_and_keeps_expected_owner() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (mut port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let expected = owner();
    let supplied = expected.clone();
    let work = thread::spawn(move || {
        let result = port.dispatch_page_act(
            Some(&supplied),
            target(),
            PageAction::Click,
            &control("atomic"),
        );
        (port, result)
    });
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
    let done = state.borrow_mut().callbacks.pop().unwrap();
    assert_eq!(
        done.complete(Ok(reply("atomic"))),
        CompletionDelivery::Queued
    );
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Replied);
    assert_eq!(work.join().unwrap().1, Ok(reply("atomic")));
    let s = state.borrow();
    assert_eq!((s.ordinary, s.atomic), (0, 1));
    assert_eq!(s.owners, vec![Some(expected)]);
}

#[test]
fn default_atomic_hook_rejects_without_generic_fallback_and_pair_remains_usable() {
    let (mut port, mut engine, events) = pair(InlineBackend);
    let work = thread::spawn(move || {
        let result = port.dispatch_page_act(
            Some(&owner()),
            target(),
            PageAction::Click,
            &control("not-implemented"),
        );
        (port, result)
    });
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Replied);
    let (port, result) = work.join().unwrap();
    assert!(matches!(result, Err(RuntimeFailure::Unsupported(_))));
    // Drain completion wake before issuing the next request.
    while events.try_recv().is_ok() {}
    let work = worker(port, control("after-refusal"));
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Replied);
    assert_eq!(work.join().unwrap().1, Ok(reply("after-refusal")));
}

#[test]
fn successive_callbacks_do_not_share_return_address_even_for_same_request_id() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (mut port, mut engine, events) = pair(DelayedBackend(state.clone()));
    for n in 0..2 {
        let work = worker(port, control("same-id-not-an-authority"));
        wait(&events);
        assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
        let done = state.borrow_mut().callbacks.pop().unwrap();
        let expected = reply(&format!("{n}"));
        assert_eq!(
            done.complete(Ok(expected.clone())),
            CompletionDelivery::Queued
        );
        wait(&events);
        assert_eq!(engine.pump_one(), CallbackPumpResult::Replied);
        let (returned, result) = work.join().unwrap();
        assert_eq!(result, Ok(expected));
        port = returned;
    }
    assert_eq!(state.borrow().started.len(), 2);
}

#[test]
fn reply_bounds_and_internal_diagnostics_apply_before_actor_delivery() {
    for bad in [
        RuntimeReply {
            result: JsonObject::new(),
            current_url: Some("https://outside.invalid/".to_owned()),
        },
        RuntimeReply {
            result: JsonObject::from([(
                "large".to_owned(),
                JsonValue::String("x".repeat(2 * 1024 * 1024)),
            )]),
            current_url: None,
        },
    ] {
        let state = Rc::new(RefCell::new(NativeState::default()));
        let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
        let work = worker(port, control("invalid-reply"));
        wait(&events);
        assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
        let done = state.borrow_mut().callbacks.pop().unwrap();
        assert_eq!(done.complete(Ok(bad)), CompletionDelivery::Queued);
        wait(&events);
        assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
        assert_eq!(
            work.join().unwrap().1,
            Err(RuntimeFailure::Internal(
                "callback engine failed; runtime retired".to_owned()
            ))
        );
    }
}

#[test]
fn backend_internal_text_is_not_copied_into_response() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let work = worker(port, control("redaction"));
    wait(&events);
    engine.pump_one();
    let done = state.borrow_mut().callbacks.pop().unwrap();
    assert_eq!(
        done.complete(Err(RuntimeFailure::Internal(
            "sensitive-page-text".to_owned()
        ))),
        CompletionDelivery::Queued
    );
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert_eq!(
        work.join().unwrap().1,
        Err(RuntimeFailure::Internal(
            "callback engine failed; runtime retired".to_owned()
        ))
    );
}

struct PanickingBackend(Rc<RefCell<usize>>);
impl CallbackPageRuntime for PanickingBackend {
    fn start(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        _done: EngineCompletion,
    ) {
        panic!("fixture start panic");
    }
    fn retire(&mut self) {
        *self.0.borrow_mut() += 1;
        panic!("fixture retire panic");
    }
}
#[test]
fn backend_start_and_retire_panics_leave_pair_permanently_retired() {
    let cleanups = Rc::new(RefCell::new(0));
    let (port, mut engine, events) = pair(PanickingBackend(cleanups.clone()));
    let work = worker(port, control("panic"));
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert_eq!(work.join().unwrap().1, Err(RuntimeFailure::BrowserCrashed));
    engine.retire();
    drop(engine);
    assert_eq!(*cleanups.borrow(), 1);
}

#[test]
fn completion_waker_failure_closes_pair_without_unwinding_callback_or_drop() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let panics = Arc::new(AtomicBool::new(false));
    let p = panics.clone();
    let (wake, events) = mpsc::channel();
    let (port, mut engine) = callback_engine_pair(
        DelayedBackend(state.clone()),
        Arc::new(move || {
            assert!(!p.load(Ordering::SeqCst), "fixture wake failure");
            let _ = wake.send(());
        }),
    );
    let work = worker(port, control("waker"));
    wait(&events);
    engine.pump_one();
    let done = state.borrow_mut().callbacks.pop().unwrap();
    panics.store(true, Ordering::SeqCst);
    assert_eq!(
        done.complete(Ok(reply("never-delivered"))),
        CompletionDelivery::WakeFailed
    );
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert!(work.join().unwrap().1.is_err());
}

#[test]
fn same_thread_dispatch_cannot_block_its_own_native_event_loop() {
    let (mut port, mut engine, _events) = pair(InlineBackend);
    assert!(matches!(
        port.dispatch(None, BrowserActorMessage::Health, &control("same-thread")),
        Err(RuntimeFailure::PolicyDenied(_))
    ));
    assert_eq!(engine.pump_one(), CallbackPumpResult::Idle);
}

#[test]
fn explicit_retire_on_idle_owner_is_idempotent_and_does_not_create_work() {
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (_port, mut engine, _events) = pair(DelayedBackend(state.clone()));
    engine.retire();
    engine.retire();
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    drop(engine);
    assert_eq!(state.borrow().ordinary, 0);
    assert_eq!(state.borrow().cleanups, 1);
}

#[test]
fn queued_request_identity_drift_prevents_callback_start() {
    let fixture = super::super::authority_tests::Fixture::new();
    let custody = fixture.attested.request_custody().unwrap();
    let mut ctl = control("before-start-identity");
    ctl.authority = Some(custody.verifier());
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let work = worker(port, ctl);
    wait(&events);
    std::fs::write(
        fixture.process.join("cgroup"),
        "0::/system.slice/changed.service\n",
    )
    .unwrap();
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert!(work.join().unwrap().1.is_err());
    assert_eq!(state.borrow().ordinary, 0);
    assert!(custody.verifier().verify_current().is_err());
}

#[test]
fn buffered_callback_success_is_rechecked_against_current_request_identity() {
    let fixture = super::super::authority_tests::Fixture::new();
    let custody = fixture.attested.request_custody().unwrap();
    let mut ctl = control("after-callback-identity");
    ctl.authority = Some(custody.verifier());
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let work = worker(port, ctl);
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Pending);
    let done = state.borrow_mut().callbacks.pop().unwrap();
    assert_eq!(
        done.complete(Ok(reply("must-not-escape"))),
        CompletionDelivery::Queued
    );
    std::fs::write(fixture.process.join("exe"), b"different-binary").unwrap();
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert_eq!(
        work.join().unwrap().1,
        Err(RuntimeFailure::PeerIdentityRevoked)
    );
    assert_eq!(state.borrow().ordinary, 1);
}

#[test]
fn completion_checks_current_identity_before_eventual_atomic_work() {
    let fixture = super::super::authority_tests::Fixture::new();
    let custody = fixture.attested.request_custody().unwrap();
    let mut ctl = control("before-eventual-work");
    ctl.authority = Some(custody.verifier());
    let state = Rc::new(RefCell::new(NativeState::default()));
    let (port, mut engine, events) = pair(DelayedBackend(state.clone()));
    let work = worker(port, ctl);
    wait(&events);
    engine.pump_one();
    let done = state.borrow_mut().callbacks.pop().unwrap();
    std::fs::write(fixture.process.join("cgroup"), "0::/changed.service\n").unwrap();
    assert_eq!(
        done.ensure_current_peer(),
        Err(RuntimeFailure::PeerIdentityRevoked)
    );
    // Identity verification is permanently revoked even if material is restored.
    std::fs::write(
        fixture.process.join("cgroup"),
        "0::/system.slice/fixture.service\n",
    )
    .unwrap();
    assert_eq!(
        done.ensure_current_peer(),
        Err(RuntimeFailure::PeerIdentityRevoked)
    );
    let _ = done.complete(Ok(reply("no-resurrection")));
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    assert!(work.join().unwrap().1.is_err());
}

#[derive(Default)]
struct ImmediateTrace {
    controls: Vec<(String, Instant, bool)>,
    ordinary: usize,
    atomic: usize,
    drops: usize,
    thread_ids: Vec<ThreadId>,
}
struct ImmediateBackend(Rc<RefCell<ImmediateTrace>>);
impl PageRuntime for ImmediateBackend {
    fn dispatch(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        ctl: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        ctl.ensure_current_peer()?;
        let mut t = self.0.borrow_mut();
        t.ordinary += 1;
        t.controls
            .push((ctl.request_id.clone(), ctl.deadline, ctl.is_cancelled()));
        t.thread_ids.push(thread::current().id());
        Ok(reply(&ctl.request_id))
    }
    fn dispatch_page_act(
        &mut self,
        got: Option<&PageOwnerSnapshot>,
        reference: ElementReference,
        action: PageAction,
        ctl: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        assert_eq!(got, Some(&owner()));
        assert_eq!(reference, target());
        assert_eq!(action, PageAction::Click);
        ctl.ensure_current_peer()?;
        let mut t = self.0.borrow_mut();
        t.atomic += 1;
        t.controls
            .push((ctl.request_id.clone(), ctl.deadline, ctl.is_cancelled()));
        Ok(reply(&ctl.request_id))
    }
}
impl Drop for ImmediateBackend {
    fn drop(&mut self) {
        self.0.borrow_mut().drops += 1;
    }
}

#[test]
fn immediate_bridge_uses_original_control_and_creator_thread() {
    let trace = Rc::new(RefCell::new(ImmediateTrace::default()));
    let (port, mut engine, events) = pair(ImmediateCallbacks::new(ImmediateBackend(trace.clone())));
    let ctl = control("inline-control");
    let expected = (ctl.request_id.clone(), ctl.deadline, false);
    let work = worker(port, ctl);
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Replied);
    let (port, result) = work.join().unwrap();
    assert_eq!(result, Ok(reply("inline-control")));
    assert_eq!(trace.borrow().controls, vec![expected]);
    assert_eq!(trace.borrow().thread_ids, vec![thread::current().id()]);
    engine.retire();
    engine.retire();
    drop(engine);
    drop(port);
    assert_eq!(trace.borrow().drops, 1);
}

#[test]
fn immediate_bridge_preserves_distinct_atomic_hook() {
    let trace = Rc::new(RefCell::new(ImmediateTrace::default()));
    let (mut port, mut engine, events) =
        pair(ImmediateCallbacks::new(ImmediateBackend(trace.clone())));
    let work = thread::spawn(move || {
        let result = port.dispatch_page_act(
            Some(&owner()),
            target(),
            PageAction::Click,
            &control("inline-atomic"),
        );
        (port, result)
    });
    wait(&events);
    assert_eq!(engine.pump_one(), CallbackPumpResult::Replied);
    let (port, result) = work.join().unwrap();
    assert_eq!(result, Ok(reply("inline-atomic")));
    assert_eq!((trace.borrow().ordinary, trace.borrow().atomic), (0, 1));
    drop(port);
    drop(engine);
    assert_eq!(trace.borrow().drops, 1);
}

#[test]
fn immediate_bridge_cancelled_queue_never_enters_backend() {
    let trace = Rc::new(RefCell::new(ImmediateTrace::default()));
    let (port, mut engine, events) = pair(ImmediateCallbacks::new(ImmediateBackend(trace.clone())));
    let ctl = control("inline-cancel");
    let cancel = ctl.cancellation_token();
    let work = worker(port, ctl);
    wait(&events);
    cancel.cancel();
    assert_eq!(engine.pump_one(), CallbackPumpResult::Retired);
    let (port, result) = work.join().unwrap();
    assert!(result.is_err());
    assert_eq!(trace.borrow().ordinary, 0);
    drop(port);
    drop(engine);
    assert_eq!(trace.borrow().drops, 1);
}
