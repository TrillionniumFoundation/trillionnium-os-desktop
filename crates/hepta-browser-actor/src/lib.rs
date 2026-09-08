#![forbid(unsafe_code)]

//! Product-facing BrowserActor authority boundary.
//!
//! Construction and every request require an opaque, pidfd-backed
//! [`AttestedPeer`]. The large mechanism and fault-injection corpus lives in an
//! implementation crate that is intentionally not re-exported.
//!
//! Caller-constructed principal/mechanism bindings are not part of this API:
//!
//! ```compile_fail
//! use hepta_browser_actor::PrincipalBinding;
//! ```
//!
//! The product actor deliberately does not implement the ordinary, weaker
//! `BrowserRequestHandler` compatibility trait:
//!
//! ```compile_fail
//! use hepta_agent_port::BrowserRequestHandler;
//! use hepta_browser_actor::{BrowserActor, DeterministicLocalRuntime};
//! fn require_ordinary_handler<T: BrowserRequestHandler>() {}
//! require_ordinary_handler::<BrowserActor<DeterministicLocalRuntime>>();
//! ```

use hepta_browser_actor_simulation as simulation;

pub use hepta_agent_port::{AgentPortError, DispatchContext, HandlerOutcome};
pub use hepta_agent_transport::PeerIdentity;
pub use hepta_browser_codec::{
    BrowserRequest, BrowserResponse, ElementReference, JsonObject, JsonValue, NavigationTarget,
    ObservationField, PageAction, ProfilePersistence, ProfileSpec, WaitCondition,
};
pub use hepta_peer_attestation::{AttestedPeer, ProcfsPeerAttestor};
pub use hepta_session_core::{ReceiptJournal, SessionEvent, TransitionError};
pub use simulation::{
    BrowserActorMessage, CancellationToken, DeterministicLocalRuntime, PageOwnerSnapshot,
    PageRuntime, ReceiptLifecycleObserver, RequestControl, RuntimeFailure, RuntimeReply,
    TaskFlowPrincipal, executable_sha256, scoped_frame_id,
};

/// The only product-facing BrowserActor.
///
/// Its internal mechanism cannot be extracted, and there is no ordinary
/// `handle` entry point. Each request enters through [`Self::handle_attested`],
/// where the peer snapshot is refreshed and request-scoped custody is retained
/// across runtime dispatch and terminal result classification.
pub struct BrowserActor<R: PageRuntime> {
    inner: simulation::BrowserActor<R>,
}

impl<R: PageRuntime> BrowserActor<R> {
    /// Construct an actor from a live opaque attestation object.
    ///
    /// A caller-provided PID/UID/GID tuple alone is insufficient. The attested
    /// process start time, cgroup, systemd unit, and executable digest are read
    /// from the attestor-selected source and bound into the private mechanism.
    pub fn from_attested(
        principal: TaskFlowPrincipal,
        peer: PeerIdentity,
        attestor: &ProcfsPeerAttestor,
        attested: &AttestedPeer,
        runtime: R,
    ) -> Result<Self, AgentPortError> {
        let snapshot = attested.refresh_snapshot(attestor).map_err(|error| {
            AgentPortError::Handler(format!("peer attestation refresh failed: {error}"))
        })?;
        let binding = simulation::PrincipalBinding::bind_attested(principal, peer, &snapshot)
            .map_err(|error| {
                AgentPortError::Handler(format!("principal binding failed: {error}"))
            })?;
        Ok(Self {
            inner: simulation::BrowserActor::new(binding, runtime),
        })
    }

    /// Dispatch exactly one request while retaining request-scoped peer custody.
    ///
    /// The internal actor refreshes the same attestation source, verifies
    /// process-start/cgroup/unit/executable continuity, mints a non-cloneable
    /// custody owner, propagates its verifier through queued runtime controls,
    /// and refuses or marks indeterminate any result after custody revocation.
    pub fn handle_attested(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        attestor: &ProcfsPeerAttestor,
        attested: &AttestedPeer,
    ) -> Result<HandlerOutcome, AgentPortError> {
        self.inner
            .handle_attested(context, request, attestor, attested)
    }

    /// Return the semantic principal; mechanism identity remains private.
    pub fn principal(&self) -> &TaskFlowPrincipal {
        self.inner.principal_binding().principal()
    }

    pub fn page_owner(&self) -> Option<PageOwnerSnapshot> {
        self.inner.page_owner()
    }

    pub fn cancel_request(&mut self, request_id: impl Into<String>) {
        self.inner.cancel_request(request_id);
    }

    pub fn cancellation_token(&mut self, request_id: impl Into<String>) -> CancellationToken {
        self.inner.cancellation_token(request_id)
    }

    pub fn active_cancellation_token(&self, request_id: &str) -> Option<CancellationToken> {
        self.inner.active_cancellation_token(request_id)
    }

    pub fn apply_session_event(
        &mut self,
        event: SessionEvent,
        now_ms: u64,
    ) -> Result<(), TransitionError> {
        self.inner.apply_session_event(event, now_ms)
    }

    pub fn receipt_observer(
        &self,
        journal: ReceiptJournal,
        image_id: impl Into<String>,
    ) -> ReceiptLifecycleObserver {
        self.inner.receipt_observer(journal, image_id)
    }
}
