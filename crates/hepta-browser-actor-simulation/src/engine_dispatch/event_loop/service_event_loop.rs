//! Typed fixed-profile service mechanism. An unbound pair cannot issue work.
//! The future opaque service core alone may construct the private registration
//! from a genuine original request. No registrar or raw endpoint is exported.
use super::*;
use hepta_peer_attestation::{ApprovedServiceRequestVerifier, ApprovedServiceSessionVerifier};
use std::sync::{Mutex, Weak};

struct RegistrationNonce;

struct ServiceDispatchScope {
    engine: Weak<ServiceEngineState>,
    nonce: Arc<RegistrationNonce>,
    session: Arc<ApprovedServiceSessionVerifier>,
    request: Arc<ApprovedServiceRequestVerifier>,
    request_id: String,
    original_deadline: Instant,
    dispatch_deadline: Instant,
    operation: BrowserOperation,
}

impl ServiceDispatchScope {
    fn current(&self, engine: &Arc<ServiceEngineState>) -> Result<(), RuntimeFailure> {
        engine.creator()?;
        let origin = self.engine.upgrade().ok_or(RuntimeFailure::BrowserCrashed)?;
        if !Arc::ptr_eq(&origin, engine) || engine.closed.load(Ordering::SeqCst) {
            return Err(RuntimeFailure::BrowserCrashed);
        }
        let bound = engine.session.lock().map_err(|_| RuntimeFailure::BrowserCrashed)?;
        let bound = bound.as_ref().ok_or(RuntimeFailure::PeerIdentityRevoked)?;
        if !Arc::ptr_eq(bound, &self.session) {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        self.session.ensure_current().map_err(|_| RuntimeFailure::PeerIdentityRevoked)?;
        if self.dispatch_deadline > self.original_deadline || Instant::now() >= self.dispatch_deadline {
            return Err(RuntimeFailure::DeadlineExceeded);
        }
        self.request.with_original_pair(&self.session, |_, _, _, original_deadline| {
            if original_deadline != self.original_deadline {
                return Err(RuntimeFailure::PeerIdentityRevoked);
            }
            Ok(())
        }).map_err(|_| RuntimeFailure::PeerIdentityRevoked)??;
        self.session.ensure_current().map_err(|_| RuntimeFailure::PeerIdentityRevoked)?;
        if Instant::now() >= self.dispatch_deadline {
            return Err(RuntimeFailure::DeadlineExceeded);
        }
        Ok(())
    }
}

struct ServiceRegistration {
    nonce: Arc<RegistrationNonce>,
    scope: Arc<ServiceDispatchScope>,
}

struct ServiceEngineState {
    creator_pid: u32,
    creator_thread: ThreadId,
    closed: Arc<AtomicBool>,
    session: Mutex<Option<Arc<ApprovedServiceSessionVerifier>>>,
    registration: Mutex<Option<ServiceRegistration>>,
}

impl ServiceEngineState {
    fn creator(&self) -> Result<(), RuntimeFailure> {
        if self.creator_pid != std::process::id() {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        Ok(())
    }

    fn service_current(&self) -> Result<(), RuntimeFailure> {
        self.creator()?;
        if self.closed.load(Ordering::SeqCst) {
            return Err(RuntimeFailure::BrowserCrashed);
        }
        if let Some(session) = self.session.lock().map_err(|_| RuntimeFailure::BrowserCrashed)?.as_ref() {
            // P1 checks its original creator namespace before policy/Owner I/O.
            session.ensure_current().map_err(|_| RuntimeFailure::PeerIdentityRevoked)?;
        }
        Ok(())
    }

    fn capture(self: &Arc<Self>, call: &PendingCall) -> Result<Arc<ServiceDispatchScope>, RuntimeFailure> {
        self.service_current()?;
        let registration = self.registration.lock().map_err(|_| RuntimeFailure::BrowserCrashed)?
            .take().ok_or(RuntimeFailure::PeerIdentityRevoked)?;
        let scope = registration.scope;
        if !Arc::ptr_eq(&registration.nonce, &scope.nonce)
            || scope.request_id != call.control.request_id
            || scope.dispatch_deadline != call.control.deadline
            || scope.operation != call.request.operation
        {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        scope.current(self)?;
        Ok(scope)
    }
}

/// One fixed endpoint. Only a future opaque service core may consume its
/// private engine and install a genuine request scope inside this module.
/// Creating this value is not Source approval or a listener factory.
///
/// ```compile_fail,E0616
/// use hepta_browser_actor_simulation::engine_dispatch::event_loop::ServiceEngineEndpoint;
/// fn raw(e: ServiceEngineEndpoint) { let _ = e.inner; }
/// ```
pub struct ServiceEngineEndpoint {
    inner: Option<EngineThreadRuntime>,
    state: Arc<ServiceEngineState>,
}

impl Drop for ServiceEngineEndpoint {
    fn drop(&mut self) {
        if self.inner.is_some() {
            self.state.closed.store(true, Ordering::SeqCst);
        }
        // Dropping the ordinary endpoint schedules a denial-only wake. This
        // type owns no Servo object or action permission.
    }
}

/// One original scope travels with this command and never gets recaptured from
/// a subsequent idle poll, another request ID or a replacement session.
pub struct ServiceEngineCommand {
    owner: Option<PageOwnerSnapshot>,
    message: BrowserActorMessage,
    completion: ServiceEngineCompletion,
}

impl ServiceEngineCommand {
    pub fn into_parts(self) -> (Option<PageOwnerSnapshot>, BrowserActorMessage, ServiceEngineCompletion) {
        (self.owner, self.message, self.completion)
    }
}

/// Single-use callback containing only readonly original proofs. It cannot
/// keep the original owning Agent slot or persistent Owner custody alive.
/// No inner legacy completion can be extracted.
///
/// ```compile_fail,E0616
/// use hepta_browser_actor_simulation::engine_dispatch::event_loop::ServiceEngineCompletion;
/// fn raw(c: ServiceEngineCompletion) { let _ = c.inner; }
/// ```
/// ```compile_fail,E0382
/// use hepta_browser_actor_simulation::engine_dispatch::event_loop::ServiceEngineCompletion;
/// use hepta_browser_actor_simulation::RuntimeReply;
/// fn twice(c: ServiceEngineCompletion, a: RuntimeReply, b: RuntimeReply) {
///     c.complete(Ok(a));
///     c.complete(Ok(b));
/// }
/// ```
pub struct ServiceEngineCompletion {
    inner: Option<EngineCompletion>,
    engine: Arc<ServiceEngineState>,
    scope: Arc<ServiceDispatchScope>,
}

impl ServiceEngineCompletion {
    pub fn request_id(&self) -> &str {
        &self.scope.request_id
    }

    pub fn deadline(&self) -> Instant {
        self.scope.dispatch_deadline
    }

    pub fn ensure_current_request(&self) -> Result<(), RuntimeFailure> {
        self.scope.current(&self.engine)?;
        self.inner.as_ref().ok_or(RuntimeFailure::BrowserCrashed)?.ensure_current_peer()?;
        self.scope.current(&self.engine)
    }

    pub fn complete(mut self, result: Result<RuntimeReply, RuntimeFailure>) -> CompletionDelivery {
        let result = self.ensure_current_request().and(result)
            .and_then(|reply| bound_reply(reply, EngineUrlScope::ClosedImmutableReadOnly))
            .and_then(|reply| self.ensure_current_request().map(|()| reply));
        let Some(inner) = self.inner.take() else {
            return CompletionDelivery::Retired;
        };
        let delivered = inner.complete(result);
        // Queueing is not final forwarding. Even after a physical queue write,
        // Source loss closes this pair before its new active pipeline forwards.
        if self.scope.current(&self.engine).is_err() {
            self.engine.closed.store(true, Ordering::SeqCst);
            return CompletionDelivery::Retired;
        }
        delivered
    }
}

impl Drop for ServiceEngineCompletion {
    fn drop(&mut self) {
        if self.inner.is_some() {
            // Local denial before legacy token Drop; no Source/Owner filesystem
            // query or claimed rollback from a destructor, including fork copies.
            self.engine.closed.store(true, Ordering::SeqCst);
        }
    }
}

struct ServiceActiveCall {
    call: PendingCall,
    scope: Arc<ServiceDispatchScope>,
    completion: Receiver<Result<RuntimeReply, RuntimeFailure>>,
    valid: Arc<AtomicBool>,
}

/// Creator-thread bridge. No caller callback runtime, public registrar or
/// native lifecycle is supplied. Unbound state is idle; an unbound call refuses.
///
/// ```compile_fail,E0277
/// use hepta_browser_actor_simulation::engine_dispatch::event_loop::ServiceEngineBridge;
/// fn requires_send<T: Send>() {}
/// fn foreign_thread() { requires_send::<ServiceEngineBridge>(); }
/// ```
pub struct ServiceEngineBridge {
    receiver: Receiver<PendingCall>,
    state: Arc<ServiceEngineState>,
    waker: Arc<dyn EngineEventLoopWaker>,
    active: Option<ServiceActiveCall>,
    command: Option<ServiceEngineCommand>,
    retired: bool,
    _thread_affinity: PhantomData<Rc<()>>,
}

impl ServiceEngineBridge {
    fn owner_current(&self) -> Result<(), RuntimeFailure> {
        self.state.creator()?;
        if thread::current().id() != self.state.creator_thread {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        self.state.service_current()
    }

    pub fn pump_one(&mut self) -> CallbackPumpResult {
        if self.retired {
            return CallbackPumpResult::Retired;
        }
        if self.owner_current().is_err() {
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
        let scope = match self.state.capture(&call).and_then(|scope| {
            call.control.ensure_current_peer()?;
            scope.current(&self.state)?;
            closed_operation(&call.request.operation)?;
            Ok(scope)
        }) {
            Ok(scope) => scope,
            Err(error) => {
                let _ = call.reply.try_send(Err(error));
                call.control.cancel();
                self.retire();
                return CallbackPumpResult::Retired;
            }
        };
        let message = match ordinary_message(&call) {
            Ok(message) => message,
            Err(error) => {
                let _ = call.reply.try_send(Err(error));
                self.retire();
                return CallbackPumpResult::Retired;
            }
        };
        let (sender, completion) = mpsc::sync_channel(1);
        let valid = Arc::new(AtomicBool::new(true));
        let token = EngineCompletion {
            sender: Some(sender), valid: valid.clone(), closed: self.state.closed.clone(),
            control: call.control.clone(), waker: self.waker.clone(),
            url_scope: EngineUrlScope::ClosedImmutableReadOnly,
        };
        self.active = Some(ServiceActiveCall { call, scope: scope.clone(), completion, valid });
        let owner = self.active.as_ref().expect("active service call installed").call.owner.clone();
        self.command = Some(ServiceEngineCommand {
            owner, message,
            completion: ServiceEngineCompletion { inner: Some(token), engine: self.state.clone(), scope },
        });
        self.poll_active()
    }

    fn poll_active(&mut self) -> CallbackPumpResult {
        let active = self.active.as_ref().expect("service poll requires active call");
        if let Err(error) = self.owner_current()
            .and_then(|()| active.scope.current(&self.state))
            .and_then(|()| active.call.control.ensure_active())
        {
            self.fail_active(error);
            return CallbackPumpResult::Retired;
        }
        let result = match active.completion.try_recv() {
            Ok(result) => result,
            Err(TryRecvError::Empty) => return CallbackPumpResult::Pending,
            Err(TryRecvError::Disconnected) => Err(RuntimeFailure::BrowserCrashed),
        };
        // This is the service pipeline itself, not an outer check around the
        // legacy poll. Keep the captured proof through the final result chain.
        let result = active.scope.current(&self.state)
            .and_then(|()| active.call.control.ensure_current_peer())
            .and(result)
            .and_then(|reply| bound_reply(reply, EngineUrlScope::ClosedImmutableReadOnly))
            .and_then(|reply| active.scope.current(&self.state).map(|()| reply))
            .and_then(|reply| active.call.control.ensure_active().map(|()| reply))
            .map_err(redact_failure);
        let uncertain = result.as_ref().is_err_and(is_uncertain_failure);
        let active = self.active.take().expect("service active call remains installed");
        active.valid.store(false, Ordering::SeqCst);
        // Pre/post samples cannot make Source mutation atomic with this send.
        // A post failure retains uncertainty and retires; it never claims the
        // buffered value was not physically written or clears product history.
        let sent = active.call.reply.try_send(result);
        let current = active.call.control.ensure_active()
            .and_then(|()| active.scope.current(&self.state));
        if sent.is_err() || uncertain || current.is_err() {
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

    pub fn take_command(&mut self) -> Option<ServiceEngineCommand> {
        if self.owner_current().is_err()
            || self.command.as_ref().is_some_and(|command| command.completion.ensure_current_request().is_err())
        {
            self.retire();
            return None;
        }
        self.command.take()
    }

    pub fn next_wake_deadline(&self) -> Option<Instant> {
        self.active.as_ref().map(|active| active.scope.dispatch_deadline)
    }

    pub fn retire(&mut self) {
        if self.retired {
            return;
        }
        self.retired = true;
        self.state.closed.store(true, Ordering::SeqCst);
        if let Some(active) = self.active.take() {
            active.valid.store(false, Ordering::SeqCst);
            active.call.control.cancel();
            let _ = active.call.reply.try_send(Err(RuntimeFailure::BrowserCrashed));
        }
        self.command.take();
        if let Ok(call) = self.receiver.try_recv() {
            call.control.cancel();
        }
        if let Ok(mut registration) = self.state.registration.lock() {
            registration.take();
        }
    }
}

impl Drop for ServiceEngineBridge {
    fn drop(&mut self) {
        self.retire();
    }
}

fn closed_operation(operation: &BrowserOperation) -> Result<(), RuntimeFailure> {
    match operation {
        BrowserOperation::Health | BrowserOperation::SessionSnapshot
        | BrowserOperation::PageObserve { .. } | BrowserOperation::SessionClose => Ok(()),
        BrowserOperation::SessionCreate { profile, .. }
            if profile.profile_id == "immutable-read-only-v1"
                && profile.persistence == hepta_browser_codec::ProfilePersistence::Ephemeral => Ok(()),
        _ => Err(RuntimeFailure::PolicyDenied("closed service operation refused")),
    }
}

/// Create an unused closed mechanism pair. No request, Source, principal,
/// supplied callback runtime, URL selector, listener or future budget is taken.
/// P2A has not yet implemented the sole private genuine-binding constructor;
/// consequently this P2B foundation cannot produce an approved native command.
pub fn closed_immutable_service_engine_pair(
    waker: Arc<dyn EngineEventLoopWaker>,
) -> (ServiceEngineEndpoint, ServiceEngineBridge) {
    let (sender, receiver) = mpsc::sync_channel(ENGINE_PENDING_LIMIT);
    let closed = Arc::new(AtomicBool::new(false));
    let owner_thread = thread::current().id();
    let state = Arc::new(ServiceEngineState {
        creator_pid: std::process::id(), creator_thread: owner_thread,
        closed: closed.clone(), session: Mutex::new(None), registration: Mutex::new(None),
    });
    let endpoint = EngineThreadRuntime {
        sender, closed, owner_thread, waker: waker.clone(), url_scope: EngineUrlScope::ClosedImmutableReadOnly,
    };
    (
        ServiceEngineEndpoint { inner: Some(endpoint), state: state.clone() },
        ServiceEngineBridge { receiver, state, waker, active: None, command: None,
                              retired: false, _thread_affinity: PhantomData },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unbound_pair_never_emits_an_approved_command() {
        let (_endpoint, mut bridge) = closed_immutable_service_engine_pair(Arc::new(|| {}));
        assert_eq!(bridge.pump_one(), CallbackPumpResult::Idle);
        assert!(bridge.take_command().is_none());
        assert!(bridge.next_wake_deadline().is_none());
    }

    #[test]
    fn dropped_endpoint_permanently_retires_unused_bridge() {
        let (endpoint, mut bridge) = closed_immutable_service_engine_pair(Arc::new(|| {}));
        drop(endpoint);
        assert_eq!(bridge.pump_one(), CallbackPumpResult::Retired);
        assert_eq!(bridge.pump_one(), CallbackPumpResult::Retired);
        assert!(bridge.take_command().is_none());
    }

    #[test]
    fn fixed_profile_refuses_external_and_unimplemented_operations() {
        for operation in [
            BrowserOperation::PageNavigate {
                target: hepta_browser_codec::NavigationTarget::ExternalHttps {
                    url: "https://example.invalid/".into(),
                },
                expected_document_generation: 1,
            },
            BrowserOperation::PageWait {
                condition: hepta_browser_codec::WaitCondition::DocumentReady,
                timeout_ms: 1,
            },
            BrowserOperation::PageExtract { schema_id: "not-approved".into() },
        ] {
            assert!(closed_operation(&operation).is_err());
        }
    }

    #[test]
    fn create_requires_exact_fixed_ephemeral_profile() {
        for (id, persistence) in [
            ("wrong", hepta_browser_codec::ProfilePersistence::Ephemeral),
            ("immutable-read-only-v1", hepta_browser_codec::ProfilePersistence::Persistent),
        ] {
            assert!(closed_operation(&BrowserOperation::SessionCreate {
                profile: hepta_browser_codec::ProfileSpec { profile_id: id.into(), persistence },
                ui_mode: "headed".into(),
            }).is_err());
        }
        assert!(closed_operation(&BrowserOperation::SessionCreate {
            profile: hepta_browser_codec::ProfileSpec {
                profile_id: "immutable-read-only-v1".into(),
                persistence: hepta_browser_codec::ProfilePersistence::Ephemeral,
            },
            ui_mode: "headed".into(),
        }).is_ok());
    }
}
