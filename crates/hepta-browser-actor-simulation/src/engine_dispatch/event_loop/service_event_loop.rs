//! Typed fixed-profile service mechanism. An unbound pair cannot issue work.
//! The future opaque service core alone may construct the private registration
//! from a genuine original request. No registrar or raw endpoint is exported.
mod service_actor;
pub use service_actor::ServiceBrowserActorCore;

use super::*;
use hepta_browser_codec::{BrowserRequest, encode_request};
use hepta_peer_attestation::{ApprovedServiceRequestVerifier, ApprovedServiceSessionVerifier};
use std::sync::{Mutex, OnceLock, Weak};

struct RegistrationNonce;

struct ServiceDispatchScope {
    engine: Weak<ServiceEngineState>,
    nonce: Arc<RegistrationNonce>,
    session: Arc<ApprovedServiceSessionVerifier>,
    request: Arc<ApprovedServiceRequestVerifier>,
    request_id: String,
    original_deadline: Instant,
    dispatch_deadline: Instant,
    shortened_deadline: OnceLock<Instant>,
    operation: BrowserOperation,
    original_request: BrowserRequest,
    original_canonical: Vec<u8>,
    canonical_sha256: String,
    engine_canonical: Vec<u8>,
    runtime_started: AtomicBool,
    runtime_finished: AtomicBool,
    retired: AtomicBool,
}

impl ServiceDispatchScope {
    // Readonly diagnostic ceiling. The single installed value can only narrow
    // the immutable registration/context and original Control/Agent clocks.
    fn dispatch_cutoff(&self) -> Instant {
        self.shortened_deadline
            .get()
            .copied()
            .unwrap_or(self.dispatch_deadline)
            .min(self.dispatch_deadline)
            .min(self.original_deadline)
    }

    fn check_dispatch_cutoff(&self) -> Result<(), RuntimeFailure> {
        if self.dispatch_deadline > self.original_deadline
            || Instant::now() >= self.dispatch_cutoff()
        {
            return Err(RuntimeFailure::DeadlineExceeded);
        }
        Ok(())
    }

    fn current(&self, engine: &Arc<ServiceEngineState>) -> Result<(), RuntimeFailure> {
        engine.creator()?;
        // The captured P1 creator/namespace proof precedes any inherited
        // mutable registration lock. Numeric PID alone is not that proof.
        self.session
            .ensure_current()
            .map_err(|_| RuntimeFailure::PeerIdentityRevoked)?;
        if self.retired.load(Ordering::SeqCst) {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        self.check_dispatch_cutoff()?;
        let original = encode_request(&self.original_request)
            .map_err(|_| RuntimeFailure::PolicyDenied("original canonical container invalid"))?;
        let mut runtime_request = self.original_request.clone();
        runtime_request.deadline_unix_ms = None;
        let expected_engine = encode_request(&runtime_request)
            .map_err(|_| RuntimeFailure::PolicyDenied("closed runtime envelope invalid"))?;
        if original != self.original_canonical
            || crate::executable_sha256(&original) != self.canonical_sha256
            || expected_engine != self.engine_canonical
            || self.request_id != self.original_request.request_id
            || self.operation != self.original_request.operation
        {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        let origin = self
            .engine
            .upgrade()
            .ok_or(RuntimeFailure::BrowserCrashed)?;
        if !Arc::ptr_eq(&origin, engine) || engine.closed.load(Ordering::SeqCst) {
            return Err(RuntimeFailure::BrowserCrashed);
        }
        let bound = engine
            .session
            .get()
            .ok_or(RuntimeFailure::PeerIdentityRevoked)?;
        if !Arc::ptr_eq(bound, &self.session) {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        self.check_dispatch_cutoff()?;
        self.request
            .with_original_pair(&self.session, |_, _, _, original_deadline| {
                if original_deadline != self.original_deadline {
                    return Err(RuntimeFailure::PeerIdentityRevoked);
                }
                Ok(())
            })
            .map_err(|_| RuntimeFailure::PeerIdentityRevoked)??;
        self.session
            .ensure_current()
            .map_err(|_| RuntimeFailure::PeerIdentityRevoked)?;
        self.check_dispatch_cutoff()?;
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
    session: OnceLock<Arc<ApprovedServiceSessionVerifier>>,
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
        if let Some(session) = self.session.get() {
            // P1 checks its original creator namespace before policy/Owner I/O.
            session
                .ensure_current()
                .map_err(|_| RuntimeFailure::PeerIdentityRevoked)?;
        }
        Ok(())
    }

    fn capture(
        self: &Arc<Self>,
        call: &PendingCall,
    ) -> Result<Arc<ServiceDispatchScope>, RuntimeFailure> {
        self.service_current()?;
        if self.session.get().is_none() {
            // Unbound calls never query a possibly inherited mutable lock.
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        let registration = self
            .registration
            .lock()
            .map_err(|_| RuntimeFailure::BrowserCrashed)?
            .take()
            .ok_or(RuntimeFailure::PeerIdentityRevoked)?;
        let scope = registration.scope;
        if !Arc::ptr_eq(&registration.nonce, &scope.nonce)
            || scope.request_id != call.control.request_id
            || scope.dispatch_deadline != call.control.deadline
            || scope.operation != call.request.operation
        {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        scope.current(self)?;
        let call_canonical = encode_request(&call.request).map_err(|_| {
            RuntimeFailure::PolicyDenied("pending canonical runtime envelope invalid")
        })?;
        if call_canonical != scope.engine_canonical {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
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
    pub fn into_parts(
        self,
    ) -> (
        Option<PageOwnerSnapshot>,
        BrowserActorMessage,
        ServiceEngineCompletion,
    ) {
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
/// The denial cutoff installer requires exclusive custody of this completion.
///
/// ```compile_fail,E0596
/// use hepta_browser_actor_simulation::engine_dispatch::event_loop::ServiceEngineCompletion;
/// fn shared(c: &ServiceEngineCompletion, cutoff: std::time::Instant) {
///     let _ = c.shorten_deadline_once(cutoff);
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
        self.scope.dispatch_cutoff()
    }

    /// Install one additional denial-only cutoff for this actual completion.
    /// Future inputs are clamped to both captured ceilings. A second install,
    /// expired cutoff or original proof failure permanently denies this pair.
    /// This neither approves a native deadline nor renews a request budget.
    pub fn shorten_deadline_once(&mut self, cutoff: Instant) -> Result<Instant, RuntimeFailure> {
        // A fork copy is rejected before the inherited OnceLock or waker.
        self.engine.creator()?;
        let checked = (|| {
            self.ensure_current_request()?;
            let inner = self.inner.as_ref().ok_or(RuntimeFailure::BrowserCrashed)?;
            if inner.request_id() != self.scope.request_id
                || inner.deadline() != self.scope.dispatch_deadline
                || !self.scope.runtime_started.load(Ordering::SeqCst)
                || self.scope.runtime_finished.load(Ordering::SeqCst)
            {
                return Err(RuntimeFailure::PeerIdentityRevoked);
            }
            let cutoff = cutoff
                .min(self.scope.dispatch_deadline)
                .min(self.scope.original_deadline);
            // There is exactly one private writer: this non-Clone completion's
            // exclusive mutable method. Readers use nonblocking get only.
            self.scope
                .shortened_deadline
                .set(cutoff)
                .map_err(|_| RuntimeFailure::PeerIdentityRevoked)?;
            self.ensure_current_request()?;
            // Publishing a shorter wake deadline is denial, never native work.
            if !notify_engine(inner.waker.as_ref()) {
                return Err(RuntimeFailure::BrowserCrashed);
            }
            self.ensure_current_request()?;
            Ok(self.scope.dispatch_cutoff())
        })();
        if checked.is_err() {
            // Local sticky denial; no fabricated remote cancellation/report,
            // registration lock, owning-slot release or terminal success.
            self.scope.retired.store(true, Ordering::SeqCst);
            self.engine.closed.store(true, Ordering::SeqCst);
        }
        checked
    }

    pub fn ensure_current_request(&self) -> Result<(), RuntimeFailure> {
        self.scope.current(&self.engine)?;
        self.inner
            .as_ref()
            .ok_or(RuntimeFailure::BrowserCrashed)?
            .ensure_current_peer()?;
        self.scope.current(&self.engine)
    }

    pub fn complete(mut self, result: Result<RuntimeReply, RuntimeFailure>) -> CompletionDelivery {
        let result = self
            .ensure_current_request()
            .and(result)
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
            sender: Some(sender),
            valid: valid.clone(),
            closed: self.state.closed.clone(),
            control: call.control.clone(),
            waker: self.waker.clone(),
            url_scope: EngineUrlScope::ClosedImmutableReadOnly,
        };
        self.active = Some(ServiceActiveCall {
            call,
            scope: scope.clone(),
            completion,
            valid,
        });
        scope.runtime_started.store(true, Ordering::SeqCst);
        let owner = self
            .active
            .as_ref()
            .expect("active service call installed")
            .call
            .owner
            .clone();
        self.command = Some(ServiceEngineCommand {
            owner,
            message,
            completion: ServiceEngineCompletion {
                inner: Some(token),
                engine: self.state.clone(),
                scope,
            },
        });
        self.poll_active()
    }

    fn poll_active(&mut self) -> CallbackPumpResult {
        let active = self
            .active
            .as_ref()
            .expect("service poll requires active call");
        if let Err(error) = self
            .owner_current()
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
        let result = active
            .scope
            .current(&self.state)
            .and_then(|()| active.call.control.ensure_current_peer())
            .and(result)
            .and_then(|reply| bound_reply(reply, EngineUrlScope::ClosedImmutableReadOnly))
            .and_then(|reply| active.scope.current(&self.state).map(|()| reply))
            .and_then(|reply| active.call.control.ensure_active().map(|()| reply))
            .map_err(redact_failure);
        let uncertain = result.as_ref().is_err_and(is_uncertain_failure);
        let active = self
            .active
            .take()
            .expect("service active call remains installed");
        active.valid.store(false, Ordering::SeqCst);
        // Pre/post samples cannot make Source mutation atomic with this send.
        // A post failure retains uncertainty and retires; it never claims the
        // buffered value was not physically written or clears product history.
        // The same installed cutoff is sampled immediately at the physical
        // forward boundary, after all full Source/pair and result checks.
        let result = active.scope.check_dispatch_cutoff().and(result);
        let uncertain = uncertain || result.as_ref().is_err_and(is_uncertain_failure);
        let sent = active.call.reply.try_send(result);
        let current = active
            .call
            .control
            .ensure_active()
            .and_then(|()| active.scope.current(&self.state));
        if sent.is_err() || uncertain || current.is_err() {
            self.state.closed.store(true, Ordering::SeqCst);
            active.scope.retired.store(true, Ordering::SeqCst);
            active.scope.runtime_finished.store(true, Ordering::SeqCst);
            self.retire();
            return CallbackPumpResult::Retired;
        }
        active.scope.runtime_finished.store(true, Ordering::SeqCst);
        CallbackPumpResult::Replied
    }

    fn fail_active(&mut self, error: RuntimeFailure) {
        if let Some(active) = self.active.take() {
            self.state.closed.store(true, Ordering::SeqCst);
            active.scope.retired.store(true, Ordering::SeqCst);
            active.scope.runtime_finished.store(true, Ordering::SeqCst);
            active.valid.store(false, Ordering::SeqCst);
            let _ = active.call.reply.try_send(Err(error));
        }
        self.retire();
    }

    pub fn take_command(&mut self) -> Option<ServiceEngineCommand> {
        if self.owner_current().is_err()
            || self
                .command
                .as_ref()
                .is_some_and(|command| command.completion.ensure_current_request().is_err())
        {
            self.retire();
            return None;
        }
        self.command.take()
    }

    pub fn next_wake_deadline(&self) -> Option<Instant> {
        self.active
            .as_ref()
            .map(|active| active.scope.dispatch_cutoff())
    }

    pub fn retire(&mut self) {
        if self.retired {
            return;
        }
        self.retired = true;
        self.state.closed.store(true, Ordering::SeqCst);
        if let Some(active) = self.active.take() {
            active.scope.retired.store(true, Ordering::SeqCst);
            active.scope.runtime_finished.store(true, Ordering::SeqCst);
            active.valid.store(false, Ordering::SeqCst);
            active.call.control.cancel();
            let _ = active
                .call
                .reply
                .try_send(Err(RuntimeFailure::BrowserCrashed));
        }
        self.command.take();
        if let Ok(call) = self.receiver.try_recv() {
            call.control.cancel();
        }
        // closed permanently refuses the retained registration. Denial/Drop
        // must not acquire an inherited registration lock after Source refusal.
    }
}

impl Drop for ServiceEngineBridge {
    fn drop(&mut self) {
        self.retire();
    }
}

fn closed_operation(operation: &BrowserOperation) -> Result<(), RuntimeFailure> {
    match operation {
        BrowserOperation::Health
        | BrowserOperation::SessionSnapshot
        | BrowserOperation::PageObserve { .. }
        | BrowserOperation::SessionClose => Ok(()),
        BrowserOperation::SessionCreate { profile, .. }
            if profile.profile_id == "immutable-read-only-v1"
                && profile.persistence == hepta_browser_codec::ProfilePersistence::Ephemeral =>
        {
            Ok(())
        }
        _ => Err(RuntimeFailure::PolicyDenied(
            "closed service operation refused",
        )),
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
        creator_pid: std::process::id(),
        creator_thread: owner_thread,
        closed: closed.clone(),
        session: OnceLock::new(),
        registration: Mutex::new(None),
    });
    let endpoint = EngineThreadRuntime {
        sender,
        closed,
        owner_thread,
        waker: waker.clone(),
        url_scope: EngineUrlScope::ClosedImmutableReadOnly,
    };
    (
        ServiceEngineEndpoint {
            inner: Some(endpoint),
            state: state.clone(),
        },
        ServiceEngineBridge {
            receiver,
            state,
            waker,
            active: None,
            command: None,
            retired: false,
            _thread_affinity: PhantomData,
        },
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
            BrowserOperation::PageExtract {
                schema_id: "not-approved".into(),
            },
        ] {
            assert!(closed_operation(&operation).is_err());
        }
    }

    #[test]
    fn create_requires_exact_fixed_ephemeral_profile() {
        for (id, persistence) in [
            ("wrong", hepta_browser_codec::ProfilePersistence::Ephemeral),
            (
                "immutable-read-only-v1",
                hepta_browser_codec::ProfilePersistence::Persistent,
            ),
        ] {
            assert!(
                closed_operation(&BrowserOperation::SessionCreate {
                    profile: hepta_browser_codec::ProfileSpec {
                        profile_id: id.into(),
                        persistence
                    },
                    ui_mode: "headed".into(),
                })
                .is_err()
            );
        }
        assert!(
            closed_operation(&BrowserOperation::SessionCreate {
                profile: hepta_browser_codec::ProfileSpec {
                    profile_id: "immutable-read-only-v1".into(),
                    persistence: hepta_browser_codec::ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".into(),
            })
            .is_ok()
        );
    }
}
