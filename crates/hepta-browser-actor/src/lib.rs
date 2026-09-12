#![forbid(unsafe_code)]

//! Product-facing BrowserActor authority boundary.
//!
//! Construction and every request require an opaque, pidfd-backed
//! [`AttestedPeer`]. S06 deliberately exposes no caller-supplied runtime trait,
//! runtime value, generic actor parameter, ordinary handler, listener, or
//! installable binary. A future Servo adapter must be introduced as a distinct
//! concrete reviewed product type in a later gate.
//!
//! Caller-constructed principal/mechanism bindings are not part of this API:
//!
//! ```compile_fail
//! use hepta_browser_actor::PrincipalBinding;
//! ```
//!
//! Raw session-state synthesis is not part of the product API. If both the
//! generic event type and the untrusted mutator were ever reintroduced, this
//! compile-fail guard would unexpectedly compile:
//!
//! ```compile_fail
//! use hepta_browser_actor::{BrowserActor, SessionEvent};
//! fn forge_state(actor: &mut BrowserActor, event: SessionEvent) {
//!     actor.apply_session_event(event, 0).unwrap();
//! }
//! ```
//!
//! Arbitrary runtime injection is not representable:
//!
//! ```compile_fail
//! use hepta_browser_actor::BrowserActor;
//! struct ForgedRuntime;
//! fn accepts_forged_runtime(_: BrowserActor<ForgedRuntime>) {}
//! ```
//!
//! The product actor deliberately does not implement the ordinary, weaker
//! `BrowserRequestHandler` compatibility trait:
//!
//! ```compile_fail
//! use hepta_agent_port::BrowserRequestHandler;
//! use hepta_browser_actor::BrowserActor;
//! fn require_ordinary_handler<T: BrowserRequestHandler>() {}
//! require_ordinary_handler::<BrowserActor>();
//! ```

use hepta_browser_actor_simulation as simulation;

mod servo_runtime;

pub use servo_runtime::{
    ServoBrowserActor, ServoCompletionDelivery, ServoEventLoopWaker, ServoPumpResult,
    ServoRuntimeCommand, ServoRuntimeCompletion, ServoRuntimeEndpoint, ServoRuntimeError,
    ServoRuntimeOperation, ServoRuntimeOwner, servo_runtime_pair,
};

pub use hepta_agent_port::{AgentPortError, DispatchContext, HandlerOutcome};
pub use hepta_agent_transport::PeerIdentity;
pub use hepta_browser_codec::{
    BrowserRequest, BrowserResponse, ElementReference, JsonObject, JsonValue, NavigationTarget,
    ObservationField, PageAction, ProfilePersistence, ProfileSpec, WaitCondition,
};
pub use hepta_peer_attestation::{AttestedPeer, ProcfsPeerAttestor};
pub use hepta_session_core::ReceiptJournal;
pub use simulation::{
    CancellationToken, PageOwnerSnapshot, ReceiptLifecycleObserver, TaskFlowPrincipal,
    executable_sha256, scoped_frame_id,
};

/// The only S06 product-facing BrowserActor.
///
/// The actor owns the only runtime type admitted by this source gate. Callers
/// cannot supply a trait implementation that ignores request custody or starts
/// deferred work after a terminal result. The deterministic runtime has no
/// external-network/effect authority; later engine adapters require a separate
/// concrete type, review, and promotion gate.
pub struct BrowserActor {
    inner: simulation::BrowserActor<simulation::DeterministicLocalRuntime>,
}

impl BrowserActor {
    /// Construct an actor from a live opaque attestation object.
    ///
    /// A caller-provided PID/UID/GID tuple alone is insufficient. The attested
    /// process start time, cgroup, systemd unit, and executable digest are read
    /// from the attestor-selected source and bound into the private mechanism.
    /// The local runtime is created inside the actor and cannot be substituted.
    pub fn from_attested(
        principal: TaskFlowPrincipal,
        peer: PeerIdentity,
        attestor: &ProcfsPeerAttestor,
        attested: &AttestedPeer,
    ) -> Result<Self, AgentPortError> {
        let snapshot = attested.refresh_snapshot(attestor).map_err(|error| {
            AgentPortError::Handler(format!("peer attestation refresh failed: {error}"))
        })?;
        let binding = simulation::PrincipalBinding::bind_attested(principal, peer, &snapshot)
            .map_err(|error| {
                AgentPortError::Handler(format!("principal binding failed: {error}"))
            })?;
        Ok(Self {
            inner: simulation::BrowserActor::new(
                binding,
                simulation::DeterministicLocalRuntime::default(),
            ),
        })
    }

    /// Dispatch exactly one request while retaining request-scoped peer custody.
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

    /// Return the bounded current PageOwner snapshot, if a session exists.
    pub fn page_owner(&self) -> Option<PageOwnerSnapshot> {
        self.inner.page_owner()
    }

    /// Request cancellation for one actor-owned request identity.
    pub fn cancel_request(&mut self, request_id: impl Into<String>) {
        self.inner.cancel_request(request_id);
    }

    /// Create or retrieve the shared cancellation token for one request.
    pub fn cancellation_token(&mut self, request_id: impl Into<String>) -> CancellationToken {
        self.inner.cancellation_token(request_id)
    }

    /// Return an existing active cancellation token without creating authority.
    pub fn active_cancellation_token(&self, request_id: &str) -> Option<CancellationToken> {
        self.inner.active_cancellation_token(request_id)
    }

    /// Create a receipt observer. Receipt facts never authorize execution.
    pub fn receipt_observer(
        &self,
        journal: ReceiptJournal,
        image_id: impl Into<String>,
    ) -> ReceiptLifecycleObserver {
        self.inner.receipt_observer(journal, image_id)
    }
}
