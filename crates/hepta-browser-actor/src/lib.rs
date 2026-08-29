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
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

pub const D3_PLAN_REVISION: &str = "2026-08-29-d6";
pub const D3_SERVO_COMMIT: &str = "670ae8a70801b162e186f81cbb5bdd2d59c39108";
pub const D3_BROWSERD_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const MAX_PRINCIPAL_ID_BYTES: usize = 128;
pub const MAX_UNIT_BYTES: usize = 192;
pub const MAX_CGROUP_BYTES: usize = 512;
pub const MAX_WEBVIEW_TOKEN_BYTES: usize = 128;

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
}

impl PrincipalBinding {
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
        })
    }

    pub fn principal(&self) -> &TaskFlowPrincipal {
        &self.principal
    }

    pub fn mechanism(&self) -> &MechanismIdentity {
        &self.mechanism
    }

    pub fn verify_dispatch_peer(&self, peer: PeerIdentity) -> Result<(), PrincipalBindingError> {
        if peer.pid != self.mechanism.peer.pid
            || peer.uid != self.mechanism.peer.uid
            || peer.gid != self.mechanism.peer.gid
        {
            return Err(PrincipalBindingError::PeerDrift);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PrincipalBindingError {
    InvalidField(&'static str),
    MissingPeerPid,
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
pub struct RequestControl {
    pub request_id: String,
    pub deadline: Instant,
    cancelled: bool,
}

impl RequestControl {
    pub fn ensure_active(&self) -> Result<(), RuntimeFailure> {
        if self.cancelled {
            return Err(RuntimeFailure::Cancelled);
        }
        if Instant::now() >= self.deadline {
            return Err(RuntimeFailure::DeadlineExceeded);
        }
        Ok(())
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
            BrowserActorMessage::Act { target, action } => {
                if !is_loopback_http(&self.current_url) {
                    return Err(RuntimeFailure::PolicyDenied(
                        "page actions are enabled only on deterministic loopback fixtures",
                    ));
                }
                self.actions_applied = self.actions_applied.saturating_add(1);
                Ok(RuntimeReply {
                    result: json_object([
                        (
                            "action",
                            JsonValue::String(page_action_name(&action).to_owned()),
                        ),
                        ("action_count", json_u64(self.actions_applied)?),
                        ("applied", JsonValue::Bool(true)),
                        ("frame_id", JsonValue::String(target.frame_id)),
                    ]),
                    current_url: Some(self.current_url.clone()),
                })
            }
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
            shared: Rc::new(RefCell::new(SharedActorState { page: None })),
        }
    }

    pub fn principal_binding(&self) -> &PrincipalBinding {
        &self.binding
    }

    pub fn page_owner(&self) -> Option<PageOwnerSnapshot> {
        self.page.as_ref().map(PageOwner::snapshot)
    }

    pub fn cancel_request(&mut self, request_id: impl Into<String>) {
        self.cancelled_requests.insert(request_id.into());
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
        ReceiptLifecycleObserver {
            journal,
            image_id: image_id.into(),
            principal_id: self.binding.principal.principal_id.clone(),
            shared: self.shared.clone(),
            inflight: BTreeMap::new(),
            logical_clock: 0,
        }
    }

    fn publish_shared(&self) {
        self.shared.borrow_mut().page = self.page.as_ref().map(PageOwner::snapshot);
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

    fn runtime_dispatch(
        &mut self,
        request: &BrowserRequest,
        context: &DispatchContext,
        message: BrowserActorMessage,
    ) -> Result<RuntimeReply, HandlerOutcome> {
        let cancelled = self.cancelled_requests.remove(&request.request_id);
        let control = RequestControl {
            request_id: request.request_id.clone(),
            deadline: context.effective_deadline,
            cancelled,
        };
        let owner = self.page.as_ref().map(PageOwner::snapshot);
        self.runtime
            .dispatch(owner.as_ref(), message, &control)
            .map_err(runtime_failure)
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
}

impl<R: PageRuntime> BrowserRequestHandler for BrowserActor<R> {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        if let Err(error) = self.binding.verify_dispatch_peer(context.peer) {
            return Ok(failure(
                BrowserErrorCode::PolicyDenied,
                &format!("semantic principal binding rejected transport peer: {error}"),
            ));
        }
        context.remaining()?;
        if !matches!(
            &request.operation,
            BrowserOperation::Health | BrowserOperation::SessionCreate { .. }
        ) && let Err(outcome) = self.verify_bound_request(request)
        {
            return Ok(outcome);
        }

        let outcome = match &request.operation {
            BrowserOperation::Health => {
                let mut result = json_object([
                    ("browser_actor_ready", JsonValue::Bool(true)),
                    ("external_effect_authority", JsonValue::Bool(false)),
                    ("local_fixture_only", JsonValue::Bool(true)),
                    (
                        "principal_id",
                        JsonValue::String(self.binding.principal.principal_id.clone()),
                    ),
                ]);
                result.insert(
                    "session_active".to_owned(),
                    JsonValue::Bool(self.page.is_some()),
                );
                HandlerOutcome::Success(result)
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
                    self.session_counter = self.session_counter.saturating_add(1);
                    self.webview_counter = self.webview_counter.saturating_add(1);
                    let session_id = format!(
                        "session-{}-{}",
                        self.binding.mechanism.peer.uid, self.session_counter
                    );
                    let webview_token = format!("webview-{}", self.webview_counter);
                    validate_token("session_id", &session_id, 128)
                        .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                    validate_token("webview_token", &webview_token, MAX_WEBVIEW_TOKEN_BYTES)
                        .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                    let reply = match self.runtime_dispatch(
                        request,
                        context,
                        BrowserActorMessage::CreateSession {
                            session_id: session_id.clone(),
                            profile: profile.clone(),
                        },
                    ) {
                        Ok(reply) => reply,
                        Err(outcome) => return Ok(outcome),
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
                    let reply =
                        self.runtime_dispatch(request, context, BrowserActorMessage::Snapshot);
                    let page = self.page.as_mut().expect("PageOwner exists");
                    let _ = page
                        .session
                        .apply(SessionEvent::EndAgentObservation, now_ms);
                    match reply {
                        Ok(reply) => {
                            if let Some(url) = reply.current_url {
                                page.current_url = url;
                            }
                            self.publish_shared();
                            HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                        }
                        Err(outcome) => outcome,
                    }
                }
            }
            BrowserOperation::SessionClose => {
                let reply = self.runtime_dispatch(request, context, BrowserActorMessage::Close);
                match reply {
                    Ok(reply) => {
                        let page = self.page.as_mut().expect("PageOwner exists");
                        page.session
                            .apply(SessionEvent::Close, monotonic_request_ms(context))
                            .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                        let mut result = reply.result;
                        result.insert(
                            "session_id".to_owned(),
                            JsonValue::String(page.session_id.clone()),
                        );
                        self.page = None;
                        self.publish_shared();
                        HandlerOutcome::Success(result)
                    }
                    Err(outcome) => outcome,
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
                        let reply = self.runtime_dispatch(
                            request,
                            context,
                            BrowserActorMessage::Navigate {
                                url,
                                expected_document_generation: *expected_document_generation,
                            },
                        );
                        let page = self.page.as_mut().expect("PageOwner exists");
                        match reply {
                            Ok(reply) => {
                                page.session
                                    .apply(SessionEvent::NavigationCommitted, now_ms)
                                    .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                                if let Some(url) = reply.current_url {
                                    page.current_url = url;
                                }
                                self.publish_shared();
                                HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                            }
                            Err(outcome) => {
                                let _ = page.session.apply(SessionEvent::NavigationFailed, now_ms);
                                self.publish_shared();
                                outcome
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
                    let reply = self.runtime_dispatch(
                        request,
                        context,
                        BrowserActorMessage::Observe {
                            fields: fields.clone(),
                        },
                    );
                    let page = self.page.as_mut().expect("PageOwner exists");
                    match reply {
                        Ok(reply) => {
                            page.session
                                .apply(SessionEvent::SemanticSnapshotPublished, now_ms)
                                .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                            page.session
                                .apply(SessionEvent::EndAgentObservation, now_ms)
                                .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                            if let Some(url) = reply.current_url {
                                page.current_url = url;
                            }
                            self.publish_shared();
                            HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                        }
                        Err(outcome) => {
                            let _ = page
                                .session
                                .apply(SessionEvent::EndAgentObservation, now_ms);
                            self.publish_shared();
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
                        let reply = self.runtime_dispatch(
                            request,
                            context,
                            BrowserActorMessage::Act {
                                target: target.clone(),
                                action: action.clone(),
                            },
                        );
                        let page = self.page.as_mut().expect("PageOwner exists");
                        match reply {
                            Ok(reply) => {
                                page.session
                                    .apply(SessionEvent::DomCommitted, now_ms)
                                    .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                                page.session
                                    .apply(SessionEvent::EndAgentMutation, now_ms)
                                    .map_err(|error| AgentPortError::Handler(error.to_string()))?;
                                self.publish_shared();
                                HandlerOutcome::Success(self.snapshot_result(reply.result)?)
                            }
                            Err(outcome) => {
                                let _ = page.session.apply(SessionEvent::EndAgentMutation, now_ms);
                                self.publish_shared();
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
                let remaining = context.remaining()?;
                let timeout = Duration::from_millis(*timeout_ms).min(remaining);
                let reply = self.runtime_dispatch(
                    request,
                    context,
                    BrowserActorMessage::Wait {
                        condition: condition.clone(),
                        timeout,
                    },
                );
                match reply {
                    Ok(reply) => HandlerOutcome::Success(self.snapshot_result(reply.result)?),
                    Err(outcome) => outcome,
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
                    let reply = self.runtime_dispatch(
                        request,
                        context,
                        BrowserActorMessage::Extract {
                            schema_id: schema_id.clone(),
                        },
                    );
                    let page = self.page.as_mut().expect("PageOwner exists");
                    let _ = page
                        .session
                        .apply(SessionEvent::EndAgentObservation, now_ms);
                    self.publish_shared();
                    match reply {
                        Ok(reply) => HandlerOutcome::Success(self.snapshot_result(reply.result)?),
                        Err(outcome) => outcome,
                    }
                }
            }
        };
        context.remaining()?;
        Ok(outcome)
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

    fn coordinates(&self, request: &BrowserRequest) -> ReceiptCoordinates {
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
            session_id: request.session_id.clone().unwrap_or(page.session_id),
            session_generation: request
                .session_generation
                .unwrap_or(revisions.session_generation),
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
        self.logical_clock = self.logical_clock.saturating_add(1);
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
            monotonic_ms: self.logical_clock,
            wall_clock_unix_ms: wall_clock_unix_ms()?,
        };
        self.journal
            .append(event)
            .map_err(|error| AgentPortError::Handler(format!("receipt journal failed: {error}")))?;
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
        self.append(
            context,
            request,
            ReceiptLifecycleState::Requested,
            None,
            None,
            None,
        )
    }

    fn dispatched(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<(), AgentPortError> {
        self.append(
            context,
            request,
            ReceiptLifecycleState::Dispatched,
            None,
            None,
            None,
        )
    }

    fn completed(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        response: &BrowserResponse,
        canonical_response_sha256: &str,
    ) -> Result<(), AgentPortError> {
        let (outcome, error_code) = match &response.outcome {
            Ok(_) => (ReceiptOutcome::Succeeded, None),
            Err(error) => {
                let outcome = match error.code {
                    BrowserErrorCode::PolicyDenied | BrowserErrorCode::Unsupported => {
                        ReceiptOutcome::Refused
                    }
                    BrowserErrorCode::Cancelled => ReceiptOutcome::Cancelled,
                    _ => ReceiptOutcome::Failed,
                };
                (outcome, Some(error.code.as_str()))
            }
        };
        let result = self.append(
            context,
            request,
            ReceiptLifecycleState::Completed,
            Some(outcome),
            Some(canonical_response_sha256),
            error_code,
        );
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
        TransitionError::Closed => failure(
            BrowserErrorCode::StaleSession,
            "PageOwner session is closed",
        ),
        other => failure(BrowserErrorCode::Internal, &other.to_string()),
    }
}

fn reference_error(
    target: &ElementReference,
    revisions: trillionnium_contract_core::RevisionClock,
) -> Option<BrowserErrorCode> {
    if target.session_generation != revisions.session_generation {
        Some(BrowserErrorCode::StaleSession)
    } else if target.document_generation != revisions.document_generation {
        Some(BrowserErrorCode::StaleDocument)
    } else if target.semantic_snapshot_revision != revisions.semantic_snapshot_revision {
        Some(BrowserErrorCode::StaleSnapshot)
    } else {
        None
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

fn page_action_name(action: &PageAction) -> &'static str {
    match action {
        PageAction::Click => "click",
        PageAction::Type { .. } => "type",
        PageAction::Press { .. } => "press",
        PageAction::Scroll { .. } => "scroll",
        PageAction::Select { .. } => "select",
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
    url.starts_with("http://127.0.0.1/")
        || url.starts_with("http://127.0.0.1:")
        || url.starts_with("http://localhost/")
        || url.starts_with("http://localhost:")
        || url.starts_with("http://[::1]/")
        || url.starts_with("http://[::1]:")
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
    use hepta_session_core::{JournalId, ReceiptJournal};
    use std::fs;

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
}
