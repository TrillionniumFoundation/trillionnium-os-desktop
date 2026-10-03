//! Nongeneric actual original wire/product owner. No weaker public handler.
use super::*;
use report::ReportOriginalOwners;

/// Own one genuine persistent Requests, fixed typed endpoint and managed writer.
/// This local Source factory does not approve the installed storage namespace,
/// supply a Servo embedder or activate the default daemon.
///
/// ```compile_fail,E0616
/// use hepta_browserd::ApprovedServiceProductCoordinator;
/// fn raw(c: ApprovedServiceProductCoordinator) { let _ = c.requests; }
/// ```
/// ```compile_fail,E0277
/// use hepta_browserd::ApprovedServiceProductCoordinator;
/// use hepta_agent_port::BrowserRequestHandler;
/// fn weaker<T: BrowserRequestHandler>() {}
/// fn escape() { weaker::<ApprovedServiceProductCoordinator>(); }
/// ```
/// ```compile_fail,E0277
/// use hepta_browserd::ApprovedServiceProductCoordinator;
/// fn clone_required<T: Clone>() {}
/// fn duplicate() { clone_required::<ApprovedServiceProductCoordinator>(); }
/// ```
pub struct ApprovedServiceProductCoordinator {
    requests: Option<ApprovedServiceRequests>,
    session: ApprovedServiceSessionVerifier,
    endpoint: Option<ServiceServoRuntimeEndpoint>,
    actor: Option<ServiceServoBrowserActor>,
    lifecycle: Option<ServiceManagedLifecycle>,
    worker: Option<ServiceReportWorker>,
    phase: ServiceProductPhase,
    quarantine: Arc<AtomicBool>,
}

/// Diagnostic result from one actual original invocation. No raw receipt seal.
///
/// ```compile_fail,E0616
/// use hepta_browserd::ServiceRetainedObservation;
/// fn forge(o: ServiceRetainedObservation) { let _ = o.deadline; }
/// ```
/// ```compile_fail,E0432
/// use hepta_browserd::ServiceTerminalSeal;
/// ```
pub struct ServiceRetainedObservation {
    deadline: Instant,
    service: Result<ServiceEvidence, ProductDispatchError>,
    report: Result<ServiceReportObservation, ProductDispatchError>,
    phase: ServiceProductPhase,
}

struct ReceivedProductInput {
    stream: UnixStream,
    deadline: Instant,
    custody: ControlRequestCustody,
    reporter: ApprovedServiceRetainedReporter,
    binding: ApprovedServiceRequestBinding,
    principal: String,
}

struct PipelineTrace {
    invocation: Option<JournalInvocation>,
    seal: Option<ServiceTerminalSeal>,
    physical_write_return: bool,
}

impl ApprovedServiceProductCoordinator {
    pub fn from_owner(
        owner: ApprovedServiceOwnerBinding,
        endpoint: ServiceServoRuntimeEndpoint,
        journal: ReceiptJournal,
        image_id: String,
    ) -> Result<Self, ProductDispatchError> {
        owner
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let requests = ApprovedServiceRequests::from_owner(owner)
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let session = requests
            .session_verifier()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let lifecycle_session = requests
            .session_verifier()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let lifecycle = ServiceManagedLifecycle::new(journal, lifecycle_session, image_id)?;
        requests
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        Ok(Self {
            requests: Some(requests),
            session,
            endpoint: Some(endpoint),
            actor: None,
            lifecycle: Some(lifecycle),
            worker: None,
            phase: ServiceProductPhase::Idle,
            quarantine: Arc::new(AtomicBool::new(false)),
        })
    }

    pub fn serve_original_control(
        &mut self,
        connection: RootPathControlConnection,
        expected_agent_path: &Path,
    ) -> Result<ServiceRetainedObservation, ProductDispatchError> {
        self.ensure_current_service()?;
        if self.phase != ServiceProductPhase::Idle
            || self.worker.is_some()
            || self.quarantine.load(Ordering::SeqCst)
        {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        if let Err(error) = self
            .lifecycle
            .as_mut()
            .ok_or(ProductDispatchError::Closed)?
            .idle_current()
        {
            self.quarantine_same_chain();
            return Err(error);
        }
        let received = self
            .requests
            .as_mut()
            .ok_or(ProductDispatchError::Closed)?
            .bind_control(connection, expected_agent_path)
            .map_err(|_| ProductDispatchError::PeerRefused)?
            .receive_request()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let deadline = received
            .original_deadline()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        self.phase = ServiceProductPhase::Active;
        let nonce = Arc::new(InvocationNonce);
        let cancellation = Arc::new(ServiceCancellationLatch::new());
        let mut guard = InvocationUnwind {
            quarantine: self.quarantine.clone(),
            cancellation: cancellation.clone(),
            armed: true,
        };
        let mut observation = None;
        let post = received.consume_with_request_binding(
            |stream, deadline, custody, reporter, attested, principal, binding| {
                // P1's selected Binding, not this additional readonly snapshot,
                // continues to own the original Agent action incarnation.
                drop(attested);
                observation = Some(self.serve_received(
                    ReceivedProductInput {
                        stream,
                        deadline,
                        custody,
                        reporter,
                        binding,
                        principal: principal.to_owned(),
                    },
                    nonce,
                    cancellation,
                ));
            },
        );
        let mut result = match observation {
            Some(Ok(result)) => result,
            Some(Err(error)) => {
                self.quarantine_same_chain();
                return Err(error);
            }
            None => {
                self.quarantine_same_chain();
                return Err(ProductDispatchError::PeerRefused);
            }
        };
        if post.is_err() || self.ensure_current_service().is_err() {
            self.quarantine_same_chain();
            result.service = Err(ProductDispatchError::PeerRefused);
        }
        if self.quarantine.load(Ordering::SeqCst) {
            self.phase = ServiceProductPhase::Quarantined;
        } else {
            if let Err(error) = self
                .lifecycle
                .as_mut()
                .ok_or(ProductDispatchError::Closed)?
                .idle_current()
            {
                self.quarantine_same_chain();
                return Err(error);
            }
            if self.worker.is_some() {
                self.quarantine_same_chain();
            }
            if !self.quarantine.load(Ordering::SeqCst) {
                self.phase = ServiceProductPhase::Idle;
            }
        }
        result.deadline = deadline;
        result.phase = self.phase;
        // This only disarms the local unwind guard. Quarantine cannot be cleared.
        guard.armed = false;
        Ok(result)
    }

    pub fn ensure_current_service(&self) -> Result<(), ProductDispatchError> {
        // Actual P1 creator/namespace precedes any mutable/private access.
        self.session.ensure_current().map_err(|_| {
            self.quarantine.store(true, Ordering::SeqCst);
            ProductDispatchError::PeerRefused
        })?;
        self.requests
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .ensure_current()
            .map_err(|_| {
                self.quarantine.store(true, Ordering::SeqCst);
                ProductDispatchError::PeerRefused
            })?;
        if let Some(actor) = &self.actor {
            actor.ensure_current_service().map_err(|error| {
                self.quarantine.store(true, Ordering::SeqCst);
                port_error(error)
            })?;
        }
        Ok(())
    }

    pub fn phase(&self) -> Result<ServiceProductPhase, ProductDispatchError> {
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        Ok(if self.phase == ServiceProductPhase::Closed {
            ServiceProductPhase::Closed
        } else if self.quarantine.load(Ordering::SeqCst) {
            ServiceProductPhase::Quarantined
        } else {
            self.phase
        })
    }

    pub fn retire(&mut self) -> Result<(), ProductDispatchError> {
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        self.quarantine.store(true, Ordering::SeqCst);
        self.phase = ServiceProductPhase::Closed;
        if let Some(actor) = &mut self.actor {
            actor.cancel_prepared_request().map_err(port_error)?;
        }
        self.requests.take();
        // No join, reopening, writer extraction or claim all native work ended.
        Ok(())
    }

    fn serve_received(
        &mut self,
        input: ReceivedProductInput,
        nonce: Arc<InvocationNonce>,
        cancellation: Arc<ServiceCancellationLatch>,
    ) -> Result<ServiceRetainedObservation, ProductDispatchError> {
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let (peer, _, principal) = input
            .binding
            .verify_for_service(&self.session)
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        if principal != input.principal {
            return Err(ProductDispatchError::PeerRefused);
        }
        let verifier = input
            .binding
            .verifier_for_service(&self.session)
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        original_current(&verifier, &self.session, input.deadline)?;
        let wake = OriginalConnectedDenial::capture_original(&input.stream)
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        original_current(&verifier, &self.session, input.deadline)?;
        let requests = self.requests.as_ref().ok_or(ProductDispatchError::Closed)?;
        let worker_session = requests
            .session_verifier()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let report_session = requests
            .session_verifier()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let writer = self
            .lifecycle
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .writer_identity();
        self.worker = Some(ServiceReportWorker::spawn(
            ReportOriginalOwners {
                reporter: input.reporter,
                custody: input.custody,
                wake,
                session: worker_session,
                nonce: nonce.clone(),
                writer,
                deadline: input.deadline,
                cancellation: cancellation.clone(),
            },
            report_session,
        )?);
        let mut trace = PipelineTrace {
            invocation: None,
            seal: None,
            physical_write_return: false,
        };
        let service = self.process_wire(
            input.stream,
            input.binding,
            &verifier,
            peer,
            (&principal, input.deadline, nonce, cancellation),
            &mut trace,
        );
        if service.is_err() {
            if trace.physical_write_return {
                self.quarantine_same_chain();
            }
            if let Some(invocation) = trace.invocation.as_mut() {
                if invocation.dispatched || invocation.may_dispatch {
                    self.quarantine_same_chain();
                }
                if invocation.terminal.is_none() {
                    match self
                        .lifecycle
                        .as_mut()
                        .ok_or(ProductDispatchError::Closed)?
                        .interrupted(invocation)
                    {
                        Ok(seal) => trace.seal = seal,
                        Err(_) => self.quarantine_same_chain(),
                    }
                }
            }
        }
        // Report publication revokes action and therefore follows original wire
        // post and owning A retirement. It can never race ahead of the response.
        if let Some(actor) = &mut self.actor {
            if actor.retire_prepared_request().is_err() {
                self.quarantine_same_chain();
                // No terminal report can revoke custody before owning A has
                // actually retired after the original bridge post.
                trace.seal.take();
            }
        } else if self.endpoint.is_none() {
            self.quarantine_same_chain();
        }
        let report = self
            .worker
            .as_mut()
            .ok_or(ProductDispatchError::Closed)?
            .finish(trace.seal.take());
        if report.is_ok() {
            self.worker.take();
        } else {
            self.quarantine_same_chain();
        }
        if let Some(invocation) = &trace.invocation
            && self
                .lifecycle
                .as_mut()
                .ok_or(ProductDispatchError::Closed)?
                .finish(invocation)
                .is_err()
        {
            self.quarantine_same_chain();
        }
        if self
            .actor
            .as_ref()
            .is_some_and(|actor| actor.ensure_current_service().is_err())
        {
            self.quarantine_same_chain();
        }
        Ok(ServiceRetainedObservation {
            deadline: input.deadline,
            service,
            report,
            phase: self.phase,
        })
    }

    fn process_wire(
        &mut self,
        stream: UnixStream,
        binding: ApprovedServiceRequestBinding,
        verifier: &ApprovedServiceRequestVerifier,
        peer: PeerIdentity,
        original: (
            &str,
            Instant,
            Arc<InvocationNonce>,
            Arc<ServiceCancellationLatch>,
        ),
        trace: &mut PipelineTrace,
    ) -> Result<ServiceEvidence, ProductDispatchError> {
        let (principal, deadline, nonce, cancellation) = original;
        let (mut wire, decoded) =
            OriginalServiceWire::receive_original(stream, deadline, peer, verifier, &self.session)?;
        cancellation.current()?;
        original_current(verifier, &self.session, decoded.context.effective_deadline)?;
        if let Some(actor) = &mut self.actor {
            let token = actor
                .prepare_original_request(binding, &decoded.context, &decoded.request)
                .map_err(port_error)?;
            cancellation.install(token)?;
        } else {
            let actor_session = self
                .requests
                .as_ref()
                .ok_or(ProductDispatchError::Closed)?
                .session_verifier()
                .map_err(|_| ProductDispatchError::PeerRefused)?;
            let endpoint = self.endpoint.take().ok_or(ProductDispatchError::Closed)?;
            let actor = ServiceServoBrowserActor::from_original_request(
                endpoint,
                actor_session,
                binding,
                &decoded.context,
                &decoded.request,
            )
            .map_err(port_error)?;
            let token = actor
                .active_cancellation_token()
                .map_err(port_error)?
                .ok_or(ProductDispatchError::Closed)?;
            self.actor = Some(actor);
            cancellation.install(token)?;
        }
        let actor = self.actor.as_mut().ok_or(ProductDispatchError::Closed)?;
        if actor.principal().map_err(port_error)?.principal_id != principal {
            return Err(ProductDispatchError::PeerRefused);
        }
        let mut refusal = actor
            .preflight_original(&decoded.context, &decoded.request)
            .map_err(port_error)?;
        if refusal.is_none()
            && self
                .lifecycle
                .as_mut()
                .ok_or(ProductDispatchError::Closed)?
                .duplicate(&decoded.request.request_id)?
        {
            refusal = Some(BrowserWireError {
                code: BrowserErrorCode::PolicyDenied,
                message: "request identity is already recorded".to_owned(),
                details: None,
            });
        }
        if let Some(error) = refusal {
            let response = wire::prepare_response(&decoded.request, HandlerOutcome::Failure(error))
                .map_err(port_error)?;
            let published = wire.publish_original(&decoded, response, verifier, &self.session);
            trace.physical_write_return = published.physical_write_return;
            return published.result;
        }
        original_current(verifier, &self.session, decoded.context.effective_deadline)?;
        cancellation.current()?;
        let page = actor.page_owner().map_err(port_error)?;
        let lifecycle = self
            .lifecycle
            .as_mut()
            .ok_or(ProductDispatchError::Closed)?;
        trace.invocation = Some(lifecycle.begin(nonce, deadline, &decoded, page, principal)?);
        let invocation = trace
            .invocation
            .as_mut()
            .ok_or(ProductDispatchError::Closed)?;
        original_current(verifier, &self.session, decoded.context.effective_deadline)?;
        cancellation.current()?;
        lifecycle.requested(invocation)?;
        original_current(verifier, &self.session, decoded.context.effective_deadline)?;
        cancellation.current()?;
        lifecycle.dispatched(invocation)?;
        original_current(verifier, &self.session, decoded.context.effective_deadline)?;
        cancellation.current()?;
        invocation.may_dispatch = true;
        let outcome = actor
            .handle_original(&decoded.context, &decoded.request)
            .map_err(port_error)?;
        original_current(verifier, &self.session, decoded.context.effective_deadline)?;
        let response = wire::prepare_response(&decoded.request, outcome).map_err(port_error)?;
        original_current(verifier, &self.session, decoded.context.effective_deadline)?;
        trace.seal = Some(lifecycle.completed(invocation, &response)?);
        original_current(verifier, &self.session, decoded.context.effective_deadline)?;
        let published = wire.publish_original(&decoded, response, verifier, &self.session);
        trace.physical_write_return = published.physical_write_return;
        published.result
    }

    fn quarantine_same_chain(&mut self) {
        self.quarantine.store(true, Ordering::SeqCst);
        self.phase = ServiceProductPhase::Quarantined;
    }
}

impl ServiceRetainedObservation {
    pub fn original_deadline(&self) -> Instant {
        self.deadline
    }
    pub fn service(&self) -> &Result<ServiceEvidence, ProductDispatchError> {
        &self.service
    }
    pub fn report(&self) -> &Result<ServiceReportObservation, ProductDispatchError> {
        &self.report
    }
    pub fn phase(&self) -> ServiceProductPhase {
        self.phase
    }
}

impl Drop for ApprovedServiceProductCoordinator {
    fn drop(&mut self) {
        self.quarantine.store(true, Ordering::SeqCst);
        if self.session.ensure_current().is_err() {
            std::mem::forget(self.actor.take());
            std::mem::forget(self.endpoint.take());
            std::mem::forget(self.lifecycle.take());
            std::mem::forget(self.worker.take());
            std::mem::forget(self.requests.take());
        }
        // Normal creator cleanup drops original custody; never joins a worker.
    }
}
