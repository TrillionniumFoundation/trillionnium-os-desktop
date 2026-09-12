//! Bounded, in-process dispatch to a thread-affine engine owner.
//!
//! This schedules `PageRuntime` calls; it does not implement Servo, authorize a
//! principal, or resolve a DOM node. The owner is deliberately not Send/Sync.
//! A real engine must still implement the atomic semantic hook and all live
//! revision checks. See `docs/architecture/ENGINE_THREAD_DISPATCH.md`.

pub mod event_loop;

use crate::{
    BrowserActorMessage, PageOwnerSnapshot, PageRuntime, RequestControl, RuntimeFailure,
    RuntimeReply,
};
use hepta_browser_codec::{
    BrowserOperation, BrowserRequest, ElementReference, JsonValue, NavigationTarget, PageAction,
    ProfilePersistence, encode_request,
};
use std::marker::PhantomData;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::rc::Rc;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, SyncSender, TryRecvError};
use std::thread::{self, ThreadId};
use std::time::Duration;

/// Cancellation polling bounds responsiveness of the waiting actor, not the
/// running engine. An adapter must check its shared control at bounded points.
pub const ENGINE_CANCEL_POLL: Duration = Duration::from_millis(5);
pub const ENGINE_PENDING_LIMIT: usize = 1;

/// Wake the existing engine event loop. Implementations must return promptly,
/// never pump recursively, and never wait for the requesting actor thread.
pub trait EngineEventLoopWaker: Send + Sync {
    fn wake(&self);
}

impl<F: Fn() + Send + Sync> EngineEventLoopWaker for F {
    fn wake(&self) {
        self();
    }
}

/// Actor-side endpoint. Move this endpoint (not the engine) to the actor thread.
/// It is not cloneable, pipelines no requests, and never retries a dispatch.
pub struct EngineThreadRuntime {
    sender: SyncSender<PendingCall>,
    closed: Arc<AtomicBool>,
    owner_thread: ThreadId,
    waker: Arc<dyn EngineEventLoopWaker>,
}

/// Engine-side endpoint. Construct and pump it on the engine event-loop thread.
///
/// ```compile_fail
/// use hepta_browser_actor::engine_dispatch::EngineThreadOwner;
/// use hepta_browser_actor::DeterministicLocalRuntime;
/// fn needs_send<T: Send>() {}
/// needs_send::<EngineThreadOwner<DeterministicLocalRuntime>>();
/// ```
///
/// ```compile_fail
/// use hepta_browser_actor::engine_dispatch::EngineThreadOwner;
/// use hepta_browser_actor::DeterministicLocalRuntime;
/// fn needs_sync<T: Sync>() {}
/// needs_sync::<EngineThreadOwner<DeterministicLocalRuntime>>();
/// ```
pub struct EngineThreadOwner<R> {
    receiver: Receiver<PendingCall>,
    runtime: R,
    closed: Arc<AtomicBool>,
    owner_thread: ThreadId,
    _thread_affinity: PhantomData<Rc<()>>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EnginePumpResult {
    Idle,
    Replied,
    Discarded,
    Closed,
}

struct PendingCall {
    request: BrowserRequest,
    create_session_id: Option<String>,
    owner: Option<PageOwnerSnapshot>,
    control: RequestControl,
    reply: SyncSender<Result<RuntimeReply, RuntimeFailure>>,
}

/// Create an explicitly installed scheduler on the current engine thread.
/// This creates no thread, listener, browser, profile, credentials or executor.
/// Existing synchronous adapters and all product activation defaults are unchanged.
pub fn engine_thread_pair<R: PageRuntime>(
    runtime: R,
    waker: Arc<dyn EngineEventLoopWaker>,
) -> (EngineThreadRuntime, EngineThreadOwner<R>) {
    let (sender, receiver) = mpsc::sync_channel(ENGINE_PENDING_LIMIT);
    let closed = Arc::new(AtomicBool::new(false));
    let owner_thread = thread::current().id();
    (
        EngineThreadRuntime {
            sender,
            closed: closed.clone(),
            owner_thread,
            waker,
        },
        EngineThreadOwner {
            receiver,
            runtime,
            closed,
            owner_thread,
            _thread_affinity: PhantomData,
        },
    )
}

// If a wait exits abnormally (including an unwind), revoke queued/running work
// and permanently close this pair. No next request can receive a late reply.
struct PendingWait<'a> {
    closed: &'a AtomicBool,
    control: &'a RequestControl,
    waker: &'a dyn EngineEventLoopWaker,
    disarmed: bool,
}
impl Drop for PendingWait<'_> {
    fn drop(&mut self) {
        if !self.disarmed {
            self.control.cancel();
            self.closed.store(true, Ordering::SeqCst);
            notify_engine(self.waker);
        }
    }
}

impl EngineThreadRuntime {
    fn preflight(
        &self,
        owner: Option<&PageOwnerSnapshot>,
        control: &RequestControl,
    ) -> Result<(), RuntimeFailure> {
        control.ensure_active()?;
        if self.closed.load(Ordering::SeqCst) {
            return Err(RuntimeFailure::BrowserCrashed);
        }
        if thread::current().id() == self.owner_thread {
            return Err(RuntimeFailure::PolicyDenied(
                "synchronous engine dispatch on its owner thread would deadlock",
            ));
        }
        crate::validate_token("request_id", &control.request_id, 128)
            .map_err(|_| RuntimeFailure::PolicyDenied("invalid engine request identifier"))?;
        validate_owner(owner)
    }

    fn call(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        request: BrowserRequest,
        create_session_id: Option<String>,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        control.ensure_active()?;
        if self.closed.load(Ordering::SeqCst) {
            return Err(RuntimeFailure::BrowserCrashed);
        }
        if thread::current().id() == self.owner_thread {
            return Err(RuntimeFailure::PolicyDenied(
                "synchronous engine dispatch on its owner thread would deadlock",
            ));
        }
        // Validate typed requests using the existing canonical codec, rather
        // than introducing a second protocol or cloning unbounded input.
        encode_request(&request).map_err(|_| {
            RuntimeFailure::PolicyDenied("engine dispatch request violates Browser API bounds")
        })?;
        validate_owner(owner)?;
        if let Some(session) = &create_session_id {
            crate::validate_token("session_id", session, 128).map_err(|_| {
                RuntimeFailure::PolicyDenied("invalid reserved engine session identifier")
            })?;
        }
        control.ensure_active()?;
        let (reply, receiver) = mpsc::sync_channel(1);
        let pending = PendingCall {
            request,
            create_session_id,
            owner: owner.cloned(),
            control: control.clone(),
            reply,
        };
        let mut wait = PendingWait {
            closed: &self.closed,
            control,
            waker: self.waker.as_ref(),
            disarmed: false,
        };
        // Never wait for queue capacity: an unexpected queued item is an
        // invariant failure, not a reason to enqueue a second operation.
        self.sender
            .try_send(pending)
            .map_err(|_| RuntimeFailure::BrowserCrashed)?;
        if catch_unwind(AssertUnwindSafe(|| self.waker.wake())).is_err() {
            return Err(RuntimeFailure::BrowserCrashed);
        }
        loop {
            let remaining = control.remaining()?;
            match receiver.recv_timeout(remaining.min(ENGINE_CANCEL_POLL)) {
                Ok(result) => {
                    control.ensure_active()?;
                    if let Err(error) = &result
                        && is_uncertain_failure(error)
                    {
                        return result;
                    }
                    // An owner drop or a concurrent revocation must not make a
                    // buffered successful reply reusable as an active runtime.
                    if self.closed.load(Ordering::SeqCst) {
                        return Err(RuntimeFailure::BrowserCrashed);
                    }
                    wait.disarmed = true;
                    return result;
                }
                Err(RecvTimeoutError::Timeout) => {
                    control.ensure_active()?;
                    if self.closed.load(Ordering::SeqCst) {
                        return Err(RuntimeFailure::BrowserCrashed);
                    }
                }
                Err(RecvTimeoutError::Disconnected) => {
                    return Err(RuntimeFailure::BrowserCrashed);
                }
            }
        }
    }
}

impl PageRuntime for EngineThreadRuntime {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        if matches!(&message, BrowserActorMessage::Act { .. }) {
            return Err(RuntimeFailure::Unsupported(
                "generic Act cannot bypass atomic semantic dispatch",
            ));
        }
        self.preflight(owner, control)?;
        let (operation, create_session_id) = match message {
            BrowserActorMessage::Health => (BrowserOperation::Health, None),
            BrowserActorMessage::CreateSession {
                session_id,
                profile,
            } => {
                if profile.persistence != ProfilePersistence::Ephemeral {
                    return Err(RuntimeFailure::PolicyDenied(
                        "D3 profiles must be ephemeral",
                    ));
                }
                (
                    BrowserOperation::SessionCreate {
                        profile,
                        ui_mode: "headed".to_owned(),
                    },
                    Some(session_id),
                )
            }
            BrowserActorMessage::Snapshot => (BrowserOperation::SessionSnapshot, None),
            BrowserActorMessage::Close => (BrowserOperation::SessionClose, None),
            BrowserActorMessage::Navigate {
                url,
                expected_document_generation,
            } => (
                BrowserOperation::PageNavigate {
                    target: NavigationTarget::LocalHttpFixture { url },
                    expected_document_generation,
                },
                None,
            ),
            BrowserActorMessage::Observe { fields } => {
                (BrowserOperation::PageObserve { fields }, None)
            }
            BrowserActorMessage::Wait { condition, timeout } => {
                let timeout_ms = u64::try_from(timeout.as_millis())
                    .map_err(|_| RuntimeFailure::PolicyDenied("wait duration overflow"))?;
                // Refuse sub-millisecond precision loss instead of silently
                // changing the adapter's original deadline semantics.
                if Duration::from_millis(timeout_ms) != timeout {
                    return Err(RuntimeFailure::PolicyDenied(
                        "wait duration is not whole milliseconds",
                    ));
                }
                (
                    BrowserOperation::PageWait {
                        condition,
                        timeout_ms,
                    },
                    None,
                )
            }
            BrowserActorMessage::Extract { schema_id } => {
                (BrowserOperation::PageExtract { schema_id }, None)
            }
            BrowserActorMessage::Act { .. } => {
                return Err(RuntimeFailure::Unsupported(
                    "generic Act cannot bypass atomic semantic dispatch",
                ));
            }
        };
        self.call(
            owner,
            request(owner, operation, control),
            create_session_id,
            control,
        )
    }

    fn dispatch_page_act(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        target: ElementReference,
        action: PageAction,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        self.preflight(owner, control)?;
        self.call(
            owner,
            request(owner, BrowserOperation::PageAct { target, action }, control),
            None,
            control,
        )
    }
}

fn request(
    owner: Option<&PageOwnerSnapshot>,
    operation: BrowserOperation,
    control: &RequestControl,
) -> BrowserRequest {
    let unbound = matches!(
        operation,
        BrowserOperation::Health | BrowserOperation::SessionCreate { .. }
    );
    BrowserRequest {
        request_id: control.request_id.clone(),
        session_id: if unbound {
            None
        } else {
            owner.map(|p| p.session_id.clone())
        },
        session_generation: if unbound {
            None
        } else {
            owner.map(|p| p.session.revisions.session_generation)
        },
        // The original monotonic deadline is carried separately and never
        // round-tripped through the wall clock or extended by queueing.
        deadline_unix_ms: None,
        operation,
    }
}

fn validate_owner(owner: Option<&PageOwnerSnapshot>) -> Result<(), RuntimeFailure> {
    if let Some(owner) = owner {
        let valid = owner.local_fixture_only
            && crate::validate_token("session_id", &owner.session_id, 128).is_ok()
            && crate::validate_token("webview_token", &owner.webview_token, 128).is_ok()
            && (owner.current_url == "about:blank" || crate::is_loopback_http(&owner.current_url));
        if !valid {
            return Err(RuntimeFailure::PolicyDenied(
                "invalid or non-local D3 engine owner",
            ));
        }
    }
    Ok(())
}

fn is_uncertain_failure(error: &RuntimeFailure) -> bool {
    !matches!(
        error,
        RuntimeFailure::PolicyDenied(_) | RuntimeFailure::Unsupported(_)
    )
}

impl<R: PageRuntime> EngineThreadOwner<R> {
    /// Pump at most one call without waiting for a request. The event loop must
    /// service native events between calls; each adapter call must itself be
    /// bounded/cooperatively cancellable. This is not thread preemption.
    pub fn pump_one(&mut self) -> EnginePumpResult {
        if self.closed.load(Ordering::SeqCst) || thread::current().id() != self.owner_thread {
            self.closed.store(true, Ordering::SeqCst);
            if let Ok(call) = self.receiver.try_recv() {
                call.control.cancel();
            }
            return EnginePumpResult::Closed;
        }
        let call = match self.receiver.try_recv() {
            Ok(call) => call,
            Err(TryRecvError::Empty) => return EnginePumpResult::Idle,
            Err(TryRecvError::Disconnected) => {
                self.closed.store(true, Ordering::SeqCst);
                return EnginePumpResult::Closed;
            }
        };
        if let Err(error) = call.control.ensure_current_peer() {
            let _ = call.reply.try_send(Err(error));
            self.closed.store(true, Ordering::SeqCst);
            return EnginePumpResult::Discarded;
        }
        // Nothing inside this closure may obtain authority from the request's
        // snapshot alone. The engine must validate its own current DOM/revisions.
        let result = catch_unwind(AssertUnwindSafe(|| dispatch_call(&mut self.runtime, &call)))
            .unwrap_or(Err(RuntimeFailure::BrowserCrashed));
        let result = call
            .control
            .ensure_current_peer()
            .and(result)
            .and_then(bound_reply)
            .and_then(|reply| call.control.ensure_active().map(|()| reply))
            .map_err(|error| match error {
                // Backend diagnostics may contain page data. Do not forward
                // arbitrary engine strings into actor responses/receipts.
                RuntimeFailure::Internal(_) => {
                    RuntimeFailure::Internal("engine dispatch failed; runtime retired".to_owned())
                }
                error => error,
            });
        if result.as_ref().is_err_and(is_uncertain_failure) {
            self.closed.store(true, Ordering::SeqCst);
        }
        if call.reply.try_send(result).is_err() {
            call.control.cancel();
            self.closed.store(true, Ordering::SeqCst);
            return EnginePumpResult::Discarded;
        }
        EnginePumpResult::Replied
    }
}

// Move only bounded typed inputs into the backend; generic Act is unreachable.
fn dispatch_call<R: PageRuntime>(
    runtime: &mut R,
    call: &PendingCall,
) -> Result<RuntimeReply, RuntimeFailure> {
    if let BrowserOperation::PageAct { target, action } = &call.request.operation {
        return runtime.dispatch_page_act(
            call.owner.as_ref(),
            target.clone(),
            action.clone(),
            &call.control,
        );
    }
    runtime.dispatch(call.owner.as_ref(), ordinary_message(call)?, &call.control)
}

// Both synchronous and callback owners share exactly the same operation mapping.
// PageAct has no ordinary-message representation.
fn ordinary_message(call: &PendingCall) -> Result<BrowserActorMessage, RuntimeFailure> {
    Ok(match &call.request.operation {
        BrowserOperation::PageAct { .. } => {
            return Err(RuntimeFailure::Unsupported(
                "generic Act cannot bypass atomic semantic dispatch",
            ));
        }
        BrowserOperation::Health => BrowserActorMessage::Health,
        BrowserOperation::SessionCreate { profile, .. } => BrowserActorMessage::CreateSession {
            session_id: call.create_session_id.clone().ok_or_else(|| {
                RuntimeFailure::Internal("missing reserved engine session".to_owned())
            })?,
            profile: profile.clone(),
        },
        BrowserOperation::SessionSnapshot => BrowserActorMessage::Snapshot,
        BrowserOperation::SessionClose => BrowserActorMessage::Close,
        BrowserOperation::PageNavigate {
            target: NavigationTarget::LocalHttpFixture { url },
            expected_document_generation,
        } => BrowserActorMessage::Navigate {
            url: url.clone(),
            expected_document_generation: *expected_document_generation,
        },
        BrowserOperation::PageNavigate { .. } => {
            return Err(RuntimeFailure::PolicyDenied("non-local engine navigation"));
        }
        BrowserOperation::PageObserve { fields } => BrowserActorMessage::Observe {
            fields: fields.clone(),
        },
        BrowserOperation::PageWait {
            condition,
            timeout_ms,
        } => BrowserActorMessage::Wait {
            condition: condition.clone(),
            timeout: Duration::from_millis(*timeout_ms),
        },
        BrowserOperation::PageExtract { schema_id } => BrowserActorMessage::Extract {
            schema_id: schema_id.clone(),
        },
    })
}

fn bound_reply(mut reply: RuntimeReply) -> Result<RuntimeReply, RuntimeFailure> {
    if reply
        .current_url
        .as_ref()
        .is_some_and(|url| url != "about:blank" && !crate::is_loopback_http(url))
    {
        return Err(RuntimeFailure::Internal(
            "engine reply escaped D3 local URL policy".to_owned(),
        ));
    }
    // Borrow the object through the canonical encoder; no recursive clone of
    // an unchecked backend result is performed. Actor/AgentPort still apply
    // their own, potentially narrower, response-envelope limits afterwards.
    let value = JsonValue::Object(std::mem::take(&mut reply.result));
    value.canonical_bytes().map_err(|_| {
        RuntimeFailure::Internal("engine reply exceeds canonical JSON bounds".to_owned())
    })?;
    let JsonValue::Object(result) = value else {
        unreachable!()
    };
    reply.result = result;
    Ok(reply)
}

// Scheduling a wake may panic in a faulty embedder. Never unwind a destructor.
// A successful wake is only a notification, not proof the loop was pumped.
fn notify_engine(waker: &dyn EngineEventLoopWaker) -> bool {
    catch_unwind(AssertUnwindSafe(|| waker.wake())).is_ok()
}

impl Drop for EngineThreadRuntime {
    fn drop(&mut self) {
        self.closed.store(true, Ordering::SeqCst);
        notify_engine(self.waker.as_ref());
    }
}
impl<R> Drop for EngineThreadOwner<R> {
    fn drop(&mut self) {
        self.closed.store(true, Ordering::SeqCst);
        // PendingCall destruction closes its reply sender. The owner is
        // thread-affine, so no backend call can run concurrently with Drop.
        let _ = self.receiver.try_recv();
    }
}

#[cfg(test)]
#[path = "engine_dispatch/tests.rs"]
mod tests;

#[cfg(test)]
#[path = "engine_dispatch/transport_tests.rs"]
mod transport_tests;

#[cfg(test)]
#[path = "engine_dispatch/authority_tests.rs"]
mod authority_tests;
