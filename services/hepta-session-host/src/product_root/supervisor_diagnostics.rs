//! Root-private observations of the original Supervisor; never authority.
use super::{Result, fs};
use codex_hepta_contracts::AgentId;
use codex_hepta_supervisor::{
    AgentSupervisorSnapshot, ProcessExit, ProcessLog, ProcessStream, SupervisorEvent,
    SupervisorEventKind,
};
use serde::Serialize;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

const FILE_NAME: &str = "supervisor-final.json";
const LOG_BYTES: usize = 16 * 1024;
const LOG_ENTRIES: usize = 32;
const EVENT_ENTRIES: usize = 16;

#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum ObservationPhase {
    Startup,
    Monitor,
}

#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum CleanupObservation {
    StopLoopReturned,
    KillLoopReturned,
    Unconfirmed,
}

pub(super) struct DiagnosticSink {
    directory: PathBuf,
    device: u64,
    inode: u64,
}

impl DiagnosticSink {
    pub(super) fn prepare(directory: &Path) -> Result<Self> {
        let metadata = private_directory(directory)?;
        match std::fs::symlink_metadata(directory.join(FILE_NAME)) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
            Ok(_) => return Err("original Supervisor diagnostic already exists".into()),
        }
        Ok(Self {
            directory: directory.to_path_buf(),
            device: metadata.dev(),
            inode: metadata.ino(),
        })
    }

    pub(super) fn retain(
        &self,
        agent: &AgentId,
        phase: ObservationPhase,
        cleanup: CleanupObservation,
        before: Option<Captured>,
        after: Option<Captured>,
    ) -> Result<()> {
        let metadata = private_directory(&self.directory)?;
        if (metadata.dev(), metadata.ino()) != (self.device, self.inode) {
            return Err("original Supervisor diagnostic directory changed".into());
        }
        let document = FinalObservation::new(agent, phase, cleanup, before, after);
        // The existing writer requires <=64 KiB, O_EXCL/O_NOFOLLOW, mode 0600,
        // file fsync and parent fsync. Failure never authorizes a retry/replace.
        fs::json_new(&self.directory.join(FILE_NAME), &document)
    }
}

fn private_directory(directory: &Path) -> Result<std::fs::Metadata> {
    // SAFETY: only actual current credentials are observed.
    if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
        return Err("actual Root is required for private Supervisor diagnostics".into());
    }
    fs::root_directory(directory)?;
    let metadata = std::fs::symlink_metadata(directory)?;
    if metadata.mode() & 0o7777 != 0o700 {
        return Err("Root0700 Supervisor diagnostic directory required".into());
    }
    Ok(metadata)
}

/// Captures only already-observed original ring data. It never polls a child,
/// drains a pipe, changes the original owner, or waits for an extra observation.
pub(super) struct Captured {
    snapshot: SnapshotObservation,
    logs: LogTail,
}

impl Captured {
    pub(super) fn from_snapshot(snapshot: AgentSupervisorSnapshot) -> Self {
        Self {
            snapshot: SnapshotObservation {
                active: snapshot.active,
                healthy: snapshot.healthy,
                runtime_generation: snapshot.runtime_generation,
                spawn_generation: snapshot.spawn_generation,
                process_system_id: snapshot.process_system_id,
                observed_event_count: snapshot.events.len(),
                omitted_event_count: snapshot.events.len().saturating_sub(EVENT_ENTRIES),
                last_agent_exit: snapshot.events.iter().rev().find_map(|event| {
                    if let SupervisorEventKind::Exited(exit) = &event.kind {
                        Some(ExitObservation::new(event.generation, *exit))
                    } else {
                        None
                    }
                }),
                events: snapshot
                    .events
                    .iter()
                    .skip(snapshot.events.len().saturating_sub(EVENT_ENTRIES))
                    .map(EventObservation::from_event)
                    .collect(),
            },
            logs: LogTail::from_logs(&snapshot.logs),
        }
    }
}

#[derive(Serialize)]
struct FinalObservation {
    schema: &'static str,
    scope: &'static str,
    agent_id: String,
    phase: ObservationPhase,
    cleanup_observation: CleanupObservation,
    before_cleanup: Option<SnapshotObservation>,
    after_cleanup: Option<SnapshotObservation>,
    log_snapshot: &'static str,
    log_tail: LogTail,
    historical_ring_loss_and_late_pipe_bytes: &'static str,
    event_payloads_omitted: bool,
    authority_granted: bool,
}

impl FinalObservation {
    fn new(
        agent: &AgentId,
        phase: ObservationPhase,
        cleanup: CleanupObservation,
        before: Option<Captured>,
        after: Option<Captured>,
    ) -> Self {
        let (before_cleanup, before_logs) = before.map_or((None, None), |value| {
            (Some(value.snapshot), Some(value.logs))
        });
        let (after_cleanup, after_logs) = after.map_or((None, None), |value| {
            (Some(value.snapshot), Some(value.logs))
        });
        let (log_snapshot, log_tail) = match (before_logs, after_logs) {
            (_, Some(logs)) if logs.observed_bytes > 0 => ("after_cleanup", logs),
            (Some(logs), _) => ("before_cleanup", logs),
            (None, Some(logs)) => ("after_cleanup", logs),
            (None, None) => ("unavailable", LogTail::from_logs(&[])),
        };
        Self {
            schema: "trill.original-root.supervisor-diagnostic.v1",
            scope: "original_observed_supervisor_ring_only",
            agent_id: agent.to_string(),
            phase,
            cleanup_observation: cleanup,
            before_cleanup,
            after_cleanup,
            log_snapshot,
            log_tail,
            historical_ring_loss_and_late_pipe_bytes: "unknown",
            event_payloads_omitted: true,
            authority_granted: false,
        }
    }
}

#[derive(Serialize)]
struct SnapshotObservation {
    active: bool,
    healthy: bool,
    runtime_generation: Option<u64>,
    spawn_generation: Option<u64>,
    process_system_id: Option<u64>,
    observed_event_count: usize,
    omitted_event_count: usize,
    last_agent_exit: Option<ExitObservation>,
    events: Vec<EventObservation>,
}

#[derive(Serialize)]
struct ExitObservation {
    generation: u64,
    success: bool,
    code: Option<i32>,
}

impl ExitObservation {
    fn new(generation: u64, exit: ProcessExit) -> Self {
        Self {
            generation,
            success: exit.success,
            code: exit.code,
        }
    }
}

#[derive(Serialize)]
struct EventObservation {
    generation: u64,
    kind: &'static str,
    exit: Option<ExitObservation>,
}

impl EventObservation {
    fn from_event(event: &SupervisorEvent) -> Self {
        use SupervisorEventKind as Kind;
        let kind = match &event.kind {
            Kind::Spawned => "spawned",
            Kind::Healthy => "healthy",
            Kind::Lifecycle(_) => "lifecycle",
            Kind::DrainRequested => "drain_requested",
            Kind::StopRequested => "stop_requested",
            Kind::KillRequested => "kill_requested",
            Kind::RestartQueued => "restart_queued",
            Kind::AutomaticRestartQueued { .. } => "automatic_restart_queued",
            Kind::AutomaticRestartBudgetExhausted { .. } => "automatic_restart_budget_exhausted",
            Kind::UpgradeQueued { .. } => "upgrade_queued",
            Kind::UpgradeCommitted { .. } => "upgrade_committed",
            Kind::AutomaticRollbackQueued { .. } => "automatic_rollback_queued",
            Kind::AutomaticRollbackCommitted { .. } => "automatic_rollback_committed",
            Kind::AutomaticRollbackFailed { .. } => "automatic_rollback_failed",
            Kind::ExplicitRollbackQueued { .. } => "explicit_rollback_queued",
            Kind::ExplicitRollbackCommitted { .. } => "explicit_rollback_committed",
            Kind::Exited(_) => "exited",
            Kind::OrphanAdopted => "orphan_adopted",
            Kind::OrphanMissing => "orphan_missing",
            Kind::OrphanRejected => "orphan_rejected",
            Kind::MatrixSpawned => "matrix_spawned",
            Kind::MatrixHealthy => "matrix_healthy",
            Kind::MatrixStopRequested => "matrix_stop_requested",
            Kind::MatrixKillRequested => "matrix_kill_requested",
            Kind::MatrixExited(_) => "matrix_exited",
            Kind::MatrixOrphanAdopted => "matrix_orphan_adopted",
            Kind::MatrixOrphanMissing => "matrix_orphan_missing",
            Kind::MatrixOrphanRejected => "matrix_orphan_rejected",
            Kind::MatrixDegraded(_) => "matrix_degraded",
            Kind::MatrixRestartBudgetExhausted { .. } => "matrix_restart_budget_exhausted",
            Kind::GenerationFenced { .. } => "generation_fenced",
            Kind::DriverFault(_) => "driver_fault",
        };
        let exit = match &event.kind {
            Kind::Exited(exit) | Kind::MatrixExited(exit) => {
                Some(ExitObservation::new(event.generation, *exit))
            }
            _ => None,
        };
        Self {
            generation: event.generation,
            kind,
            exit,
        }
    }
}

#[derive(Serialize)]
struct LogTail {
    observed_entries: usize,
    observed_bytes: usize,
    retained_entries: usize,
    retained_bytes: usize,
    omitted_entries: usize,
    omitted_bytes: usize,
    chunks: Vec<LogChunk>,
}

#[derive(Serialize)]
struct LogChunk {
    stream: &'static str,
    original_entry_bytes: usize,
    retained_tail_bytes: usize,
    bytes_hex: String,
}

impl LogTail {
    fn from_logs(logs: &[ProcessLog]) -> Self {
        let observed_bytes = logs.iter().map(|log| log.bytes.len()).sum();
        let mut remaining = LOG_BYTES;
        let mut chunks = Vec::new();
        for log in logs.iter().rev().take(LOG_ENTRIES) {
            if remaining == 0 {
                break;
            }
            let length = log.bytes.len().min(remaining);
            let bytes = &log.bytes[log.bytes.len() - length..];
            let mut bytes_hex = String::with_capacity(length * 2);
            const HEX: &[u8; 16] = b"0123456789abcdef";
            for byte in bytes {
                bytes_hex.push(char::from(HEX[usize::from(byte >> 4)]));
                bytes_hex.push(char::from(HEX[usize::from(byte & 15)]));
            }
            chunks.push(LogChunk {
                stream: match log.stream {
                    ProcessStream::Stdout => "stdout",
                    ProcessStream::Stderr => "stderr",
                },
                original_entry_bytes: log.bytes.len(),
                retained_tail_bytes: length,
                bytes_hex,
            });
            remaining -= length;
        }
        chunks.reverse();
        let retained_entries = chunks.len();
        let retained_bytes = LOG_BYTES - remaining;
        Self {
            observed_entries: logs.len(),
            observed_bytes,
            retained_entries,
            retained_bytes,
            omitted_entries: logs.len() - retained_entries,
            omitted_bytes: observed_bytes - retained_bytes,
            chunks,
        }
    }
}

#[cfg(test)]
#[path = "supervisor_diagnostics_tests.rs"]
mod tests;
