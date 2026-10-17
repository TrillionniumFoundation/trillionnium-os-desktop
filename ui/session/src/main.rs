//! Independent host-only process launcher/lifecycle owner.
//! It is not a Wayland compositor and it grants no kernel permissions.
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions, Permissions};
use std::io::{self, Read};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{DirBuilderExt, FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::mpsc::{self, Receiver, Sender};

use trill_ui_core::{
    read_frame, socket_path, unix_ms, write_frame, AppKind, HostResources, HostWaylandObservation,
    Request, Response, TaskRecord, TaskState, WaylandSocketStatus, Workspace, MAX_ACTIVE_TASKS,
    MAX_TRACKED_TASKS,
};

// Linux flock(2) is advisory; it provides a crash-released startup mutex,
// NOT authentication or isolation from another process with the same UID.
#[cfg(target_os = "linux")]
unsafe extern "C" {
    fn flock(fd: i32, operation: i32) -> i32;
    fn getsockopt(
        fd: i32,
        level: i32,
        optname: i32,
        value: *mut std::ffi::c_void,
        length: *mut u32,
    ) -> i32;
    fn geteuid() -> u32;
}

#[cfg(target_os = "linux")]
const LINUX_O_NOFOLLOW: i32 = 0o400000;

/// This narrow parent/child signal never creates a HOS2 operation or permission.
const FIRST_FRAME_MARKER: &[u8] = b"TRILL_UI_FIRST_FRAME_V1\n";

fn observe_first_frame<R: Read + Send + 'static>(id: u64, mut from_child: R, sender: Sender<u64>) {
    std::thread::spawn(move || {
        let mut frame = [0u8; FIRST_FRAME_MARKER.len()];
        if from_child.read_exact(&mut frame).is_ok() && frame.as_slice() == FIRST_FRAME_MARKER {
            let _ = sender.send(id);
        }
    });
}

#[derive(Clone, Debug, PartialEq, Eq)]
enum DisplayProbe {
    Unconfigured,
    Missing,
    NotSocket,
    Socket { device: u64, inode: u64 },
}

impl DisplayProbe {
    const fn status(&self) -> WaylandSocketStatus {
        match self {
            Self::Unconfigured => WaylandSocketStatus::Unconfigured,
            Self::Missing => WaylandSocketStatus::Missing,
            Self::NotSocket => WaylandSocketStatus::NotSocket,
            Self::Socket { .. } => WaylandSocketStatus::SocketObserved,
        }
    }
}

/// Read-only metadata. No connection is made and no assertion about
/// compositor health, mapped surfaces, focus, or a successful GPU frame.
fn probe_wayland_path(path: Option<&Path>) -> DisplayProbe {
    let Some(path) = path else {
        return DisplayProbe::Unconfigured;
    };
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_socket() => DisplayProbe::Socket {
            device: metadata.dev(),
            inode: metadata.ino(),
        },
        Ok(_) => DisplayProbe::NotSocket, // never follow a fake socket symlink
        Err(error) if error.kind() == io::ErrorKind::NotFound => DisplayProbe::Missing,
        Err(_) => DisplayProbe::NotSocket,
    }
}

fn probe_host_wayland() -> DisplayProbe {
    let Some(name) = std::env::var_os("WAYLAND_DISPLAY") else {
        return DisplayProbe::Unconfigured;
    };
    let display = PathBuf::from(name);
    let resolved = if display.is_absolute() {
        display
    } else {
        let Some(runtime) = std::env::var_os("XDG_RUNTIME_DIR") else {
            return DisplayProbe::Unconfigured;
        };
        PathBuf::from(runtime).join(display)
    };
    probe_wayland_path(Some(&resolved))
}

#[derive(Default)]
struct DisplayTracker {
    last: Option<DisplayProbe>,
    epoch: u64,
}

impl DisplayTracker {
    fn observe(&mut self, probe: DisplayProbe) -> HostWaylandObservation {
        if self.last.as_ref() != Some(&probe) {
            self.last = Some(probe.clone());
            self.epoch = self.epoch.saturating_add(1);
        }
        HostWaylandObservation {
            status: probe.status(),
            socket_observation_epoch: self.epoch,
            sampled_unix_ms: unix_ms(),
        }
    }
}

struct Session {
    display: DisplayTracker,
    instance: String,
    app_binary: PathBuf,
    next_id: u64,
    tasks: BTreeMap<u64, TaskRecord>,
    children: BTreeMap<u64, Child>,
    first_frame_tx: Sender<u64>,
    first_frame_rx: Receiver<u64>,
}

impl Session {
    fn new(app_binary: PathBuf) -> io::Result<Self> {
        // A generation fence must not silently degrade to PID + clock time:
        // after a supervisor crash, task IDs can restart at 1. Host Linux
        // randomness is required; failure is fatal rather than guessable reuse.
        let mut random = [0u8; 16];
        fs::File::open("/dev/urandom")?.read_exact(&mut random)?;
        let instance = random.iter().map(|byte| format!("{byte:02x}")).collect();
        let (first_frame_tx, first_frame_rx) = mpsc::channel();
        Ok(Self {
            display: DisplayTracker::default(),
            instance,
            app_binary,
            next_id: 1,
            tasks: BTreeMap::new(),
            children: BTreeMap::new(),
            first_frame_tx,
            first_frame_rx,
        })
    }

    /// Only completed/failed/confirmed-cancelled records can be pruned.
    /// An unknown or in-flight effect must never disappear to make room.
    fn prepare_launch(&mut self) -> Result<(), &'static str> {
        self.refresh();
        if self.children.len() >= MAX_ACTIVE_TASKS {
            return Err("Too many unreaped host processes; try again after they exit");
        }
        while self.tasks.len() >= MAX_TRACKED_TASKS {
            let oldest_terminal = self
                .tasks
                .iter()
                .find(|(_, task)| task.state.is_terminal())
                .map(|(&id, _)| id);
            if let Some(id) = oldest_terminal {
                self.tasks.remove(&id);
            } else {
                return Err(
                    "Host task history full of nonterminal/unknown work; no effect attempted",
                );
            }
        }
        Ok(())
    }

    fn launch(&mut self, workspace: Workspace, app: AppKind) -> Response {
        if let Err(message) = self.prepare_launch() {
            return Response::Error {
                message: message.into(),
                session_instance: self.instance.clone(),
            };
        }
        let id = self.next_id;
        let Some(next) = id.checked_add(1) else {
            return Response::Error {
                message: "task id exhausted".into(),
                session_instance: self.instance.clone(),
            };
        };
        self.next_id = next;
        let mut task = TaskRecord::new(id, workspace, app);
        // A child can outlive the compositor that was present at launch.
        // Record the socket identity only for later fail-closed comparison.
        let at_launch = self.display.observe(probe_host_wayland());
        if at_launch.status == WaylandSocketStatus::SocketObserved {
            task.wayland_socket_epoch_at_launch = Some(at_launch.socket_observation_epoch);
        }
        // No arbitrary command strings, shell expansion, user paths or elevated rights.
        let spawn = Command::new(&self.app_binary)
            .arg("--kind")
            .arg(app.code())
            .arg("--workspace")
            .arg(workspace.code())
            .arg("--task-id")
            .arg(id.to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::piped()) // private one-frame readiness pipe, not a global text stream
            .spawn();
        match spawn {
            Ok(mut child) => {
                if let Some(stdout) = child.stdout.take() {
                    observe_first_frame(id, stdout, self.first_frame_tx.clone());
                }
                task.pid = Some(child.id());
                task.detail = "Host child spawned; exit outcome not yet known".into();
                task.transition(TaskState::Running);
                self.children.insert(id, child);
            }
            Err(err) => {
                task.detail = format!("Host spawn failed: {err}");
                task.transition(TaskState::Failed);
            }
        }
        self.tasks.insert(id, task.clone());
        Response::Task {
            task,
            session_instance: self.instance.clone(),
        }
    }

    fn refresh(&mut self) {
        while let Ok(id) = self.first_frame_rx.try_recv() {
            if let Some(task) = self.tasks.get_mut(&id) {
                if task.ui_first_frame_unix_ms.is_none() {
                    task.ui_first_frame_unix_ms = Some(unix_ms());
                    task.updated_unix_ms = unix_ms();
                    if !task.state.is_terminal() {
                        task.detail = "Observed child egui first-frame update via private stdout pipe; window mapping/GPU NOT verified".into();
                    }
                }
            }
        }
        let mut reaped = Vec::new();
        for (&id, child) in &mut self.children {
            match child.try_wait() {
                Ok(Some(exit)) => {
                    if let Some(task) = self.tasks.get_mut(&id) {
                        settle_exit(task, exit);
                    }
                    reaped.push(id);
                }
                Ok(None) => {}
                Err(err) => {
                    if let Some(task) = self.tasks.get_mut(&id) {
                        task.transition(TaskState::Unknown);
                        task.detail = format!("Could not observe child exit: {err}");
                    }
                }
            }
        }
        for id in reaped {
            self.children.remove(&id);
        }
    }

    fn cancel(&mut self, id: u64) -> Response {
        let Some(task) = self.tasks.get_mut(&id) else {
            return Response::Error {
                message: format!("task {id} does not exist"),
                session_instance: self.instance.clone(),
            };
        };
        let Some(child) = self.children.get_mut(&id) else {
            return Response::Error {
                message: "No owned live child; no cancellation claimed".into(),
                session_instance: self.instance.clone(),
            };
        };
        if matches!(task.state, TaskState::CancelRequested) {
            return Response::Task {
                task: task.clone(),
                session_instance: self.instance.clone(),
            };
        }
        if task.state.is_terminal() {
            return Response::Error {
                message: "task already terminal".into(),
                session_instance: self.instance.clone(),
            };
        }
        match child.kill() {
            Ok(()) => {
                task.transition(TaskState::CancelRequested);
                task.detail = "SIGKILL sent; confirmation pending child reap".into();
            }
            Err(err) => {
                task.detail = format!("Cancellation request failed: {err}");
                task.updated_unix_ms = unix_ms();
            }
        }
        Response::Task {
            task: task.clone(),
            session_instance: self.instance.clone(),
        }
    }

    fn handle(&mut self, request: Request) -> Response {
        self.refresh();
        match request {
            Request::Snapshot => {
                let observation = self.display.observe(probe_host_wayland());
                Response::Snapshot {
                    tasks: self.tasks.values().rev().cloned().collect(),
                    resources: host_resources(observation),
                    session_instance: self.instance.clone(),
                }
            }
            Request::Launch {
                workspace,
                app,
                expected_instance,
            } => {
                if expected_instance != self.instance {
                    Response::Error {
                        message: "Stale session generation; app launch NOT attempted".into(),
                        session_instance: self.instance.clone(),
                    }
                } else {
                    self.launch(workspace, app)
                }
            }
            Request::Cancel {
                id,
                expected_instance,
            } => {
                if expected_instance != self.instance {
                    Response::Error {
                        message: "Stale session generation; process cancellation NOT attempted"
                            .into(),
                        session_instance: self.instance.clone(),
                    }
                } else {
                    self.cancel(id)
                }
            }
        }
    }
}

fn settle_exit(task: &mut TaskRecord, exit: ExitStatus) {
    let next = if task.state == TaskState::CancelRequested && exit.signal() == Some(9) {
        TaskState::Cancelled
    } else if exit.success() {
        TaskState::Completed
    } else {
        TaskState::Failed
    };
    if !task.transition(next) {
        task.detail = format!("Conflicting lifecycle transition after observed exit: {exit}");
        task.updated_unix_ms = unix_ms();
        return;
    }
    task.exit_code = exit.code();
    task.detail = match task.state {
        TaskState::Completed => "Observed process exit code 0 (not Hepta task completion)".into(),
        TaskState::Cancelled => "Observed SIGKILL termination".into(),
        _ => format!("Observed non-successful process exit: {exit}"),
    };
}

fn host_resources(wayland: HostWaylandObservation) -> HostResources {
    let meminfo = fs::read_to_string("/proc/meminfo").unwrap_or_default();
    let extract = |key: &str| -> Option<u64> {
        meminfo.lines().find_map(|line| {
            line.strip_prefix(key)?
                .split_whitespace()
                .next()?
                .parse()
                .ok()
        })
    };
    let load_average_1m = fs::read_to_string("/proc/loadavg")
        .ok()
        .and_then(|line| line.split_whitespace().next()?.parse::<f32>().ok());
    HostResources {
        sampled_unix_ms: unix_ms(),
        mem_total_kib: extract("MemTotal:"),
        mem_available_kib: extract("MemAvailable:"),
        load_average_1m,
        source: "Linux host /proc and Wayland socket metadata (NOT HOS2)".into(),
        wayland,
    }
}

fn private_socket_dir(path: &std::path::Path) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::other("socket path lacks parent"))?;
    let runtime = parent
        .parent()
        .ok_or_else(|| io::Error::other("no runtime directory"))?;
    let metadata = fs::symlink_metadata(runtime)?;
    if !metadata.file_type().is_dir() || metadata.permissions().mode() & 0o777 != 0o700 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "XDG_RUNTIME_DIR must be exactly 0700",
        ));
    }
    if !parent.exists() {
        // Create with 0700 *atomically*: creating with a default umask then
        // chmod-ing leaves a short world-traversable window on 0022 hosts.
        let mut builder = fs::DirBuilder::new();
        builder.mode(0o700);
        builder.create(parent)?;
    }
    // symlink_metadata deliberately does not follow a replaced directory
    // symlink; reject rather than chmod-ing a possibly redirected path.
    let metadata = fs::symlink_metadata(parent)?;
    if !metadata.file_type().is_dir() || metadata.permissions().mode() & 0o777 != 0o700 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "UI socket directory must be exactly 0700",
        ));
    }
    Ok(())
}

/// Hold the open File throughout Session lifetime. A second supervisor
/// cannot unlink a live predecessor's socket during stale-socket recovery.
/// flock auto-releases even on SIGKILL; the lock file can safely persist.
fn acquire_session_lock(socket: &std::path::Path) -> io::Result<File> {
    #[cfg(not(target_os = "linux"))]
    {
        let _ = socket;
        return Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "Linux host-only session lock",
        ));
    }
    #[cfg(target_os = "linux")]
    {
        let parent = socket
            .parent()
            .ok_or_else(|| io::Error::other("socket path lacks parent"))?;
        let lock_path = parent.join("session.lock");
        let lock = OpenOptions::new()
            .write(true)
            .create(true)
            .mode(0o600)
            .custom_flags(LINUX_O_NOFOLLOW)
            .open(&lock_path)?;
        let metadata = lock.metadata()?;
        if !metadata.file_type().is_file() || metadata.permissions().mode() & 0o777 != 0o600 {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "session.lock must be regular 0600",
            ));
        }
        // LOCK_EX | LOCK_NB: fail immediately if any instance is alive.
        let status = unsafe { flock(lock.as_raw_fd(), 2 | 4) };
        if status != 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(lock)
    }
}

/// Linux's SO_PEERCRED is a host socket boundary, not a trusted HOS2
/// CapSpace, broker identity or authorization for Hepta effects. It rejects
/// a leaked/mispermissioned cross-UID socket before accepting a request.
#[cfg(target_os = "linux")]
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct LinuxPeerCred {
    pid: i32,
    uid: u32,
    gid: u32,
}

#[cfg(target_os = "linux")]
fn linux_socket_peer_credentials(stream: &UnixStream) -> io::Result<LinuxPeerCred> {
    // SOL_SOCKET=1, SO_PEERCRED=17 on Linux. No extra libc dependency or
    // second permission protocol is introduced by these ABI constants.
    const SOL_SOCKET: i32 = 1;
    const SO_PEERCRED: i32 = 17;
    let mut cred = LinuxPeerCred {
        pid: 0,
        uid: u32::MAX,
        gid: u32::MAX,
    };
    let mut length = std::mem::size_of::<LinuxPeerCred>() as u32;
    let rc = unsafe {
        getsockopt(
            stream.as_raw_fd(),
            SOL_SOCKET,
            SO_PEERCRED,
            std::ptr::addr_of_mut!(cred).cast(),
            &mut length,
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error());
    }
    if length != std::mem::size_of::<LinuxPeerCred>() as u32 || cred.pid <= 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Invalid Linux IPC peer credentials",
        ));
    }
    Ok(cred)
}

#[cfg(target_os = "linux")]
fn validate_same_uid(cred: LinuxPeerCred, expected_uid: u32) -> io::Result<()> {
    // Kernel-derived UID match only, not security among processes sharing
    // one UID and not a trusted A05 authority or Hepta capability.
    if cred.uid != expected_uid {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Cross-UID host UI IPC request refused",
        ));
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn require_same_uid_peer(stream: &UnixStream) -> io::Result<()> {
    let cred = linux_socket_peer_credentials(stream)?;
    validate_same_uid(cred, unsafe { geteuid() })
}

#[cfg(not(target_os = "linux"))]
fn require_same_uid_peer(_stream: &UnixStream) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "A10 host UI IPC requires Linux SO_PEERCRED",
    ))
}

fn serve_connection(mut stream: UnixStream, session: &mut Session) -> io::Result<()> {
    require_same_uid_peer(&stream)?;
    // Invalid/malformed peers must not prevent reaping independent apps.
    // A valid Request::Snapshot/Cancel already refreshes in handle(), but
    // rejected frames never reach handle(). Refresh before parsing every peer.
    session.refresh();
    // This is a local single-owner session loop, so an idle same-UID peer
    // must not block task reaping and every other GUI client for two seconds.
    // A legitimate request is <=64 KiB and written as one bounded frame.
    stream.set_read_timeout(Some(std::time::Duration::from_millis(500)))?;
    stream.set_write_timeout(Some(std::time::Duration::from_millis(500)))?;
    let response = match read_frame(&mut stream) {
        Ok(frame) => match serde_json::from_slice::<Request>(&frame) {
            Ok(command) => session.handle(command),
            Err(error) => Response::Error {
                message: format!("Invalid IPC request: {error}"),
                session_instance: session.instance.clone(),
            },
        },
        Err(error) => Response::Error {
            message: format!("Invalid IPC frame: {error}"),
            session_instance: session.instance.clone(),
        },
    };
    // Never emit a partial/truncated JSON frame or silently lose lifecycle
    // provenance if a future TaskRecord field makes a snapshot too large.
    match write_frame(&mut stream, &response) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::InvalidData => write_frame(
            &mut stream,
            &Response::Error {
                message: "Session snapshot is too large; no task state is being asserted".into(),
                session_instance: session.instance.clone(),
            },
        ),
        Err(error) => Err(error),
    }
}

fn main() -> io::Result<()> {
    let socket = socket_path()?;
    private_socket_dir(&socket)?;
    // Never inspect/delete a stale Unix socket until the exclusive lock is
    // acquired. This prevents the dual-starter unlink/rebind race.
    let _instance_lock = acquire_session_lock(&socket)?;
    if let Ok(metadata) = fs::symlink_metadata(&socket) {
        if !metadata.file_type().is_socket() {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "socket path occupied by non-socket",
            ));
        }
        match UnixStream::connect(&socket) {
            Ok(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::AddrInUse,
                    "session service already running",
                ))
            }
            Err(e) if e.kind() == io::ErrorKind::ConnectionRefused => fs::remove_file(&socket)?,
            Err(e) => return Err(e),
        };
    }
    let listener = UnixListener::bind(&socket)?;
    fs::set_permissions(&socket, Permissions::from_mode(0o600))?;
    let app_binary = std::env::current_exe()?.with_file_name("trill-app-window");
    eprintln!(
        "trill-session pid={} socket={} app={}",
        std::process::id(),
        socket.display(),
        app_binary.display()
    );
    let mut session = Session::new(app_binary)?;
    // Reap children even while the shell/client is stopped. Blocking
    // incoming() would accumulate zombies until the GUI reconnects.
    listener.set_nonblocking(true)?;
    loop {
        match listener.accept() {
            Ok((stream, _addr)) => {
                stream.set_nonblocking(false)?;
                if let Err(e) = serve_connection(stream, &mut session) {
                    eprintln!("session request error: {e}");
                }
            }
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                session.refresh();
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => {
                eprintln!("session accept error: {e}");
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::process::ExitStatusExt;
    use std::{thread, time::Duration};

    #[cfg(target_os = "linux")]
    #[test]
    fn connected_host_peer_uses_kernel_credentials_not_claimed_session_id() {
        let (session_side, _client_side) = UnixStream::pair().unwrap();
        let observed = linux_socket_peer_credentials(&session_side).unwrap();
        assert_eq!(observed.uid, unsafe { geteuid() });
        assert_eq!(observed.pid, std::process::id() as i32);
        assert!(require_same_uid_peer(&session_side).is_ok());

        // Reuse the EXACT production predicate with a deliberately
        // mismatched owner UID. No second-user account is needed in CI.
        let other_uid = observed.uid.wrapping_add(1);
        assert_eq!(
            validate_same_uid(observed, other_uid)
                .unwrap_err()
                .kind(),
            io::ErrorKind::PermissionDenied
        );
        assert!(validate_same_uid(observed, observed.uid).is_ok());
    }

    #[test]
    fn display_probe_is_fail_closed_and_socket_epochs_track_observed_changes() {
        let dir = std::env::temp_dir().join(format!(
            "trill-wayland-observe-{}-{}",
            std::process::id(),
            unix_ms()
        ));
        fs::create_dir(&dir).unwrap();
        let socket = dir.join("test-wayland");
        let mut tracker = DisplayTracker::default();
        let initial = tracker.observe(probe_wayland_path(None));
        assert_eq!(initial.status, WaylandSocketStatus::Unconfigured);
        let missing = tracker.observe(probe_wayland_path(Some(&socket)));
        assert_eq!(missing.status, WaylandSocketStatus::Missing);
        assert!(missing.socket_observation_epoch > initial.socket_observation_epoch);

        fs::write(&socket, b"not a socket").unwrap();
        let invalid = tracker.observe(probe_wayland_path(Some(&socket)));
        assert_eq!(invalid.status, WaylandSocketStatus::NotSocket);
        fs::remove_file(&socket).unwrap();

        let listener = UnixListener::bind(&socket).unwrap();
        let present = tracker.observe(probe_wayland_path(Some(&socket)));
        assert_eq!(present.status, WaylandSocketStatus::SocketObserved);
        assert_eq!(
            tracker
                .observe(probe_wayland_path(Some(&socket)))
                .socket_observation_epoch,
            present.socket_observation_epoch,
            "an unchanged socket must not generate false restart events"
        );
        drop(listener);
        fs::remove_file(&socket).unwrap();
        let gone = tracker.observe(probe_wayland_path(Some(&socket)));
        assert_eq!(gone.status, WaylandSocketStatus::Missing);
        assert!(gone.socket_observation_epoch > present.socket_observation_epoch);

        let listener = UnixListener::bind(&socket).unwrap();
        let recreated = tracker.observe(probe_wayland_path(Some(&socket)));
        assert_eq!(recreated.status, WaylandSocketStatus::SocketObserved);
        assert!(recreated.socket_observation_epoch > gone.socket_observation_epoch);
        drop(listener);
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn display_path_symlink_is_not_interpreted_as_a_socket() {
        let dir = std::env::temp_dir().join(format!(
            "trill-wayland-symlink-{}-{}",
            std::process::id(),
            unix_ms()
        ));
        fs::create_dir(&dir).unwrap();
        let socket = dir.join("socket");
        let alias = dir.join("alias");
        let listener = UnixListener::bind(&socket).unwrap();
        std::os::unix::fs::symlink(&socket, &alias).unwrap();
        assert_eq!(probe_wayland_path(Some(&alias)), DisplayProbe::NotSocket);
        drop(listener);
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn session_startup_is_exclusive_and_recovers_a_crashed_lock_owner() {
        let dir = std::env::temp_dir().join(format!(
            "trill-lock-runtime-{}-{}",
            std::process::id(),
            unix_ms()
        ));
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, Permissions::from_mode(0o700)).unwrap();
        let socket = dir.join("trillionnium-ui/session.sock");
        private_socket_dir(&socket).unwrap();
        let first = acquire_session_lock(&socket).unwrap();
        let second = acquire_session_lock(&socket);
        assert_eq!(
            second.unwrap_err().kind(),
            io::ErrorKind::WouldBlock,
            "another session must not replace a live owner"
        );
        drop(first);
        // The on-disk lock remains, but dropping or crashing the first
        // owner releases the kernel lock without requiring stale PID cleanup.
        let third = acquire_session_lock(&socket).unwrap();
        drop(third);
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn session_lock_symlink_is_rejected() {
        let dir = std::env::temp_dir().join(format!(
            "trill-lock-symlink-{}-{}",
            std::process::id(),
            unix_ms()
        ));
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, Permissions::from_mode(0o700)).unwrap();
        let socket = dir.join("trillionnium-ui/session.sock");
        private_socket_dir(&socket).unwrap();
        let protected = dir.join("keep.txt");
        fs::write(&protected, b"do-not-modify").unwrap();
        std::os::unix::fs::symlink(&protected, dir.join("trillionnium-ui/session.lock")).unwrap();
        assert!(acquire_session_lock(&socket).is_err());
        assert_eq!(fs::read(&protected).unwrap(), b"do-not-modify");
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn session_generations_are_strong_and_distinct() {
        let first = Session::new(PathBuf::from("/bin/true")).unwrap();
        let second = Session::new(PathBuf::from("/bin/true")).unwrap();
        assert_ne!(first.instance, second.instance);
        assert_eq!(first.instance.len(), 32); // 128-bit host random generation
        assert!(first.instance.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn runtime_directory_refuses_world_readable_mode() {
        let dir = std::env::temp_dir().join(format!(
            "trill-unsafe-runtime-{}-{}",
            std::process::id(),
            unix_ms()
        ));
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, Permissions::from_mode(0o755)).unwrap();
        let outcome = private_socket_dir(&dir.join("trillionnium-ui/session.sock"));
        assert_eq!(outcome.unwrap_err().kind(), io::ErrorKind::PermissionDenied);
        assert!(!dir.join("trillionnium-ui").exists());
        fs::remove_dir(&dir).unwrap();
    }

    #[test]
    fn non_writable_runtime_or_socket_directory_is_rejected() {
        let dir = std::env::temp_dir().join(format!(
            "trill-nonwritable-runtime-{}-{}",
            std::process::id(),
            unix_ms()
        ));
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, Permissions::from_mode(0o500)).unwrap();
        let socket = dir.join("trillionnium-ui/session.sock");
        let err = private_socket_dir(&socket).unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::PermissionDenied);
        fs::set_permissions(&dir, Permissions::from_mode(0o700)).unwrap();
        let child = dir.join("trillionnium-ui");
        fs::create_dir(&child).unwrap();
        fs::set_permissions(&child, Permissions::from_mode(0o500)).unwrap();
        let err = private_socket_dir(&socket).unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::PermissionDenied);
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn new_ui_socket_directory_starts_private_without_post_create_chmod() {
        let dir = std::env::temp_dir().join(format!(
            "trill-private-dir-{}-{}",
            std::process::id(),
            unix_ms()
        ));
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, Permissions::from_mode(0o700)).unwrap();
        let child = dir.join("trillionnium-ui");
        private_socket_dir(&child.join("session.sock")).unwrap();
        let mode = fs::symlink_metadata(&child).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o700, "session directory must never start as 0755");
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn socket_directory_cannot_be_redirected_through_a_symlink() {
        let dir = std::env::temp_dir().join(format!(
            "trill-symlink-runtime-{}-{}",
            std::process::id(),
            unix_ms()
        ));
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, Permissions::from_mode(0o700)).unwrap();
        fs::create_dir(dir.join("outside")).unwrap();
        std::os::unix::fs::symlink(dir.join("outside"), dir.join("trillionnium-ui")).unwrap();
        let outcome = private_socket_dir(&dir.join("trillionnium-ui/session.sock"));
        assert_eq!(outcome.unwrap_err().kind(), io::ErrorKind::PermissionDenied);
        fs::remove_file(dir.join("trillionnium-ui")).unwrap();
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn malformed_socket_peer_still_allows_child_reaping() {
        use std::io::Write as _;
        let mut session = Session::new(PathBuf::from("/bin/true")).unwrap();
        let Response::Task { task, .. } = session.launch(Workspace::Personal, AppKind::Notes)
        else {
            panic!("expected child");
        };
        // Keep sending malformed frames while /bin/true is scheduled.
        // Never use a fixed sleep as proof the child has already exited.
        let mut settled = false;
        for _ in 0..100 {
            let (mut sender, receiver) = UnixStream::pair().unwrap();
            sender.write_all(b"not-a-json-request\n").unwrap();
            serve_connection(receiver, &mut session).unwrap();
            if session.tasks[&task.id].state == TaskState::Completed {
                settled = true;
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        assert!(settled, "malformed traffic must still reap /bin/true");
        assert_eq!(session.tasks[&task.id].exit_code, Some(0));
        assert!(session.children.is_empty());
    }

    #[test]
    fn first_frame_requires_exact_child_pipe_signal() {
        let (sender, receiver) = mpsc::channel();
        observe_first_frame(
            9,
            io::Cursor::new(b"TRILL_UI_FIRST_FRAME_V1\n".to_vec()),
            sender.clone(),
        );
        assert_eq!(receiver.recv_timeout(Duration::from_secs(2)).unwrap(), 9);
        observe_first_frame(
            10,
            io::Cursor::new(b"AN_APP_DID_NOT_MAP_A_WINDOW\n".to_vec()),
            sender,
        );
        assert!(receiver.recv_timeout(Duration::from_millis(100)).is_err());
    }

    #[test]
    fn normal_exit_is_observed_not_fabricated() {
        let mut session = Session::new(PathBuf::from("/bin/true")).unwrap();
        let Response::Task { task, .. } = session.launch(Workspace::Personal, AppKind::Notes)
        else {
            panic!("expected launch");
        };
        assert_eq!(task.state, TaskState::Running);
        for _ in 0..100 {
            session.refresh();
            if session.tasks[&task.id].state.is_terminal() {
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        assert_eq!(session.tasks[&task.id].state, TaskState::Completed);
        assert_eq!(session.tasks[&task.id].exit_code, Some(0));
    }

    #[test]
    fn restricted_terminal_is_a_real_owned_task_with_explicit_execution_mode() {
        let mut session = Session::new(PathBuf::from("/bin/true")).unwrap();
        let Response::Task { task, .. } = session.launch(Workspace::Build, AppKind::Terminal)
        else {
            panic!("expected terminal child launch");
        };
        assert_eq!(task.state, TaskState::Running);
        assert_eq!(
            task.execution_mode,
            "linux_host_process_restricted_terminal"
        );
        for _ in 0..100 {
            session.refresh();
            if session.tasks[&task.id].state.is_terminal() {
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        assert_eq!(session.tasks[&task.id].state, TaskState::Completed);
        assert_eq!(session.tasks[&task.id].exit_code, Some(0));
        assert!(session.tasks[&task.id].detail.contains("not Hepta"));
    }

    #[test]
    fn cancellation_is_requested_before_real_child_reap_confirms_it() {
        // Linux-host process proof: this test intentionally requires no
        // compositor, IME, GPU or Hepta service.
        // A panic must not leave a 30-second host process orphaned by the
        // test runner. Reap every owned child before removing fixture files.
        struct Fixture {
            dir: std::path::PathBuf,
            session: Option<Session>,
        }
        impl Drop for Fixture {
            fn drop(&mut self) {
                if let Some(session) = self.session.as_mut() {
                    for child in session.children.values_mut() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
                let _ = fs::remove_dir_all(&self.dir);
            }
        }

        let dir = std::env::temp_dir().join(format!(
            "trill-cancel-fixture-{}-{}",
            std::process::id(),
            unix_ms()
        ));
        fs::create_dir(&dir).unwrap();
        let mut fixture = Fixture {
            dir: dir.clone(),
            session: None,
        };
        fs::set_permissions(&dir, Permissions::from_mode(0o700)).unwrap();
        let child_file = dir.join("child.sh");
        fs::write(&child_file, b"#!/bin/sh\nexec /bin/sleep 30\n").unwrap();
        fs::set_permissions(&child_file, Permissions::from_mode(0o700)).unwrap();

        fixture.session = Some(Session::new(child_file).unwrap());
        let session = fixture.session.as_mut().unwrap();
        let expected_instance = session.instance.clone();
        let Response::Task { task, .. } = session.handle(Request::Launch {
            workspace: Workspace::Build,
            app: AppKind::Notes,
            expected_instance: expected_instance.clone(),
        }) else {
            panic!("expected real child launch");
        };
        assert_eq!(task.state, TaskState::Running);
        assert!(task.pid.is_some());

        let Response::Task {
            task: requested, ..
        } = session.handle(Request::Cancel {
            id: task.id,
            expected_instance,
        })
        else {
            panic!("expected bounded cancellation acknowledgement");
        };
        assert_eq!(requested.state, TaskState::CancelRequested);
        assert_eq!(
            requested.exit_code, None,
            "SIGKILL ACK does not prove child reap"
        );

        for _ in 0..100 {
            session.refresh();
            if session.tasks[&task.id].state.is_terminal() {
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        let terminal = &session.tasks[&task.id];
        assert_eq!(terminal.state, TaskState::Cancelled);
        assert!(terminal.detail.contains("SIGKILL"));
        assert!(session.children.is_empty(), "observed child must be reaped");
    }

    #[test]
    fn missing_binary_is_a_failed_task_not_success() {
        let mut session = Session::new(PathBuf::from("/does-not-exist/trill-app-window")).unwrap();
        let Response::Task { task, .. } = session.launch(Workspace::Research, AppKind::Calculator)
        else {
            panic!("expected task");
        };
        assert_eq!(task.state, TaskState::Failed);
        assert!(task.detail.contains("spawn failed"));
    }

    #[test]
    fn bounded_history_prunes_terminal_records_but_not_unknown_effects() {
        let mut session = Session::new(PathBuf::from("/bin/true")).unwrap();
        for id in 1..=MAX_TRACKED_TASKS as u64 {
            let mut task = TaskRecord::new(id, Workspace::Build, AppKind::Notes);
            task.transition(TaskState::Running);
            task.transition(TaskState::Completed);
            session.tasks.insert(id, task);
        }
        session.next_id = MAX_TRACKED_TASKS as u64 + 1;
        let Response::Task { task, .. } = session.launch(Workspace::Personal, AppKind::Calculator)
        else {
            panic!("a terminal history entry should be reclaimed");
        };
        assert_eq!(task.id, MAX_TRACKED_TASKS as u64 + 1);
        assert_eq!(session.tasks.len(), MAX_TRACKED_TASKS);
        assert!(!session.tasks.contains_key(&1));
        for id in 2..=MAX_TRACKED_TASKS as u64 {
            session.tasks.get_mut(&id).unwrap().state = TaskState::Unknown;
        }
        // Make newly started task terminal and then remove it; remaining
        // unknown states cannot be pruned to admit new work.
        let mut child = session.children.remove(&task.id).unwrap();
        child.kill().ok();
        child.wait().unwrap();
        session.tasks.remove(&task.id);
        let unknown = TaskRecord {
            state: TaskState::Unknown,
            ..TaskRecord::new(task.id, Workspace::Build, AppKind::Notes)
        };
        session.tasks.insert(task.id, unknown);
        let before = session.tasks.len();
        let Response::Error { message, .. } = session.launch(Workspace::Research, AppKind::Notes)
        else {
            panic!("unknown effects must block eviction");
        };
        assert!(message.contains("unknown"));
        assert_eq!(session.tasks.len(), before);
    }

    #[test]
    fn nonzero_or_signal_results_never_fake_success() {
        let mut task = TaskRecord::new(7, Workspace::Build, AppKind::Calculator);
        assert!(task.transition(TaskState::Running));
        settle_exit(&mut task, ExitStatus::from_raw(1 << 8));
        assert_eq!(task.state, TaskState::Failed);
        let mut cancelled = TaskRecord::new(8, Workspace::Build, AppKind::Notes);
        cancelled.transition(TaskState::Running);
        cancelled.transition(TaskState::CancelRequested);
        settle_exit(&mut cancelled, ExitStatus::from_raw(9));
        assert_eq!(cancelled.state, TaskState::Cancelled);
    }
}
