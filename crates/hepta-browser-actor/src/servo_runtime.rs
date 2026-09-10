//! Concrete, callback-driven Servo adapter boundary for the product BrowserActor.
//!
//! This module deliberately does not expose the generic simulation runtime
//! trait.  The actor endpoint and the engine owner are created as one pair on
//! the native event-loop thread.  The endpoint may move to the Agent/actor
//! worker; the owner is `!Send`/`!Sync` and must be pumped on the creator
//! thread.  The owner yields one typed [`ServoRuntimeCommand`] at a time and a
//! single-use completion token.  A Servo embedder must retain and revalidate
//! its engine-owned node before completing a semantic action.
//!
//! Creating this bridge is not evidence that Servo is installed or running.
//! That claim requires the exact-pin S08 qualification workflow and its real
//! upstream adapter.  No listener, external navigation, capability grant,
//! automatic replay, hardware, signing, or release authority is introduced.

use std::cell::RefCell;
use std::rc::Rc;
use std::sync::Arc;
use std::time::{Duration, Instant};

use hepta_agent_port::{AgentPortError, DispatchContext, HandlerOutcome};
use hepta_agent_transport::PeerIdentity;
use hepta_browser_actor_simulation as simulation;
use hepta_browser_codec::{
    BrowserRequest, ElementReference, JsonObject, ObservationField, PageAction, ProfileSpec,
    WaitCondition,
};
use hepta_peer_attestation::{AttestedPeer, ProcfsPeerAttestor};
use hepta_session_core::ReceiptJournal;

use simulation::engine_dispatch::event_loop::{
    CallbackEngineOwner, CallbackPageRuntime, CallbackPumpResult, CompletionDelivery,
    EngineCompletion, callback_engine_pair,
};
use simulation::{
    BrowserActorMessage, CancellationToken, PageOwnerSnapshot, ReceiptLifecycleObserver,
    RuntimeFailure, RuntimeReply, TaskFlowPrincipal,
};

/// Wake the native Servo event loop after a request or completion transition.
/// Implementations must be nonblocking and must not recursively pump Servo.
pub trait ServoEventLoopWaker: Send + Sync {
    fn wake(&self);
}

impl<F: Fn() + Send + Sync> ServoEventLoopWaker for F {
    fn wake(&self) {
        self();
    }
}

struct ServoWakerAdapter(Arc<dyn ServoEventLoopWaker>);

impl simulation::engine_dispatch::EngineEventLoopWaker for ServoWakerAdapter {
    fn wake(&self) {
        self.0.wake();
    }
}

/// Actor-side endpoint for exactly one concrete callback-driven Servo owner.
///
/// The field is private and the value is non-cloneable.  Callers obtain it only
/// together with [`ServoRuntimeOwner`] from [`servo_runtime_pair`].
pub struct ServoRuntimeEndpoint {
    inner: simulation::engine_dispatch::EngineThreadRuntime,
}

/// Product actor whose only runtime is the concrete S08 Servo bridge.
///
/// This type is intentionally distinct from the deterministic [`crate::BrowserActor`].
/// It accepts no generic runtime parameter or caller-implemented runtime trait.
pub struct ServoBrowserActor {
    inner: simulation::BrowserActor<simulation::engine_dispatch::EngineThreadRuntime>,
}

impl ServoBrowserActor {
    /// Bind one concrete Servo endpoint to a live, pidfd-backed principal.
    pub fn from_attested(
        principal: TaskFlowPrincipal,
        peer: PeerIdentity,
        attestor: &ProcfsPeerAttestor,
        attested: &AttestedPeer,
        endpoint: ServoRuntimeEndpoint,
    ) -> Result<Self, AgentPortError> {
        let snapshot = attested.refresh_snapshot(attestor).map_err(|error| {
            AgentPortError::Handler(format!("peer attestation refresh failed: {error}"))
        })?;
        let binding = simulation::PrincipalBinding::bind_attested(principal, peer, &snapshot)
            .map_err(|error| {
                AgentPortError::Handler(format!("principal binding failed: {error}"))
            })?;
        Ok(Self {
            inner: simulation::BrowserActor::new(binding, endpoint.inner),
        })
    }

    /// Dispatch exactly one request under the original live peer custody.
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

    /// Return only the semantic principal.  Mechanism identity remains private.
    pub fn principal(&self) -> &TaskFlowPrincipal {
        self.inner.principal_binding().principal()
    }

    /// Return the bounded current PageOwner snapshot, when one exists.
    pub fn page_owner(&self) -> Option<PageOwnerSnapshot> {
        self.inner.page_owner()
    }

    /// Revoke one in-flight request; this never grants state-transition authority.
    pub fn cancel_request(&mut self, request_id: impl Into<String>) {
        self.inner.cancel_request(request_id);
    }

    /// Create or retrieve the shared cancellation token for one request.
    pub fn cancellation_token(&mut self, request_id: impl Into<String>) -> CancellationToken {
        self.inner.cancellation_token(request_id)
    }

    /// Return an existing token without creating new authority.
    pub fn active_cancellation_token(&self, request_id: &str) -> Option<CancellationToken> {
        self.inner.active_cancellation_token(request_id)
    }

    /// Construct a durable lifecycle observer.  Journal facts never authorize execution.
    pub fn receipt_observer(
        &self,
        journal: ReceiptJournal,
        image_id: impl Into<String>,
    ) -> ReceiptLifecycleObserver {
        self.inner.receipt_observer(journal, image_id)
    }
}

/// Operation delivered to the exact Servo embedder.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ServoRuntimeOperation {
    Health,
    CreateSession {
        session_id: String,
        profile: ProfileSpec,
    },
    Snapshot,
    Close,
    Navigate {
        url: String,
        expected_document_generation: u64,
    },
    Observe {
        fields: Vec<ObservationField>,
    },
    Wait {
        condition: WaitCondition,
        timeout: Duration,
    },
    Extract {
        schema_id: String,
    },
    Act {
        target: ElementReference,
        action: PageAction,
    },
}

/// One request transferred from the actor thread to the native Servo owner.
///
/// The expected PageOwner is not proof of live engine state.  The adapter must
/// compare it with the current WebView/document/accessibility tree and, for an
/// action, call [`ServoRuntimeCompletion::ensure_current_peer`] immediately
/// before one retained-node operation.
pub struct ServoRuntimeCommand {
    owner: Option<PageOwnerSnapshot>,
    operation: ServoRuntimeOperation,
    completion: ServoRuntimeCompletion,
}

impl ServoRuntimeCommand {
    pub fn owner(&self) -> Option<&PageOwnerSnapshot> {
        self.owner.as_ref()
    }

    pub fn operation(&self) -> &ServoRuntimeOperation {
        &self.operation
    }

    pub fn into_parts(
        self,
    ) -> (
        Option<PageOwnerSnapshot>,
        ServoRuntimeOperation,
        ServoRuntimeCompletion,
    ) {
        (self.owner, self.operation, self.completion)
    }
}

/// Narrow error vocabulary accepted from the concrete Servo adapter.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServoRuntimeError {
    PolicyDenied(&'static str),
    Unsupported(&'static str),
    Cancelled,
    DeadlineExceeded,
    BrowserCrashed,
    PeerIdentityRevoked,
    Internal(&'static str),
}

impl From<ServoRuntimeError> for RuntimeFailure {
    fn from(value: ServoRuntimeError) -> Self {
        match value {
            ServoRuntimeError::PolicyDenied(message) => Self::PolicyDenied(message),
            ServoRuntimeError::Unsupported(message) => Self::Unsupported(message),
            ServoRuntimeError::Cancelled => Self::Cancelled,
            ServoRuntimeError::DeadlineExceeded => Self::DeadlineExceeded,
            ServoRuntimeError::BrowserCrashed => Self::BrowserCrashed,
            ServoRuntimeError::PeerIdentityRevoked => Self::PeerIdentityRevoked,
            ServoRuntimeError::Internal(message) => Self::Internal(message.to_owned()),
        }
    }
}

/// Result of delivering a single-use Servo completion back to the actor.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServoCompletionDelivery {
    Queued,
    Retired,
    ReceiverGone,
    WakeFailed,
}

impl From<CompletionDelivery> for ServoCompletionDelivery {
    fn from(value: CompletionDelivery) -> Self {
        match value {
            CompletionDelivery::Queued => Self::Queued,
            CompletionDelivery::Retired => Self::Retired,
            CompletionDelivery::ReceiverGone => Self::ReceiverGone,
            CompletionDelivery::WakeFailed => Self::WakeFailed,
        }
    }
}

/// Single-use completion for one concrete Servo command.
pub struct ServoRuntimeCompletion {
    inner: EngineCompletion,
}

impl ServoRuntimeCompletion {
    pub fn request_id(&self) -> &str {
        self.inner.request_id()
    }

    pub fn deadline(&self) -> Instant {
        self.inner.deadline()
    }

    pub fn ensure_active(&self) -> Result<(), ServoRuntimeError> {
        self.inner.ensure_active().map_err(map_runtime_error)
    }

    /// Revalidate cancellation, deadline and pidfd-backed request custody.
    /// An action adapter must call this immediately before Servo dispatch.
    pub fn ensure_current_peer(&self) -> Result<(), ServoRuntimeError> {
        self.inner.ensure_current_peer().map_err(map_runtime_error)
    }

    pub fn complete_success(
        self,
        result: JsonObject,
        current_url: Option<String>,
    ) -> ServoCompletionDelivery {
        self.inner
            .complete(Ok(RuntimeReply {
                result,
                current_url,
            }))
            .into()
    }

    pub fn complete_error(self, error: ServoRuntimeError) -> ServoCompletionDelivery {
        self.inner.complete(Err(error.into())).into()
    }
}

fn map_runtime_error(error: RuntimeFailure) -> ServoRuntimeError {
    match error {
        RuntimeFailure::PolicyDenied(message) => ServoRuntimeError::PolicyDenied(message),
        RuntimeFailure::Unsupported(message) => ServoRuntimeError::Unsupported(message),
        RuntimeFailure::Cancelled => ServoRuntimeError::Cancelled,
        RuntimeFailure::DeadlineExceeded => ServoRuntimeError::DeadlineExceeded,
        RuntimeFailure::BrowserCrashed => ServoRuntimeError::BrowserCrashed,
        RuntimeFailure::PeerIdentityRevoked => ServoRuntimeError::PeerIdentityRevoked,
        RuntimeFailure::Internal(_) => {
            ServoRuntimeError::Internal("runtime control failed; diagnostic redacted")
        }
    }
}

struct ServoCommandBridge {
    state: Rc<RefCell<ServoCommandState>>,
}

#[derive(Default)]
struct ServoCommandState {
    pending: Option<ServoRuntimeCommand>,
    retired: bool,
}

impl ServoCommandBridge {
    fn publish(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        operation: ServoRuntimeOperation,
        completion: EngineCompletion,
    ) {
        let mut state = self.state.borrow_mut();
        if state.retired || state.pending.is_some() {
            state.retired = true;
            drop(state);
            let _ = completion.complete(Err(RuntimeFailure::BrowserCrashed));
            return;
        }
        state.pending = Some(ServoRuntimeCommand {
            owner: owner.cloned(),
            operation,
            completion: ServoRuntimeCompletion { inner: completion },
        });
    }
}

impl CallbackPageRuntime for ServoCommandBridge {
    fn start(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        completion: EngineCompletion,
    ) {
        let operation = match message {
            BrowserActorMessage::Health => ServoRuntimeOperation::Health,
            BrowserActorMessage::CreateSession {
                session_id,
                profile,
            } => ServoRuntimeOperation::CreateSession {
                session_id,
                profile,
            },
            BrowserActorMessage::Snapshot => ServoRuntimeOperation::Snapshot,
            BrowserActorMessage::Close => ServoRuntimeOperation::Close,
            BrowserActorMessage::Navigate {
                url,
                expected_document_generation,
            } => ServoRuntimeOperation::Navigate {
                url,
                expected_document_generation,
            },
            BrowserActorMessage::Observe { fields } => ServoRuntimeOperation::Observe { fields },
            BrowserActorMessage::Wait { condition, timeout } => {
                ServoRuntimeOperation::Wait { condition, timeout }
            }
            BrowserActorMessage::Extract { schema_id } => {
                ServoRuntimeOperation::Extract { schema_id }
            }
            BrowserActorMessage::Act { .. } => {
                let _ = completion.complete(Err(RuntimeFailure::Unsupported(
                    "generic Act cannot enter the concrete Servo bridge",
                )));
                return;
            }
        };
        self.publish(owner, operation, completion);
    }

    fn start_page_act(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        target: ElementReference,
        action: PageAction,
        completion: EngineCompletion,
    ) {
        self.publish(
            owner,
            ServoRuntimeOperation::Act { target, action },
            completion,
        );
    }

    fn retire(&mut self) {
        let mut state = self.state.borrow_mut();
        state.retired = true;
        state.pending.take();
    }
}

/// Creator-thread owner for the concrete Servo command bridge.
///
/// This wrapper remains `!Send`/`!Sync` because the underlying callback owner
/// carries explicit `Rc` thread affinity.
pub struct ServoRuntimeOwner {
    inner: CallbackEngineOwner<ServoCommandBridge>,
    state: Rc<RefCell<ServoCommandState>>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServoPumpResult {
    Idle,
    Pending,
    Replied,
    Retired,
}

impl ServoRuntimeOwner {
    pub fn pump_one(&mut self) -> ServoPumpResult {
        match self.inner.pump_one() {
            CallbackPumpResult::Idle => ServoPumpResult::Idle,
            CallbackPumpResult::Pending => ServoPumpResult::Pending,
            CallbackPumpResult::Replied => ServoPumpResult::Replied,
            CallbackPumpResult::Retired => ServoPumpResult::Retired,
        }
    }

    /// Take the sole typed command.  `None` means no command is ready.
    pub fn take_command(&mut self) -> Option<ServoRuntimeCommand> {
        self.state.borrow_mut().pending.take()
    }

    /// Native loops should schedule a wake no later than this instant while a
    /// callback is outstanding.
    pub fn next_wake_deadline(&self) -> Option<Instant> {
        self.inner.next_wake_deadline()
    }

    /// Permanently retire the bridge.  Pending effects are never replayed.
    pub fn retire(&mut self) {
        self.inner.retire();
        let mut state = self.state.borrow_mut();
        state.retired = true;
        state.pending.take();
    }
}

/// Create one actor endpoint and its non-Send native Servo owner on the current
/// event-loop thread.
pub fn servo_runtime_pair(
    waker: Arc<dyn ServoEventLoopWaker>,
) -> (ServoRuntimeEndpoint, ServoRuntimeOwner) {
    let state = Rc::new(RefCell::new(ServoCommandState::default()));
    let bridge = ServoCommandBridge {
        state: state.clone(),
    };
    let (endpoint, owner) = callback_engine_pair(bridge, Arc::new(ServoWakerAdapter(waker)));
    (
        ServoRuntimeEndpoint { inner: endpoint },
        ServoRuntimeOwner {
            inner: owner,
            state,
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use hepta_agent_port::BrowserRequestHandler;
    use hepta_browser_codec::{BrowserOperation, JsonValue};
    use simulation::{MechanismIdentity, PrincipalBinding};
    use std::thread;

    fn binding(peer: PeerIdentity) -> PrincipalBinding {
        PrincipalBinding::bind(
            TaskFlowPrincipal {
                principal_id: "s08-test-principal".to_owned(),
                expected_uid: peer.uid,
                expected_gid: peer.gid,
                expected_systemd_unit: "hepta-agent.service".to_owned(),
                expected_cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
                expected_executable_sha256: "a".repeat(64),
            },
            MechanismIdentity {
                peer,
                systemd_unit: "hepta-agent.service".to_owned(),
                cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
                executable_sha256: "a".repeat(64),
            },
        )
        .expect("valid test binding")
    }

    #[test]
    fn concrete_bridge_delivers_exactly_one_typed_command() {
        let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
        let peer = PeerIdentity {
            pid: Some(4242),
            uid: 1000,
            gid: 1000,
        };
        let worker = thread::spawn(move || {
            let mut actor = simulation::BrowserActor::new(binding(peer), endpoint.inner);
            let context = DispatchContext {
                peer,
                transport_sequence: 1,
                canonical_request_sha256: "b".repeat(64),
                effect_class: hepta_browser_codec::EffectClass::Observation,
                accepted_at: Instant::now(),
                effective_deadline: Instant::now() + Duration::from_secs(2),
            };
            let request = BrowserRequest {
                request_id: "s08-health".to_owned(),
                session_id: None,
                session_generation: None,
                deadline_unix_ms: None,
                operation: BrowserOperation::Health,
            };
            BrowserRequestHandler::handle(&mut actor, &context, &request).expect("health dispatch")
        });

        let deadline = Instant::now() + Duration::from_secs(2);
        let command = loop {
            let _ = owner.pump_one();
            if let Some(command) = owner.take_command() {
                break command;
            }
            assert!(Instant::now() < deadline, "command was not delivered");
            thread::yield_now();
        };
        assert!(matches!(command.operation(), ServoRuntimeOperation::Health));
        let (_page, _operation, completion) = command.into_parts();
        let mut result = JsonObject::new();
        result.insert("real_servo_adapter".to_owned(), JsonValue::Bool(true));
        assert_eq!(
            completion.complete_success(result, Some("about:blank".to_owned())),
            ServoCompletionDelivery::Queued
        );
        let _ = owner.pump_one();
        assert!(matches!(
            worker.join().expect("worker join"),
            HandlerOutcome::Success(_)
        ));
        assert!(owner.take_command().is_none());
    }
}
