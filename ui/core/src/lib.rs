//! Host-only desktop prototype messages. These are NOT HOS2, a kernel permission
//! protocol, or a trusted Hepta operation ledger.
pub mod conversation;
pub mod hepta;
pub mod notes;
pub mod notes_bootstrap;
#[cfg(target_os = "linux")]
pub mod notes_private_unix;
pub mod notes_recovery;
#[cfg(target_os = "linux")]
pub mod notes_store;
pub mod objective;
pub mod observation;

#[cfg(feature = "hepta-shared-presenter")]
pub mod shared_chat;

use serde::{Deserialize, Serialize};

pub mod host_peer;
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
    /// Linux host Wayland socket epoch observed when Session requested this
    /// native child launch. This is NOT a surface-mapped or connected event.
    #[serde(default)]
    pub wayland_socket_epoch_at_launch: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub notes_destination: Option<notes::NotesDestinationObservation>,
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
            wayland_socket_epoch_at_launch: None,
            notes_destination: None,
        }
    }

    /// A Linux socket change may invalidate the old client display channel,
    /// but even a matching socket epoch does NOT prove Wayland surface mapping.
    pub fn host_window_observation(
        &self,
        current: &HostWaylandObservation,
    ) -> HostWindowObservation {
        let Some(at_launch) = self.wayland_socket_epoch_at_launch else {
            return HostWindowObservation::NoSocketAtLaunch;
        };
        if current.status != WaylandSocketStatus::SocketObserved {
            return HostWindowObservation::SocketUnavailable;
        }
        if current.socket_observation_epoch != at_launch {
            return HostWindowObservation::SocketChanged;
        }
        HostWindowObservation::SameSocketUnverified
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

/// Unprivileged host metadata classification; there is intentionally no
/// "window restored" or "surface ready" result without a compositor receipt.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HostWindowObservation {
    NoSocketAtLaunch,
    SocketUnavailable,
    SocketChanged,
    SameSocketUnverified,
}

impl HostWindowObservation {
    pub const fn label(self) -> &'static str {
        match self {
            Self::NoSocketAtLaunch => "UNVERIFIED: NO WAYLAND SOCKET AT LAUNCH",
            Self::SocketUnavailable => "UNVERIFIED: WAYLAND SOCKET UNAVAILABLE",
            Self::SocketChanged => "UNVERIFIED: WAYLAND SOCKET CHANGED SINCE LAUNCH",
            Self::SameSocketUnverified => "UNVERIFIED: SAME SOCKET METADATA",
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
    #[serde(default, deserialize_with = "deserialize_host_load_legacy")]
    pub load_average_1m: Option<f32>,
    pub source: String,
    /// Older host snapshots must default to unknown rather than implying a
    /// live compositor or restored Wayland surface.
    #[serde(default)]
    pub wayland: HostWaylandObservation,
}

// Preserve the original JSON number dispatch for this observation: integer
// tokens narrow directly from i64/u64, and decimal tokens narrow from f64.
// Requesting f32 directly would enable serde_json's feature-unified single-
// precision parser; converting every token through f64 would instead double-
// round some large integers. Missing/null and accepted f32 overflow stay local
// observation semantics, not an authority or completion assertion. The native
// Hepta graph also enables arbitrary_precision, whose decimal number visits a
// private serde map. Use serde_json's Number implementation to consume that
// representation even inside Response's internally tagged serde buffer.
// RawValue cannot be deserialized through that buffer.
fn deserialize_host_load_legacy<'de, D>(deserializer: D) -> Result<Option<f32>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let Some(number) = Option::<serde_json::Number>::deserialize(deserializer)? else {
        return Ok(None);
    };
    if let Some(value) = number.as_u64() {
        return Ok(Some(value as f32));
    }
    if let Some(value) = number.as_i64() {
        return Ok(Some(value as f32));
    }
    let value = number
        .as_f64()
        .filter(|value| value.is_finite())
        .ok_or_else(|| {
            serde::de::Error::custom("host load exceeds the original JSON number range")
        })?;
    Ok(Some(value as f32))
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Request {
    Snapshot,
    ObjectiveAvailability {
        expected_instance: String,
    },
    ObjectiveSubmit {
        client_intent_id: String,
        text: String,
        expected_instance: String,
    },
    ObjectiveStatus {
        client_intent_id: String,
        expected_instance: String,
    },
    ObjectiveCancel {
        client_intent_id: String,
        expected_instance: String,
    },
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
    Objective {
        observation: objective::ObjectiveObservation,
        session_instance: String,
    },
    Snapshot {
        tasks: Vec<TaskRecord>,
        resources: HostResources,
        session_instance: String,
        /// Optional on older host snapshots. A missing field is NOT OBSERVED.
        #[serde(default)]
        hepta: hepta::HeptaProjection,
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

/// A strict host-UI request object. Serde's internally tagged enum with a
/// unit Snapshot variant may accept extra JSON keys even with
/// deny_unknown_fields; parsing directly as Request is not a wire-level
/// unknown-field and duplicate-key rejection contract.
struct UniqueRequestFields(serde_json::Map<String, serde_json::Value>);

impl<'de> Deserialize<'de> for UniqueRequestFields {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        use serde::de::{Error, MapAccess, Visitor};
        struct UniqueObjectVisitor;
        impl<'de> Visitor<'de> for UniqueObjectVisitor {
            type Value = UniqueRequestFields;

            fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                formatter.write_str("a single host UI request JSON object")
            }

            fn visit_map<A>(self, mut input: A) -> Result<Self::Value, A::Error>
            where
                A: MapAccess<'de>,
            {
                let mut fields = serde_json::Map::new();
                while let Some((key, value)) = input.next_entry::<String, serde_json::Value>()? {
                    if fields.insert(key, value).is_some() {
                        return Err(A::Error::custom("duplicate host request key"));
                    }
                }
                Ok(UniqueRequestFields(fields))
            }
        }
        deserializer.deserialize_map(UniqueObjectVisitor)
    }
}

/// Exactly one bounded, schema-matching request. Reject unsolicited or
/// duplicate fields BEFORE Session can read/launch/kill any owned process.
/// This is an unprivileged Linux host UX IPC guard, NOT A05 authorization.
pub fn parse_host_request(frame: &[u8]) -> io::Result<Request> {
    if frame.len() > MAX_FRAME {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Host request exceeds MAX_FRAME",
        ));
    }
    let UniqueRequestFields(fields) = serde_json::from_slice(frame)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    let allowed: &[&str] = match fields.get("type").and_then(serde_json::Value::as_str) {
        Some("snapshot") => &["type"],
        Some("objective_availability") => &["type", "expected_instance"],
        Some("objective_submit") => &["type", "client_intent_id", "text", "expected_instance"],
        Some("objective_status" | "objective_cancel") => {
            &["type", "client_intent_id", "expected_instance"]
        }
        Some("launch") => &["type", "workspace", "app", "expected_instance"],
        Some("cancel") => &["type", "id", "expected_instance"],
        _ => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Unknown or missing host request type",
            ))
        }
    };
    if fields.len() != allowed.len() || fields.keys().any(|name| !allowed.contains(&name.as_str()))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Missing or unexpected host request field",
        ));
    }
    serde_json::from_value(serde_json::Value::Object(fields))
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))
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
    // Verify the kernel's server UID BEFORE sending a request or trusting a
    // snapshot. A forged cross-UID socket must not supply fake host tasks.
    host_peer::require_same_uid_peer(&stream)?;
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
    fn older_session_snapshot_cannot_claim_a_hepta_connection() {
        let old = r#"{"type":"snapshot","tasks":[],"resources":{"sampled_unix_ms":5,"mem_total_kib":null,"mem_available_kib":null,"load_average_1m":null,"source":"old host"},"session_instance":"old"}"#;
        let Response::Snapshot { hepta, .. } = serde_json::from_str(old).unwrap() else {
            panic!("expected snapshot");
        };
        assert_eq!(hepta.connection, hepta::HeptaConnectionState::NotObserved);
        assert!(hepta.last_observation.is_none());
    }

    #[test]
    fn host_request_schema_rejects_unknown_and_duplicate_fields_before_effects() {
        for invalid in [
            r#"{"type":"snapshot","data":[1]}"#,
            r#"{"type":"snapshot","type":"snapshot"}"#,
            r#"{"type":"snapshot","expected_instance":"irrelevant"}"#,
            r#"{"type":"launch","workspace":"personal","app":"notes","expected_instance":"A","surprise":true}"#,
            r#"{"type":"launch","workspace":"personal","app":"notes","expected_instance":"A","workspace":"research"}"#,
            r#"{"type":"cancel","id":7,"expected_instance":"A","id":8}"#,
            r#"{"type":"cancel","id":7,"expected_instance":"A","extra":0}"#,
            r#"{"type":"cancel","id":7,"expected_instance":"A","app":"notes"}"#,
            r#"{"type":"cancel","id":"7","expected_instance":"A"}"#,
            r#"{"type":"launch","workspace":"personal","expected_instance":"A"}"#,
            r#"{"type":"snapshot","extra":{"type":"launch"}}"#,
            r#"{"type":"not-an-operation"}"#,
            r#"["snapshot"]"#,
            r#"null"#,
        ] {
            assert!(
                parse_host_request(invalid.as_bytes()).is_err(),
                "Unexpectedly accepted host control request: {invalid}"
            );
        }
        let valid_snapshot = parse_host_request(br#"{"type":"snapshot"}"#).unwrap();
        assert!(matches!(valid_snapshot, Request::Snapshot));

        let valid_launch = parse_host_request(
            br#"{"type":"launch","workspace":"research","app":"notes","expected_instance":"A"}"#,
        )
        .unwrap();
        assert!(matches!(
            valid_launch,
            Request::Launch {
                workspace: Workspace::Research,
                app: AppKind::Notes,
                expected_instance,
            } if expected_instance == "A"
        ));
        let valid_cancel =
            parse_host_request(br#"{"type":"cancel","id":17,"expected_instance":"A"}"#).unwrap();
        assert!(matches!(
            valid_cancel,
            Request::Cancel {
                id: 17,
                expected_instance,
            } if expected_instance == "A"
        ));
    }

    #[test]
    fn old_host_snapshot_defaults_to_unconfigured_wayland() {
        let old = r#"{"sampled_unix_ms":5,"mem_total_kib":null,"mem_available_kib":null,"load_average_1m":null,"source":"old host"}"#;
        let resources: HostResources = serde_json::from_str(old).unwrap();
        assert_eq!(resources.wayland.status, WaylandSocketStatus::Unconfigured);
        assert_eq!(resources.wayland.socket_observation_epoch, 0);
        assert_eq!(resources.wayland.status.label(), "NOT CONFIGURED");
    }

    #[test]
    fn per_app_wayland_socket_epoch_is_never_surface_restoration_proof() {
        let mut app = TaskRecord::new(1, Workspace::Research, AppKind::Notes);
        let mut sampled = HostWaylandObservation {
            status: WaylandSocketStatus::SocketObserved,
            socket_observation_epoch: 7,
            sampled_unix_ms: 1,
        };
        assert_eq!(
            app.host_window_observation(&sampled),
            HostWindowObservation::NoSocketAtLaunch
        );
        app.wayland_socket_epoch_at_launch = Some(7);
        assert_eq!(
            app.host_window_observation(&sampled),
            HostWindowObservation::SameSocketUnverified
        );
        sampled.socket_observation_epoch = 8;
        assert_eq!(
            app.host_window_observation(&sampled),
            HostWindowObservation::SocketChanged
        );
        sampled.status = WaylandSocketStatus::Missing;
        assert_eq!(
            app.host_window_observation(&sampled),
            HostWindowObservation::SocketUnavailable
        );
        assert!(app
            .host_window_observation(&sampled)
            .label()
            .contains("UNVERIFIED"));
    }

    #[test]
    fn old_task_json_without_socket_epoch_is_fail_closed() {
        let task = TaskRecord::new(9, Workspace::Build, AppKind::Calculator);
        let json = serde_json::to_string(&task).unwrap();
        let old = json.replace(",\"wayland_socket_epoch_at_launch\":null", "");
        assert_ne!(json, old);
        let decoded: TaskRecord = serde_json::from_str(&old).unwrap();
        assert_eq!(decoded.wayland_socket_epoch_at_launch, None);
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
