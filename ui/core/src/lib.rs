//! Host-only desktop prototype messages. These are NOT HOS2, a kernel permission
//! protocol, or a trusted Hepta operation ledger.
use serde::{Deserialize, Serialize};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub const MAX_FRAME: usize = 64 * 1024;
// This is an ephemeral UX transport, never an unbounded task/event ledger.
pub const MAX_TRACKED_TASKS: usize = 96;
pub const MAX_ACTIVE_TASKS: usize = 24;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Workspace {
    Personal,
    Research,
    Build,
}

impl Workspace {
    pub const ALL: [Workspace; 3] = [Self::Personal, Self::Research, Self::Build];

    pub fn name(self) -> &'static str {
        match self {
            Self::Personal => "Personal",
            Self::Research => "Research",
            Self::Build => "Build",
        }
    }

    pub fn code(self) -> &'static str {
        match self {
            Self::Personal => "personal",
            Self::Research => "research",
            Self::Build => "build",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AppKind {
    Notes,
    Calculator,
    /// A deliberately restricted task terminal. It is an app window, not a
    /// shell: the client only implements a fixed command allowlist and never
    /// spawns a user supplied process.
    Terminal,
}

impl AppKind {
    pub const ALL: [AppKind; 3] = [Self::Notes, Self::Calculator, Self::Terminal];

    pub fn name(self) -> &'static str {
        match self {
            Self::Notes => "Notes / 笔记",
            Self::Calculator => "Calculator / 计算器",
            Self::Terminal => "Restricted Terminal / 受限终端",
        }
    }

    pub fn code(self) -> &'static str {
        match self {
            Self::Notes => "notes",
            Self::Calculator => "calculator",
            Self::Terminal => "terminal",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskState {
    Pending,
    Running,
    Completed,
    Failed,
    Partial,
    Unknown,
    CancelRequested,
    Cancelled,
}

impl TaskState {
    pub fn label(self) -> &'static str {
        match self {
            Self::Pending => "PENDING",
            Self::Running => "RUNNING",
            Self::Completed => "COMPLETED",
            Self::Failed => "FAILED",
            Self::Partial => "PARTIAL",
            Self::Unknown => "UNKNOWN",
            Self::CancelRequested => "CANCEL REQUESTED",
            Self::Cancelled => "CANCELLED",
        }
    }

    pub fn is_terminal(self) -> bool {
        matches!(self, Self::Completed | Self::Failed | Self::Cancelled)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TaskRecord {
    pub id: u64,
    pub workspace: Workspace,
    pub app: AppKind,
    pub state: TaskState,
    pub pid: Option<u32>,
    pub exit_code: Option<i32>,
    pub detail: String,
    pub created_unix_ms: u64,
    pub updated_unix_ms: u64,
    pub execution_mode: String,
    pub hos2_revision: Option<u64>,
    /// First completed egui App::update widget layout, signalled by THIS child.
    /// This is not a compositor surface-mapped or GPU-fence confirmation.
    pub ui_first_frame_unix_ms: Option<u64>,
}

impl TaskRecord {
    pub fn new(id: u64, workspace: Workspace, app: AppKind) -> Self {
        let now = unix_ms();
        Self {
            id,
            workspace,
            app,
            state: TaskState::Pending,
            pid: None,
            exit_code: None,
            detail: "Waiting for host process spawn".to_owned(),
            created_unix_ms: now,
            updated_unix_ms: now,
            execution_mode: match app {
                AppKind::Terminal => "linux_host_process_restricted_terminal".to_owned(),
                _ => "linux_host_process".to_owned(),
            },
            hos2_revision: None,
            ui_first_frame_unix_ms: None,
        }
    }

    /// Only the lifecycle owner may call this. An LLM message is not evidence.
    pub fn transition(&mut self, to: TaskState) -> bool {
        use TaskState::*;
        let valid = matches!(
            (self.state, to),
            (Pending, Running | Failed)
                | (
                    Running,
                    Completed | Failed | Partial | Unknown | CancelRequested
                )
                | (Partial, Completed | Failed | Unknown | CancelRequested)
                | (Unknown, Completed | Failed | Partial | CancelRequested)
                | (CancelRequested, Cancelled | Completed | Failed | Unknown)
        );
        if valid {
            self.state = to;
            self.updated_unix_ms = unix_ms();
        }
        valid
    }
}

/// Host-only Unix socket metadata, not a Wayland protocol handshake or a
/// claim that an application's surface is mapped or recoverable.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WaylandSocketStatus {
    #[default]
    Unconfigured,
    Missing,
    NotSocket,
    SocketObserved,
}

impl WaylandSocketStatus {
    pub const fn label(self) -> &'static str {
        match self {
            Self::Unconfigured => "NOT CONFIGURED",
            Self::Missing => "SOCKET MISSING",
            Self::NotSocket => "UNTRUSTED SOCKET PATH",
            Self::SocketObserved => "SOCKET PRESENT (UNVERIFIED)",
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostWaylandObservation {
    pub status: WaylandSocketStatus,
    /// Monotone within this unprivileged host Session only. No A05/A07 trust.
    pub socket_observation_epoch: u64,
    pub sampled_unix_ms: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostResources {
    pub sampled_unix_ms: u64,
    pub mem_total_kib: Option<u64>,
    pub mem_available_kib: Option<u64>,
    pub load_average_1m: Option<f32>,
    pub source: String,
    /// Older host snapshots must default to unknown rather than implying a
    /// live compositor or restored Wayland surface.
    #[serde(default)]
    pub wayland: HostWaylandObservation,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Request {
    Snapshot,
    Launch {
        workspace: Workspace,
        app: AppKind,
        expected_instance: String,
    },
    Cancel {
        id: u64,
        expected_instance: String,
    },
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Response {
    Snapshot {
        tasks: Vec<TaskRecord>,
        resources: HostResources,
        session_instance: String,
    },
    Task {
        task: TaskRecord,
        session_instance: String,
    },
    Error {
        message: String,
        session_instance: String,
    },
}

pub fn unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .min(u128::from(u64::MAX)) as u64
}

pub fn socket_path() -> io::Result<PathBuf> {
    let runtime = std::env::var_os("XDG_RUNTIME_DIR").ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::NotFound,
            "XDG_RUNTIME_DIR must name a private directory",
        )
    })?;
    let runtime = PathBuf::from(runtime);
    if !runtime.is_absolute() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "XDG_RUNTIME_DIR must be absolute",
        ));
    }
    Ok(runtime.join("trillionnium-ui").join("session.sock"))
}

pub fn read_frame<R: Read>(input: R) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    let mut reader = BufReader::new(input.take((MAX_FRAME + 1) as u64));
    reader.read_until(b'\n', &mut bytes)?;
    if bytes.is_empty() || bytes.len() > MAX_FRAME || bytes.last() != Some(&b'\n') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid or oversized IPC frame",
        ));
    }
    Ok(bytes)
}

/// Serialize exactly one length-bounded newline-delimited JSON frame.
/// The receiver must reject oversized frames rather than partially parse data.
pub fn write_frame<W: Write, T: Serialize>(mut out: W, value: &T) -> io::Result<()> {
    let bytes = serde_json::to_vec(value).map_err(io::Error::other)?;
    if bytes.len() + 1 > MAX_FRAME {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "IPC output exceeds MAX_FRAME",
        ));
    }
    out.write_all(&bytes)?;
    out.write_all(b"\n")
}

#[cfg(unix)]
pub fn request(req: &Request) -> io::Result<Response> {
    request_at(&socket_path()?, req)
}

/// The supplied path supports tests using a private temporary runtime dir.
/// This is transport plumbing, not a permissions authority.
#[cfg(unix)]
pub fn request_at(socket: &Path, req: &Request) -> io::Result<Response> {
    use std::os::unix::net::UnixStream;
    let mut stream = UnixStream::connect(socket)?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    write_frame(&mut stream, req)?;
    let frame = read_frame(&mut stream)?;
    serde_json::from_slice(&frame).map_err(io::Error::other)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn old_host_snapshot_defaults_to_unconfigured_wayland() {
        let old = r#"{"sampled_unix_ms":5,"mem_total_kib":null,"mem_available_kib":null,"load_average_1m":null,"source":"old host"}"#;
        let resources: HostResources = serde_json::from_str(old).unwrap();
        assert_eq!(resources.wayland.status, WaylandSocketStatus::Unconfigured);
        assert_eq!(resources.wayland.socket_observation_epoch, 0);
        assert_eq!(resources.wayland.status.label(), "NOT CONFIGURED");
    }

    #[test]
    fn real_terminal_state_requires_prior_running() {
        let mut task = TaskRecord::new(1, Workspace::Build, AppKind::Notes);
        assert!(!task.transition(TaskState::Completed));
        assert_eq!(task.state, TaskState::Pending);
        assert!(task.transition(TaskState::Running));
        assert!(task.transition(TaskState::CancelRequested));
        assert!(task.transition(TaskState::Completed)); // independently observed exit may race SIGKILL
        assert!(!task.transition(TaskState::Running));
    }

    #[test]
    fn all_unsettled_states_have_distinct_labels() {
        let states = [
            TaskState::Pending,
            TaskState::Running,
            TaskState::Partial,
            TaskState::Unknown,
            TaskState::CancelRequested,
            TaskState::Failed,
            TaskState::Completed,
            TaskState::Cancelled,
        ];
        let mut labels = std::collections::HashSet::new();
        for state in states {
            assert!(labels.insert(state.label()));
        }
        assert!(!TaskState::Unknown.is_terminal());
        assert!(!TaskState::CancelRequested.is_terminal());
    }

    #[test]
    fn utf8_round_trip_preserves_chinese_ime_text() {
        let message = "中文输入测试：拼音、候选词、焦点切换 📝";
        let encoded = serde_json::to_vec(&message).unwrap();
        let decoded: String = serde_json::from_slice(&encoded).unwrap();
        assert_eq!(message, decoded);
    }

    #[test]
    fn framing_rejects_unterminated_or_oversized_inputs() {
        assert!(read_frame("{}".as_bytes()).is_err());
        assert!(read_frame(vec![b'x'; MAX_FRAME + 2].as_slice()).is_err());
        assert_eq!(read_frame("{}\n".as_bytes()).unwrap(), b"{}\n");
    }

    #[test]
    fn serialized_ipc_output_is_also_bounded() {
        let mut out = Vec::new();
        let oversized = "x".repeat(MAX_FRAME);
        let err = write_frame(&mut out, &oversized).unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::InvalidData);
        assert!(out.is_empty(), "no partial success frame may be sent");
        write_frame(&mut out, &"中文").unwrap();
        assert_eq!(
            serde_json::from_slice::<String>(&read_frame(out.as_slice()).unwrap()).unwrap(),
            "中文"
        );
    }

    #[test]
    fn write_commands_require_session_fencing_identity() {
        let without_generation = r#"{"type":"cancel","id":1}"#;
        assert!(serde_json::from_str::<Request>(without_generation).is_err());
        let command = Request::Cancel {
            id: 1,
            expected_instance: "generation-A".into(),
        };
        let encoded = serde_json::to_string(&command).unwrap();
        let decoded: Request = serde_json::from_str(&encoded).unwrap();
        assert!(
            matches!(decoded, Request::Cancel { id: 1, expected_instance } if expected_instance == "generation-A")
        );
    }

    #[test]
    fn unknown_task_status_does_not_deserialize_as_success() {
        assert!(serde_json::from_str::<TaskState>("\"successful\"").is_err());
        assert_eq!(
            serde_json::from_str::<TaskState>("\"unknown\"").unwrap(),
            TaskState::Unknown
        );
    }
}
