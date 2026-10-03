//! Closed original-request Core. Only this nested child consumes the private
//! fixed endpoint. It exposes no raw actor, runtime, registrar or journal.
use super::*;
use crate::{BrowserActor, CancellationToken, PageRuntime, PrincipalBinding, TaskFlowPrincipal};
use hepta_agent_port::{AgentPortError, DispatchContext, HandlerOutcome};
use hepta_browser_codec::{BrowserErrorCode, BrowserRequest, BrowserWireError, encode_request};
use hepta_peer_attestation::{ApprovedServiceRequestBinding, ApprovedServiceSessionVerifier};

struct PreparedOriginal {
    _binding: ApprovedServiceRequestBinding,
    verifier: Arc<ApprovedServiceRequestVerifier>,
    scope: Arc<ServiceDispatchScope>,
    context: DispatchContext,
    cancellation: CancellationToken,
    handled: bool,
}

struct DispatchUnwind {
    engine: Arc<ServiceEngineState>,
    scope: Arc<ServiceDispatchScope>,
    uncertain: Arc<AtomicBool>,
    armed: bool,
}

impl Drop for DispatchUnwind {
    fn drop(&mut self) {
        if self.armed {
            // A local sticky denial. Drop never observes Source or takes the
            // registration lock, and cannot undo a native or wire effect.
            self.uncertain.store(true, Ordering::SeqCst);
            self.scope.retired.store(true, Ordering::SeqCst);
            self.engine.closed.store(true, Ordering::SeqCst);
        }
    }
}

// Fixed and private: callers cannot select a runtime or replace its captured
// scope. The old actor retires its token after dispatch returns, so wait here
// before returning a buffered reply to that actor.
struct ServiceScopedRuntime {
    inner: EngineThreadRuntime,
    engine: Arc<ServiceEngineState>,
    scope: Arc<ServiceDispatchScope>,
    uncertain: Arc<AtomicBool>,
}

impl PageRuntime for ServiceScopedRuntime {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        self.scope.current(&self.engine)?;
        if control.request_id != self.scope.request_id
            || control.deadline != self.scope.dispatch_deadline
        {
            return Err(RuntimeFailure::PeerIdentityRevoked);
        }
        control.ensure_current_peer()?;
        control.remaining()?;
        let mut guard = DispatchUnwind {
            engine: self.engine.clone(),
            scope: self.scope.clone(),
            uncertain: self.uncertain.clone(),
            armed: true,
        };
        let result = self.inner.dispatch(owner, message, control);
        // The physical reply alone is not bridge-post completion. Keep the
        // original cancellation token active through the real post samples.
        await_final_forward(&self.engine, &self.scope, Some(control), None)?;
        if result.as_ref().is_err_and(is_uncertain_failure) {
            return result;
        }
        guard.armed = false;
        result
    }

    fn dispatch_page_act(
        &mut self,
        _owner: Option<&PageOwnerSnapshot>,
        _target: hepta_browser_codec::ElementReference,
        _action: hepta_browser_codec::PageAction,
        _control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        Err(RuntimeFailure::Unsupported(
            "closed service does not admit semantic action",
        ))
    }
}

fn await_final_forward(
    engine: &Arc<ServiceEngineState>,
    scope: &Arc<ServiceDispatchScope>,
    control: Option<&RequestControl>,
    context: Option<&DispatchContext>,
) -> Result<(), RuntimeFailure> {
    loop {
        // Full captured Source/namespace/pair/clock checks precede any wait.
        // closed/retired is checked before finished, including when failure
        // sets finished after permanently closing the engine.
        scope.current(engine)?;
        if let Some(control) = control {
            control.remaining()?;
        }
        if let Some(context) = context {
            context
                .remaining()
                .map_err(|_| RuntimeFailure::DeadlineExceeded)?;
        }
        if !scope.runtime_started.load(Ordering::SeqCst)
            || scope.runtime_finished.load(Ordering::SeqCst)
        {
            // Only the captured bridge writes finished after its post samples.
            // Recheck actual proof and the original remaining budget after it.
            scope.current(engine)?;
            if let Some(control) = control {
                control.remaining()?;
            }
            if let Some(context) = context {
                context
                    .remaining()
                    .map_err(|_| RuntimeFailure::DeadlineExceeded)?;
            }
            return Ok(());
        }
        std::thread::yield_now();
    }
}

/// Non-generic Core owning the only private legacy actor for its fixed engine.
/// A genuine P1 binding selects the principal and original pair. No installed
/// factory, managed journal, durable outcome or native health is selected here.
///
/// ```compile_fail,E0616
/// use hepta_browser_actor_simulation::ServiceBrowserActorCore;
/// fn raw(core: ServiceBrowserActorCore) { let _ = core.inner; }
/// ```
/// ```compile_fail,E0107
/// use hepta_browser_actor_simulation::{ServiceBrowserActorCore, DeterministicLocalRuntime};
/// fn weaker(_: ServiceBrowserActorCore<DeterministicLocalRuntime>) {}
/// ```
pub struct ServiceBrowserActorCore {
    inner: BrowserActor<ServiceScopedRuntime>,
    engine: Arc<ServiceEngineState>,
    session: Arc<ApprovedServiceSessionVerifier>,
    prepared: Option<PreparedOriginal>,
    uncertain: Arc<AtomicBool>,
}

impl ServiceBrowserActorCore {
    pub fn from_original_request(
        mut endpoint: ServiceEngineEndpoint,
        session: ApprovedServiceSessionVerifier,
        binding: ApprovedServiceRequestBinding,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<Self, AgentPortError> {
        endpoint.state.creator().map_err(runtime_error)?;
        session.ensure_current().map_err(approval_error)?;
        // get never waits. This unique, moved endpoint is the sole initializer;
        // there is no public setter or second Core for its engine Arc.
        if endpoint.state.session.get().is_some() || endpoint.state.closed.load(Ordering::SeqCst) {
            return Err(refused("service endpoint is already bound or retired"));
        }
        if endpoint
            .state
            .registration
            .lock()
            .map_err(|_| refused("registration poisoned"))?
            .is_some()
        {
            return Err(refused("service endpoint already has a registration"));
        }
        let engine = endpoint.state.clone();
        let session = Arc::new(session);
        let (selected, mut prepared) =
            capture_original(&engine, &session, binding, context, request, None)?;
        let uncertain = Arc::new(AtomicBool::new(false));
        let mut construction = DispatchUnwind {
            engine: engine.clone(),
            scope: prepared.scope.clone(),
            uncertain: uncertain.clone(),
            armed: true,
        };
        session.ensure_current().map_err(approval_error)?;
        engine
            .session
            .set(session.clone())
            .map_err(|_| refused("service session cannot be replaced"))?;
        let runtime = endpoint
            .inner
            .take()
            .ok_or_else(|| refused("service endpoint was consumed"))?;
        let mut inner = BrowserActor::new(
            selected,
            ServiceScopedRuntime {
                inner: runtime,
                engine: engine.clone(),
                scope: prepared.scope.clone(),
                uncertain: uncertain.clone(),
            },
        );
        prepared.cancellation = inner.cancellation_token(&request.request_id);
        prepared.scope.current(&engine).map_err(runtime_error)?;
        construction.armed = false;
        Ok(Self {
            inner,
            engine,
            session,
            prepared: Some(prepared),
            uncertain,
        })
    }

    /// Consume one fresh same-service owning binding. Rebinding is private and
    /// refuses active, prepared, unknown or retired state before mutation.
    pub fn prepare_original_request(
        &mut self,
        binding: ApprovedServiceRequestBinding,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<CancellationToken, AgentPortError> {
        self.ensure_current_service()?;
        if self.prepared.is_some()
            || self.uncertain.load(Ordering::SeqCst)
            || self.inner.runtime_unavailable
            || !self.inner.cancellation_tokens.is_empty()
            || !self.inner.cancelled_requests.is_empty()
            || self.inner.request_authority.borrow().is_some()
            || self.inner.control_authority.borrow().is_some()
            || (self
                .inner
                .runtime
                .scope
                .runtime_started
                .load(Ordering::SeqCst)
                && !self
                    .inner
                    .runtime
                    .scope
                    .runtime_finished
                    .load(Ordering::SeqCst))
        {
            return Err(refused(
                "service actor conflicts with previous preparation or uncertainty",
            ));
        }
        if self
            .engine
            .registration
            .lock()
            .map_err(|_| refused("registration poisoned"))?
            .is_some()
        {
            return Err(refused("previous registration remains pending"));
        }
        let (selected, mut prepared) = capture_original(
            &self.engine,
            &self.session,
            binding,
            context,
            request,
            Some(self.inner.principal_binding().principal()),
        )?;
        // All full external observations precede private mechanism mutation.
        prepared
            .scope
            .current(&self.engine)
            .map_err(runtime_error)?;
        self.inner.binding = selected;
        // Previous preparation/authority/unknown work is absent. Completions
        // retain their own old Arc; they never read this later scope.
        self.inner.runtime.scope = prepared.scope.clone();
        prepared.cancellation = self.inner.cancellation_token(&request.request_id);
        let cancellation = prepared.cancellation.clone();
        self.prepared = Some(prepared);
        Ok(cancellation)
    }

    pub fn preflight_original(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<Option<BrowserWireError>, AgentPortError> {
        self.ensure_current_service()?;
        let prepared = self
            .prepared
            .as_ref()
            .ok_or_else(|| refused("no original preparation"))?;
        check_input(prepared, context, request, &self.engine)?;
        if prepared.handled
            || prepared.cancellation.is_cancelled()
            || self.uncertain.load(Ordering::SeqCst)
        {
            return Err(refused(
                "original preparation is handled, cancelled or uncertain",
            ));
        }
        let verifier = prepared.verifier.clone();
        let scope = prepared.scope.clone();
        let inner = &mut self.inner;
        let result = verifier
            .with_original_pair(&self.session, |attestor, attested, control, original| {
                if original != scope.original_deadline || context.effective_deadline > original {
                    return Err(refused("original request ceiling differs"));
                }
                inner.preflight_attested_controlled(context, request, attestor, attested, control)
            })
            .map_err(approval_error)?;
        scope.current(&self.engine).map_err(runtime_error)?;
        context.remaining()?;
        if !matches!(result, Ok(None)) {
            scope.retired.store(true, Ordering::SeqCst);
        }
        result
    }

    /// Repeat original checks after the future product durability barrier.
    /// The owning binding stays Prepared/Handled until explicit retirement
    /// after the actual bridge final-forward post samples have finished.
    pub fn handle_original(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        if let Some(error) = self.preflight_original(context, request)? {
            return Ok(HandlerOutcome::Failure(error));
        }
        let prepared = self
            .prepared
            .as_ref()
            .ok_or_else(|| refused("no original preparation"))?;
        check_input(prepared, context, request, &self.engine)?;
        let verifier = prepared.verifier.clone();
        let scope = prepared.scope.clone();
        self.engine.service_current().map_err(runtime_error)?;
        {
            let mut registration = self
                .engine
                .registration
                .lock()
                .map_err(|_| refused("registration poisoned"))?;
            if registration.is_some() {
                return Err(refused("one registration is already pending"));
            }
            *registration = Some(ServiceRegistration {
                nonce: scope.nonce.clone(),
                scope: scope.clone(),
            });
        }
        scope.current(&self.engine).map_err(runtime_error)?;
        let mut guard = DispatchUnwind {
            engine: self.engine.clone(),
            scope: scope.clone(),
            uncertain: self.uncertain.clone(),
            armed: false,
        };
        let inner = &mut self.inner;
        let result =
            verifier.with_original_pair(&self.session, |attestor, attested, control, original| {
                if original != scope.original_deadline || context.effective_deadline > original {
                    return Err(refused("original request ceiling differs"));
                }
                guard.armed = true;
                inner.handle_attested_controlled(context, request, attestor, attested, control)
            });
        if let Some(prepared) = self.prepared.as_mut() {
            prepared.handled = true;
        }
        // The old actor has now retired its runtime token. The private wrapper
        // awaited while that token was live; this independent Core check uses
        // the exact original context and captured Source, never a new token.
        let post =
            await_final_forward(&self.engine, &scope, None, Some(context)).map_err(runtime_error);
        match (result, post) {
            (Ok(outcome), Ok(())) => {
                let known = match &outcome {
                    Ok(HandlerOutcome::Success(_)) => !self.inner.runtime_unavailable,
                    Ok(HandlerOutcome::Failure(error)) => {
                        !matches!(
                            error.code,
                            BrowserErrorCode::Indeterminate | BrowserErrorCode::BrowserCrashed
                        ) && !self.inner.runtime_unavailable
                    }
                    Err(_) => false,
                };
                if known {
                    guard.armed = false;
                }
                outcome
            }
            (Err(error), _) if !guard.armed => Err(approval_error(error)),
            (_, _) if !scope.runtime_started.load(Ordering::SeqCst) => {
                guard.armed = false;
                scope.retired.store(true, Ordering::SeqCst);
                Err(refused("original scope refused before runtime work"))
            }
            _ => Ok(HandlerOutcome::Failure(BrowserWireError {
                code: BrowserErrorCode::Indeterminate,
                message: "original scope retired after possible runtime dispatch".into(),
                details: None,
            })),
        }
    }

    pub fn cancel_prepared_request(&mut self) -> Result<(), AgentPortError> {
        self.ensure_current_service()?;
        if let Some(prepared) = &self.prepared {
            prepared.cancellation.cancel();
            prepared.scope.retired.store(true, Ordering::SeqCst);
            if prepared.scope.runtime_started.load(Ordering::SeqCst)
                && !prepared.scope.runtime_finished.load(Ordering::SeqCst)
            {
                self.uncertain.store(true, Ordering::SeqCst);
                self.engine.closed.store(true, Ordering::SeqCst);
            }
        }
        Ok(())
    }

    pub fn active_cancellation_token(&self) -> Result<Option<CancellationToken>, AgentPortError> {
        self.ensure_current_service()?;
        Ok(self.prepared.as_ref().map(|p| p.cancellation.clone()))
    }

    pub fn retire_prepared_request(&mut self) -> Result<(), AgentPortError> {
        // A retired/expired request is not a prerequisite of persistent Source
        // continuity. This check uses only the fixed original service session.
        self.engine.creator().map_err(runtime_error)?;
        self.session.ensure_current().map_err(approval_error)?;
        let Some(prepared) = self.prepared.as_ref() else {
            return Ok(());
        };
        if prepared.handled
            && prepared.scope.runtime_started.load(Ordering::SeqCst)
            && !prepared.scope.runtime_finished.load(Ordering::SeqCst)
            && !self.engine.closed.load(Ordering::SeqCst)
        {
            return Err(refused(
                "original binding must remain through bridge post samples",
            ));
        }
        prepared.cancellation.cancel();
        prepared.scope.retired.store(true, Ordering::SeqCst);
        self.inner
            .retire_prepared_request(&prepared.scope.request_id)?;
        self.session.ensure_current().map_err(approval_error)?;
        {
            let mut registration = self
                .engine
                .registration
                .lock()
                .map_err(|_| refused("registration poisoned"))?;
            if let Some(value) = registration.as_ref() {
                if !Arc::ptr_eq(&value.nonce, &prepared.scope.nonce) {
                    self.uncertain.store(true, Ordering::SeqCst);
                    self.engine.closed.store(true, Ordering::SeqCst);
                    return Err(refused("foreign registration cannot be cleared"));
                }
                registration.take();
            }
        }
        self.prepared.take();
        Ok(())
    }

    pub fn ensure_current_service(&self) -> Result<(), AgentPortError> {
        self.engine.creator().map_err(runtime_error)?;
        self.session.ensure_current().map_err(approval_error)?;
        let held = self
            .engine
            .session
            .get()
            .ok_or_else(|| refused("fixed session absent"))?;
        if !Arc::ptr_eq(held, &self.session) || self.engine.closed.load(Ordering::SeqCst) {
            return Err(refused("fixed service engine retired or substituted"));
        }
        Ok(())
    }

    pub fn principal(&self) -> Result<&TaskFlowPrincipal, AgentPortError> {
        self.ensure_current_service()?;
        Ok(self.inner.principal_binding().principal())
    }

    pub fn page_owner(&self) -> Result<Option<PageOwnerSnapshot>, AgentPortError> {
        self.ensure_current_service()?;
        let page = self.inner.page_owner();
        self.ensure_current_service()?;
        Ok(page)
    }
}

impl Drop for ServiceBrowserActorCore {
    fn drop(&mut self) {
        // Local denial and original action custody Drop, not Source retirement
        // or engine-object destruction. No Source query or registration lock.
        self.engine.closed.store(true, Ordering::SeqCst);
        if let Some(prepared) = self.prepared.as_ref() {
            prepared.cancellation.cancel();
            prepared.scope.retired.store(true, Ordering::SeqCst);
        }
    }
}

fn capture_original(
    engine: &Arc<ServiceEngineState>,
    session: &Arc<ApprovedServiceSessionVerifier>,
    binding: ApprovedServiceRequestBinding,
    context: &DispatchContext,
    request: &BrowserRequest,
    previous_principal: Option<&TaskFlowPrincipal>,
) -> Result<(PrincipalBinding, PreparedOriginal), AgentPortError> {
    engine.creator().map_err(runtime_error)?;
    session.ensure_current().map_err(approval_error)?;
    let (canonical, engine_canonical) = canonical_domains(context, request)?;
    let canonical_sha256 = crate::executable_sha256(&canonical);
    context.remaining()?;
    let (peer, snapshot, principal_id) = binding
        .verify_for_service(session)
        .map_err(approval_error)?;
    if peer != context.peer {
        return Err(refused("original Agent differs from context peer"));
    }
    let principal = TaskFlowPrincipal {
        principal_id,
        expected_uid: snapshot.uid,
        expected_gid: snapshot.gid,
        expected_systemd_unit: snapshot
            .systemd_unit
            .clone()
            .ok_or_else(|| refused("approved Agent unit absent"))?,
        expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
        expected_executable_sha256: snapshot.executable_sha256.clone(),
    };
    if previous_principal.is_some_and(|p| p != &principal) {
        return Err(refused(
            "same-source semantic or fixed mechanism principal changed",
        ));
    }
    let selected = PrincipalBinding::bind_attested(principal, peer, &snapshot)
        .map_err(|_| refused("genuine approved binding rejected"))?;
    let verifier = Arc::new(
        binding
            .verifier_for_service(session)
            .map_err(approval_error)?,
    );
    let original_deadline = verifier
        .with_original_pair(session, |_, _, _, original| {
            if context.effective_deadline > original {
                return Err(refused(
                    "caller deadline exceeds original Control/Agent ceiling",
                ));
            }
            Ok(original)
        })
        .map_err(approval_error)??;
    let scope = Arc::new(ServiceDispatchScope {
        engine: Arc::downgrade(engine),
        nonce: Arc::new(RegistrationNonce),
        session: session.clone(),
        request: verifier.clone(),
        request_id: request.request_id.clone(),
        original_deadline,
        dispatch_deadline: context.effective_deadline,
        shortened_deadline: OnceLock::new(),
        operation: request.operation.clone(),
        original_request: request.clone(),
        original_canonical: canonical,
        canonical_sha256,
        engine_canonical,
        runtime_started: AtomicBool::new(false),
        runtime_finished: AtomicBool::new(false),
        retired: AtomicBool::new(false),
    });
    binding
        .verify_for_service(session)
        .map_err(approval_error)?;
    session.ensure_current().map_err(approval_error)?;
    context.remaining()?;
    Ok((
        selected,
        PreparedOriginal {
            _binding: binding,
            verifier,
            scope,
            context: context.clone(),
            cancellation: CancellationToken::new(),
            handled: false,
        },
    ))
}

fn check_input(
    prepared: &PreparedOriginal,
    context: &DispatchContext,
    request: &BrowserRequest,
    engine: &Arc<ServiceEngineState>,
) -> Result<(), AgentPortError> {
    prepared.scope.current(engine).map_err(runtime_error)?;
    let canonical =
        encode_request(request).map_err(|_| refused("original canonical request invalid"))?;
    let original = &prepared.context;
    if canonical != prepared.scope.original_canonical
        || crate::executable_sha256(&canonical) != prepared.scope.canonical_sha256
        || context.peer != original.peer
        || context.transport_sequence != original.transport_sequence
        || context.canonical_request_sha256 != original.canonical_request_sha256
        || context.effect_class != original.effect_class
        || context.accepted_at != original.accepted_at
        || context.effective_deadline != original.effective_deadline
    {
        return Err(refused(
            "prepared whole request or exact captured context changed",
        ));
    }
    context.remaining()?;
    Ok(())
}

fn refused(message: &str) -> AgentPortError {
    AgentPortError::Handler(message.into())
}
fn runtime_error(_: RuntimeFailure) -> AgentPortError {
    refused("service runtime original proof refused")
}
fn approval_error(_: hepta_peer_attestation::ApprovedPolicyError) -> AgentPortError {
    refused("genuine service original proof refused")
}

fn canonical_domains(
    context: &DispatchContext,
    request: &BrowserRequest,
) -> Result<(Vec<u8>, Vec<u8>), AgentPortError> {
    closed_operation(&request.operation).map_err(runtime_error)?;
    if matches!(&request.operation, BrowserOperation::SessionCreate { ui_mode, .. } if ui_mode != "headed")
    {
        return Err(refused(
            "closed service Create requires the exact admitted headed mode",
        ));
    }
    let canonical =
        encode_request(request).map_err(|_| refused("original canonical request invalid"))?;
    if crate::executable_sha256(&canonical) != context.canonical_request_sha256
        || request.effect_class() != context.effect_class
        || context.accepted_at > Instant::now()
        || context.accepted_at >= context.effective_deadline
    {
        return Err(refused(
            "canonical whole request or caller context range differs",
        ));
    }
    context.remaining()?;
    let mut runtime_request = request.clone();
    // Exact closed projection used by the old EngineThreadRuntime: only the
    // wall-clock wire field disappears. Create was strictly admitted headed.
    runtime_request.deadline_unix_ms = None;
    let engine =
        encode_request(&runtime_request).map_err(|_| refused("runtime envelope invalid"))?;
    Ok((canonical, engine))
}

#[cfg(test)]
mod tests {
    use super::*;
    use hepta_agent_transport::PeerIdentity;
    use hepta_browser_codec::{EffectClass, ProfilePersistence, ProfileSpec};

    // Pure correspondence fixtures, without a forged P1 Binding or Source.
    fn request() -> BrowserRequest {
        BrowserRequest {
            request_id: "closed-create".into(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: Some(1234),
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: "immutable-read-only-v1".into(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".into(),
            },
        }
    }

    fn context(request: &BrowserRequest) -> DispatchContext {
        let now = Instant::now();
        DispatchContext {
            peer: PeerIdentity {
                pid: Some(std::process::id()),
                uid: 1,
                gid: 1,
            },
            transport_sequence: 1,
            canonical_request_sha256: crate::executable_sha256(&encode_request(request).unwrap()),
            effect_class: request.effect_class(),
            accepted_at: now,
            effective_deadline: now + std::time::Duration::from_secs(1),
        }
    }

    #[test]
    fn original_and_runtime_domains_keep_exact_wall_clock_difference() {
        let original = request();
        let context = context(&original);
        let (wire, runtime) = canonical_domains(&context, &original).unwrap();
        assert_eq!(wire, encode_request(&original).unwrap());
        let mut expected = original.clone();
        expected.deadline_unix_ms = None;
        assert_eq!(runtime, encode_request(&expected).unwrap());
        assert_ne!(wire, runtime);
    }

    #[test]
    fn create_other_mode_refuses_instead_of_normalizing_original_container() {
        let mut original = request();
        let context = context(&original);
        if let BrowserOperation::SessionCreate { ui_mode, .. } = &mut original.operation {
            *ui_mode = "headless".into();
        }
        assert!(encode_request(&original).is_err());
        assert!(canonical_domains(&context, &original).is_err());
    }

    #[test]
    fn canonical_hash_covers_entire_original_wall_clock_and_identifier() {
        let original = request();
        let context = context(&original);
        let mut changed = original.clone();
        changed.deadline_unix_ms = Some(1235);
        assert!(canonical_domains(&context, &changed).is_err());
        changed = original.clone();
        changed.request_id = "different".into();
        assert!(canonical_domains(&context, &changed).is_err());
    }

    #[test]
    fn effect_class_and_future_caller_context_are_not_accepted_as_proof() {
        let original = request();
        let mut changed = context(&original);
        changed.effect_class = EffectClass::PotentialExternalEffect;
        assert!(canonical_domains(&changed, &original).is_err());
        changed = context(&original);
        changed.accepted_at = changed.effective_deadline;
        assert!(canonical_domains(&changed, &original).is_err());
    }

    #[test]
    fn expired_context_refuses_without_new_clock_or_native_work() {
        let original = request();
        let mut changed = context(&original);
        changed.effective_deadline = changed.accepted_at;
        assert!(canonical_domains(&changed, &original).is_err());
    }
}
