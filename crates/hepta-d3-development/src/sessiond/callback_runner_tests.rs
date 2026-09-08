//! Real runner/latch/threads with explicit test callbacks, not a native browser.
use super::super::tests::control;
use super::*;
use hepta_browser_actor::engine_dispatch::event_loop::{CompletionDelivery, EngineCompletion};
use hepta_browser_actor::{BrowserActorMessage, PageOwnerSnapshot, PageRuntime, RuntimeReply};
use hepta_browser_codec::JsonObject;
use std::cell::RefCell;
use std::rc::Rc;
use std::sync::mpsc;
use std::time::Duration;

#[derive(Default)]
struct Events {
    pending: Option<EngineCompletion>,
    starts: usize,
    turns: usize,
    completed: usize,
    retire: usize,
    start_turn: usize,
    thread_ids: Vec<thread::ThreadId>,
}
struct Delayed(Rc<RefCell<Events>>);
impl CallbackPageRuntime for Delayed {
    fn start(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        done: EngineCompletion,
    ) {
        done.ensure_current_peer().unwrap();
        let mut state = self.0.borrow_mut();
        assert!(state.pending.is_none());
        state.starts += 1;
        state.start_turn = state.turns;
        state.pending = Some(done);
        state.thread_ids.push(thread::current().id());
    }
    fn retire(&mut self) {
        let mut state = self.0.borrow_mut();
        state.retire += 1;
        state.pending.take();
        state.thread_ids.push(thread::current().id());
    }
}
fn reply() -> RuntimeReply {
    RuntimeReply {
        result: JsonObject::new(),
        current_url: None,
    }
}

#[test]
fn callback_runner_yields_and_completes_deferred_work_on_owner() {
    let state = Rc::new(RefCell::new(Events::default()));
    let events = state.clone();
    let owner = thread::current().id();
    let worker = run_callback_on_owner(
        Delayed(state.clone()),
        move || {
            let mut e = events.borrow_mut();
            e.turns += 1;
            if e.pending.is_some() && e.turns >= e.start_turn + 2 {
                let done = e.pending.take().unwrap();
                assert_eq!(done.complete(Ok(reply())), CompletionDelivery::Queued);
                e.completed += 1;
            }
            Ok(Some(Instant::now() + Duration::from_millis(1)))
        },
        |mut port, stop| {
            for _ in 0..4 {
                stop.ensure_active()?;
                assert!(
                    port.dispatch(None, BrowserActorMessage::Health, &control())
                        .is_ok()
                );
            }
            Ok(thread::current().id())
        },
    )
    .unwrap();
    let e = state.borrow();
    assert_ne!(owner, worker);
    assert_eq!((e.starts, e.completed, e.retire), (4, 4, 1));
    assert!(e.thread_ids.iter().all(|id| *id == owner));
}

#[test]
fn callback_cancellation_retires_backend_and_idle_accept() {
    let state = Rc::new(RefCell::new(Events::default()));
    let events = state.clone();
    let ctl = control();
    let cancel = ctl.cancellation_token();
    let result = run_callback_on_owner(
        Delayed(state.clone()),
        move || {
            if events.borrow().pending.is_some() {
                cancel.cancel();
            }
            Ok(None)
        },
        move |mut port, stop| {
            assert!(
                port.dispatch(None, BrowserActorMessage::Health, &ctl)
                    .is_err()
            );
            // Retirement can lag actor cancellation; observe it without new work.
            while stop.ensure_active().is_ok() {
                thread::park_timeout(Duration::from_millis(1));
            }
            assert!(
                port.dispatch(None, BrowserActorMessage::Health, &control())
                    .is_err()
            );
            Ok(())
        },
    );
    assert!(result.is_ok());
    assert_eq!((state.borrow().starts, state.borrow().retire), (1, 1));
    assert!(state.borrow().pending.is_none());
}

#[test]
fn pending_callback_uses_original_deadline_without_a_completion() {
    let state = Rc::new(RefCell::new(Events::default()));
    let result = run_callback_on_owner(
        Delayed(state.clone()),
        || Ok(None),
        |mut port, _| {
            let mut ctl = control();
            ctl.deadline = Instant::now() + Duration::from_millis(35);
            assert!(
                port.dispatch(None, BrowserActorMessage::Health, &ctl)
                    .is_err()
            );
            Ok(())
        },
    );
    assert!(result.is_ok());
    assert_eq!(state.borrow().retire, 1);
    assert!(state.borrow().pending.is_none());
}

#[test]
fn event_driver_error_cancels_pending_request_before_join() {
    let state = Rc::new(RefCell::new(Events::default()));
    let events = state.clone();
    let answer = run_callback_on_owner(
        Delayed(state.clone()),
        move || {
            if events.borrow().pending.is_some() {
                return Err(invalid("test-only internal diagnostic").into());
            }
            Ok(None)
        },
        |mut port, stop| {
            assert!(
                port.dispatch(None, BrowserActorMessage::Health, &control())
                    .is_err()
            );
            assert!(stop.ensure_active().is_err());
            Ok(())
        },
    );
    assert_eq!(
        answer.unwrap_err().to_string(),
        "D3 owner event driver failed; service stopped"
    );
    assert_eq!(state.borrow().retire, 1);
}

#[test]
fn event_driver_panic_is_joined_and_retired_once() {
    let state = Rc::new(RefCell::new(Events::default()));
    let events = state.clone();
    let answer = run_callback_on_owner(
        Delayed(state.clone()),
        move || {
            assert!(events.borrow().pending.is_none(), "test driver panic");
            Ok(None)
        },
        |mut port, _| {
            assert!(
                port.dispatch(None, BrowserActorMessage::Health, &control())
                    .is_err()
            );
            Ok(())
        },
    );
    assert_eq!(
        answer.unwrap_err().to_string(),
        "D3 owner event driver panicked; service stopped"
    );
    assert_eq!(state.borrow().retire, 1);
}

#[test]
fn callback_worker_early_error_and_panic_both_retire_without_dispatch() {
    for panic in [false, true] {
        let state = Rc::new(RefCell::new(Events::default()));
        let answer: Result<(), AnyError> = run_callback_on_owner(
            Delayed(state.clone()),
            || Ok(None),
            move |_, _| {
                assert!(!panic, "test worker panic");
                Err(invalid("worker setup failed").into())
            },
        );
        assert_eq!(
            answer.unwrap_err().to_string(),
            if panic {
                "D3 connection worker panicked; service stopped"
            } else {
                "worker setup failed"
            }
        );
        assert_eq!((state.borrow().starts, state.borrow().retire), (0, 1));
    }
}

#[test]
fn wake_latch_is_not_consumed_by_unrelated_thread_parking() {
    let wake = WakeSignal::default();
    wake.begin_cycle().unwrap();
    wake.notify();
    thread::current().unpark();
    thread::park();
    assert!(
        *wake.pending.lock().unwrap(),
        "unrelated code cannot consume private wake state"
    );
    wake.wait_until(None).unwrap();
}

#[test]
fn notifications_during_drain_remain_latched_and_coalesce() {
    let wake = WakeSignal::default();
    wake.notify();
    wake.begin_cycle().unwrap();
    assert!(!*wake.pending.lock().unwrap());
    for _ in 0..1000 {
        wake.notify();
    }
    assert!(*wake.pending.lock().unwrap());
    wake.wait_until(None).unwrap();
    wake.begin_cycle().unwrap();
    assert!(!*wake.pending.lock().unwrap());
}

#[test]
fn sleeping_owner_is_woken_by_new_notification() {
    let wake = Arc::new(WakeSignal::default());
    let other = wake.clone();
    let (ready, rx) = mpsc::sync_channel(1);
    let waiter = thread::spawn(move || {
        other.begin_cycle().unwrap();
        ready.send(()).unwrap();
        other
            .wait_until(Some(Instant::now() + Duration::from_secs(5)))
            .unwrap();
        assert!(*other.pending.lock().unwrap());
    });
    rx.recv_timeout(Duration::from_secs(5)).unwrap();
    wake.notify();
    waiter.join().unwrap();
}

#[test]
fn spurious_condition_notification_does_not_extend_absolute_timer() {
    let wake = Arc::new(WakeSignal::default());
    let other = wake.clone();
    let until = Instant::now() + Duration::from_millis(30);
    let notifier = thread::spawn(move || {
        while Instant::now() < until {
            other.changed.notify_one();
            thread::yield_now();
        }
    });
    wake.wait_until(Some(until)).unwrap();
    assert!(
        Instant::now() >= until,
        "no early return without a pending event"
    );
    assert!(!*wake.pending.lock().unwrap());
    notifier.join().unwrap();
}

#[test]
fn poisoned_notification_state_is_rejected_not_reinitialized() {
    let wake = WakeSignal::default();
    let _ = catch_unwind(AssertUnwindSafe(|| {
        let _held = wake.pending.lock().unwrap();
        panic!("test mutex poison");
    }));
    wake.notify();
    assert!(wake.begin_cycle().is_err());
    assert!(wake.wait_until(Some(Instant::now())).is_err());
}

#[test]
fn worker_completion_publishes_finished_before_wake() {
    let finished = Arc::new(AtomicBool::new(false));
    let wake = Arc::new(WakeSignal::default());
    drop(CompletionWake {
        finished: finished.clone(),
        wake: wake.clone(),
    });
    assert!(finished.load(Ordering::Acquire));
    assert!(*wake.pending.lock().unwrap());
}

#[test]
fn native_and_request_timers_choose_the_earliest_existing_instant() {
    let now = Instant::now();
    let later = now + Duration::from_secs(1);
    assert_eq!(earliest(None, None), None);
    assert_eq!(earliest(Some(now), None), Some(now));
    assert_eq!(earliest(None, Some(later)), Some(later));
    assert_eq!(earliest(Some(now), Some(later)), Some(now));
    assert_eq!(earliest(Some(later), Some(now)), Some(now));
}
