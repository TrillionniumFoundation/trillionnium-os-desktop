//! Thin original-request facade. The simulation Core owns all private engine
//! registration and canonical proofs; no raw actor or weaker handler escapes.
use super::*;
use hepta_peer_attestation::{ApprovedServiceRequestBinding, ApprovedServiceSessionVerifier};
use simulation::ServiceBrowserActorCore;

/// Concrete typed original-request actor. No supplied runtime or profile,
/// journal/factory activation or first-request lifetime is accepted.
///
/// ```compile_fail,E0616
/// use hepta_browser_actor::ServiceServoBrowserActor;
/// fn raw(actor: ServiceServoBrowserActor) { let _ = actor.inner; }
/// ```
/// ```compile_fail,E0277
/// use hepta_agent_port::BrowserRequestHandler;
/// use hepta_browser_actor::ServiceServoBrowserActor;
/// fn weak<T: BrowserRequestHandler>() {}
/// fn escape() { weak::<ServiceServoBrowserActor>(); }
/// ```
pub struct ServiceServoBrowserActor {
    inner: ServiceBrowserActorCore,
}

impl ServiceServoBrowserActor {
    pub fn from_original_request(
        mut endpoint: ServiceServoRuntimeEndpoint,
        session: ApprovedServiceSessionVerifier,
        binding: ApprovedServiceRequestBinding,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<Self, AgentPortError> {
        let endpoint = endpoint
            .inner
            .take()
            .ok_or_else(|| AgentPortError::Handler("typed endpoint consumed".into()))?;
        ServiceBrowserActorCore::from_original_request(endpoint, session, binding, context, request)
            .map(|inner| Self { inner })
    }

    pub fn prepare_original_request(
        &mut self,
        binding: ApprovedServiceRequestBinding,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<CancellationToken, AgentPortError> {
        self.inner
            .prepare_original_request(binding, context, request)
    }

    pub fn preflight_original(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<Option<BrowserWireError>, AgentPortError> {
        self.inner.preflight_original(context, request)
    }

    pub fn handle_original(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        self.inner.handle_original(context, request)
    }

    pub fn cancel_prepared_request(&mut self) -> Result<(), AgentPortError> {
        self.inner.cancel_prepared_request()
    }

    pub fn active_cancellation_token(&self) -> Result<Option<CancellationToken>, AgentPortError> {
        self.inner.active_cancellation_token()
    }

    pub fn retire_prepared_request(&mut self) -> Result<(), AgentPortError> {
        self.inner.retire_prepared_request()
    }

    pub fn ensure_current_service(&self) -> Result<(), AgentPortError> {
        self.inner.ensure_current_service()
    }

    pub fn principal(&self) -> Result<&TaskFlowPrincipal, AgentPortError> {
        self.inner.principal()
    }

    pub fn page_owner(&self) -> Result<Option<PageOwnerSnapshot>, AgentPortError> {
        self.inner.page_owner()
    }
}
