//! Private, strict read subset of the upstream v2 wire; provenance is pinned in
//! UPSTREAM_CONTRACT.json. Do not add a raw JSON or caller-selected method API.

use crate::{Capability, EventObservation, HealthObservation, ObserverError, RunObservation};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

pub(crate) const OVERLOAD_FRAME: &[u8] = b"{\"type\":\"overloaded\",\"retry_after_ms\":50}\n";

#[derive(Serialize)]
pub(crate) struct Request<'a> {
    pub schema_version: u32,
    pub request_id: u64,
    pub spawn_generation: u64,
    pub method: Method<'a>,
}

#[derive(Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub(crate) enum Method<'a> {
    Health,
    Capabilities,
    Events { after_cursor: u64, limit: u16 },
    RunStatus { run_id: &'a str },
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Response {
    pub schema_version: u32,
    pub request_id: u64,
    pub agent_id: String,
    pub spawn_generation: u64,
    pub current_generation: u64,
    pub payload: Payload,
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum Payload {
    Health(Health),
    Capabilities(Capabilities),
    Events(EventBatch),
    RunStatus { run: Option<RunReceipt> },
    Error { code: String, message: String },
}

#[derive(Clone, Copy, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Lifecycle {
    Stopped,
    Starting,
    Running,
    Draining,
    Failed,
}

impl Lifecycle {
    /// Upstream AgentdState::refresh_generation accepts exactly these phases
    /// of one immutable process spawn, not an arbitrary newer generation.
    fn generation(self, spawn_generation: u64) -> Option<u64> {
        match self {
            Self::Starting => Some(spawn_generation),
            Self::Running => spawn_generation.checked_add(1),
            Self::Draining => spawn_generation.checked_add(2),
            Self::Stopped | Self::Failed => None,
        }
    }

    fn name(self) -> &'static str {
        match self {
            Self::Stopped => "stopped",
            Self::Starting => "starting",
            Self::Running => "running",
            Self::Draining => "draining",
            Self::Failed => "failed",
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Health {
    promotion_ready: bool,
    ready: bool,
    fenced: bool,
    lifecycle: Lifecycle,
    process_id: u32,
    // Parse known upstream fields, discard before projection. They are not an
    // invitation to open those paths, and never appear in errors or UI state.
    workspace: PathBuf,
    home_root: PathBuf,
    run_root: PathBuf,
}

impl Health {
    pub fn project(
        self,
        peer_pid: u32,
        spawn_generation: u64,
        current_generation: u64,
    ) -> Result<HealthObservation, ObserverError> {
        if self.process_id != peer_pid {
            return Err(ObserverError::PeerDenied);
        }
        if self.fenced || self.lifecycle.generation(spawn_generation) != Some(current_generation) {
            return Err(ObserverError::GenerationFenced);
        }
        if (self.ready && (self.lifecycle != Lifecycle::Running || !self.promotion_ready))
            || (self.promotion_ready
                && !matches!(self.lifecycle, Lifecycle::Starting | Lifecycle::Running))
            || [&self.workspace, &self.home_root, &self.run_root]
                .iter()
                .any(|path| !path.is_absolute())
        {
            return Err(ObserverError::ProtocolMismatch);
        }
        Ok(HealthObservation {
            ready: self.ready,
            promotion_ready: self.promotion_ready,
            fenced: self.fenced,
            lifecycle: self.lifecycle.name().to_owned(),
            process_id: self.process_id,
        })
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Capabilities {
    schema_version: u32,
    capabilities: Vec<Capability>,
}

impl Capabilities {
    pub fn project(mut self) -> Result<Vec<Capability>, ObserverError> {
        if self.schema_version != 1
            || self.capabilities.len() > 64
            || self
                .capabilities
                .iter()
                .any(|capability| !valid_identity(&capability.id) || capability.major == 0)
        {
            return Err(ObserverError::ProtocolMismatch);
        }
        self.capabilities.sort_by(|a, b| a.id.cmp(&b.id));
        if self
            .capabilities
            .windows(2)
            .any(|pair| pair[0].id == pair[1].id)
        {
            return Err(ObserverError::ProtocolMismatch);
        }
        Ok(self.capabilities)
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct EventBatch {
    pub events: Vec<Event>,
    pub gap: bool,
    pub next_cursor: u64,
    pub latest_cursor: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Event {
    cursor: u64,
    kind: EventKind,
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
enum EventKind {
    // Empty struct variants deliberately enforce deny_unknown_fields; serde
    // otherwise ignores extra map fields on internally tagged unit variants.
    Bootstrapped {},
    Lifecycle {
        lifecycle: Lifecycle,
        generation: u64,
    },
    AppServerReady {},
    Draining {},
    GenerationFenced {},
}

impl EventBatch {
    pub fn project(
        &self,
        after_cursor: u64,
        limit: u16,
        spawn_generation: u64,
        current_generation: u64,
    ) -> Result<Vec<EventObservation>, ObserverError> {
        if self.events.len() > usize::from(limit) {
            return Err(ObserverError::ProtocolMismatch);
        }
        // The upstream ring is process-local. A cursor ahead of its tail means
        // the caller cannot continue this history; no fabricated empty success.
        if after_cursor > self.latest_cursor {
            return Err(ObserverError::EventCursorAhead);
        }
        if self.events.is_empty() {
            if self.gap || self.next_cursor != after_cursor || self.latest_cursor != after_cursor {
                return Err(ObserverError::ProtocolMismatch);
            }
            return Ok(Vec::new());
        }
        let first = self.events[0].cursor;
        let expected_first = after_cursor
            .checked_add(1)
            .ok_or(ObserverError::ProtocolMismatch)?;
        if (self.gap && first <= expected_first)
            || (!self.gap && first != expected_first)
            || self.next_cursor != self.events.last().expect("nonempty").cursor
            || self.latest_cursor < self.next_cursor
            || (self.events.len() < usize::from(limit) && self.next_cursor != self.latest_cursor)
            || self
                .events
                .windows(2)
                .any(|pair| pair[0].cursor.checked_add(1) != Some(pair[1].cursor))
        {
            return Err(ObserverError::ProtocolMismatch);
        }
        self.events
            .iter()
            .map(|event| {
                let (kind, generation, lifecycle) = match event.kind {
                    EventKind::Bootstrapped {} => ("bootstrapped", None, None),
                    EventKind::Lifecycle {
                        lifecycle,
                        generation,
                    } => {
                        // Earlier phases remain in the same process-local
                        // event ring after promotion/drain. A future phase,
                        // wrong offset or a non-serving lifecycle is fenced.
                        if lifecycle.generation(spawn_generation) != Some(generation)
                            || generation > current_generation
                        {
                            return Err(ObserverError::GenerationFenced);
                        }
                        (
                            "lifecycle",
                            Some(generation),
                            Some(lifecycle.name().to_owned()),
                        )
                    }
                    EventKind::AppServerReady {} => ("app_server_ready", None, None),
                    EventKind::Draining {} => ("draining", None, None),
                    EventKind::GenerationFenced {} => {
                        return Err(ObserverError::GenerationFenced);
                    }
                };
                Ok(EventObservation {
                    cursor: event.cursor,
                    kind: kind.to_owned(),
                    generation,
                    lifecycle,
                })
            })
            .collect()
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum RunPhase {
    Admitted,
    ContextAttached,
    Dispatched,
    Cancelling,
    Cancelled,
    Succeeded,
    Failed,
    Indeterminate,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RunReceipt {
    run_id: String,
    revision: u64,
    phase: RunPhase,
    context_digest: Option<String>,
    #[serde(default)]
    compilation_receipt_digest: Option<String>,
    authority_epoch: u64,
    generation: u64,
    fence_digest: String,
    deadline_ms: u64,
    cancel_reason: Option<String>,
    cancel_ack_deadline_ms: Option<u64>,
    terminal_observed: bool,
    idempotent: bool,
}

impl RunReceipt {
    pub fn project(self, expected_run_id: &str) -> Result<RunObservation, ObserverError> {
        if self.run_id != expected_run_id
            || self.revision == 0
            || self.authority_epoch == 0
            || self.generation == 0
            || self.deadline_ms == 0
            || !valid_digest(&self.fence_digest)
            || self
                .context_digest
                .as_deref()
                .is_some_and(|d| !valid_digest(d))
            || self
                .compilation_receipt_digest
                .as_deref()
                .is_some_and(|d| !valid_digest(d))
            || self.cancel_reason.as_deref().is_some_and(|reason| {
                reason.trim().is_empty() || reason.len() > 512 || reason.as_bytes().contains(&0)
            })
            || self.cancel_ack_deadline_ms == Some(0)
            || self.terminal_observed
                != matches!(
                    self.phase,
                    RunPhase::Cancelled | RunPhase::Succeeded | RunPhase::Failed
                )
        {
            return Err(ObserverError::ProtocolMismatch);
        }
        let phase = match self.phase {
            RunPhase::Admitted => "admitted",
            RunPhase::ContextAttached => "context_attached",
            RunPhase::Dispatched => "dispatched",
            RunPhase::Cancelling => "cancelling",
            RunPhase::Cancelled => "cancelled",
            RunPhase::Succeeded => "succeeded",
            RunPhase::Failed => "failed",
            RunPhase::Indeterminate => "indeterminate",
        };
        Ok(RunObservation {
            run_id: self.run_id,
            revision: self.revision,
            phase: phase.to_owned(),
            authority_epoch: self.authority_epoch,
            generation: self.generation,
            terminal_observed: self.terminal_observed,
            idempotent: self.idempotent,
        })
    }
}

pub(crate) fn valid_identity(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte))
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && !value.bytes().all(|byte| byte == b'0')
        && value
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
}
