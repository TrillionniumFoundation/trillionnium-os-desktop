//! Nonblocking owner-side initiation with single-use callback completion.
//!
//! This is an opt-in in-process mechanism, not a Servo adapter. No method pumps
//! a native loop, waits on a channel, creates a thread or starts a listener.
//! Integrators must promptly return from `start`, service native events, and
//! pump on callback wakes and `next_wake_deadline`. See EVENT_LOOP_COMPLETION.md.

#[path = "immediate_callbacks.rs"]
mod immediate;
pub use immediate::ImmediateCallbacks;

use super::{
    BrowserActorMessage, BrowserOperation, ENGINE_CANCEL_POLL, ENGINE_PENDING_LIMIT,
    ElementReference, EngineEventLoopWaker, EngineThreadRuntime, PageAction, PageOwnerSnapshot,
    PendingCall, RequestControl, RuntimeFailure, RuntimeReply, bound_reply, is_uncertain_failure,
    notify_engine, ordinary_message,
};
use std::marker::PhantomData;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::rc::Rc;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, SyncSender, TryRecvError};
use std::thread::{self, ThreadId};
use std::time::Instant;

/// Start exactly one operation without waiting for the engine's callback.
///
/// The backend owns its native callback registration and keeps the completion
/// until success, refusal or failure is known. Dropping it without completion
/// is an indeterminate engine failure. PolicyDenied/Unsupported may only be
/// reported for side-effect-free refusals; other failures retire the pair.
/// The snapshot is expected state, not proof of a current DOM or permission.
///
/// A real adapter must recheck `completion.ensure_current_peer()` and its own live node,
/// generation, frame and principal before an eventual action. This interface
/// cannot make two separate resolve/action callbacks atomic.
pub trait CallbackPageRuntime {
    fn start(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        completion: EngineCompletion,
    );

    /// No default coordinate/generic-Act fallback. The eventual engine adapter
    /// must retain and act on the same engine-owned current node atomically.
    fn start_page_act(
        &mut self,
        _owner: Option<&PageOwnerSnapshot>,
        _target: ElementReference,
        _action: PageAction,
        completion: EngineCompletion,
    ) {
        let _ = completion.complete(Err(RuntimeFailure::Unsupported(
            "callback semantic node resolution is unavailable",
        )));
    }

    /// Permanently retire this pair: detach registrations and release retained
    /// callback state promptly. Never retry a page action, navigate, create a
    /// replacement engine, or infer that an external effect was undone here.
    /// Called at most once, on the creator thread, including owner Drop.
    fn retire(&mut self);
}

/// A callback's single-use, unforgeable return address for exactly one request.
/// `Queued` means only queued, never actor admission or durable success.
/// The original control remains revocable; retaining this token cannot extend
/// its deadline or request peer custody. It contains no DOM/engine pointer.
///
/// ```compile_fail
/// use hepta_browser_actor::engine_dispatch::event_loop::EngineCompletion;
/// fn duplicate(done: EngineCompletion) { let _second = done.clone(); }
/// ```
/// ```compile_fail
/// use hepta_browser_actor::{RuntimeReply};
/// use hepta_browser_actor::engine_dispatch::event_loop::EngineCompletion;
/// fn twice(done: EngineCompletion, reply: RuntimeReply) {
///     let _ = done.complete(Ok(reply.clone()));
///     let _ = done.complete(Ok(reply));
/// }
/// ```
pub struct EngineCompletion {
    sender: Option<SyncSender<Result<RuntimeReply, RuntimeFailure>>>,
    valid: Arc<AtomicBool>,
    closed: Arc<AtomicBool>,
    control: RequestControl,
    waker: Arc<dyn EngineEventLoopWaker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[must_use = "Queued is not confirmation of a delivered or journaled outcome"]
pub enum CompletionDelivery {
    Queued,
    Retired,
    ReceiverGone,
    WakeFailed,
}

impl EngineCompletion {
    pub fn request_id(&self) -> &str {
        &self.control.request_id
    }

    pub fn deadline(&self) -> Instant {
        self.control.deadline
    }

    /// Check this callback's lifetime as well as the original request control.
    /// A retired token never revives, even if the request ID is reused elsewhere.
    pub fn ensure_active(&self) -> Result<(), RuntimeFailure> {
        if !self.valid.load(Ordering::SeqCst) || self.closed.load(Ordering::SeqCst) {
            return Err(RuntimeFailure::BrowserCrashed);
        }
        self.control.ensure_active()
    }

    /// An eventual action callback must call this immediately before the actual
    /// engine-owned atomic operation. It is still not atomic with process exit.
    pub fn ensure_current_peer(&self) -> Result<(), RuntimeFailure> {
        self.ensure_active()?;
        self.control.ensure_current_peer()?;
        self.ensure_active()
    }

    /// Consume this token once. Inputs are bounded without recursively cloning
    /// a backend value. Completion may run on another thread, but the owner
    /// alone validates full peer continuity and returns the final reply.
    pub fn complete(mut self, result: Result<RuntimeReply, RuntimeFailure>) -> CompletionDelivery {
        let sender = self.sender.take().expect("completion owns one sender");
        if !self.valid.load(Ordering::SeqCst) || self.closed.load(Ordering::SeqCst) {
            return CompletionDelivery::Retired;
        }
        let result = self
            .control
            .ensure_active()
            .and(result)
            .and_then(bound_reply)
            .and_then(|reply| self.control.ensure_active().map(|()| reply))
            .map_err(redact_failure);
        if sender.try_send(result).is_err() {
            self.closed.store(true, Ordering::SeqCst);
            self.control.cancel();
            notify_engine(self.waker.as_ref());
            return CompletionDelivery::ReceiverGone;
        }
        if !notify_engine(self.waker.as_ref()) {
            self.closed.store(true, Ordering::SeqCst);
            self.control.cancel();
            return CompletionDelivery::WakeFailed;
        }
        CompletionDelivery::Queued
    }
}

impl Drop for EngineCompletion {
    fn drop(&mut self) {
        if let Some(sender) = self.sender.take()
            && self.valid.load(Ordering::SeqCst)
            && !self.closed.load(Ordering::SeqCst)
        {
            // Lost callbacks do not become successful empty replies.
            let _ = sender.try_send(Err(RuntimeFailure::BrowserCrashed));
            if !notify_engine(self.waker.as_ref()) {
                self.closed.store(true, Ordering::SeqCst);
                self.control.cancel();
            }
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CallbackPumpResult {
    Idle,
    Pending,
    Replied,
    Retired,
}

struct ActiveCall {
    call: PendingCall,
    completion: Receiver<Result<RuntimeReply, RuntimeFailure>>,
    valid: Arc<AtomicBool>,
}

/// Construct and pump on the native engine thread. Neither Send nor Sync.
/// At most one active call and one not-yet-consumed queue slot exist; the
/// non-cloneable actor endpoint serializes requests. Native events must run
/// between pumps; repeated pumping must not replace the application's loop.
///
/// ```compile_fail
/// use hepta_browser_actor::engine_dispatch::event_loop::{CallbackEngineOwner, CallbackPageRuntime};
/// fn move_owner<R: CallbackPageRuntime + Send>() {
///     fn needs_send<T: Send>() {}
///     needs_send::<CallbackEngineOwner<R>>();
/// }
/// ```
///
/// ```compile_fail
/// use hepta_browser_actor::engine_dispatch::event_loop::{CallbackEngineOwner, CallbackPageRuntime};
/// fn share_owner<R: CallbackPageRuntime + Sync>() {
///     fn needs_sync<T: Sync>() {}
///     needs_sync::<CallbackEngineOwner<R>>();
/// }
/// ```
pub struct CallbackEngineOwner<R: CallbackPageRuntime> {
    receiver: Receiver<PendingCall>,
    runtime: R,
    active: Option<ActiveCall>,
    closed: Arc<AtomicBool>,
    waker: Arc<dyn EngineEventLoopWaker>,
    owner_thread: ThreadId,
    retired: bool,
    _thread_affinity: PhantomData<Rc<()>>,
}

/// Opt-in alternative to engine_thread_pair for asynchronous native engines.
/// This does not select a daemon profile, instantiate a Servo object, create a
/// thread/window/listener, or change the synchronous development backend.
/// ```
/// use std::sync::Arc;
/// use hepta_browser_actor::{BrowserActorMessage, PageOwnerSnapshot};
/// use hepta_browser_actor::engine_dispatch::event_loop::{
///     callback_engine_pair, CallbackPageRuntime, CallbackPumpResult, EngineCompletion,
/// };
/// struct Native;
/// impl CallbackPageRuntime for Native {
///     fn start(&mut self, _: Option<&PageOwnerSnapshot>, _: BrowserActorMessage, done: EngineCompletion) {
///         // Real adapters retain `done` in an actual native callback.
///         drop(done);
///     }
///     fn retire(&mut self) {}
/// }
/// let (_endpoint, mut owner) = callback_engine_pair(Native, Arc::new(|| {}));
/// assert_eq!(owner.pump_one(), CallbackPumpResult::Idle);
/// owner.retire();
/// ```
pub fn callback_engine_pair<R: CallbackPageRuntime>(
    runtime: R,
    waker: Arc<dyn EngineEventLoopWaker>,
) -> (EngineThreadRuntime, CallbackEngineOwner<R>) {
    let (sender, receiver) = mpsc::sync_channel(ENGINE_PENDING_LIMIT);
    let closed = Arc::new(AtomicBool::new(false));
    let owner_thread = thread::current().id();
    (
        EngineThreadRuntime {
            sender,
            closed: closed.clone(),
            owner_thread,
            waker: waker.clone(),
        },
        CallbackEngineOwner {
            receiver,
            runtime,
            active: None,
            closed,
            waker,
            owner_thread,
            retired: false,
            _thread_affinity: PhantomData,
        },
    )
}

impl<R: CallbackPageRuntime> CallbackEngineOwner<R> {
    /// Schedule a native timer for this instant while a callback is outstanding,
    /// also processing all waker events. This is a cancellation check schedule,
    /// not a latency guarantee or a freshly granted deadline.
    pub fn next_wake_deadline(&self) -> Option<Instant> {
        if self.retired {
            return None;
        }
        if self.closed.load(Ordering::SeqCst) {
            return Some(Instant::now());
        }
        self.active.as_ref().map(|active| {
            active
                .call
                .control
                .deadline
                .min(Instant::now() + ENGINE_CANCEL_POLL)
        })
    }

    /// Initiate at most one operation or consume one completion, without waiting
    /// for a callback. Full process identity is checked at initiation and final
    /// reply; pending polls use only the cheap cancellation/pidfd check. Backend
    /// start, peer I/O, result validation and retire are not forcibly preempted.
    pub fn pump_one(&mut self) -> CallbackPumpResult {
        if self.retired {
            return CallbackPumpResult::Retired;
        }
        if self.closed.load(Ordering::SeqCst) || thread::current().id() != self.owner_thread {
            self.retire();
            return CallbackPumpResult::Retired;
        }
        if self.active.is_some() {
            return self.poll_active();
        }
        let call = match self.receiver.try_recv() {
            Ok(call) => call,
            Err(TryRecvError::Empty) => return CallbackPumpResult::Idle,
            Err(TryRecvError::Disconnected) => {
                self.retire();
                return CallbackPumpResult::Retired;
            }
        };
        if let Err(error) = call.control.ensure_current_peer() {
            let _ = call.reply.try_send(Err(error));
            call.control.cancel();
            self.retire();
            return CallbackPumpResult::Retired;
        }
        let (sender, completion) = mpsc::sync_channel(1);
        let valid = Arc::new(AtomicBool::new(true));
        let ticket = EngineCompletion {
            sender: Some(sender),
            valid: valid.clone(),
            closed: self.closed.clone(),
            control: call.control.clone(),
            waker: self.waker.clone(),
        };
        // Publish active state before callbacks can fire synchronously.
        self.active = Some(ActiveCall {
            call,
            completion,
            valid,
        });
        let active = self.active.as_ref().expect("active call was installed");
        let started = catch_unwind(AssertUnwindSafe(|| match &active.call.request.operation {
            BrowserOperation::PageAct { target, action } => self.runtime.start_page_act(
                active.call.owner.as_ref(),
                target.clone(),
                action.clone(),
                ticket,
            ),
            _ => match ordinary_message(&active.call) {
                Ok(message) => self
                    .runtime
                    .start(active.call.owner.as_ref(), message, ticket),
                Err(error) => {
                    let _ = ticket.complete(Err(error));
                }
            },
        }));
        if started.is_err() {
            self.fail_active(RuntimeFailure::BrowserCrashed);
            return CallbackPumpResult::Retired;
        }
        self.poll_active()
    }

    fn poll_active(&mut self) -> CallbackPumpResult {
        if self.closed.load(Ordering::SeqCst) {
            self.retire();
            return CallbackPumpResult::Retired;
        }
        let active = self.active.as_ref().expect("poll requires one active call");
        if let Err(error) = active.call.control.ensure_active() {
            self.fail_active(error);
            return CallbackPumpResult::Retired;
        }
        let result = match active.completion.try_recv() {
            Ok(result) => result,
            Err(TryRecvError::Empty) => return CallbackPumpResult::Pending,
            Err(TryRecvError::Disconnected) => Err(RuntimeFailure::BrowserCrashed),
        };
        // Recheck after receiving, never release a buffered success on stale
        // request identity. This is a sample, not atomic with exec/exit.
        let result = active
            .call
            .control
            .ensure_current_peer()
            .and(result)
            .and_then(bound_reply)
            .and_then(|reply| active.call.control.ensure_active().map(|()| reply))
            .map_err(redact_failure);
        let uncertain = result.as_ref().is_err_and(is_uncertain_failure);
        let active = self.active.take().expect("active call was present");
        active.valid.store(false, Ordering::SeqCst);
        if active.call.reply.try_send(result).is_err() || uncertain {
            // Do not cancel a successfully delivered error before the actor can
            // classify it. Pair closure and receiver invalidation suffice here.
            self.retire();
            return CallbackPumpResult::Retired;
        }
        CallbackPumpResult::Replied
    }

    fn fail_active(&mut self, error: RuntimeFailure) {
        if let Some(active) = self.active.take() {
            active.valid.store(false, Ordering::SeqCst);
            let _ = active.call.reply.try_send(Err(error));
        }
        self.retire();
    }

    /// Stop callbacks and pending work permanently. Effects are never retried or
    /// automatically compensated. Calling this repeatedly does no new cleanup.
    pub fn retire(&mut self) {
        if self.retired {
            return;
        }
        self.retired = true;
        self.closed.store(true, Ordering::SeqCst);
        if let Some(active) = self.active.take() {
            active.valid.store(false, Ordering::SeqCst);
            active.call.control.cancel();
            let _ = active
                .call
                .reply
                .try_send(Err(RuntimeFailure::BrowserCrashed));
        }
        if let Ok(call) = self.receiver.try_recv() {
            call.control.cancel();
            let _ = call.reply.try_send(Err(RuntimeFailure::BrowserCrashed));
        }
        // Retire must be called on the same owner thread, never from completion
        // or worker Drop. Catch an adapter cleanup panic without resurrecting it.
        let _ = catch_unwind(AssertUnwindSafe(|| self.runtime.retire()));
    }
}

impl<R: CallbackPageRuntime> Drop for CallbackEngineOwner<R> {
    fn drop(&mut self) {
        self.retire();
    }
}

fn redact_failure(error: RuntimeFailure) -> RuntimeFailure {
    match error {
        RuntimeFailure::Internal(_) => {
            RuntimeFailure::Internal("callback engine failed; runtime retired".to_owned())
        }
        error => error,
    }
}

#[cfg(test)]
#[path = "event_loop_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "event_loop_transport_tests.rs"]
mod transport_tests;
