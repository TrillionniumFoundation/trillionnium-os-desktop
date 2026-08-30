#![forbid(unsafe_code)]

//! D3 PageOwner and BrowserActor control core.
//!
//! This crate binds one semantic TaskFlow principal to one attested mechanism
//! identity, owns one logical PageOwner/session, maps the strict Browser API to
//! typed runtime messages, enforces generation and local-fixture policy, and
//! emits durable requested/dispatched/terminal receipt lifecycle events through
//! the AgentPort observer boundary. It creates no listener and grants no
//! external network or production-release authority.

use hepta_agent_port::{
    AgentPortError, BrowserRequestHandler, DispatchContext, HandlerOutcome,
    OperationLifecycleObserver,
};
use hepta_agent_transport::PeerIdentity;
use hepta_browser_codec::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, BrowserResponse, BrowserWireError,
    EffectClass, ElementReference, JsonObject, JsonValue, NavigationTarget, ObservationField,
    PageAction, ProfilePersistence, ProfileSpec, WaitCondition,
};
use hepta_session_core::{
    ControlSource, ControlState, JournalError, PrivacyClass, ReceiptEffectClass, ReceiptEvent,
    ReceiptJournal, ReceiptLifecycleState, ReceiptOutcome, ReceiptSource, SessionEvent,
    SessionMachine, SessionPhase, SessionSnapshot, TransitionError,
};
use sha2::{Digest as _, Sha256};
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::rc::Rc;
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use trillionnium_contract_core::{RefFreshness, RevisionClock, classify_reference};

pub const D3_PLAN_REVISION: &str = "2026-08-29-d6";
pub const D3_SERVO_COMMIT: &str = "670ae8a70801b162e186f81cbb5bdd2d59c39108";
pub const D3_BROWSERD_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const MAX_PRINCIPAL_ID_BYTES: usize = 128;
pub const MAX_UNIT_BYTES: usize = 192;
pub const MAX_CGROUP_BYTES: usize = 512;
pub const MAX_WEBVIEW_TOKEN_BYTES: usize = 128;
// Keep the direct runtime guard aligned with the canonical codec/contracts
// URL bound.  Actor callers normally arrive through the codec, but this
// defense-in-depth check also protects typed/internal callers that construct a
// `NavigationTarget` without going through wire validation.
const MAX_LOOPBACK_URL_BYTES: usize = 8_192;
/// Upper bound supplied to a best-effort runtime Close when CreateSession
/// crossed the cancellation/deadline boundary before a local PageOwner was
/// installed.  The runtime adapter is responsible for honoring this control
/// deadline at bounded points; if it cannot confirm Close within the budget,
/// the actor poisons the runtime rather than admitting another hidden
/// session.
const CREATE_RECONCILIATION_BUDGET: Duration = Duration::from_millis(100);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TaskFlowPrincipal {
    pub principal_id: String,
    pub expected_uid: u32,
    pub expected_gid: u32,
    pub expected_systemd_unit: String,
    pub expected_cgroup_v2_path: String,
    pub expected_executable_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MechanismIdentity {
    pub peer: PeerIdentity,
    pub systemd_unit: String,
    pub cgroup_v2_path: String,
    pub executable_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PrincipalBinding {
    principal: TaskFlowPrincipal,
    mechanism: MechanismIdentity,
    // A binding created from an attested snapshot retains the process start
    // time.  This is intentionally private so adding continuity evidence does
    // not break callers that construct `MechanismIdentity` values directly.
    attested_start_time_ticks: Option<u64>,
}

impl PrincipalBinding {
    /// Build the mechanism identity directly from the attested procfs
    /// snapshot. This keeps the semantic-principal binding on the same
    /// immutable identity facts that the AgentPort custody layer verified;
    /// callers cannot substitute a hand-written executable or unit digest.
    pub fn bind_attested(
        principal: TaskFlowPrincipal,
        peer: PeerIdentity,
        snapshot: &hepta_peer_attestation::PeerRuntimeSnapshot,
    ) -> Result<Self, PrincipalBindingError> {
        let mechanism = MechanismIdentity::from_attested(peer, snapshot)?;
        let mut binding = Self::bind(principal, mechanism)?;
        binding.attested_start_time_ticks = Some(snapshot.start_time_ticks);
        Ok(binding)
    }

    pub fn bind(
        principal: TaskFlowPrincipal,
        mechanism: MechanismIdentity,
    ) -> Result<Self, PrincipalBindingError> {
        validate_token(
            "principal_id",
            &principal.principal_id,
            MAX_PRINCIPAL_ID_BYTES,
        )?;
        validate_text(
            "expected_systemd_unit",
            &principal.expected_systemd_unit,
            MAX_UNIT_BYTES,
        )?;
        validate_text(
            "expected_cgroup_v2_path",
            &principal.expected_cgroup_v2_path,
            MAX_CGROUP_BYTES,
        )?;
        validate_sha256(&principal.expected_executable_sha256)?;
        validate_text("systemd_unit", &mechanism.systemd_unit, MAX_UNIT_BYTES)?;
        validate_text(
            "cgroup_v2_path",
            &mechanism.cgroup_v2_path,
            MAX_CGROUP_BYTES,
        )?;
        validate_sha256(&mechanism.executable_sha256)?;
        let Some(pid) = mechanism.peer.pid else {
            return Err(PrincipalBindingError::MissingPeerPid);
        };
        if pid == 0 {
            return Err(PrincipalBindingError::MissingPeerPid);
        }
        if mechanism.peer.uid != principal.expected_uid {
            return Err(PrincipalBindingError::UidMismatch {
                expected: principal.expected_uid,
                actual: mechanism.peer.uid,
            });
        }
        if mechanism.peer.gid != principal.expected_gid {
            return Err(PrincipalBindingError::GidMismatch {
                expected: principal.expected_gid,
                actual: mechanism.peer.gid,
            });
        }
        if mechanism.systemd_unit != principal.expected_systemd_unit {
            return Err(PrincipalBindingError::UnitMismatch);
        }
        if mechanism.cgroup_v2_path != principal.expected_cgroup_v2_path {
            return Err(PrincipalBindingError::CgroupMismatch);
        }
        if mechanism.executable_sha256 != principal.expected_executable_sha256 {
            return Err(PrincipalBindingError::ExecutableMismatch);
        }
        Ok(Self {
            principal,
            mechanism,
            attested_start_time_ticks: None,
        })
    }

    pub fn principal(&self) -> &TaskFlowPrincipal {
        &self.principal
    }

    pub fn mechanism(&self) -> &MechanismIdentity {
        &self.mechanism
    }

    /// Verify the transport tuple for every dispatch.
    ///
    /// This check is intentionally cheap and remains useful for callers that
    /// only have `SO_PEERCRED`.  A binding made by [`Self::bind_attested`]
    /// should use [`Self::verify_dispatch_attestation`] as well while the
    /// pidfd-backed attestation is retained for the complete one-request
    /// lifetime.
    pub fn verify_dispatch_peer(&self, peer: PeerIdentity) -> Result<(), PrincipalBindingError> {
        if peer.pid != self.mechanism.peer.pid
            || peer.uid != self.mechanism.peer.uid
            || peer.gid != self.mechanism.peer.gid
        {
            return Err(PrincipalBindingError::PeerDrift);
        }
        Ok(())
    }

    /// Verify a fresh procfs snapshot against the mechanism identity that was
    /// bound before dispatch.
    ///
    /// In addition to UID/GID/cgroup/unit/executable continuity, an attested
    /// binding checks the process start time.  A changed start time denotes a
    /// PID reuse and is rejected even when the replacement process happens to
    /// have the same credentials and executable image.
    pub fn verify_dispatch_attestation(
        &self,
        peer: PeerIdentity,
        snapshot: &hepta_peer_attestation::PeerRuntimeSnapshot,
    ) -> Result<(), PrincipalBindingError> {
        self.verify_dispatch_peer(peer)?;

        if snapshot.start_time_ticks == 0 {
            return Err(PrincipalBindingError::PeerDrift);
        }

        let expected_pid = self
            .mechanism
            .peer
            .pid
            .ok_or(PrincipalBindingError::MissingPeerPid)?;
        if snapshot.pid != expected_pid || snapshot.pid != peer.pid.unwrap_or_default() {
            return Err(PrincipalBindingError::PeerDrift);
        }
        if snapshot.uid != self.mechanism.peer.uid {
            return Err(PrincipalBindingError::UidMismatch {
                expected: self.mechanism.peer.uid,
                actual: snapshot.uid,
            });
        }
        if snapshot.gid != self.mechanism.peer.gid {
            return Err(PrincipalBindingError::GidMismatch {
                expected: self.mechanism.peer.gid,
                actual: snapshot.gid,
            });
        }
        if snapshot.cgroup_v2_path != self.mechanism.cgroup_v2_path {
            return Err(PrincipalBindingError::CgroupMismatch);
        }
        let unit = snapshot
            .systemd_unit
            .as_ref()
            .ok_or(PrincipalBindingError::MissingSystemdUnit)?;
        if unit != &self.mechanism.systemd_unit {
            return Err(PrincipalBindingError::UnitMismatch);
        }
        if snapshot.executable_sha256 != self.mechanism.executable_sha256 {
            return Err(PrincipalBindingError::ExecutableMismatch);
        }
        if let Some(start_time_ticks) = self.attested_start_time_ticks
            && snapshot.start_time_ticks != start_time_ticks
        {
            return Err(PrincipalBindingError::PeerDrift);
        }
        Ok(())
    }
}

impl MechanismIdentity {
    pub fn from_attested(
        peer: PeerIdentity,
        snapshot: &hepta_peer_attestation::PeerRuntimeSnapshot,
    ) -> Result<Self, PrincipalBindingError> {
        if snapshot.start_time_ticks == 0 {
            return Err(PrincipalBindingError::PeerDrift);
        }
        if snapshot.pid != peer.pid.unwrap_or_default()
            || snapshot.uid != peer.uid
            || snapshot.gid != peer.gid
        {
            return Err(PrincipalBindingError::PeerDrift);
        }
        let systemd_unit = snapshot
            .systemd_unit
            .clone()
            .ok_or(PrincipalBindingError::MissingSystemdUnit)?;
        Ok(Self {
            peer,
            systemd_unit,
            cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
            executable_sha256: snapshot.executable_sha256.clone(),
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PrincipalBindingError {
    InvalidField(&'static str),
    MissingPeerPid,
    MissingSystemdUnit,
    UidMismatch { expected: u32, actual: u32 },
    GidMismatch { expected: u32, actual: u32 },
    UnitMismatch,
    CgroupMismatch,
    ExecutableMismatch,
    PeerDrift,
}

impl fmt::Display for PrincipalBindingError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidField(field) => {
                write!(formatter, "invalid principal binding field {field}")
            }
            Self::MissingPeerPid => formatter.write_str("mechanism peer PID is missing"),
            Self::MissingSystemdUnit => {
                formatter.write_str("attested mechanism has no systemd unit")
            }
            Self::UidMismatch { expected, actual } => {
                write!(
                    formatter,
                    "mechanism UID {actual} does not equal {expected}"
                )
            }
            Self::GidMismatch { expected, actual } => {
                write!(
                    formatter,
                    "mechanism GID {actual} does not equal {expected}"
                )
            }
            Self::UnitMismatch => formatter.write_str("mechanism systemd unit does not match"),
            Self::CgroupMismatch => formatter.write_str("mechanism cgroup path does not match"),
            Self::ExecutableMismatch => {
                formatter.write_str("mechanism executable digest does not match")
            }
            Self::PeerDrift => formatter.write_str("transport peer drifted from principal binding"),
        }
    }
}

impl std::error::Error for PrincipalBindingError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PageOwnerSnapshot {
    pub session_id: String,
    pub session: SessionSnapshot,
    pub webview_token: String,
    pub current_url: String,
    pub local_fixture_only: bool,
}

#[derive(Debug, Clone)]
struct PageOwner {
    session_id: String,
    session: SessionMachine,
    webview_token: String,
    current_url: String,
    local_fixture_only: bool,
}

impl PageOwner {
    fn snapshot(&self) -> PageOwnerSnapshot {
        PageOwnerSnapshot {
            session_id: self.session_id.clone(),
            session: self.session.snapshot(),
            webview_token: self.webview_token.clone(),
            current_url: self.current_url.clone(),
            local_fixture_only: self.local_fixture_only,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BrowserActorMessage {
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
    Act {
        target: ElementReference,
        action: PageAction,
    },
    Wait {
        condition: WaitCondition,
        timeout: Duration,
    },
    Extract {
        schema_id: String,
    },
}

#[derive(Debug, Clone)]
pub struct CancellationToken(Arc<AtomicBool>);

impl CancellationToken {
    /// Create a token that can be shared with a runtime adapter or its worker
    /// threads.  Clones observe and update the same cancellation state.
    pub fn new() -> Self {
        Self(Arc::new(AtomicBool::new(false)))
    }

    /// Request cancellation.  Runtime adapters must still check the token at
    /// bounded points; cancellation never claims that an already-started
    /// external effect was rolled back.
    pub fn cancel(&self) {
        self.0.store(true, Ordering::SeqCst);
    }

    pub fn is_cancelled(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }
}

impl Default for CancellationToken {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone)]
pub struct RequestControl {
    pub request_id: String,
    pub deadline: Instant,
    cancelled: bool,
    cancellation: CancellationToken,
}

impl RequestControl {
    pub fn ensure_active(&self) -> Result<(), RuntimeFailure> {
        if self.cancelled || self.cancellation.is_cancelled() {
            return Err(RuntimeFailure::Cancelled);
        }
        if Instant::now() >= self.deadline {
            return Err(RuntimeFailure::DeadlineExceeded);
        }
        Ok(())
    }

    /// Return a clone of the shared cancellation state for an adapter that
    /// performs work outside the synchronous `dispatch` call.
    pub fn cancellation_token(&self) -> CancellationToken {
        self.cancellation.clone()
    }

    /// Cancel this request from code that owns its runtime control handle.
    pub fn cancel(&self) {
        self.cancellation.cancel();
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled || self.cancellation.is_cancelled()
    }

    /// Return the remaining bounded runtime budget after checking cancellation
    /// and deadline state.
    pub fn remaining(&self) -> Result<Duration, RuntimeFailure> {
        self.ensure_active()?;
        self.deadline
            .checked_duration_since(Instant::now())
            .filter(|remaining| !remaining.is_zero())
            .ok_or(RuntimeFailure::DeadlineExceeded)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeReply {
    pub result: JsonObject,
    pub current_url: Option<String>,
}

pub trait PageRuntime {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure>;

    /// Resolve and apply a semantic page action as one runtime-owned
    /// operation.
    ///
    /// A PageAct target carries frame and structural evidence.  The actor
    /// cannot validate that evidence from revision counters alone: only the
    /// engine adapter can re-resolve the target in the current frame, reject
    /// ambiguity/material structural drift, and retain the resolved node
    /// through the action.  Keeping resolution and dispatch in one hook avoids
    /// a resolve/act time-of-check/time-of-use gap.
    ///
    /// The default is deliberately fail closed.  Runtime adapters must opt in
    /// explicitly once they have a real DOM/accessibility resolver; callers
    /// must never treat the generic [`Self::dispatch`] Act message as proof
    /// that semantic re-resolution occurred.
    fn dispatch_page_act(
        &mut self,
        _owner: Option<&PageOwnerSnapshot>,
        _target: ElementReference,
        _action: PageAction,
        _control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        Err(RuntimeFailure::Unsupported(
            "semantic frame/structure re-resolution is unavailable",
        ))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RuntimeFailure {
    PolicyDenied(&'static str),
    Unsupported(&'static str),
    Cancelled,
    DeadlineExceeded,
    BrowserCrashed,
    Internal(String),
}

impl fmt::Display for RuntimeFailure {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::PolicyDenied(message) => write!(formatter, "runtime policy denied: {message}"),
            Self::Unsupported(message) => write!(formatter, "runtime unsupported: {message}"),
            Self::Cancelled => formatter.write_str("runtime request cancelled"),
            Self::DeadlineExceeded => formatter.write_str("runtime deadline exceeded"),
            Self::BrowserCrashed => formatter.write_str("runtime browser crashed"),
            Self::Internal(message) => write!(formatter, "runtime failed: {message}"),
        }
    }
}

impl std::error::Error for RuntimeFailure {}

/// Runtime dispatch failures carry whether the adapter returned an otherwise
/// successful reply that crossed the cancellation/deadline boundary (or
/// otherwise reported an interruption after work may have begun).  Callers
/// handling stateful navigation/actions use this bit to avoid applying a
/// normal `NavigationFailed`/rollback transition when the runtime's effect
/// is no longer knowable.
#[derive(Debug)]
struct RuntimeDispatchError {
    outcome: HandlerOutcome,
    /// A broader hint for stateful operations.  Runtime crashes and internal
    /// failures are also treated as potentially effectful; policy/unsupported
    /// refusals remain harmless preflight failures.
    effect_may_have_started: bool,
}

#[derive(Debug, Clone)]
pub struct DeterministicLocalRuntime {
    current_url: String,
    open_session: Option<String>,
    actions_applied: u64,
}

impl Default for DeterministicLocalRuntime {
    fn default() -> Self {
        Self {
            current_url: "about:blank".to_owned(),
            open_session: None,
            actions_applied: 0,
        }
    }
}

impl PageRuntime for DeterministicLocalRuntime {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        control.ensure_active()?;
        match message {
            BrowserActorMessage::Health => Ok(RuntimeReply {
                result: json_object([
                    ("browser_actor_ready", JsonValue::Bool(true)),
                    ("external_effect_authority", JsonValue::Bool(false)),
                    ("local_fixture_only", JsonValue::Bool(true)),
                ]),
                current_url: Some(self.current_url.clone()),
            }),
            BrowserActorMessage::CreateSession {
                session_id,
                profile,
            } => {
                if profile.persistence != ProfilePersistence::Ephemeral {
                    return Err(RuntimeFailure::PolicyDenied(
                        "persistent profiles are closed in the deterministic development profile",
                    ));
                }
                self.open_session = Some(session_id.clone());
                self.current_url = "about:blank".to_owned();
                Ok(RuntimeReply {
                    result: json_object([
                        ("profile_id", JsonValue::String(profile.profile_id)),
                        (
                            "runtime",
                            JsonValue::String("deterministic_local".to_owned()),
                        ),
                        ("session_id", JsonValue::String(session_id)),
                    ]),
                    current_url: Some(self.current_url.clone()),
                })
            }
            BrowserActorMessage::Snapshot => {
                let owner = owner.ok_or_else(|| {
                    RuntimeFailure::Internal("snapshot has no PageOwner".to_owned())
                })?;
                Ok(RuntimeReply {
                    result: json_object([
                        ("current_url", JsonValue::String(self.current_url.clone())),
                        (
                            "webview_token",
                            JsonValue::String(owner.webview_token.clone()),
                        ),
                    ]),
                    current_url: Some(self.current_url.clone()),
                })
            }
            BrowserActorMessage::Close => {
                self.open_session = None;
                Ok(RuntimeReply {
                    result: json_object([("closed", JsonValue::Bool(true))]),
                    current_url: None,
                })
            }
            BrowserActorMessage::Navigate {
                url,
                expected_document_generation,
            } => {
                if !is_loopback_http(&url) {
                    return Err(RuntimeFailure::PolicyDenied(
                        "only loopback HTTP fixtures are enabled before the D6 egress gate",
                    ));
                }
                self.current_url = url.clone();
                Ok(RuntimeReply {
                    result: json_object([
                        (
                            "expected_document_generation",
                            json_u64(expected_document_generation)?,
                        ),
                        ("navigated", JsonValue::Bool(true)),
                        ("url", JsonValue::String(url)),
                    ]),
                    current_url: Some(self.current_url.clone()),
                })
            }
            BrowserActorMessage::Observe { fields } => {
                let names = fields
                    .into_iter()
                    .map(|field| JsonValue::String(observation_field_name(field).to_owned()))
                    .collect();
                Ok(RuntimeReply {
                    result: json_object([
                        ("fields", JsonValue::Array(names)),
                        (
                            "local_fixture",
                            JsonValue::Bool(is_loopback_http(&self.current_url)),
                        ),
                        ("url", JsonValue::String(self.current_url.clone())),
                    ]),
                    current_url: Some(self.current_url.clone()),
                })
            }
            BrowserActorMessage::Act { .. } => Err(RuntimeFailure::Unsupported(
                "semantic frame/structure re-resolution is unavailable",
            )),
            BrowserActorMessage::Wait { condition, timeout } => {
                if timeout.is_zero() {
                    return Err(RuntimeFailure::DeadlineExceeded);
                }
                control.ensure_active()?;
                Ok(RuntimeReply {
                    result: json_object([
                        (
                            "condition",
                            JsonValue::String(wait_condition_name(&condition).to_owned()),
                        ),
                        ("satisfied", JsonValue::Bool(true)),
                        (
                            "timeout_ms",
                            json_u64(
                                u64::try_from(timeout.as_millis())
                                    .map_err(|_| RuntimeFailure::DeadlineExceeded)?,
                            )?,
                        ),
                    ]),
                    current_url: Some(self.current_url.clone()),
                })
            }
            BrowserActorMessage::Extract { schema_id } => Ok(RuntimeReply {
                result: json_object([
                    ("schema_id", JsonValue::String(schema_id)),
                    (
                        "value",
                        JsonValue::Object(json_object([
                            ("action_count", json_u64(self.actions_applied)?),
                            ("url", JsonValue::String(self.current_url.clone())),
                        ])),
                    ),
                ]),
                current_url: Some(self.current_url.clone()),
            }),
        }
    }
}

#[derive(Debug, Clone)]
struct ReceiptCoordinates {
    session_id: String,
    session_generation: u64,
    document_generation: u64,
    semantic_snapshot_revision: u64,
    mutation_epoch: u64,
}

#[derive(Debug, Clone)]
struct SharedActorState {
    page: Option<PageOwnerSnapshot>,
}

pub struct BrowserActor<R> {
    binding: PrincipalBinding,
    runtime: R,
    page: Option<PageOwner>,
    session_counter: u64,
    webview_counter: u64,
    cancelled_requests: BTreeSet<String>,
    cancellation_tokens: BTreeMap<String, CancellationToken>,
    /// Set after an ambiguous runtime cleanup.  A poisoned runtime cannot be
    /// safely reused for a new PageOwner because the previous WebView/session
    /// may still exist outside the actor's local state.
    runtime_unavailable: bool,
    /// Set after a request crosses the runtime dispatch boundary.  The marker
    /// is reset for each synchronous request and lets the final deadline gate
    /// distinguish an expired pure preflight from an expired runtime effect.
    runtime_dispatch_started: bool,
    shared: Rc<RefCell<SharedActorState>>,
}

impl<R: PageRuntime> BrowserActor<R> {
    pub fn new(binding: PrincipalBinding, runtime: R) -> Self {
        Self {
            binding,
            runtime,
            page: None,
            session_counter: 0,
            webview_counter: 0,
            cancelled_requests: BTreeSet::new(),
            cancellation_tokens: BTreeMap::new(),
            runtime_unavailable: false,
            runtime_dispatch_started: false,
            shared: Rc::new(RefCell::new(SharedActorState { page: None })),
        }
    }

    pub fn principal_binding(&self) -> &PrincipalBinding {
        &self.binding
    }

    /// Dispatch one request after refreshing the caller's procfs attestation.
    ///
    /// The regular [`BrowserRequestHandler::handle`] implementation retains
    /// the inexpensive SO_PEERCRED tuple check for compatibility.  Services
    /// that hold an [`hepta_peer_attestation::AttestedPeer`] for a connection
    /// should call this method instead: it checks the pidfd, reads a fresh
    /// bounded snapshot, and verifies start-time/cgroup/unit/executable
    /// continuity before runtime work begins.  The attested peer should be
    /// scoped to one request/connection and dropped immediately afterwards.
    pub fn handle_attested(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        attestor: &hepta_peer_attestation::ProcfsPeerAttestor,
        attested: &hepta_peer_attestation::AttestedPeer,
    ) -> Result<HandlerOutcome, AgentPortError> {
        let request_id = request.request_id.clone();
        self.with_request_cancellation(&request_id, |actor| {
            actor.handle_attested_inner(context, request, attestor, attested)
        })
    }

    fn handle_attested_inner(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        attestor: &hepta_peer_attestation::ProcfsPeerAttestor,
        attested: &hepta_peer_attestation::AttestedPeer,
    ) -> Result<HandlerOutcome, AgentPortError> {
        // Refreshing procfs and hashing `/proc/<pid>/exe` is bounded but can
        // still consume a meaningful part of the request budget.  Refuse to
        // start that work after the absolute deadline and re-check before the
        // actor enters its runtime dispatch path.
        context.remaining()?;
        if let Err(error) = attested.ensure_alive() {
            return Ok(failure(
                BrowserErrorCode::PolicyDenied,
                &format!("peer attestation is no longer alive: {error}"),
            ));
        }
        let snapshot = match attestor.read_snapshot(attested.snapshot().pid) {
            Ok(snapshot) => snapshot,
            Err(error) => {
                return Ok(failure(
                    BrowserErrorCode::PolicyDenied,
                    &format!("peer attestation refresh failed: {error}"),
                ));
            }
        };
        context.remaining()?;
        if let Err(error) = self
            .binding
            .verify_dispatch_attestation(context.peer, &snapshot)
        {
            return Ok(failure(
                BrowserErrorCode::PolicyDenied,
                &format!("peer attestation continuity rejected dispatch: {error}"),
            ));
        }
        if let Err(error) = attested.ensure_alive() {
            return Ok(failure(
                BrowserErrorCode::PolicyDenied,
                &format!("peer attestation changed before dispatch: {error}"),
            ));
        }
        self.handle_inner(context, request)
    }

    pub fn page_owner(&self) -> Option<PageOwnerSnapshot> {
        self.page.as_ref().map(PageOwner::snapshot)
    }

    pub fn cancel_request(&mut self, request_id: impl Into<String>) {
        let request_id = request_id.into();
        if let Some(token) = self.cancellation_tokens.get(&request_id) {
            token.cancel();
        } else {
            self.cancelled_requests.insert(request_id);
        }
    }

    /// Prepare a shared cancellation token for a request that is about to be
    /// dispatched.  The caller may clone and cancel it from another thread;
    /// the runtime receives the same token through [`RequestControl`].
    pub fn cancellation_token(&mut self, request_id: impl Into<String>) -> CancellationToken {
        self.cancellation_tokens
            .entry(request_id.into())
            .or_default()
            .clone()
    }

    /// Inspect a token registered for a request.  This is useful to bridge a
    /// transport-level cancellation callback without exposing actor internals.
    pub fn active_cancellation_token(&self, request_id: &str) -> Option<CancellationToken> {
        self.cancellation_tokens.get(request_id).cloned()
    }

    pub fn apply_session_event(
        &mut self,
        event: SessionEvent,
        now_ms: u64,
    ) -> Result<(), TransitionError> {
        let page = self.page.as_mut().ok_or(TransitionError::Closed)?;
        page.session.apply(event, now_ms)?;
        self.publish_shared();
        Ok(())
    }

    pub fn receipt_observer(
        &self,
        journal: ReceiptJournal,
        image_id: impl Into<String>,
    ) -> ReceiptLifecycleObserver {
        let logical_clock = journal.last_monotonic_ms();
        ReceiptLifecycleObserver {
            journal,
            image_id: image_id.into(),
            principal_id: self.binding.principal.principal_id.clone(),
            shared: self.shared.clone(),
            inflight: BTreeMap::new(),
            logical_clock,
        }
    }

    fn publish_shared(&self) {
        self.shared.borrow_mut().page = self.page.as_ref().map(PageOwner::snapshot);
    }

    /// Admit one request's cancellation state for the complete preflight and
    /// dispatch path.  A cancellation requested before admission is moved to
    /// a token so the request observes it even if it reaches the runtime; the
    /// token/marker is retired after *every* outcome, including validation or
    /// state-machine rejection, so a request ID cannot poison a later one.
    fn with_request_cancellation<T>(
        &mut self,
        request_id: &str,
        operation: impl FnOnce(&mut Self) -> T,
    ) -> T {
        if self.cancelled_requests.remove(request_id) {
            self.cancellation_tokens
                .entry(request_id.to_owned())
                .or_default()
                .cancel();
        }
        let result = operation(self);
        self.cancellation_tokens.remove(request_id);
        // A cancellation callback that races with a completed synchronous
        // dispatch may have inserted a pre-admission marker after
        // `runtime_dispatch` retired the token.  It is too late to affect the
        // completed request; discard it rather than applying it to a reused ID.
        self.cancelled_requests.remove(request_id);
        result
    }

    fn verify_bound_request(&self, request: &BrowserRequest) -> Result<(), HandlerOutcome> {
        let page = self.page.as_ref().ok_or_else(|| {
            failure(
                BrowserErrorCode::StaleSession,
                "no active PageOwner exists for the supplied session",
            )
        })?;
        if request.session_id.as_deref() != Some(page.session_id.as_str()) {
            return Err(failure(
                BrowserErrorCode::StaleSession,
                "session_id does not identify the active PageOwner",
            ));
        }
        let current = page.session.snapshot().revisions.session_generation;
        if request.session_generation != Some(current) {
            return Err(failure(
                BrowserErrorCode::StaleSession,
                "session_generation is stale",
            ));
        }
        Ok(())
    }

    fn page_revision_near_wire_ceiling(&self) -> bool {
        self.page
            .as_ref()
            .is_some_and(|page| revision_clock_near_wire_ceiling(page.session.snapshot().revisions))
    }

    /// Retire an owner before dispatch when one of its revision fields can no
    /// longer be represented by the Browser API's signed integer envelope.
    /// Allowing a runtime call first would permit a real effect and only then
    /// fail while constructing `snapshot_result`, leaving stale identity
    /// state live.  The runtime is poisoned because local retirement cannot
    /// prove that a remote WebView was not created or changed.
    fn retire_terminal_revision_owner(&mut self, context: &DispatchContext) -> HandlerOutcome {
        self.runtime_unavailable = true;
        if self.page.is_some() && self.close_local_page_owner(context).is_err() {
            self.page = None;
            self.publish_shared();
        }
        failure(
            BrowserErrorCode::Internal,
            "PageOwner revision reached the Browser API integer ceiling",
        )
    }

    /// Run one runtime call under the request's shared cancellation/deadline
    /// control.  Keeping control creation and retirement in one helper is
    /// important for PageAct: semantic resolution and the eventual action
    /// must observe the same token and deadline without a gap in which a
    /// cancellation callback could be detached.
    fn with_runtime_control<T>(
        &mut self,
        request: &BrowserRequest,
        context: &DispatchContext,
        call: impl FnOnce(
            &mut R,
            Option<&PageOwnerSnapshot>,
            &RequestControl,
        ) -> Result<T, RuntimeFailure>,
    ) -> Result<T, RuntimeDispatchError> {
        let request_id = request.request_id.clone();
        let cancelled = self.cancelled_requests.remove(&request_id);
        let cancellation = self
            .cancellation_tokens
            .entry(request_id.clone())
            .or_default()
            .clone();
        if cancelled {
            cancellation.cancel();
        }
        let control = RequestControl {
            request_id,
            deadline: context.effective_deadline,
            cancelled,
            cancellation,
        };
        // A cancellation/deadline observed before entering the adapter is a
        // harmless preflight rejection: no remote effect could have started,
        // and stateful callers may keep their ordinary local cleanup path.
        // This also closes the tiny race where a request expires between the
        // outer gate and runtime dispatch.
        if let Err(error) = control.ensure_active() {
            self.cancellation_tokens.remove(&request.request_id);
            return Err(RuntimeDispatchError {
                outcome: runtime_failure(error),
                effect_may_have_started: false,
            });
        }
        let owner = self.page.as_ref().map(PageOwner::snapshot);
        self.runtime_dispatch_started = true;
        let result = call(&mut self.runtime, owner.as_ref(), &control);
        // Drop the registration after this synchronous dispatch.  A caller
        // that needs to cancel work in flight keeps its cloned token alive.
        self.cancellation_tokens.remove(&request.request_id);
        match result {
            Ok(reply) => match control.ensure_active() {
                Ok(()) => Ok(reply),
                Err(error) => Err(RuntimeDispatchError {
                    outcome: runtime_failure(error),
                    // The adapter returned a reply, so its operation may
                    // already have changed the browser even though the
                    // control boundary rejected the result.
                    effect_may_have_started: true,
                }),
            },
            Err(RuntimeFailure::BrowserCrashed) => {
                // A runtime crash is a state transition, not merely a wire
                // error.  Invalidate every session/reference layer before
                // returning the failure so a subsequent request cannot be
                // dispatched against a dead PageOwner.
                if let Err(outcome) = self.mark_browser_crashed(context) {
                    Err(RuntimeDispatchError {
                        outcome,
                        effect_may_have_started: true,
                    })
                } else {
                    Err(RuntimeDispatchError {
                        outcome: runtime_failure(RuntimeFailure::BrowserCrashed),
                        effect_may_have_started: true,
                    })
                }
            }
            Err(error) => {
                let effect_may_have_started = matches!(
                    &error,
                    RuntimeFailure::Cancelled
                        | RuntimeFailure::DeadlineExceeded
                        | RuntimeFailure::BrowserCrashed
                        | RuntimeFailure::Internal(_)
                );
                Err(RuntimeDispatchError {
                    outcome: runtime_failure(error),
                    effect_may_have_started,
                })
            }
        }
    }

    fn mark_browser_crashed(&mut self, context: &DispatchContext) -> Result<(), HandlerOutcome> {
        let transition = {
            let Some(page) = self.page.as_mut() else {
                // A crash while creating the first PageOwner has no session
                // identity to invalidate.  The runtime failure still
                // remains visible to the caller and the next create is
                // allowed to establish a fresh owner.
                return Ok(());
            };
            if page.session.snapshot().phase == SessionPhase::Recovering {
                return Ok(());
            }
            page.session
                .apply(SessionEvent::BrowserCrashed, monotonic_request_ms(context))
        };
        if let Err(error) = transition {
            return Err(self.crash_transition_failure(context, error));
        }
        self.publish_shared();
        Ok(())
    }

    fn crash_transition_failure(
        &mut self,
        context: &DispatchContext,
        error: TransitionError,
    ) -> HandlerOutcome {
        if matches!(error, TransitionError::RevisionExhausted) {
            // A dead runtime cannot be left behind as a Ready owner just
            // because one of the revision layers reached u64::MAX.  The
            // local Close transition is valid from every session phase;
            // retire the owner before returning the original crash class
            // so no subsequent request can dispatch into the dead runtime.
            // There is no wire-level RevisionExhausted code, therefore retain
            // BrowserCrashed and include the invariant failure in its
            // diagnostic message.
            return match self.close_local_page_owner(context) {
                Ok(_) => failure(
                    BrowserErrorCode::BrowserCrashed,
                    "browser runtime crashed; revision clock exhausted during recovery",
                ),
                Err(error) => {
                    // Even if a future state-machine change makes Close
                    // reject an exhausted phase, retaining a dead owner is
                    // less safe than dropping the local marker.  Preserve
                    // the BrowserCrashed class and force-retire the owner;
                    // the diagnostic records that local closure was not
                    // confirmed.
                    self.page = None;
                    self.publish_shared();
                    failure(
                        BrowserErrorCode::BrowserCrashed,
                        &format!(
                            "browser runtime crashed; revision clock exhausted and local owner retirement failed: {error}"
                        ),
                    )
                }
            };
        }
        failure(
            BrowserErrorCode::Internal,
            &format!("browser crash recovery transition failed: {error}"),
        )
    }

    fn page_is_recovering(&self) -> bool {
        self.page
            .as_ref()
            .is_none_or(|page| page.session.snapshot().phase == SessionPhase::Recovering)
    }

    /// Apply the local terminal transition and release the PageOwner after a
    /// close request whose runtime call could not report success.  Closing is
    /// intentionally an all-phase session transition (including
    /// `Recovering`), so the local ownership/lease marker can be retired even
    /// when the browser process stopped, the request was cancelled, or its
    /// deadline elapsed.  The caller decides whether to preserve the original
    /// runtime error; this helper only fails if the state-machine contract is
    /// violated, and never clears an owner before the transition succeeds.
    fn close_local_page_owner(
        &mut self,
        context: &DispatchContext,
    ) -> Result<String, AgentPortError> {
        let page = self.page.as_mut().ok_or_else(|| {
            AgentPortError::Handler("PageOwner vanished before local session close".to_owned())
        })?;
        let session_id = page.session_id.clone();
        page.session
            .apply(SessionEvent::Close, monotonic_request_ms(context))
            .map_err(|error| {
                AgentPortError::Handler(format!("local session close transition failed: {error}"))
            })?;
        self.page = None;
        self.publish_shared();
        Ok(session_id)
    }

    /// Reconcile a stateful page operation whose runtime result crossed a
    /// cancellation/deadline/error boundary after dispatch.  The actor cannot
    /// safely claim `NavigationFailed` or roll back a mutation because the
    /// browser may already have applied the effect.  Entering the existing
    /// recovery phase advances the process/session revision and invalidates
    /// every prior reference; subsequent bound operations are blocked until a
    /// separately attested recovery path replaces the PageOwner.
    fn reconcile_indeterminate_page_effect(&mut self, context: &DispatchContext) {
        if self.mark_browser_crashed(context).is_err() {
            // A revision-exhaustion or future transition failure must not
            // leave a locally Ready owner that could be reused against an
            // unknown runtime state.  Retire the marker and poison runtime
            // admission; the original wire failure is returned by the caller.
            self.page = None;
            self.runtime_unavailable = true;
            self.publish_shared();
        }
    }

    /// Attempt a bounded Close for a CreateSession call that returned a reply
    /// only after its cancellation/deadline control became inactive.  No
    /// PageOwner has been installed yet, so a synthetic owner snapshot carries
    /// the newly reserved session identity to runtimes that use it to locate
    /// the just-created WebView.  Failure to confirm Close poisons runtime
    /// admission instead of allowing a second hidden session to be created.
    fn reconcile_unbound_create_failure(
        &mut self,
        _context: &DispatchContext,
        session_id: &str,
        webview_token: &str,
        outcome: HandlerOutcome,
    ) -> HandlerOutcome {
        let now = Instant::now();
        // Reconciliation is deliberately allowed to outlive the original
        // request deadline. Once CreateSession crossed the runtime boundary,
        // a hidden WebView is possible; refusing cleanup merely because the
        // caller's response budget elapsed would leak that owner. The Close
        // itself remains bounded by the independent budget.
        let Some(deadline) = now.checked_add(CREATE_RECONCILIATION_BUDGET) else {
            self.runtime_unavailable = true;
            return outcome;
        };
        let control = RequestControl {
            request_id: format!("{session_id}:create-reconcile"),
            deadline,
            cancelled: false,
            cancellation: CancellationToken::new(),
        };
        let owner = PageOwnerSnapshot {
            session_id: session_id.to_owned(),
            session: SessionMachine::new().snapshot(),
            webview_token: webview_token.to_owned(),
            current_url: "about:blank".to_owned(),
            local_fixture_only: true,
        };
        let closed = self
            .runtime
            .dispatch(Some(&owner), BrowserActorMessage::Close, &control)
            .and_then(|_| control.ensure_active())
            .is_ok();
        if !closed {
            self.runtime_unavailable = true;
        }
        outcome
    }

    /// Reconcile a PageOwner that was installed by a successful CreateSession
    /// after the request's final deadline expired. The response cannot be
    /// committed, so retaining the owner would expose an unacknowledged
    /// session to the next request. Try one independent bounded Close, then
    /// always retire the local marker; failure to confirm the remote close
    /// poisons runtime admission.
    fn reconcile_late_create_after_deadline(&mut self, context: &DispatchContext) {
        let Some(owner) = self.page.as_ref().map(PageOwner::snapshot) else {
            return;
        };
        let Some(deadline) = Instant::now().checked_add(CREATE_RECONCILIATION_BUDGET) else {
            self.runtime_unavailable = true;
            self.page = None;
            self.publish_shared();
            return;
        };
        let control = RequestControl {
            request_id: format!("{}:late-deadline-close", owner.session_id),
            deadline,
            cancelled: false,
            cancellation: CancellationToken::new(),
        };
        let closed = self
            .runtime
            .dispatch(Some(&owner), BrowserActorMessage::Close, &control)
            .and_then(|_| control.ensure_active())
            .is_ok();
        if !closed {
            self.runtime_unavailable = true;
        }
        if self.close_local_page_owner(context).is_err() {
            // Never retain a local owner after an unacknowledged deadline
            // path. Force retirement if a future state-machine change makes
            // the normal Close transition reject this phase.
            self.page = None;
            self.runtime_unavailable = true;
            self.publish_shared();
        }
    }

    /// Apply the fail-closed policy when the final handler deadline expires
    /// after runtime work. Bound operations invalidate references because
    /// their result/effect is no longer observable at the transport boundary;
    /// CreateSession receives a bounded Close, while SessionClose is already
    /// terminal and only needs local retirement if an owner remains.
    fn reconcile_after_final_deadline(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        page_was_present: bool,
    ) {
        if !self.runtime_dispatch_started {
            return;
        }
        match &request.operation {
            BrowserOperation::SessionCreate { .. } if !page_was_present => {
                if self.page.is_some() {
                    self.reconcile_late_create_after_deadline(context);
                }
            }
            BrowserOperation::SessionClose => {
                // A successful Close normally clears the owner before this
                // gate. If a future adapter/transition leaves one behind,
                // retire it and poison admission rather than reusing it.
                if self.page.is_some() {
                    self.runtime_unavailable = true;
                    if self.close_local_page_owner(context).is_err() {
                        self.page = None;
                        self.publish_shared();
                    }
                }
            }
            BrowserOperation::Health => {}
            _ => self.reconcile_indeterminate_page_effect(context),
        }
    }

    fn runtime_unavailable_outcome() -> HandlerOutcome {
        failure(
            BrowserErrorCode::BrowserCrashed,
            "browser runtime is unavailable after an indeterminate session cleanup",
        )
    }

    fn runtime_dispatch(
        &mut self,
        request: &BrowserRequest,
        context: &DispatchContext,
        message: BrowserActorMessage,
    ) -> Result<RuntimeReply, HandlerOutcome> {
        self.runtime_dispatch_status(request, context, message)
            .map_err(|error| error.outcome)
    }

    /// Variant of [`Self::runtime_dispatch`] that retains whether a runtime
    /// interruption may have happened after work started.  Stateful
    /// navigation/actions must reconcile that ambiguity before returning the
    /// original wire failure.
    fn runtime_dispatch_status(
        &mut self,
        request: &BrowserRequest,
        context: &DispatchContext,
        message: BrowserActorMessage,
    ) -> Result<RuntimeReply, RuntimeDispatchError> {
        self.with_runtime_control(request, context, |runtime, owner, control| {
            runtime.dispatch(owner, message, control)
        })
    }

    fn runtime_dispatch_page_act_status(
        &mut self,
        request: &BrowserRequest,
        context: &DispatchContext,
        target: ElementReference,
        action: PageAction,
    ) -> Result<RuntimeReply, RuntimeDispatchError> {
        self.with_runtime_control(request, context, |runtime, owner, control| {
            runtime.dispatch_page_act(owner, target, action, control)
        })
    }

    fn snapshot_result(&self, mut result: JsonObject) -> Result<JsonObject, AgentPortError> {
        let page = self.page.as_ref().ok_or_else(|| {
            AgentPortError::Handler("PageOwner vanished before response binding".to_owned())
        })?;
        let snapshot = page.session.snapshot();
        insert_u64(
            &mut result,
            "document_generation",
            snapshot.revisions.document_generation,
        )?;
        insert_u64(
            &mut result,
            "mutation_epoch",
            snapshot.revisions.mutation_epoch,
        )?;
        insert_u64(
            &mut result,
            "semantic_snapshot_revision",
            snapshot.revisions.semantic_snapshot_revision,
        )?;
        insert_u64(
            &mut result,
            "session_generation",
            snapshot.revisions.session_generation,
        )?;
        result.insert(
            "session_id".to_owned(),
            JsonValue::String(page.session_id.clone()),
        );
        result.insert(
            "webview_token".to_owned(),
            JsonValue::String(page.webview_token.clone()),
        );
        Ok(result)
    }

    /// Finish an observation control section without ever swallowing a
    /// transition error.  The semantic revision event (when requested) is
    /// attempted before `EndAgentObservation`; cleanup is attempted even when
    /// the revision event fails, and the shared snapshot is published before
    /// returning an error so callers can reconcile a possibly-held control
    /// state.  This is intentionally fail-closed: an inability to release
    /// agent control is surfaced as a handler error rather than allowing a
    /// success/failure response to pretend the PageOwner is idle.
    fn finish_agent_observation(
        &mut self,
        now_ms: u64,
        operation: &'static str,
        publish_semantic_snapshot: bool,
    ) -> Result<(), AgentPortError> {
        // `with_runtime_control` transitions BrowserCrashed failures into
        // Recovering and clears Agent control.  There is no observation
        // control left to release in that state; attempting EndAgentObservation
        // would mask the original crash with a cleanup conflict.
        if self.page_is_recovering() {
            self.publish_shared();
            return Ok(());
        }
        let mut errors = Vec::new();
        {
            let page = self.page.as_mut().expect("PageOwner exists");
            if publish_semantic_snapshot
                && let Err(error) = page
                    .session
                    .apply(SessionEvent::SemanticSnapshotPublished, now_ms)
            {
                errors.push(format!(
                    "{operation} semantic snapshot transition failed: {error}"
                ));
            }
            if let Err(error) = page
                .session
                .apply(SessionEvent::EndAgentObservation, now_ms)
            {
                errors.push(format!("{operation} observation cleanup failed: {error}"));
            }
        }
        self.publish_shared();
        if errors.is_empty() {
            Ok(())
        } else {
            Err(AgentPortError::Handler(errors.join("; ")))
        }
    }

    /// Finish a mutation control section with the same fail-closed semantics
    /// as [`Self::finish_agent_observation`].  `DomCommitted` is attempted
    /// before releasing the mutation control; even if it fails, the release
    /// transition is still attempted and the resulting state is published.
    fn finish_agent_mutation(
        &mut self,
        now_ms: u64,
        operation: &'static str,
        commit_dom: bool,
    ) -> Result<(), AgentPortError> {
        // See `finish_agent_observation`: a crash already revoked the active
        // mutation control and made the PageOwner non-presentable.
        if self.page_is_recovering() {
            self.publish_shared();
            return Ok(());
        }
        let mut errors = Vec::new();
        {
            let page = self.page.as_mut().expect("PageOwner exists");
            if commit_dom && let Err(error) = page.session.apply(SessionEvent::DomCommitted, now_ms)
            {
                errors.push(format!("{operation} DOM commit transition failed: {error}"));
            }
            if let Err(error) = page.session.apply(SessionEvent::EndAgentMutation, now_ms) {
                errors.push(format!("{operation} mutation cleanup failed: {error}"));
            }
        }
        self.publish_shared();
        if errors.is_empty() {
            Ok(())
        } else {
            Err(AgentPortError::Handler(errors.join("; ")))
        }
    }

    fn finish_observation_checked(
        &mut self,
        context: &DispatchContext,
        now_ms: u64,
        operation: &'static str,
        publish_semantic_snapshot: bool,
    ) -> Result<(), AgentPortError> {
        let result = self.finish_agent_observation(now_ms, operation, publish_semantic_snapshot);
        if result.is_err() && self.page_revision_near_wire_ceiling() {
            // A failed revision transition must not leave an owner that can
            // dispatch again and only fail while encoding its response.
            let _ = self.retire_terminal_revision_owner(context);
        }
        result
    }

    fn finish_mutation_checked(
        &mut self,
        context: &DispatchContext,
        now_ms: u64,
        operation: &'static str,
        commit_dom: bool,
    ) -> Result<(), AgentPortError> {
        let result = self.finish_agent_mutation(now_ms, operation, commit_dom);
        if result.is_err() && self.page_revision_near_wire_ceiling() {
            let _ = self.retire_terminal_revision_owner(context);
        }
        result
    }
}

impl<R: PageRuntime> BrowserActor<R> {
    fn handle_inner(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        // Actor dispatch is synchronous, so this per-request marker is reset
        // before any validation. It is set only immediately before a runtime
        // adapter call and consumed by the final deadline reconciliation.
        self.runtime_dispatch_started = false;
        if let Err(error) = self.binding.verify_dispatch_peer(context.peer) {
            return Ok(failure(
                BrowserErrorCode::PolicyDenied,
                &format!("semantic principal binding rejected transport peer: {error}"),
            ));
        }
        context.remaining()?;
        // A failed reconciliation means the runtime may still own a hidden
        // WebView/session that is no longer represented by `self.page`.
        // Refuse every new operation (except a final SessionClose when a
        // local owner is still present) until the containing process is
        // restarted or an explicit recovery path replaces the runtime.
        if self.runtime_unavailable && !matches!(request.operation, BrowserOperation::SessionClose)
        {
            return Ok(Self::runtime_unavailable_outcome());
        }
        if !matches!(
            &request.operation,
            BrowserOperation::Health
                | BrowserOperation::SessionCreate { .. }
                | BrowserOperation::SessionClose
        ) && self.page_revision_near_wire_ceiling()
        {
            return Ok(self.retire_terminal_revision_owner(context));
        }
        if !matches!(
            &request.operation,
            BrowserOperation::Health | BrowserOperation::SessionCreate { .. }
        ) && let Err(outcome) = self.verify_bound_request(request)
        {
            return Ok(outcome);
        }

        let page_was_present = self.page.is_some();
        let outcome = match &request.operation {
            BrowserOperation::Health => {
                let reply = self.runtime_dispatch(request, context, BrowserActorMessage::Health);
                match reply {
                    Ok(reply) => {
                        let mut result = reply.result;
                        result.insert(
                            "principal_id".to_owned(),
                            JsonValue::String(self.binding.principal.principal_id.clone()),
                        );
                        result.insert(
                            "session_active".to_owned(),
                            JsonValue::Bool(self.page.is_some()),
                        );
                        HandlerOutcome::Success(result)
                    }
                    Err(outcome) => outcome,
                }
            }
            BrowserOperation::SessionCreate { profile, ui_mode } => {
                if ui_mode != "headed" {
                    failure(BrowserErrorCode::InvalidRequest, "ui_mode must be headed")
                } else if profile.persistence != ProfilePersistence::Ephemeral {
                    failure(
                        BrowserErrorCode::PolicyDenied,
                        "persistent profiles remain closed in the D3 development profile",
                    )
                } else if self.page.is_some() {
                    failure(
                        BrowserErrorCode::PolicyDenied,
                        "one BrowserActor may own only one active PageOwner",
                    )
                } else {
                    // Session and WebView tokens are identity material, not
                    // best-effort metrics.  Saturating here would eventually
                    // reuse the same pair after a close/recreate cycle once
                    // either counter reached `u64::MAX`, making old receipts
                    // and stale callers ambiguous.  Reserve both successors
                    // before mutating either counter or dispatching runtime
                    // work, and fail closed when the identity space is
                    // exhausted.
                    let Some(next_session_counter) = self.session_counter.checked_add(1) else {
                        return Ok(failure(
                            BrowserErrorCode::Internal,
                            "session identity counter exhausted",
                        ));
                    };
                    let Some(next_webview_counter) = self.webview_counter.checked_add(1) else {
                        return Ok(failure(
                            BrowserErrorCode::Internal,
                            "WebView identity counter exhausted",
                        ));
                    };
                    self.session_counter = next_session_counter;
                    self.webview_counter = next_webview_counter;
                    let session_id = format!(
                        "session-{}-{}",
                        self.binding.mechanism.peer.uid, self.session_counter
                    );
                    let webview_token = format!("webview-{}", self.webview_counter);
                    validate_token("session_id", &session_id, 128)
                        .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                    validate_token("webview_token", &webview_token, MAX_WEBVIEW_TOKEN_BYTES)
                        .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                    let reply = match self.runtime_dispatch_status(
                        request,
                        context,
                        BrowserActorMessage::CreateSession {
                            session_id: session_id.clone(),
                            profile: profile.clone(),
                        },
                    ) {
                        Ok(reply) => reply,
                        Err(error) => {
                            let should_reconcile = error.effect_may_have_started;
                            let outcome = error.outcome;
                            if should_reconcile {
                                return Ok(self.reconcile_unbound_create_failure(
                                    context,
                                    &session_id,
                                    &webview_token,
                                    outcome,
                                ));
                            }
                            return Ok(outcome);
                        }
                    };
                    self.page = Some(PageOwner {
                        session_id,
                        session: SessionMachine::new(),
                        webview_token,
                        current_url: reply
                            .current_url
                            .unwrap_or_else(|| "about:blank".to_owned()),
                        local_fixture_only: true,
                    });
                    self.publish_shared();
                    HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                }
            }
            BrowserOperation::SessionSnapshot => {
                let now_ms = monotonic_request_ms(context);
                if let Err(error) = self
                    .page
                    .as_mut()
                    .expect("bound request has PageOwner")
                    .session
                    .apply(SessionEvent::BeginAgentObservation, now_ms)
                {
                    transition_failure(error)
                } else {
                    let reply = self.runtime_dispatch_status(
                        request,
                        context,
                        BrowserActorMessage::Snapshot,
                    );
                    match reply {
                        Ok(reply) => {
                            self.finish_observation_checked(
                                context,
                                now_ms,
                                "SessionSnapshot",
                                false,
                            )?;
                            let page = self.page.as_mut().expect("PageOwner exists");
                            if let Some(url) = reply.current_url {
                                page.current_url = url;
                            }
                            self.publish_shared();
                            HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                        }
                        Err(error) => {
                            let effect_may_have_started = error.effect_may_have_started;
                            let outcome = error.outcome;
                            if effect_may_have_started {
                                self.reconcile_indeterminate_page_effect(context);
                            }
                            self.finish_observation_checked(
                                context,
                                now_ms,
                                "SessionSnapshot",
                                false,
                            )?;
                            outcome
                        }
                    }
                }
            }
            BrowserOperation::SessionClose => {
                let reply = self.runtime_dispatch(request, context, BrowserActorMessage::Close);
                match reply {
                    Ok(reply) => {
                        let session_id = self.close_local_page_owner(context)?;
                        let mut result = reply.result;
                        result.insert("session_id".to_owned(), JsonValue::String(session_id));
                        HandlerOutcome::Success(result)
                    }
                    Err(outcome) => {
                        // `session_close` is terminal cleanup.  Any runtime
                        // failure (including policy/unsupported/internal)
                        // leaves the remote close outcome unknown, so never
                        // retain a locally Ready owner that could be reused
                        // against a hidden WebView.  Preserve the original
                        // wire failure and poison runtime admission if the
                        // local retirement itself cannot be confirmed.
                        self.runtime_unavailable = true;
                        if self.page.is_some() && self.close_local_page_owner(context).is_err() {
                            self.page = None;
                            self.publish_shared();
                        }
                        outcome
                    }
                }
            }
            BrowserOperation::PageNavigate {
                target,
                expected_document_generation,
            } => {
                let page_snapshot = self.page.as_ref().expect("PageOwner exists").snapshot();
                if page_snapshot.session.revisions.document_generation
                    != *expected_document_generation
                {
                    failure(
                        BrowserErrorCode::StaleDocument,
                        "expected_document_generation is stale",
                    )
                } else {
                    let url = match target {
                        NavigationTarget::LocalHttpFixture { url } if is_loopback_http(url) => {
                            url.clone()
                        }
                        NavigationTarget::LocalHttpFixture { .. } => {
                            return Ok(failure(
                                BrowserErrorCode::PolicyDenied,
                                "local fixture URL is not loopback HTTP",
                            ));
                        }
                        NavigationTarget::TrustedShell
                        | NavigationTarget::TrustedApp { .. }
                        | NavigationTarget::ExternalHttps { .. } => {
                            return Ok(failure(
                                BrowserErrorCode::PolicyDenied,
                                "trusted-app and external navigation remain closed before D5/D6",
                            ));
                        }
                    };
                    let now_ms = monotonic_request_ms(context);
                    if let Err(error) = self.page.as_mut().expect("PageOwner exists").session.apply(
                        SessionEvent::NavigationStarted {
                            source: ControlSource::Agent,
                        },
                        now_ms,
                    ) {
                        transition_failure(error)
                    } else {
                        let reply = self.runtime_dispatch_status(
                            request,
                            context,
                            BrowserActorMessage::Navigate {
                                url,
                                expected_document_generation: *expected_document_generation,
                            },
                        );
                        match reply {
                            Ok(reply) => {
                                let transition = self
                                    .page
                                    .as_mut()
                                    .expect("PageOwner exists")
                                    .session
                                    .apply(SessionEvent::NavigationCommitted, now_ms);
                                self.publish_shared();
                                if let Err(error) = transition {
                                    if matches!(error, TransitionError::RevisionExhausted) {
                                        return Ok(self.retire_terminal_revision_owner(context));
                                    }
                                    return Err(AgentPortError::Handler(format!(
                                        "PageNavigate commit transition failed: {error}"
                                    )));
                                }
                                let page = self.page.as_mut().expect("PageOwner exists");
                                if let Some(url) = reply.current_url {
                                    page.current_url = url;
                                }
                                self.publish_shared();
                                HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                            }
                            Err(error) => {
                                let effect_may_have_started = error.effect_may_have_started;
                                let outcome = error.outcome;
                                // A runtime crash already moved the session
                                // into `Recovering`; a late navigation
                                // failure must not transition it back to
                                // Ready or hide the invalidation boundary.
                                if effect_may_have_started {
                                    // Cancellation/deadline/internal errors
                                    // can arrive after the browser committed
                                    // a document change.  Treat the result as
                                    // indeterminate and invalidate all
                                    // references instead of applying the
                                    // ordinary failure transition.
                                    self.reconcile_indeterminate_page_effect(context);
                                    self.publish_shared();
                                    outcome
                                } else if self.page_is_recovering()
                                    || matches!(
                                        &outcome,
                                        HandlerOutcome::Failure(error)
                                            if error.code == BrowserErrorCode::BrowserCrashed
                                    )
                                {
                                    self.publish_shared();
                                    outcome
                                } else {
                                    let transition = self
                                        .page
                                        .as_mut()
                                        .expect("PageOwner exists")
                                        .session
                                        .apply(SessionEvent::NavigationFailed, now_ms);
                                    self.publish_shared();
                                    transition.map_err(|error| {
                                        AgentPortError::Handler(format!(
                                            "PageNavigate failure transition failed: {error}"
                                        ))
                                    })?;
                                    outcome
                                }
                            }
                        }
                    }
                }
            }
            BrowserOperation::PageObserve { fields } => {
                let now_ms = monotonic_request_ms(context);
                if let Err(error) = self
                    .page
                    .as_mut()
                    .expect("PageOwner exists")
                    .session
                    .apply(SessionEvent::BeginAgentObservation, now_ms)
                {
                    transition_failure(error)
                } else {
                    let reply = self.runtime_dispatch_status(
                        request,
                        context,
                        BrowserActorMessage::Observe {
                            fields: fields.clone(),
                        },
                    );
                    match reply {
                        Ok(reply) => {
                            self.finish_observation_checked(context, now_ms, "PageObserve", true)?;
                            let page = self.page.as_mut().expect("PageOwner exists");
                            if let Some(url) = reply.current_url {
                                page.current_url = url;
                            }
                            self.publish_shared();
                            HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                        }
                        Err(error) => {
                            let effect_may_have_started = error.effect_may_have_started;
                            let outcome = error.outcome;
                            if effect_may_have_started {
                                self.reconcile_indeterminate_page_effect(context);
                            }
                            self.finish_observation_checked(context, now_ms, "PageObserve", false)?;
                            outcome
                        }
                    }
                }
            }
            BrowserOperation::PageAct { target, action } => {
                let freshness = {
                    let revisions = self
                        .page
                        .as_ref()
                        .expect("PageOwner exists")
                        .session
                        .snapshot()
                        .revisions;
                    reference_error(target, revisions)
                };
                if let Some(error) = freshness {
                    failure(error, "element reference is stale")
                } else {
                    let now_ms = monotonic_request_ms(context);
                    if let Err(error) = self
                        .page
                        .as_mut()
                        .expect("PageOwner exists")
                        .session
                        .apply(SessionEvent::BeginAgentMutation, now_ms)
                    {
                        transition_failure(error)
                    } else {
                        let reply = self.runtime_dispatch_page_act_status(
                            request,
                            context,
                            target.clone(),
                            action.clone(),
                        );
                        match reply {
                            Ok(reply) => {
                                self.finish_mutation_checked(context, now_ms, "PageAct", true)?;
                                HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                            }
                            Err(error) => {
                                let effect_may_have_started = error.effect_may_have_started;
                                let outcome = error.outcome;
                                if effect_may_have_started {
                                    // A semantic action may have mutated the
                                    // DOM before cancellation/deadline/error
                                    // was observed.  Do not release the
                                    // mutation as a normal failed operation;
                                    // move the owner into recovery so all
                                    // element references become stale.
                                    self.reconcile_indeterminate_page_effect(context);
                                    self.finish_mutation_checked(
                                        context, now_ms, "PageAct", false,
                                    )?;
                                } else {
                                    self.finish_mutation_checked(
                                        context, now_ms, "PageAct", false,
                                    )?;
                                }
                                outcome
                            }
                        }
                    }
                }
            }
            BrowserOperation::PageWait {
                condition,
                timeout_ms,
            } => {
                let freshness = {
                    let revisions = self
                        .page
                        .as_ref()
                        .expect("PageOwner exists")
                        .session
                        .snapshot()
                        .revisions;
                    wait_condition_reference_error(condition, revisions)
                };
                if let Some(error) = freshness {
                    failure(error, "element reference is stale")
                } else {
                    let remaining = context.remaining()?;
                    let timeout = Duration::from_millis(*timeout_ms).min(remaining);
                    let now_ms = monotonic_request_ms(context);
                    if let Err(error) = self
                        .page
                        .as_mut()
                        .expect("PageOwner exists")
                        .session
                        .apply(SessionEvent::BeginAgentObservation, now_ms)
                    {
                        transition_failure(error)
                    } else {
                        let reply = self.runtime_dispatch_status(
                            request,
                            context,
                            BrowserActorMessage::Wait {
                                condition: condition.clone(),
                                timeout,
                            },
                        );
                        match reply {
                            Ok(reply) => {
                                self.finish_observation_checked(
                                    context, now_ms, "PageWait", false,
                                )?;
                                HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                            }
                            Err(error) => {
                                let effect_may_have_started = error.effect_may_have_started;
                                let outcome = error.outcome;
                                if effect_may_have_started {
                                    self.reconcile_indeterminate_page_effect(context);
                                }
                                self.finish_observation_checked(
                                    context, now_ms, "PageWait", false,
                                )?;
                                outcome
                            }
                        }
                    }
                }
            }
            BrowserOperation::PageExtract { schema_id } => {
                let now_ms = monotonic_request_ms(context);
                if let Err(error) = self
                    .page
                    .as_mut()
                    .expect("PageOwner exists")
                    .session
                    .apply(SessionEvent::BeginAgentObservation, now_ms)
                {
                    transition_failure(error)
                } else {
                    let reply = self.runtime_dispatch_status(
                        request,
                        context,
                        BrowserActorMessage::Extract {
                            schema_id: schema_id.clone(),
                        },
                    );
                    match reply {
                        Ok(reply) => {
                            self.finish_observation_checked(context, now_ms, "PageExtract", false)?;
                            HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                        }
                        Err(error) => {
                            let effect_may_have_started = error.effect_may_have_started;
                            let outcome = error.outcome;
                            if effect_may_have_started {
                                self.reconcile_indeterminate_page_effect(context);
                            }
                            self.finish_observation_checked(context, now_ms, "PageExtract", false)?;
                            outcome
                        }
                    }
                }
            }
        };
        if let Err(error) = context.remaining() {
            self.reconcile_after_final_deadline(context, request, page_was_present);
            return Err(error);
        }
        Ok(outcome)
    }
}

impl<R: PageRuntime> BrowserRequestHandler for BrowserActor<R> {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        let request_id = request.request_id.clone();
        self.with_request_cancellation(&request_id, |actor| actor.handle_inner(context, request))
    }
}

pub struct ReceiptLifecycleObserver {
    journal: ReceiptJournal,
    image_id: String,
    principal_id: String,
    shared: Rc<RefCell<SharedActorState>>,
    inflight: BTreeMap<String, ReceiptCoordinates>,
    logical_clock: u64,
}

impl ReceiptLifecycleObserver {
    pub fn inspect(&mut self) -> Result<hepta_session_core::RecoveryReport, JournalError> {
        self.journal.inspect()
    }

    pub fn journal_path(&self) -> &std::path::Path {
        self.journal.path()
    }

    fn coordinates(&self, _request: &BrowserRequest) -> ReceiptCoordinates {
        let page = self.shared.borrow().page.clone();
        let fallback = ReceiptCoordinates {
            session_id: "pre-session".to_owned(),
            session_generation: 1,
            document_generation: 1,
            semantic_snapshot_revision: 0,
            mutation_epoch: 0,
        };
        let Some(page) = page else {
            return fallback;
        };
        let revisions = page.session.revisions;
        ReceiptCoordinates {
            // Once a PageOwner exists, its identity and revision tuple are
            // authoritative.  The observer runs before the handler's
            // session-binding gate, so copying caller-supplied values here
            // would let a stale/foreign request emit a receipt tagged as an
            // arbitrary session or generation.  Keep request fields out of
            // the durable coordinates; only the pre-session fallback above
            // lacks an owner from which to derive them.
            session_id: page.session_id,
            session_generation: revisions.session_generation,
            document_generation: revisions.document_generation,
            semantic_snapshot_revision: revisions.semantic_snapshot_revision,
            mutation_epoch: revisions.mutation_epoch,
        }
    }

    fn append(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        lifecycle: ReceiptLifecycleState,
        outcome: Option<ReceiptOutcome>,
        response_sha256: Option<&str>,
        error_code: Option<&str>,
    ) -> Result<(), AgentPortError> {
        // The logical timestamp is part of the durable lifecycle ordering.
        // Saturating here would eventually repeat the same timestamp forever,
        // making an exhausted observer indistinguishable from a live one.
        // Reserve the successor before constructing or appending the record;
        // on exhaustion fail closed without writing a partial event.
        let next_clock = self
            .logical_clock
            .checked_add(1)
            .ok_or_else(|| AgentPortError::Handler("receipt logical clock exhausted".to_owned()))?;
        let coordinates = self
            .inflight
            .get(&request.request_id)
            .cloned()
            .unwrap_or_else(|| self.coordinates(request));
        let event = ReceiptEvent {
            receipt_id: request.request_id.clone(),
            plan_revision: D3_PLAN_REVISION.to_owned(),
            image_id: self.image_id.clone(),
            servo_commit: D3_SERVO_COMMIT.to_owned(),
            browserd_version: D3_BROWSERD_VERSION.to_owned(),
            session_id: coordinates.session_id,
            session_generation: coordinates.session_generation,
            document_generation: coordinates.document_generation,
            semantic_snapshot_revision: coordinates.semantic_snapshot_revision,
            mutation_epoch: coordinates.mutation_epoch,
            source: ReceiptSource::Agent,
            operation: operation_name(&request.operation).to_owned(),
            lifecycle,
            outcome,
            effect_class: receipt_effect_class(context.effect_class),
            privacy_class: PrivacyClass::Internal,
            request_sha256: parse_digest(&context.canonical_request_sha256)?,
            response_sha256: response_sha256.map(parse_digest).transpose()?,
            error_code: error_code.map(str::to_owned),
            detail: Some(format!("principal={}", self.principal_id)),
            monotonic_ms: next_clock,
            wall_clock_unix_ms: wall_clock_unix_ms()?,
        };
        self.journal
            .append(event)
            .map_err(|error| AgentPortError::Handler(format!("receipt journal failed: {error}")))?;
        self.logical_clock = next_clock;
        Ok(())
    }
}

impl OperationLifecycleObserver for ReceiptLifecycleObserver {
    fn requested(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<(), AgentPortError> {
        let coordinates = self.coordinates(request);
        if self
            .inflight
            .insert(request.request_id.clone(), coordinates)
            .is_some()
        {
            return Err(AgentPortError::Handler(
                "duplicate in-flight receipt identifier".to_owned(),
            ));
        }
        // Roll back the in-memory admission marker when the durable first
        // record cannot be written.  The observer may be reused by a caller
        // after a transient journal/validation failure; retaining the marker
        // would make a later request with the same ID fail as a false
        // duplicate even though no receipt was admitted.
        let result = self.append(
            context,
            request,
            ReceiptLifecycleState::Requested,
            None,
            None,
            None,
        );
        if result.is_err() {
            self.inflight.remove(&request.request_id);
        }
        result
    }

    fn dispatched(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<(), AgentPortError> {
        let result = self.append(
            context,
            request,
            ReceiptLifecycleState::Dispatched,
            None,
            None,
            None,
        );
        if result.is_err() {
            // If the lifecycle append failed before a durable dispatched
            // record was confirmed, do not leave a stale in-memory admission
            // marker that poisons observer reuse.  A durable Requested record
            // (when present) remains authoritative; a caller must reconcile
            // or retry the dispatched transition against that journal state.
            self.inflight.remove(&request.request_id);
        }
        result
    }

    fn completed(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        response: &BrowserResponse,
        canonical_response_sha256: &str,
    ) -> Result<(), AgentPortError> {
        // A runtime failure after a potential external effect may have raced
        // the cancellation/deadline/crash boundary.  The wire response is
        // still returned to the caller, but the durable receipt must not claim
        // that the effect failed (or was rolled back) when its outcome is not
        // observable.  Recovery therefore sees an indeterminate terminal
        // state and never retries it automatically.
        let result = match &response.outcome {
            Err(error)
                if context.effect_class == EffectClass::PotentialExternalEffect
                    && potential_effect_outcome_is_unknown(error.code) =>
            {
                self.append(
                    context,
                    request,
                    ReceiptLifecycleState::Indeterminate,
                    None,
                    None,
                    Some(error.code.as_str()),
                )
            }
            Ok(_) => self.append(
                context,
                request,
                ReceiptLifecycleState::Completed,
                Some(ReceiptOutcome::Succeeded),
                Some(canonical_response_sha256),
                None,
            ),
            Err(error) => {
                let outcome = match error.code {
                    BrowserErrorCode::PolicyDenied | BrowserErrorCode::Unsupported => {
                        ReceiptOutcome::Refused
                    }
                    BrowserErrorCode::Cancelled => ReceiptOutcome::Cancelled,
                    _ => ReceiptOutcome::Failed,
                };
                self.append(
                    context,
                    request,
                    ReceiptLifecycleState::Completed,
                    Some(outcome),
                    Some(canonical_response_sha256),
                    Some(error.code.as_str()),
                )
            }
        };
        self.inflight.remove(&request.request_id);
        result
    }

    fn interrupted(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        error: &AgentPortError,
    ) -> Result<(), AgentPortError> {
        let lifecycle = if context.effect_class == EffectClass::PotentialExternalEffect {
            ReceiptLifecycleState::Indeterminate
        } else {
            ReceiptLifecycleState::Interrupted
        };
        let code = match error {
            AgentPortError::DeadlineExceeded => BrowserErrorCode::DeadlineExceeded.as_str(),
            _ => BrowserErrorCode::Internal.as_str(),
        };
        let result = self.append(context, request, lifecycle, None, None, Some(code));
        self.inflight.remove(&request.request_id);
        result
    }
}

fn failure(code: BrowserErrorCode, message: &str) -> HandlerOutcome {
    HandlerOutcome::Failure(BrowserWireError {
        code,
        message: message.to_owned(),
        details: None,
    })
}

fn runtime_failure(error: RuntimeFailure) -> HandlerOutcome {
    match error {
        RuntimeFailure::PolicyDenied(message) => failure(BrowserErrorCode::PolicyDenied, message),
        RuntimeFailure::Unsupported(message) => failure(BrowserErrorCode::Unsupported, message),
        RuntimeFailure::Cancelled => failure(BrowserErrorCode::Cancelled, "request cancelled"),
        RuntimeFailure::DeadlineExceeded => failure(
            BrowserErrorCode::DeadlineExceeded,
            "request deadline exceeded",
        ),
        RuntimeFailure::BrowserCrashed => {
            failure(BrowserErrorCode::BrowserCrashed, "browser runtime crashed")
        }
        RuntimeFailure::Internal(message) => failure(BrowserErrorCode::Internal, &message),
    }
}

fn potential_effect_outcome_is_unknown(code: BrowserErrorCode) -> bool {
    matches!(
        code,
        BrowserErrorCode::Cancelled
            | BrowserErrorCode::DeadlineExceeded
            | BrowserErrorCode::BrowserCrashed
            | BrowserErrorCode::Indeterminate
            | BrowserErrorCode::Internal
    )
}

fn transition_failure(error: TransitionError) -> HandlerOutcome {
    match error {
        TransitionError::ControlConflict(ControlState::HumanActive) => failure(
            BrowserErrorCode::HumanControlActive,
            "human control lease is active",
        ),
        TransitionError::ControlConflict(ControlState::HumanImeComposing) => failure(
            BrowserErrorCode::ImeCompositionActive,
            "human IME composition is active",
        ),
        TransitionError::ControlConflict(ControlState::AgentNavigating) => failure(
            BrowserErrorCode::NavigationInProgress,
            "Agent navigation is already in progress",
        ),
        TransitionError::PhaseConflict(SessionPhase::ModalBlocked) => failure(
            BrowserErrorCode::ModalBlocked,
            "a modal blocks the PageOwner",
        ),
        TransitionError::PhaseConflict(SessionPhase::NavigationPending) => failure(
            BrowserErrorCode::NavigationInProgress,
            "navigation is already in progress",
        ),
        TransitionError::PhaseConflict(SessionPhase::CapabilityPending) => failure(
            BrowserErrorCode::CapabilityPending,
            "capability decision is pending",
        ),
        TransitionError::PhaseConflict(SessionPhase::Recovering) => failure(
            BrowserErrorCode::BrowserCrashed,
            "PageOwner is recovering from a browser crash",
        ),
        TransitionError::PhaseConflict(SessionPhase::Cancelling) => failure(
            BrowserErrorCode::Cancelled,
            "PageOwner is reconciling a cancelled operation",
        ),
        TransitionError::Closed => failure(
            BrowserErrorCode::StaleSession,
            "PageOwner session is closed",
        ),
        other => failure(BrowserErrorCode::Internal, &other.to_string()),
    }
}

fn reference_error(
    target: &ElementReference,
    revisions: RevisionClock,
) -> Option<BrowserErrorCode> {
    match classify_reference(
        revisions,
        target.session_generation,
        target.document_generation,
        target.semantic_snapshot_revision,
    ) {
        RefFreshness::Current => None,
        RefFreshness::StaleSession => Some(BrowserErrorCode::StaleSession),
        RefFreshness::StaleDocument => Some(BrowserErrorCode::StaleDocument),
        RefFreshness::StaleSnapshot => Some(BrowserErrorCode::StaleSnapshot),
    }
}

fn wait_condition_reference_error(
    condition: &WaitCondition,
    revisions: RevisionClock,
) -> Option<BrowserErrorCode> {
    match condition {
        WaitCondition::ElementPresent { target } => reference_error(target, revisions),
        WaitCondition::DocumentReady
        | WaitCondition::UrlEquals { .. }
        | WaitCondition::TextPresent { .. }
        | WaitCondition::NetworkIdle { .. } => None,
    }
}

fn receipt_effect_class(effect: EffectClass) -> ReceiptEffectClass {
    match effect {
        EffectClass::Observation => ReceiptEffectClass::Observation,
        EffectClass::LocalInteraction => ReceiptEffectClass::LocalInteraction,
        EffectClass::PotentialExternalEffect => ReceiptEffectClass::PotentialExternalEffect,
    }
}

fn operation_name(operation: &BrowserOperation) -> &'static str {
    match operation {
        BrowserOperation::Health => "health",
        BrowserOperation::SessionCreate { .. } => "session_create",
        BrowserOperation::SessionSnapshot => "session_snapshot",
        BrowserOperation::SessionClose => "session_close",
        BrowserOperation::PageNavigate { .. } => "page_navigate",
        BrowserOperation::PageObserve { .. } => "page_observe",
        BrowserOperation::PageAct { .. } => "page_act",
        BrowserOperation::PageWait { .. } => "page_wait",
        BrowserOperation::PageExtract { .. } => "page_extract",
    }
}

fn observation_field_name(field: ObservationField) -> &'static str {
    match field {
        ObservationField::Role => "role",
        ObservationField::Name => "name",
        ObservationField::Text => "text",
        ObservationField::Href => "href",
        ObservationField::Bounds => "bounds",
    }
}

fn wait_condition_name(condition: &WaitCondition) -> &'static str {
    match condition {
        WaitCondition::DocumentReady => "document_ready",
        WaitCondition::UrlEquals { .. } => "url_equals",
        WaitCondition::ElementPresent { .. } => "element_present",
        WaitCondition::TextPresent { .. } => "text_present",
        WaitCondition::NetworkIdle { .. } => "network_idle",
    }
}

fn is_loopback_http(url: &str) -> bool {
    if url.is_empty()
        || url.len() > MAX_LOOPBACK_URL_BYTES
        || url
            .chars()
            .any(|character| character <= '\u{001f}' || character == '\u{007f}')
    {
        return false;
    }
    let Some(remainder) = url.strip_prefix("http://") else {
        return false;
    };
    let authority_end = remainder.find(['/', '?', '#']).unwrap_or(remainder.len());
    let authority = &remainder[..authority_end];
    if authority.is_empty() || authority.contains(['@', '\\']) {
        return false;
    }

    if let Some(rest) = authority.strip_prefix('[') {
        let Some(close) = rest.find(']') else {
            return false;
        };
        // Keep this in lockstep with the codec's loopback policy: only the
        // canonical bracketed `::1` spelling is admitted.
        if &rest[..close] != "::1" {
            return false;
        }
        valid_loopback_port_suffix(&rest[close + 1..])
    } else {
        if authority.matches(':').count() > 1 {
            return false;
        }
        let (host, port) = match authority.rsplit_once(':') {
            Some((host, port)) => (host, Some(port)),
            None => (authority, None),
        };
        if !host.eq_ignore_ascii_case("localhost") && host != "127.0.0.1" {
            return false;
        }
        port.is_none_or(valid_loopback_port)
    }
}

fn valid_loopback_port_suffix(suffix: &str) -> bool {
    suffix.is_empty() || suffix.strip_prefix(':').is_some_and(valid_loopback_port)
}

fn valid_loopback_port(port: &str) -> bool {
    !port.is_empty()
        && port.len() <= 5
        && port.bytes().all(|byte| byte.is_ascii_digit())
        && port.parse::<u16>().is_ok()
}

fn json_object<const N: usize>(entries: [(&str, JsonValue); N]) -> JsonObject {
    entries
        .into_iter()
        .map(|(key, value)| (key.to_owned(), value))
        .collect()
}

fn json_u64(value: u64) -> Result<JsonValue, RuntimeFailure> {
    i64::try_from(value)
        .map(JsonValue::Integer)
        .map_err(|_| RuntimeFailure::Internal("integer exceeds Browser API range".to_owned()))
}

fn insert_u64(object: &mut JsonObject, key: &str, value: u64) -> Result<(), AgentPortError> {
    let value = i64::try_from(value)
        .map_err(|_| AgentPortError::Handler(format!("{key} exceeds Browser API range")))?;
    object.insert(key.to_owned(), JsonValue::Integer(value));
    Ok(())
}

fn revision_clock_near_wire_ceiling(revisions: RevisionClock) -> bool {
    // Stateful operations may advance one or more layers after runtime work,
    // and an indeterminate outcome may need one additional recovery advance.
    // Reserve one representable value so neither path can reach i64::MAX and
    // fail only while constructing the response envelope.
    const LAST_SAFE: u64 = i64::MAX as u64 - 1;
    [
        revisions.session_generation,
        revisions.document_generation,
        revisions.semantic_snapshot_revision,
        revisions.mutation_epoch,
    ]
    .into_iter()
    .any(|revision| revision >= LAST_SAFE)
}

fn monotonic_request_ms(context: &DispatchContext) -> u64 {
    u64::try_from(context.accepted_at.elapsed().as_millis()).unwrap_or(u64::MAX)
}

fn wall_clock_unix_ms() -> Result<u64, AgentPortError> {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| AgentPortError::ClockBeforeUnixEpoch)?
        .as_millis();
    u64::try_from(millis).map_err(|_| AgentPortError::ClockBeforeUnixEpoch)
}

fn parse_digest(value: &str) -> Result<[u8; 32], AgentPortError> {
    if value.len() != 64 {
        return Err(AgentPortError::Handler("invalid SHA-256 length".to_owned()));
    }
    let mut output = [0_u8; 32];
    for (index, chunk) in value.as_bytes().chunks_exact(2).enumerate() {
        let high = hex_nibble(chunk[0])?;
        let low = hex_nibble(chunk[1])?;
        output[index] = (high << 4) | low;
    }
    if output == [0; 32] {
        return Err(AgentPortError::Handler(
            "all-zero SHA-256 is forbidden".to_owned(),
        ));
    }
    Ok(output)
}

fn hex_nibble(value: u8) -> Result<u8, AgentPortError> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        _ => Err(AgentPortError::Handler(
            "SHA-256 must be lowercase hexadecimal".to_owned(),
        )),
    }
}

fn validate_token(
    field: &'static str,
    value: &str,
    maximum: usize,
) -> Result<(), PrincipalBindingError> {
    if value.is_empty()
        || value.len() > maximum
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b':'))
    {
        return Err(PrincipalBindingError::InvalidField(field));
    }
    Ok(())
}

fn validate_text(
    field: &'static str,
    value: &str,
    maximum: usize,
) -> Result<(), PrincipalBindingError> {
    if value.is_empty() || value.len() > maximum || value.chars().any(char::is_control) {
        return Err(PrincipalBindingError::InvalidField(field));
    }
    Ok(())
}

fn validate_sha256(value: &str) -> Result<(), PrincipalBindingError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
        || value.bytes().all(|byte| byte == b'0')
    {
        return Err(PrincipalBindingError::InvalidField(
            "expected_executable_sha256",
        ));
    }
    Ok(())
}

pub fn executable_sha256(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut output = String::with_capacity(64);
    for byte in digest {
        use std::fmt::Write as _;
        let _ = write!(output, "{byte:02x}");
    }
    output
}

/// Deterministic host self-check for the D3 ownership and policy boundary.
pub fn self_check() -> Result<(), String> {
    let peer = PeerIdentity {
        pid: Some(std::process::id()),
        uid: 1000,
        gid: 1001,
    };
    let digest = executable_sha256(b"hepta-browser-actor-self-check");
    let binding = PrincipalBinding::bind(
        TaskFlowPrincipal {
            principal_id: "taskflow-self-check".to_owned(),
            expected_uid: peer.uid,
            expected_gid: peer.gid,
            expected_systemd_unit: "hepta-agent.service".to_owned(),
            expected_cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
            expected_executable_sha256: digest.clone(),
        },
        MechanismIdentity {
            peer,
            systemd_unit: "hepta-agent.service".to_owned(),
            cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
            executable_sha256: digest,
        },
    )
    .map_err(|error| error.to_string())?;
    let mut actor = BrowserActor::new(binding, DeterministicLocalRuntime::default());
    let accepted_at = Instant::now();
    let context = DispatchContext {
        peer,
        transport_sequence: 1,
        canonical_request_sha256: "4".repeat(64),
        effect_class: EffectClass::LocalInteraction,
        accepted_at,
        effective_deadline: accepted_at + Duration::from_secs(2),
    };
    let create = BrowserRequest {
        request_id: "d3-self-check-create".to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::SessionCreate {
            profile: ProfileSpec {
                profile_id: "ephemeral-self-check".to_owned(),
                persistence: ProfilePersistence::Ephemeral,
            },
            ui_mode: "headed".to_owned(),
        },
    };
    let HandlerOutcome::Success(created) = actor
        .handle(&context, &create)
        .map_err(|error| error.to_string())?
    else {
        return Err("D3 self-check could not create PageOwner".to_owned());
    };
    let session_id = match created.get("session_id") {
        Some(JsonValue::String(value)) => value.clone(),
        _ => return Err("D3 self-check response missed session_id".to_owned()),
    };
    let session_generation = match created.get("session_generation") {
        Some(JsonValue::Integer(value)) => u64::try_from(*value)
            .map_err(|_| "D3 self-check session generation is invalid".to_owned())?,
        _ => return Err("D3 self-check response missed session_generation".to_owned()),
    };
    let navigate = BrowserRequest {
        request_id: "d3-self-check-navigate".to_owned(),
        session_id: Some(session_id),
        session_generation: Some(session_generation),
        deadline_unix_ms: None,
        operation: BrowserOperation::PageNavigate {
            target: NavigationTarget::LocalHttpFixture {
                url: "http://127.0.0.1:8080/self-check".to_owned(),
            },
            expected_document_generation: 1,
        },
    };
    let mut navigation_context = context.clone();
    navigation_context.effect_class = EffectClass::PotentialExternalEffect;
    if !matches!(
        actor
            .handle(&navigation_context, &navigate)
            .map_err(|error| error.to_string())?,
        HandlerOutcome::Success(_)
    ) {
        return Err("D3 self-check local fixture navigation failed".to_owned());
    }
    let page = actor
        .page_owner()
        .ok_or_else(|| "D3 self-check lost PageOwner".to_owned())?;
    if page.session.revisions.document_generation != 2
        || !page.local_fixture_only
        || !is_loopback_http(&page.current_url)
    {
        return Err("D3 self-check PageOwner invariants failed".to_owned());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use hepta_browser_codec::{BrowserRequest, ElementReference, ProfilePersistence, ProfileSpec};
    use hepta_peer_attestation::PeerRuntimeSnapshot;
    use hepta_session_core::{JournalId, ReceiptJournal};
    use std::cell::Cell;
    use std::fs;
    use std::sync::mpsc;

    struct SharedCancellationRuntime {
        started: mpsc::Sender<()>,
        proceed: mpsc::Receiver<()>,
    }

    struct CountingRuntime {
        dispatches: Rc<Cell<usize>>,
        wait_failure: Option<RuntimeFailure>,
    }

    struct CloseFailureRuntime {
        close_failure: RuntimeFailure,
    }

    struct PostDispatchInterruptionRuntime {
        close_calls: Rc<Cell<usize>>,
        cancel_create_once: Rc<Cell<bool>>,
        cancel_navigate: bool,
        cancel_act: bool,
        cancel_observation: bool,
        close_failure: Option<RuntimeFailure>,
    }

    struct DelayedCreateRuntime {
        close_calls: Rc<Cell<usize>>,
        create_delay: Duration,
    }

    impl PageRuntime for CountingRuntime {
        fn dispatch(
            &mut self,
            _owner: Option<&PageOwnerSnapshot>,
            message: BrowserActorMessage,
            control: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            self.dispatches.set(self.dispatches.get().saturating_add(1));
            control.ensure_active()?;
            if matches!(message, BrowserActorMessage::Wait { .. })
                && let Some(error) = self.wait_failure.clone()
            {
                return Err(error);
            }
            let current_url = Some("http://127.0.0.1:8080/fixture".to_owned());
            match message {
                BrowserActorMessage::CreateSession { session_id, .. } => Ok(RuntimeReply {
                    result: json_object([("session_id", JsonValue::String(session_id))]),
                    current_url,
                }),
                BrowserActorMessage::Wait { .. } => Ok(RuntimeReply {
                    result: json_object([("satisfied", JsonValue::Bool(true))]),
                    current_url,
                }),
                _ => Ok(RuntimeReply {
                    result: JsonObject::new(),
                    current_url,
                }),
            }
        }
    }

    impl PageRuntime for CloseFailureRuntime {
        fn dispatch(
            &mut self,
            _owner: Option<&PageOwnerSnapshot>,
            message: BrowserActorMessage,
            control: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            control.ensure_active()?;
            match message {
                BrowserActorMessage::CreateSession { session_id, .. } => Ok(RuntimeReply {
                    result: json_object([("session_id", JsonValue::String(session_id))]),
                    current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
                }),
                BrowserActorMessage::Close => Err(self.close_failure.clone()),
                _ => Ok(RuntimeReply {
                    result: JsonObject::new(),
                    current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
                }),
            }
        }
    }

    impl PageRuntime for DelayedCreateRuntime {
        fn dispatch(
            &mut self,
            _owner: Option<&PageOwnerSnapshot>,
            message: BrowserActorMessage,
            _control: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            match message {
                BrowserActorMessage::CreateSession { session_id, .. } => {
                    // Deliberately ignore the control while simulating a
                    // runtime that notices the request deadline only after
                    // it has created its remote WebView. The actor must still
                    // perform its independent bounded reconciliation Close.
                    std::thread::sleep(self.create_delay);
                    Ok(RuntimeReply {
                        result: json_object([("session_id", JsonValue::String(session_id))]),
                        current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
                    })
                }
                BrowserActorMessage::Close => {
                    self.close_calls
                        .set(self.close_calls.get().saturating_add(1));
                    Ok(RuntimeReply {
                        result: JsonObject::new(),
                        current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
                    })
                }
                _ => Ok(RuntimeReply {
                    result: JsonObject::new(),
                    current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
                }),
            }
        }
    }

    impl PageRuntime for PostDispatchInterruptionRuntime {
        fn dispatch(
            &mut self,
            _owner: Option<&PageOwnerSnapshot>,
            message: BrowserActorMessage,
            control: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            match message {
                BrowserActorMessage::CreateSession { session_id, .. } => {
                    if self.cancel_create_once.replace(false) {
                        // Simulate a runtime that created the WebView and
                        // only then observed request cancellation.
                        control.cancellation_token().cancel();
                    }
                    Ok(RuntimeReply {
                        result: json_object([("session_id", JsonValue::String(session_id))]),
                        current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
                    })
                }
                BrowserActorMessage::Close => {
                    self.close_calls
                        .set(self.close_calls.get().saturating_add(1));
                    if let Some(error) = self.close_failure.clone() {
                        return Err(error);
                    }
                    control.ensure_active()?;
                    Ok(RuntimeReply {
                        result: JsonObject::new(),
                        current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
                    })
                }
                BrowserActorMessage::Navigate { .. } => {
                    if self.cancel_navigate {
                        // Simulate a document replacement followed by a late
                        // cancellation signal before the reply is observed.
                        control.cancellation_token().cancel();
                    }
                    Ok(RuntimeReply {
                        result: JsonObject::new(),
                        current_url: Some("http://127.0.0.1:8080/navigation".to_owned()),
                    })
                }
                BrowserActorMessage::Snapshot
                | BrowserActorMessage::Observe { .. }
                | BrowserActorMessage::Wait { .. }
                | BrowserActorMessage::Extract { .. }
                    if self.cancel_observation =>
                {
                    // A read/observe call can still cross a browser-side
                    // lifecycle boundary (for example a reload while
                    // collecting data).  Return a reply only after recording
                    // cancellation so the actor exercises its indeterminate
                    // reconciliation path.
                    control.cancellation_token().cancel();
                    Ok(RuntimeReply {
                        result: JsonObject::new(),
                        current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
                    })
                }
                _ => Ok(RuntimeReply {
                    result: JsonObject::new(),
                    current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
                }),
            }
        }

        fn dispatch_page_act(
            &mut self,
            _owner: Option<&PageOwnerSnapshot>,
            _target: ElementReference,
            _action: PageAction,
            control: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            if self.cancel_act {
                // Simulate a DOM mutation followed by a late cancellation.
                control.cancellation_token().cancel();
            }
            Ok(RuntimeReply {
                result: JsonObject::new(),
                current_url: Some("http://127.0.0.1:8080/fixture".to_owned()),
            })
        }
    }

    impl PageRuntime for SharedCancellationRuntime {
        fn dispatch(
            &mut self,
            _owner: Option<&PageOwnerSnapshot>,
            _message: BrowserActorMessage,
            control: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            self.started.send(()).map_err(|_| {
                RuntimeFailure::Internal("cancellation test not listening".to_owned())
            })?;
            self.proceed.recv().map_err(|_| {
                RuntimeFailure::Internal("cancellation test did not proceed".to_owned())
            })?;
            control.ensure_active()?;
            Ok(RuntimeReply {
                result: JsonObject::new(),
                current_url: None,
            })
        }
    }

    fn binding(peer: PeerIdentity) -> PrincipalBinding {
        let digest = "1".repeat(64);
        PrincipalBinding::bind(
            TaskFlowPrincipal {
                principal_id: "taskflow-test".to_owned(),
                expected_uid: peer.uid,
                expected_gid: peer.gid,
                expected_systemd_unit: "hepta-agent.service".to_owned(),
                expected_cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
                expected_executable_sha256: digest.clone(),
            },
            MechanismIdentity {
                peer,
                systemd_unit: "hepta-agent.service".to_owned(),
                cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
                executable_sha256: digest,
            },
        )
        .expect("binding")
    }

    fn context(peer: PeerIdentity, effect_class: EffectClass) -> DispatchContext {
        let accepted_at = Instant::now();
        DispatchContext {
            peer,
            transport_sequence: 1,
            canonical_request_sha256: "2".repeat(64),
            effect_class,
            accepted_at,
            effective_deadline: accepted_at + Duration::from_secs(2),
        }
    }

    fn create_page_with_runtime<R: PageRuntime>(
        actor: &mut BrowserActor<R>,
        peer: PeerIdentity,
        request_id: &str,
    ) -> (String, u64) {
        let request = BrowserRequest {
            request_id: request_id.to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: format!("{request_id}-profile"),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".to_owned(),
            },
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::LocalInteraction), &request)
            .expect("create handle");
        let HandlerOutcome::Success(result) = outcome else {
            panic!("create failed: {outcome:?}");
        };
        let session_id = match result.get("session_id") {
            Some(JsonValue::String(value)) => value.clone(),
            other => panic!("missing session id: {other:?}"),
        };
        let session_generation = match result.get("session_generation") {
            Some(JsonValue::Integer(value)) => {
                u64::try_from(*value).expect("session generation must be positive")
            }
            other => panic!("missing session generation: {other:?}"),
        };
        (session_id, session_generation)
    }

    #[test]
    fn session_identity_counter_exhaustion_fails_before_runtime_dispatch() {
        let peer = PeerIdentity {
            pid: Some(52),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: None,
            },
        );
        let create = |request_id: &str| BrowserRequest {
            request_id: request_id.to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: format!("{request_id}-profile"),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".to_owned(),
            },
        };

        actor.session_counter = u64::MAX;
        let outcome = actor
            .handle(
                &context(peer, EffectClass::LocalInteraction),
                &create("counter-session-exhausted"),
            )
            .expect("counter exhaustion should be a wire failure");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("session counter exhaustion unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Internal);
        assert_eq!(actor.session_counter, u64::MAX);
        assert_eq!(actor.webview_counter, 0);
        assert!(actor.page.is_none());
        assert_eq!(dispatches.get(), 0, "runtime must not see an exhausted ID");

        actor.session_counter = 0;
        actor.webview_counter = u64::MAX;
        let outcome = actor
            .handle(
                &context(peer, EffectClass::LocalInteraction),
                &create("counter-webview-exhausted"),
            )
            .expect("counter exhaustion should be a wire failure");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("WebView counter exhaustion unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Internal);
        assert_eq!(actor.session_counter, 0);
        assert_eq!(actor.webview_counter, u64::MAX);
        assert!(actor.page.is_none());
        assert_eq!(dispatches.get(), 0, "runtime must not see an exhausted ID");
    }

    fn page_wait_request(
        session_id: &str,
        session_generation: u64,
        request_id: &str,
    ) -> BrowserRequest {
        BrowserRequest {
            request_id: request_id.to_owned(),
            session_id: Some(session_id.to_owned()),
            session_generation: Some(session_generation),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageWait {
                condition: WaitCondition::DocumentReady,
                timeout_ms: 100,
            },
        }
    }

    fn page_navigate_request(
        session_id: &str,
        session_generation: u64,
        request_id: &str,
    ) -> BrowserRequest {
        BrowserRequest {
            request_id: request_id.to_owned(),
            session_id: Some(session_id.to_owned()),
            session_generation: Some(session_generation),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageNavigate {
                target: NavigationTarget::LocalHttpFixture {
                    url: "http://127.0.0.1:8080/navigation".to_owned(),
                },
                expected_document_generation: 1,
            },
        }
    }

    fn page_act_request(
        session_id: &str,
        session_generation: u64,
        request_id: &str,
    ) -> BrowserRequest {
        BrowserRequest {
            request_id: request_id.to_owned(),
            session_id: Some(session_id.to_owned()),
            session_generation: Some(session_generation),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageAct {
                target: ElementReference {
                    session_generation,
                    document_generation: 1,
                    semantic_snapshot_revision: 1,
                    frame_id: "main".to_owned(),
                    backend_node_key: None,
                    role: Some("button".to_owned()),
                    accessible_name_sha256: None,
                    structural_fingerprint: "a".repeat(64),
                },
                action: PageAction::Click,
            },
        }
    }

    #[test]
    fn principal_binding_rejects_unit_drift() {
        let peer = PeerIdentity {
            pid: Some(42),
            uid: 1000,
            gid: 1001,
        };
        let digest = "1".repeat(64);
        let error = PrincipalBinding::bind(
            TaskFlowPrincipal {
                principal_id: "taskflow".to_owned(),
                expected_uid: 1000,
                expected_gid: 1001,
                expected_systemd_unit: "hepta-agent.service".to_owned(),
                expected_cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
                expected_executable_sha256: digest.clone(),
            },
            MechanismIdentity {
                peer,
                systemd_unit: "other.service".to_owned(),
                cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
                executable_sha256: digest,
            },
        )
        .expect_err("unit drift must fail");
        assert_eq!(error, PrincipalBindingError::UnitMismatch);
    }

    #[test]
    fn attested_snapshot_is_the_only_source_for_mechanism_identity() {
        let peer = PeerIdentity {
            pid: Some(42),
            uid: 1000,
            gid: 1001,
        };
        let snapshot = PeerRuntimeSnapshot {
            pid: 42,
            uid: 1000,
            gid: 1001,
            start_time_ticks: 7,
            cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
            systemd_unit: Some("hepta-agent.service".to_owned()),
            executable_sha256: "1".repeat(64),
        };
        let mechanism = MechanismIdentity::from_attested(peer, &snapshot).expect("identity");
        assert_eq!(mechanism.systemd_unit, "hepta-agent.service");
        assert_eq!(mechanism.executable_sha256, "1".repeat(64));
        let principal = TaskFlowPrincipal {
            principal_id: "taskflow-attested".to_owned(),
            expected_uid: 1000,
            expected_gid: 1001,
            expected_systemd_unit: "hepta-agent.service".to_owned(),
            expected_cgroup_v2_path: "/system.slice/hepta-agent.service".to_owned(),
            expected_executable_sha256: "1".repeat(64),
        };
        let binding =
            PrincipalBinding::bind_attested(principal, peer, &snapshot).expect("attested binding");
        assert!(binding.verify_dispatch_attestation(peer, &snapshot).is_ok());

        let mut changed_start = snapshot.clone();
        changed_start.start_time_ticks = changed_start.start_time_ticks.saturating_add(1);
        assert_eq!(
            binding
                .verify_dispatch_attestation(peer, &changed_start)
                .expect_err("PID reuse must be rejected"),
            PrincipalBindingError::PeerDrift
        );

        let mut changed_executable = snapshot;
        changed_executable.executable_sha256 = "2".repeat(64);
        assert_eq!(
            binding
                .verify_dispatch_attestation(peer, &changed_executable)
                .expect_err("executable replacement must be rejected"),
            PrincipalBindingError::ExecutableMismatch
        );

        let mut zero_start = changed_executable;
        zero_start.start_time_ticks = 0;
        assert_eq!(
            MechanismIdentity::from_attested(peer, &zero_start)
                .expect_err("zero process start time must be rejected"),
            PrincipalBindingError::PeerDrift
        );
    }

    #[test]
    fn browser_actor_enforces_single_owner_local_fixture_and_freshness() {
        let peer = PeerIdentity {
            pid: Some(42),
            uid: 1000,
            gid: 1001,
        };
        let mut actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        let create = BrowserRequest {
            request_id: "create-1".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: "ephemeral-test".to_owned(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".to_owned(),
            },
        };
        let created = actor
            .handle(&context(peer, EffectClass::LocalInteraction), &create)
            .expect("create handle");
        let HandlerOutcome::Success(created) = created else {
            panic!("create failed");
        };
        let session_id = match created.get("session_id") {
            Some(JsonValue::String(value)) => value.clone(),
            other => panic!("missing session id: {other:?}"),
        };
        let generation = match created.get("session_generation") {
            Some(JsonValue::Integer(value)) => *value as u64,
            other => panic!("missing generation: {other:?}"),
        };
        let navigate = BrowserRequest {
            request_id: "navigate-1".to_owned(),
            session_id: Some(session_id.clone()),
            session_generation: Some(generation),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageNavigate {
                target: NavigationTarget::LocalHttpFixture {
                    url: "http://127.0.0.1:8080/fixture".to_owned(),
                },
                expected_document_generation: 1,
            },
        };
        let navigated = actor
            .handle(
                &context(peer, EffectClass::PotentialExternalEffect),
                &navigate,
            )
            .expect("navigate handle");
        assert!(matches!(navigated, HandlerOutcome::Success(_)));
        let stale = BrowserRequest {
            request_id: "stale-1".to_owned(),
            session_id: Some(session_id),
            session_generation: Some(generation),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageAct {
                target: ElementReference {
                    session_generation: generation,
                    document_generation: 1,
                    semantic_snapshot_revision: 0,
                    frame_id: "main".to_owned(),
                    backend_node_key: None,
                    role: Some("button".to_owned()),
                    accessible_name_sha256: None,
                    structural_fingerprint: "3".repeat(64),
                },
                action: PageAction::Click,
            },
        };
        let stale = actor
            .handle(&context(peer, EffectClass::PotentialExternalEffect), &stale)
            .expect("stale handle");
        let HandlerOutcome::Failure(error) = stale else {
            panic!("stale action unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::StaleDocument);
    }

    #[test]
    fn element_references_at_revision_sentinel_fail_closed() {
        let target = ElementReference {
            session_generation: u64::MAX,
            document_generation: 1,
            semantic_snapshot_revision: 1,
            frame_id: "main".to_owned(),
            backend_node_key: None,
            role: Some("button".to_owned()),
            accessible_name_sha256: None,
            structural_fingerprint: "a".repeat(64),
        };
        let mut current = RevisionClock::new();
        current.session_generation = u64::MAX;
        assert_eq!(
            reference_error(&target, current),
            Some(BrowserErrorCode::StaleSession),
            "terminal session identity must never be considered current"
        );

        let mut current = RevisionClock::new();
        current.document_generation = u64::MAX;
        let mut target = target;
        target.session_generation = current.session_generation;
        target.document_generation = u64::MAX;
        assert_eq!(
            reference_error(&target, current),
            Some(BrowserErrorCode::StaleDocument),
            "terminal document identity must never be considered current"
        );

        let mut current = RevisionClock::new();
        current.semantic_snapshot_revision = u64::MAX;
        target.session_generation = current.session_generation;
        target.document_generation = current.document_generation;
        target.semantic_snapshot_revision = u64::MAX;
        assert_eq!(
            reference_error(&target, current),
            Some(BrowserErrorCode::StaleSnapshot),
            "terminal snapshot identity must never be considered current"
        );
    }

    #[test]
    fn revision_wire_ceiling_reserves_recovery_transition() {
        let mut revisions = RevisionClock::new();
        assert!(!revision_clock_near_wire_ceiling(revisions));
        revisions.document_generation = i64::MAX as u64 - 2;
        assert!(!revision_clock_near_wire_ceiling(revisions));
        revisions.document_generation = i64::MAX as u64 - 1;
        assert!(revision_clock_near_wire_ceiling(revisions));
        revisions.document_generation = i64::MAX as u64;
        assert!(revision_clock_near_wire_ceiling(revisions));
    }

    #[test]
    fn page_wait_refuses_non_ready_states_before_runtime_dispatch() {
        let peer = PeerIdentity {
            pid: Some(44),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: None,
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "wait-state-create");

        let lease_id = trillionnium_contract_core::LeaseId::parse("lease_id", "wait-state-lease")
            .expect("lease");
        actor
            .apply_session_event(
                SessionEvent::HumanFocusGained {
                    lease_id,
                    ttl_ms: hepta_session_core::DEFAULT_HUMAN_LEASE_TTL_MS,
                },
                1,
            )
            .expect("human focus");
        let wait_human = page_wait_request(&session_id, session_generation, "wait-human");
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &wait_human)
            .expect("wait handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("wait unexpectedly dispatched during human focus");
        };
        assert_eq!(error.code, BrowserErrorCode::HumanControlActive);
        assert_eq!(dispatches.get(), 1, "only session creation may dispatch");

        actor
            .apply_session_event(SessionEvent::CancelRequested, 2)
            .expect("cancel request");
        let wait_cancelling = page_wait_request(&session_id, session_generation, "wait-cancelling");
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &wait_cancelling)
            .expect("wait handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("wait unexpectedly dispatched during cancellation");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
        assert_eq!(
            dispatches.get(),
            1,
            "cancellation must block runtime dispatch"
        );

        actor
            .apply_session_event(SessionEvent::CancelCompleted, 3)
            .expect("cancel completion");
        actor
            .apply_session_event(SessionEvent::BrowserCrashed, 4)
            .expect("browser crash");
        let recovered_generation = actor
            .page_owner()
            .expect("page owner")
            .session
            .revisions
            .session_generation;
        let wait_recovering =
            page_wait_request(&session_id, recovered_generation, "wait-recovering");
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &wait_recovering)
            .expect("wait handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("wait unexpectedly dispatched during recovery");
        };
        assert_eq!(error.code, BrowserErrorCode::BrowserCrashed);
        assert_eq!(dispatches.get(), 1, "recovery must block runtime dispatch");
    }

    #[test]
    fn page_act_refuses_without_atomic_semantic_resolution_before_runtime_dispatch() {
        let peer = PeerIdentity {
            pid: Some(47),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: None,
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "act-resolution-create");
        actor
            .apply_session_event(SessionEvent::SemanticSnapshotPublished, 1)
            .expect("semantic snapshot");

        let request = page_act_request(&session_id, session_generation, "act-no-resolver");
        let outcome = actor
            .handle(
                &context(peer, EffectClass::PotentialExternalEffect),
                &request,
            )
            .expect("page act handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("PageAct unexpectedly succeeded without a resolver");
        };
        assert_eq!(error.code, BrowserErrorCode::Unsupported);
        assert_eq!(dispatches.get(), 1, "generic Act dispatch must not be used");
        let page = actor.page_owner().expect("PageOwner");
        assert_eq!(page.session.control, ControlState::Idle);
        assert_eq!(page.session.phase, SessionPhase::Ready);
    }

    #[test]
    fn pre_cancelled_id_is_retired_when_state_gate_rejects_request() {
        let peer = PeerIdentity {
            pid: Some(48),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: None,
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "cancel-marker-create");
        let lease_id =
            trillionnium_contract_core::LeaseId::parse("lease_id", "cancel-marker-lease")
                .expect("lease");
        actor
            .apply_session_event(
                SessionEvent::HumanFocusGained {
                    lease_id: lease_id.clone(),
                    ttl_ms: hepta_session_core::DEFAULT_HUMAN_LEASE_TTL_MS,
                },
                1,
            )
            .expect("human focus");

        let request_id = "cancel-marker-reused";
        actor.cancel_request(request_id);
        let blocked = page_wait_request(&session_id, session_generation, request_id);
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &blocked)
            .expect("blocked wait handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("wait unexpectedly dispatched during human focus");
        };
        assert_eq!(error.code, BrowserErrorCode::HumanControlActive);
        assert_eq!(dispatches.get(), 1, "state gate must run before runtime");

        actor
            .apply_session_event(SessionEvent::HumanFocusReleased { lease_id }, 2)
            .expect("human release");
        let admitted = page_wait_request(&session_id, session_generation, request_id);
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &admitted)
            .expect("reused wait handle");
        assert!(matches!(outcome, HandlerOutcome::Success(_)));
        assert_eq!(
            dispatches.get(),
            2,
            "stale cancellation must not poison reuse"
        );
    }

    #[test]
    fn page_wait_runtime_failure_enters_recovery() {
        let peer = PeerIdentity {
            pid: Some(45),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: Some(RuntimeFailure::Cancelled),
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "wait-cleanup-create");
        let wait = page_wait_request(&session_id, session_generation, "wait-cleanup");
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &wait)
            .expect("wait handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("cancelled wait unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
        assert_eq!(dispatches.get(), 2);
        let page = actor.page_owner().expect("page owner");
        assert_eq!(page.session.control, ControlState::Idle);
        assert_eq!(page.session.phase, SessionPhase::Recovering);
        assert_eq!(page.session.revisions.session_generation, 2);
    }

    #[test]
    fn runtime_browser_crash_enters_recovery_before_returning_failure() {
        let peer = PeerIdentity {
            pid: Some(53),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: Some(RuntimeFailure::BrowserCrashed),
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "wait-browser-crash-create");
        let wait = page_wait_request(&session_id, session_generation, "wait-browser-crash");
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &wait)
            .expect("browser crash should be a wire failure");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("browser crash unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::BrowserCrashed);
        let page = actor.page_owner().expect("PageOwner retained for recovery");
        assert_eq!(page.session.phase, SessionPhase::Recovering);
        assert_eq!(page.session.control, ControlState::Idle);
        assert_eq!(page.session.revisions.session_generation, 2);
        assert_eq!(dispatches.get(), 2, "create and one crashed wait dispatch");

        // Recovery is fail closed: the stale generation cannot dispatch a
        // second wait into the already-crashed runtime.
        let second = page_wait_request(&session_id, 2, "wait-after-browser-crash");
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &second)
            .expect("recovery gate should return a wire failure");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("wait after crash unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::BrowserCrashed);
        assert_eq!(
            dispatches.get(),
            2,
            "recovery gate must block runtime dispatch"
        );
    }

    #[test]
    fn browser_crash_revision_exhaustion_retires_owner_fail_closed() {
        let peer = PeerIdentity {
            pid: Some(58),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: Some(RuntimeFailure::BrowserCrashed),
            },
        );
        let (_session_id, _session_generation) =
            create_page_with_runtime(&mut actor, peer, "wait-browser-crash-revision-exhausted");
        // SessionMachine's revision fields are intentionally private to the
        // session-core crate.  Exercise the same actor path by invoking the
        // isolated crash-transition error handler with the exact exhaustion
        // error produced by a checked revision transition.
        let outcome = actor.crash_transition_failure(
            &context(peer, EffectClass::Observation),
            TransitionError::RevisionExhausted,
        );
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("browser crash unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::BrowserCrashed);
        assert!(
            error.message.contains("revision clock exhausted"),
            "diagnostic must retain the revision exhaustion cause"
        );
        assert!(
            actor.page_owner().is_none(),
            "dead runtime must not leave a Ready owner after recovery exhaustion"
        );
        assert_eq!(dispatches.get(), 1, "only session creation dispatched");
    }

    #[test]
    fn page_wait_deadline_failure_enters_recovery() {
        let peer = PeerIdentity {
            pid: Some(47),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: Some(RuntimeFailure::DeadlineExceeded),
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "wait-deadline-create");
        let wait = page_wait_request(&session_id, session_generation, "wait-deadline");
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &wait)
            .expect("wait handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("deadline wait unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::DeadlineExceeded);
        assert_eq!(dispatches.get(), 2);
        let page = actor.page_owner().expect("page owner");
        assert_eq!(page.session.control, ControlState::Idle);
        assert_eq!(page.session.phase, SessionPhase::Recovering);
        assert_eq!(page.session.revisions.session_generation, 2);
    }

    #[test]
    fn session_close_releases_local_owner_on_runtime_interruptions() {
        let peer = PeerIdentity {
            pid: Some(54),
            uid: 1000,
            gid: 1001,
        };
        for (suffix, runtime_failure, expected_code) in [
            (
                "browser-crashed",
                RuntimeFailure::BrowserCrashed,
                BrowserErrorCode::BrowserCrashed,
            ),
            (
                "cancelled",
                RuntimeFailure::Cancelled,
                BrowserErrorCode::Cancelled,
            ),
            (
                "deadline",
                RuntimeFailure::DeadlineExceeded,
                BrowserErrorCode::DeadlineExceeded,
            ),
            (
                "internal",
                RuntimeFailure::Internal("close failed internally".to_owned()),
                BrowserErrorCode::Internal,
            ),
            (
                "unsupported",
                RuntimeFailure::Unsupported("close is unavailable"),
                BrowserErrorCode::Unsupported,
            ),
        ] {
            let mut actor = BrowserActor::new(
                binding(peer),
                CloseFailureRuntime {
                    close_failure: runtime_failure,
                },
            );
            let (session_id, session_generation) =
                create_page_with_runtime(&mut actor, peer, &format!("close-{suffix}-create"));
            let lease_id = trillionnium_contract_core::LeaseId::parse(
                "lease_id",
                format!("close-{suffix}-lease"),
            )
            .expect("lease");
            actor
                .apply_session_event(
                    SessionEvent::HumanFocusGained {
                        lease_id,
                        ttl_ms: hepta_session_core::DEFAULT_HUMAN_LEASE_TTL_MS,
                    },
                    1,
                )
                .expect("human focus");
            let close = BrowserRequest {
                request_id: format!("close-{suffix}"),
                session_id: Some(session_id),
                session_generation: Some(session_generation),
                deadline_unix_ms: None,
                operation: BrowserOperation::SessionClose,
            };
            let outcome = actor
                .handle(&context(peer, EffectClass::LocalInteraction), &close)
                .expect("close handle");
            let HandlerOutcome::Failure(error) = outcome else {
                panic!("runtime interruption unexpectedly succeeded");
            };
            assert_eq!(error.code, expected_code);
            assert!(
                actor.page_owner().is_none(),
                "local PageOwner/lease must be cleared after {suffix}"
            );
        }
    }

    #[test]
    fn observation_cleanup_transition_errors_are_explicit_and_published() {
        let peer = PeerIdentity {
            pid: Some(49),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches,
                wait_failure: None,
            },
        );
        create_page_with_runtime(&mut actor, peer, "observe-cleanup-transition-create");

        // Simulate a control owner disappearing before the adapter's finally
        // path runs.  The helper must publish the resulting snapshot and
        // return an error instead of silently treating the operation as idle.
        actor
            .page
            .as_mut()
            .expect("page owner")
            .session
            .apply(SessionEvent::BeginAgentObservation, 1)
            .expect("begin observation");
        actor
            .page
            .as_mut()
            .expect("page owner")
            .session
            .apply(SessionEvent::EndAgentObservation, 2)
            .expect("release observation");
        let error = actor
            .finish_agent_observation(3, "PageObserve", false)
            .expect_err("cleanup conflict must fail closed");
        let AgentPortError::Handler(message) = error else {
            panic!("unexpected error kind");
        };
        assert!(message.contains("PageObserve observation cleanup failed"));
        assert_eq!(
            actor
                .shared
                .borrow()
                .page
                .as_ref()
                .expect("published page")
                .session
                .control,
            ControlState::Idle
        );
    }

    #[test]
    fn mutation_cleanup_transition_errors_are_explicit_and_published() {
        let peer = PeerIdentity {
            pid: Some(50),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches,
                wait_failure: None,
            },
        );
        create_page_with_runtime(&mut actor, peer, "act-cleanup-transition-create");

        actor
            .page
            .as_mut()
            .expect("page owner")
            .session
            .apply(SessionEvent::BeginAgentMutation, 1)
            .expect("begin mutation");
        actor
            .page
            .as_mut()
            .expect("page owner")
            .session
            .apply(SessionEvent::EndAgentMutation, 2)
            .expect("release mutation");
        let error = actor
            .finish_agent_mutation(3, "PageAct", false)
            .expect_err("cleanup conflict must fail closed");
        let AgentPortError::Handler(message) = error else {
            panic!("unexpected error kind");
        };
        assert!(message.contains("PageAct mutation cleanup failed"));
        assert_eq!(
            actor
                .shared
                .borrow()
                .page
                .as_ref()
                .expect("published page")
                .session
                .control,
            ControlState::Idle
        );
    }

    #[test]
    fn agent_navigation_refuses_busy_control_before_runtime_dispatch() {
        let peer = PeerIdentity {
            pid: Some(46),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: None,
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "navigation-state-create");

        let lease_id =
            trillionnium_contract_core::LeaseId::parse("lease_id", "navigation-state-lease")
                .expect("lease");
        actor
            .apply_session_event(
                SessionEvent::HumanFocusGained {
                    lease_id: lease_id.clone(),
                    ttl_ms: hepta_session_core::DEFAULT_HUMAN_LEASE_TTL_MS,
                },
                1,
            )
            .expect("human focus");
        let navigate = page_navigate_request(&session_id, session_generation, "navigate-human");
        let outcome = actor
            .handle(
                &context(peer, EffectClass::PotentialExternalEffect),
                &navigate,
            )
            .expect("navigate handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("Agent navigation unexpectedly dispatched during human focus");
        };
        assert_eq!(error.code, BrowserErrorCode::HumanControlActive);
        assert_eq!(dispatches.get(), 1);

        actor
            .apply_session_event(
                SessionEvent::ImeStarted {
                    lease_id: lease_id.clone(),
                },
                2,
            )
            .expect("IME starts");
        let navigate = page_navigate_request(&session_id, session_generation, "navigate-ime");
        let outcome = actor
            .handle(
                &context(peer, EffectClass::PotentialExternalEffect),
                &navigate,
            )
            .expect("navigate handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("Agent navigation unexpectedly dispatched during IME composition");
        };
        assert_eq!(error.code, BrowserErrorCode::ImeCompositionActive);
        assert_eq!(dispatches.get(), 1);

        actor
            .apply_session_event(
                SessionEvent::ImeEnded {
                    lease_id: lease_id.clone(),
                },
                3,
            )
            .expect("IME ends");
        actor
            .apply_session_event(SessionEvent::HumanFocusReleased { lease_id }, 4)
            .expect("human release");
        actor
            .apply_session_event(SessionEvent::BeginAgentObservation, 5)
            .expect("observation begins");
        let navigate = page_navigate_request(&session_id, session_generation, "navigate-busy");
        let outcome = actor
            .handle(
                &context(peer, EffectClass::PotentialExternalEffect),
                &navigate,
            )
            .expect("navigate handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("Agent navigation unexpectedly dispatched during observation");
        };
        assert_eq!(error.code, BrowserErrorCode::Internal);
        assert_eq!(dispatches.get(), 1);

        actor
            .apply_session_event(SessionEvent::EndAgentObservation, 6)
            .expect("observation ends");
        let navigate = page_navigate_request(&session_id, session_generation, "navigate-ready");
        let outcome = actor
            .handle(
                &context(peer, EffectClass::PotentialExternalEffect),
                &navigate,
            )
            .expect("navigate handle");
        assert!(matches!(outcome, HandlerOutcome::Success(_)));
        assert_eq!(dispatches.get(), 2);
        let page = actor.page_owner().expect("page owner");
        assert_eq!(page.session.control, ControlState::Idle);
        assert_eq!(page.session.phase, SessionPhase::Ready);
    }

    #[test]
    fn loopback_fixture_authority_rejects_userinfo_and_ambiguous_ports() {
        for url in [
            "http://localhost",
            "http://LOCALHOST:8080/fixture",
            "http://localhost:8080/fixture",
            "http://127.0.0.1?ready=1",
            "http://[::1]:8080/fixture",
        ] {
            assert!(is_loopback_http(url), "expected loopback URL: {url}");
        }
        for url in [
            "http://127.0.0.1:80@evil.example/",
            "http://localhost@evil.example/",
            "http://127.0.0.1.evil.example/",
            "http://localhost:abc/",
            "http://localhost:/",
            "http://localhost:000000/",
            "http://localhost:65536/",
            "http://127.0.0.1:80:90/",
            "http://[::1]:80@evil.example/",
            "http://[::1]evil/",
            "https://localhost/",
        ] {
            assert!(!is_loopback_http(url), "unsafe URL was accepted: {url}");
        }
    }

    #[test]
    fn loopback_fixture_rejects_control_characters_and_oversized_urls() {
        assert!(!is_loopback_http("http://localhost/fixture\u{0001}"));
        let oversized = format!("http://localhost/{}", "a".repeat(MAX_LOOPBACK_URL_BYTES));
        assert!(!is_loopback_http(&oversized));
    }

    #[test]
    fn cancellation_is_fail_closed_before_runtime_dispatch() {
        let peer = PeerIdentity {
            pid: Some(7),
            uid: 1000,
            gid: 1001,
        };
        let mut actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        actor.cancel_request("create-cancelled");
        let request = BrowserRequest {
            request_id: "create-cancelled".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: "ephemeral".to_owned(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".to_owned(),
            },
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::LocalInteraction), &request)
            .expect("handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("cancelled request succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
        assert!(actor.page_owner().is_none());
    }

    #[test]
    fn unbound_session_close_is_rejected_before_runtime_dispatch() {
        let peer = PeerIdentity {
            pid: Some(65),
            uid: 1000,
            gid: 1001,
        };
        let dispatches = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            CountingRuntime {
                dispatches: dispatches.clone(),
                wait_failure: None,
            },
        );
        let request = BrowserRequest {
            request_id: "unbound-close".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionClose,
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::LocalInteraction), &request)
            .expect("unbound close handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("unbound close unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::StaleSession);
        assert_eq!(
            dispatches.get(),
            0,
            "runtime Close must require a bound owner"
        );
        assert!(actor.page_owner().is_none());
    }

    #[test]
    fn session_create_post_dispatch_cancellation_attempts_bounded_close() {
        let peer = PeerIdentity {
            pid: Some(59),
            uid: 1000,
            gid: 1001,
        };
        let close_calls = Rc::new(Cell::new(0));
        let cancel_create_once = Rc::new(Cell::new(true));
        let mut actor = BrowserActor::new(
            binding(peer),
            PostDispatchInterruptionRuntime {
                close_calls: close_calls.clone(),
                cancel_create_once: cancel_create_once.clone(),
                cancel_navigate: false,
                cancel_act: false,
                cancel_observation: false,
                close_failure: None,
            },
        );
        let request = BrowserRequest {
            request_id: "create-post-dispatch-cancel".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: "ephemeral-post-dispatch-cancel".to_owned(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".to_owned(),
            },
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::LocalInteraction), &request)
            .expect("create handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("late cancellation unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
        assert_eq!(
            close_calls.get(),
            1,
            "runtime Close must reconcile the hidden session"
        );
        assert!(actor.page_owner().is_none());
        assert!(
            !actor.runtime_unavailable,
            "confirmed Close keeps runtime usable"
        );

        // The failed request consumed its identity pair, and a subsequent
        // create is admitted only after the bounded Close succeeded.
        let second = BrowserRequest {
            request_id: "create-after-reconcile".to_owned(),
            ..request
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::LocalInteraction), &second)
            .expect("second create handle");
        assert!(matches!(outcome, HandlerOutcome::Success(_)));
        assert!(actor.page_owner().is_some());
        assert_eq!(close_calls.get(), 1);
    }

    #[test]
    fn session_create_post_dispatch_close_failure_poison_runtime() {
        let peer = PeerIdentity {
            pid: Some(60),
            uid: 1000,
            gid: 1001,
        };
        let close_calls = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            PostDispatchInterruptionRuntime {
                close_calls: close_calls.clone(),
                cancel_create_once: Rc::new(Cell::new(true)),
                cancel_navigate: false,
                cancel_act: false,
                cancel_observation: false,
                close_failure: Some(RuntimeFailure::Internal(
                    "close could not confirm runtime retirement".to_owned(),
                )),
            },
        );
        let request = BrowserRequest {
            request_id: "create-post-dispatch-close-failure".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: "ephemeral-post-dispatch-close-failure".to_owned(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".to_owned(),
            },
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::LocalInteraction), &request)
            .expect("create handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("late cancellation unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
        assert_eq!(close_calls.get(), 1);
        assert!(actor.page_owner().is_none());
        assert!(actor.runtime_unavailable);

        let second = BrowserRequest {
            request_id: "create-after-poison".to_owned(),
            ..request
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::LocalInteraction), &second)
            .expect("poisoned create handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("poisoned runtime unexpectedly admitted a create");
        };
        assert_eq!(error.code, BrowserErrorCode::BrowserCrashed);
        assert_eq!(
            close_calls.get(),
            1,
            "poison gate must prevent another runtime call"
        );
    }

    #[test]
    fn delayed_create_after_deadline_is_reconciled_with_independent_budget() {
        let peer = PeerIdentity {
            pid: Some(66),
            uid: 1000,
            gid: 1001,
        };
        let close_calls = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            DelayedCreateRuntime {
                close_calls: close_calls.clone(),
                // Keep this comfortably above the request budget while
                // remaining short enough that the test is deterministic and
                // does not hold the suite for the full reconciliation cap.
                create_delay: Duration::from_millis(25),
            },
        );
        let request = BrowserRequest {
            request_id: "delayed-create-deadline".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: "delayed-create-profile".to_owned(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".to_owned(),
            },
        };
        let mut short = context(peer, EffectClass::LocalInteraction);
        short.effective_deadline = short.accepted_at + Duration::from_millis(5);
        let outcome = actor
            .handle(&short, &request)
            .expect("deadline is a wire failure");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("late create unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::DeadlineExceeded);
        assert_eq!(close_calls.get(), 1, "hidden create must receive one Close");
        assert!(
            actor.page_owner().is_none(),
            "no owner may survive the deadline"
        );
        assert!(
            !actor.runtime_unavailable,
            "a confirmed bounded Close keeps the runtime reusable"
        );
    }

    #[test]
    fn final_deadline_retires_owner_installed_by_runtime() {
        let peer = PeerIdentity {
            pid: Some(67),
            uid: 1000,
            gid: 1001,
        };
        let close_calls = Rc::new(Cell::new(0));
        let mut actor = BrowserActor::new(
            binding(peer),
            DelayedCreateRuntime {
                close_calls: close_calls.clone(),
                create_delay: Duration::ZERO,
            },
        );
        let (_session_id, _generation) =
            create_page_with_runtime(&mut actor, peer, "final-deadline-owner-create");
        // Exercise the exact final-gate reconciliation deterministically: a
        // runtime dispatch has completed and installed a PageOwner, but the
        // response deadline is already gone before transport commit.
        actor.runtime_dispatch_started = true;
        let request = BrowserRequest {
            request_id: "final-deadline-owner".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: "final-deadline-owner-profile".to_owned(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".to_owned(),
            },
        };
        let mut expired = context(peer, EffectClass::LocalInteraction);
        expired.effective_deadline = expired.accepted_at;
        actor.reconcile_after_final_deadline(&expired, &request, false);
        assert_eq!(
            close_calls.get(),
            1,
            "late owner must receive bounded Close"
        );
        assert!(actor.page_owner().is_none());
        assert!(!actor.runtime_unavailable);
    }

    #[test]
    fn final_deadline_after_confirmed_close_does_not_poison_runtime() {
        let peer = PeerIdentity {
            pid: Some(68),
            uid: 1000,
            gid: 1001,
        };
        let mut actor = BrowserActor::new(
            binding(peer),
            DelayedCreateRuntime {
                close_calls: Rc::new(Cell::new(0)),
                create_delay: Duration::ZERO,
            },
        );
        let (_session_id, _generation) =
            create_page_with_runtime(&mut actor, peer, "final-deadline-close-create");
        let expired = {
            let mut context = context(peer, EffectClass::LocalInteraction);
            context.effective_deadline = context.accepted_at;
            context
        };
        // Model a runtime Close that succeeded and whose local transition was
        // already applied; only the transport's final deadline check remains.
        actor
            .close_local_page_owner(&expired)
            .expect("local close transition");
        actor.runtime_dispatch_started = true;
        let request = BrowserRequest {
            request_id: "final-deadline-close".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionClose,
        };
        actor.reconcile_after_final_deadline(&expired, &request, true);
        assert!(actor.page_owner().is_none());
        assert!(
            !actor.runtime_unavailable,
            "a confirmed remote/local close must not poison future creates"
        );
    }

    #[test]
    fn page_navigate_post_dispatch_cancellation_enters_recovery() {
        let peer = PeerIdentity {
            pid: Some(61),
            uid: 1000,
            gid: 1001,
        };
        let mut actor = BrowserActor::new(
            binding(peer),
            PostDispatchInterruptionRuntime {
                close_calls: Rc::new(Cell::new(0)),
                cancel_create_once: Rc::new(Cell::new(false)),
                cancel_navigate: true,
                cancel_act: false,
                cancel_observation: false,
                close_failure: None,
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "navigate-post-dispatch-cancel-create");
        let request = page_navigate_request(
            &session_id,
            session_generation,
            "navigate-post-dispatch-cancel",
        );
        let outcome = actor
            .handle(
                &context(peer, EffectClass::PotentialExternalEffect),
                &request,
            )
            .expect("navigate handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("late navigation cancellation unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
        let page = actor.page_owner().expect("owner retained for recovery");
        assert_eq!(page.session.phase, SessionPhase::Recovering);
        assert_eq!(page.session.control, ControlState::Idle);
        assert_eq!(page.session.revisions.session_generation, 2);
        // The old document/session tuple must no longer be accepted after an
        // effect whose result crossed the cancellation boundary.
        assert_eq!(
            reference_error(
                &ElementReference {
                    session_generation,
                    document_generation: 1,
                    semantic_snapshot_revision: 0,
                    frame_id: "main".to_owned(),
                    backend_node_key: None,
                    role: Some("button".to_owned()),
                    accessible_name_sha256: None,
                    structural_fingerprint: "a".repeat(64),
                },
                page.session.revisions,
            ),
            Some(BrowserErrorCode::StaleSession)
        );
    }

    #[test]
    fn page_act_post_dispatch_cancellation_invalidates_references() {
        let peer = PeerIdentity {
            pid: Some(62),
            uid: 1000,
            gid: 1001,
        };
        let mut actor = BrowserActor::new(
            binding(peer),
            PostDispatchInterruptionRuntime {
                close_calls: Rc::new(Cell::new(0)),
                cancel_create_once: Rc::new(Cell::new(false)),
                cancel_navigate: false,
                cancel_act: true,
                cancel_observation: false,
                close_failure: None,
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "act-post-dispatch-cancel-create");
        actor
            .apply_session_event(SessionEvent::SemanticSnapshotPublished, 1)
            .expect("semantic snapshot");
        let request = page_act_request(&session_id, session_generation, "act-post-dispatch-cancel");
        let target = match &request.operation {
            BrowserOperation::PageAct { target, .. } => target.clone(),
            _ => unreachable!("page_act_request returned another operation"),
        };
        let outcome = actor
            .handle(
                &context(peer, EffectClass::PotentialExternalEffect),
                &request,
            )
            .expect("act handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("late action cancellation unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
        let page = actor.page_owner().expect("owner retained for recovery");
        assert_eq!(page.session.phase, SessionPhase::Recovering);
        assert_eq!(page.session.control, ControlState::Idle);
        assert_eq!(page.session.revisions.session_generation, 2);
        assert_eq!(
            reference_error(&target, page.session.revisions),
            Some(BrowserErrorCode::StaleSession)
        );
    }

    #[test]
    fn observation_post_dispatch_cancellation_enters_recovery() {
        let peer = PeerIdentity {
            pid: Some(64),
            uid: 1000,
            gid: 1001,
        };
        let mut actor = BrowserActor::new(
            binding(peer),
            PostDispatchInterruptionRuntime {
                close_calls: Rc::new(Cell::new(0)),
                cancel_create_once: Rc::new(Cell::new(false)),
                cancel_navigate: false,
                cancel_act: false,
                cancel_observation: true,
                close_failure: None,
            },
        );
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "observe-post-dispatch-cancel-create");
        let request = BrowserRequest {
            request_id: "observe-post-dispatch-cancel".to_owned(),
            session_id: Some(session_id),
            session_generation: Some(session_generation),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageObserve {
                fields: vec![ObservationField::Role, ObservationField::Text],
            },
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &request)
            .expect("observe handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("late observation cancellation unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
        let page = actor.page_owner().expect("owner retained for recovery");
        assert_eq!(page.session.phase, SessionPhase::Recovering);
        assert_eq!(page.session.control, ControlState::Idle);
        assert_eq!(page.session.revisions.session_generation, 2);
    }

    #[test]
    fn cancellation_is_honoured_for_health_dispatch() {
        let peer = PeerIdentity {
            pid: Some(8),
            uid: 1000,
            gid: 1001,
        };
        let mut actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        actor.cancel_request("health-cancelled");
        let request = BrowserRequest {
            request_id: "health-cancelled".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &request)
            .expect("handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("cancelled health request succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
    }

    #[test]
    fn shared_cancellation_token_is_observed_during_runtime_dispatch() {
        let peer = PeerIdentity {
            pid: Some(18),
            uid: 1000,
            gid: 1001,
        };
        let (started_tx, started_rx) = mpsc::channel();
        let (proceed_tx, proceed_rx) = mpsc::channel();
        let mut actor = BrowserActor::new(
            binding(peer),
            SharedCancellationRuntime {
                started: started_tx,
                proceed: proceed_rx,
            },
        );
        let request_id = "health-shared-cancel".to_owned();
        let token = actor.cancellation_token(request_id.clone());
        let canceller = std::thread::spawn(move || {
            started_rx.recv().expect("runtime entered dispatch");
            token.cancel();
            proceed_tx.send(()).expect("runtime proceed");
        });
        let request = BrowserRequest {
            request_id,
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &request)
            .expect("handle");
        canceller.join().expect("cancellation thread");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("cancelled runtime unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::Cancelled);
        assert!(
            actor
                .active_cancellation_token(&request.request_id)
                .is_none()
        );
    }

    #[test]
    fn wait_rejects_stale_element_references_before_runtime_dispatch() {
        let peer = PeerIdentity {
            pid: Some(9),
            uid: 1000,
            gid: 1001,
        };
        let mut actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        let create = BrowserRequest {
            request_id: "wait-create".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: "ephemeral-wait".to_owned(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".to_owned(),
            },
        };
        let created = actor
            .handle(&context(peer, EffectClass::LocalInteraction), &create)
            .expect("create handle");
        let HandlerOutcome::Success(created) = created else {
            panic!("create failed");
        };
        let session_id = match created.get("session_id") {
            Some(JsonValue::String(value)) => value.clone(),
            other => panic!("missing session id: {other:?}"),
        };
        let session_generation = match created.get("session_generation") {
            Some(JsonValue::Integer(value)) => *value as u64,
            other => panic!("missing session generation: {other:?}"),
        };
        let wait = BrowserRequest {
            request_id: "wait-stale".to_owned(),
            session_id: Some(session_id),
            session_generation: Some(session_generation),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageWait {
                condition: WaitCondition::ElementPresent {
                    target: ElementReference {
                        session_generation,
                        document_generation: 1,
                        semantic_snapshot_revision: 1,
                        frame_id: "main".to_owned(),
                        backend_node_key: None,
                        role: Some("button".to_owned()),
                        accessible_name_sha256: None,
                        structural_fingerprint: "4".repeat(64),
                    },
                },
                timeout_ms: 100,
            },
        };
        let outcome = actor
            .handle(&context(peer, EffectClass::Observation), &wait)
            .expect("wait handle");
        let HandlerOutcome::Failure(error) = outcome else {
            panic!("stale wait unexpectedly succeeded");
        };
        assert_eq!(error.code, BrowserErrorCode::StaleSnapshot);
    }

    #[test]
    fn lifecycle_observer_commits_requested_dispatched_and_terminal_receipts() {
        let peer = PeerIdentity {
            pid: Some(42),
            uid: 1000,
            gid: 1001,
        };
        let directory = std::env::temp_dir().join(format!(
            "hepta-browser-actor-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        fs::create_dir_all(&directory).expect("create directory");
        let journal_path = directory.join("receipts.hjr");
        let journal = ReceiptJournal::create(
            &journal_path,
            JournalId([0x31; 16]),
            wall_clock_unix_ms().expect("clock"),
        )
        .expect("journal");
        let actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        let mut observer = actor.receipt_observer(journal, "d3-test-image");
        let request = BrowserRequest {
            request_id: "receipt-health".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };
        let dispatch = context(peer, EffectClass::Observation);
        observer.requested(&dispatch, &request).expect("requested");
        observer
            .dispatched(&dispatch, &request)
            .expect("dispatched");
        let response = BrowserResponse::success(
            request.request_id.clone(),
            None,
            None,
            json_object([("healthy", JsonValue::Bool(true))]),
        )
        .expect("response");
        observer
            .completed(&dispatch, &request, &response, &"5".repeat(64))
            .expect("completed");
        let report = observer.inspect().expect("inspect");
        let states: Vec<_> = report
            .records
            .iter()
            .map(|record| record.event.lifecycle)
            .collect();
        assert_eq!(
            states,
            vec![
                ReceiptLifecycleState::Requested,
                ReceiptLifecycleState::Dispatched,
                ReceiptLifecycleState::Completed,
            ]
        );
        assert_eq!(
            report
                .records
                .last()
                .and_then(|record| record.event.response_sha256),
            Some([0x55; 32])
        );
        drop(observer);
        let _ = fs::remove_dir_all(directory);
    }

    #[test]
    fn lifecycle_coordinates_ignore_foreign_request_identity_when_owner_exists() {
        let peer = PeerIdentity {
            pid: Some(56),
            uid: 1000,
            gid: 1001,
        };
        let mut actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        let (session_id, session_generation) =
            create_page_with_runtime(&mut actor, peer, "receipt-authority-create");
        let directory = std::env::temp_dir().join(format!(
            "hepta-browser-actor-authority-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        fs::create_dir_all(&directory).expect("create directory");
        let journal_path = directory.join("receipts.hjr");
        let journal = ReceiptJournal::create(
            &journal_path,
            JournalId([0x34; 16]),
            wall_clock_unix_ms().expect("clock"),
        )
        .expect("journal");
        let mut observer = actor.receipt_observer(journal, "d3-authority-image");
        let request = BrowserRequest {
            request_id: "receipt-foreign-coordinates".to_owned(),
            // These values intentionally fail the actor's binding gate.  The
            // observer still runs before that gate and must not persist them
            // as the active PageOwner coordinates.
            session_id: Some("attacker-session".to_owned()),
            session_generation: Some(u64::MAX),
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };
        let dispatch = context(peer, EffectClass::Observation);
        observer.requested(&dispatch, &request).expect("requested");
        let report = observer.inspect().expect("inspect");
        let record = report.records.first().expect("requested record");
        assert_eq!(record.event.session_id, session_id);
        assert_eq!(record.event.session_generation, session_generation);
        drop(observer);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn lifecycle_requested_rolls_back_inflight_marker_on_append_failure() {
        let peer = PeerIdentity {
            pid: Some(51),
            uid: 1000,
            gid: 1001,
        };
        let directory = std::env::temp_dir().join(format!(
            "hepta-browser-actor-requested-rollback-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        fs::create_dir_all(&directory).expect("create directory");
        let journal_path = directory.join("receipts.hjr");
        let journal = ReceiptJournal::create(
            &journal_path,
            JournalId([0x33; 16]),
            wall_clock_unix_ms().expect("clock"),
        )
        .expect("journal");
        let actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        let mut observer = actor.receipt_observer(journal, "d3-requested-rollback-image");
        let request = BrowserRequest {
            request_id: "receipt-requested-rollback".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };

        let mut invalid_dispatch = context(peer, EffectClass::Observation);
        invalid_dispatch.canonical_request_sha256 = "invalid-digest".to_owned();
        assert!(observer.requested(&invalid_dispatch, &request).is_err());
        assert!(
            !observer.inflight.contains_key(&request.request_id),
            "failed durable admission must not retain an in-memory marker"
        );

        let valid_dispatch = context(peer, EffectClass::Observation);
        observer
            .requested(&valid_dispatch, &request)
            .expect("same ID can be admitted after failed append");
        assert!(observer.inflight.contains_key(&request.request_id));
        drop(observer);
        let _ = fs::remove_dir_all(directory);
    }

    #[test]
    fn lifecycle_logical_clock_exhaustion_fails_closed_before_append() {
        let peer = PeerIdentity {
            pid: Some(57),
            uid: 1000,
            gid: 1001,
        };
        let directory = std::env::temp_dir().join(format!(
            "hepta-browser-actor-clock-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        fs::create_dir_all(&directory).expect("create directory");
        let journal_path = directory.join("receipts.hjr");
        let journal = ReceiptJournal::create(
            &journal_path,
            JournalId([0x35; 16]),
            wall_clock_unix_ms().expect("clock"),
        )
        .expect("journal");
        let actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        let mut observer = actor.receipt_observer(journal, "d3-clock-image");
        observer.logical_clock = u64::MAX;
        let request = BrowserRequest {
            request_id: "receipt-clock-overflow".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };
        let dispatch = context(peer, EffectClass::Observation);
        let error = observer
            .requested(&dispatch, &request)
            .expect_err("clock exhaustion must reject the lifecycle event");
        assert!(error.to_string().contains("logical clock exhausted"));
        assert!(observer.inflight.is_empty());
        assert!(observer.inspect().expect("inspect").records.is_empty());
        drop(observer);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn lifecycle_dispatched_append_failure_releases_inflight_marker() {
        let peer = PeerIdentity {
            pid: Some(63),
            uid: 1000,
            gid: 1001,
        };
        let directory = std::env::temp_dir().join(format!(
            "hepta-browser-actor-dispatched-marker-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        fs::create_dir_all(&directory).expect("create directory");
        let journal_path = directory.join("receipts.hjr");
        let journal = ReceiptJournal::create(
            &journal_path,
            JournalId([0x37; 16]),
            wall_clock_unix_ms().expect("clock"),
        )
        .expect("journal");
        let actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        let mut observer = actor.receipt_observer(journal, "d3-dispatched-marker-image");
        let request = BrowserRequest {
            request_id: "receipt-dispatched-marker".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };
        let dispatch = context(peer, EffectClass::Observation);
        observer.requested(&dispatch, &request).expect("requested");
        observer.logical_clock = u64::MAX;
        let error = observer
            .dispatched(&dispatch, &request)
            .expect_err("clock exhaustion must reject dispatched event");
        assert!(error.to_string().contains("logical clock exhausted"));
        assert!(observer.inflight.is_empty());
        assert_eq!(
            observer.inspect().expect("inspect").records.len(),
            1,
            "the durable Requested record remains the recovery authority"
        );

        // Once the clock is reconciled, a caller may retry the dispatched
        // transition against the durable Requested record; no stale marker
        // from the failed attempt should block it.
        observer.logical_clock = 1;
        observer
            .dispatched(&dispatch, &request)
            .expect("retry dispatched");
        assert_eq!(observer.inspect().expect("inspect").records.len(), 2);
        drop(observer);
        let _ = fs::remove_dir_all(directory);
    }

    #[test]
    fn potential_effect_runtime_failure_is_recorded_as_indeterminate() {
        let peer = PeerIdentity {
            pid: Some(43),
            uid: 1000,
            gid: 1001,
        };
        let directory = std::env::temp_dir().join(format!(
            "hepta-browser-actor-indeterminate-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        fs::create_dir_all(&directory).expect("create directory");
        let journal_path = directory.join("receipts.hjr");
        let journal = ReceiptJournal::create(
            &journal_path,
            JournalId([0x32; 16]),
            wall_clock_unix_ms().expect("clock"),
        )
        .expect("journal");
        let actor = BrowserActor::new(binding(peer), DeterministicLocalRuntime::default());
        let mut observer = actor.receipt_observer(journal, "d3-indeterminate-image");
        let request = BrowserRequest {
            request_id: "receipt-potential-crash".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::PageNavigate {
                target: NavigationTarget::LocalHttpFixture {
                    url: "http://127.0.0.1:8080/effect".to_owned(),
                },
                expected_document_generation: 1,
            },
        };
        let dispatch = context(peer, EffectClass::PotentialExternalEffect);
        observer.requested(&dispatch, &request).expect("requested");
        observer
            .dispatched(&dispatch, &request)
            .expect("dispatched");
        let response = BrowserResponse::failure(
            request.request_id.clone(),
            None,
            None,
            BrowserWireError {
                code: BrowserErrorCode::BrowserCrashed,
                message: "browser process stopped while applying navigation".to_owned(),
                details: None,
            },
        )
        .expect("response");
        observer
            .completed(&dispatch, &request, &response, &"6".repeat(64))
            .expect("completed");
        let report = observer.inspect().expect("inspect");
        let terminal = report.records.last().expect("terminal record");
        assert_eq!(
            terminal.event.lifecycle,
            ReceiptLifecycleState::Indeterminate
        );
        assert_eq!(terminal.event.outcome, None);
        assert_eq!(terminal.event.response_sha256, None);
        assert_eq!(
            terminal.event.error_code.as_deref(),
            Some("browser_crashed")
        );
        drop(observer);
        let _ = fs::remove_dir_all(directory);
    }
}
