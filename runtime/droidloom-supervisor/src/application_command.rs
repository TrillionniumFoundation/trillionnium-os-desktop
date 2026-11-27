//! FD-bound Android namespace entry and bounded, invocation-owned retirement.
//!
//! A command owns only its new cgroup, never the Android cell's PID namespace.
//! Missing cgroup delegation is a precondition error; there is no PID/timeout
//! fallback. A failed retirement retains its handles and blocks new commands.

use std::ffi::{CStr, CString};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Output, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, TryLockError};
use std::thread;
use std::time::{Duration, Instant};

use crate::development::owned_process::{open_pidfd, pidfd_exited};

#[path = "physical_qualification_channel.rs"]
pub mod physical_qualification_channel;
#[path = "working_qualification.rs"]
pub mod working_qualification;

#[path = "application_leaf_unit.rs"]
mod application_leaf_unit;
#[path = "application_leaf_resources.rs"]
mod gallery_resources;
#[path = "native_application_ui_entry.rs"]
mod native_application_ui_entry;
pub use native_application_ui_entry::{SettingsPermissionCaseObservation, run_settings_permission_case, settings_permission_case_window_seconds, CameraPhotoObservation, CameraPhotoSceneObservation, CameraPhotoCaseObservation, camera_photo_case_window_seconds, run_camera_photo_case, RetainedScopedWindowPixels, RetainedNativeUiTranscript, ScopedWindowPixels, NativeUiSession, NativeUiTranscript, NativeUiStabilityWindow, NativeUiStabilityEvidence, NativeUiStabilitySummary, stability_additional_window_seconds, NativeUiPermissionWindow, NativeUiPermissionPreservation, permission_preservation_additional_window_seconds};
pub use application_leaf_unit::{NativeOwnedLeafUnit, OwnedLeafProfile};

const OUTPUT_LIMIT: usize = 64 * 1024;
const RETIRE_TIMEOUT: Duration = Duration::from_secs(2);
const POLL_INTERVAL: Duration = Duration::from_millis(5);
static NEXT_GROUP: AtomicU64 = AtomicU64::new(0);
// Also serializes invocations. At most one unresolved owned group is retained.
static RETAINED: Mutex<Option<Invocation>> = Mutex::new(None);

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn open_at(directory: RawFd, name: &CStr, flags: libc::c_int) -> io::Result<File> {
    // SAFETY: name is NUL-terminated; a successful openat gives one owned FD.
    let fd = unsafe { libc::openat(directory, name.as_ptr(), flags | libc::O_CLOEXEC) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: fd was newly allocated by openat.
    Ok(unsafe { File::from_raw_fd(fd) })
}

fn bounded_text(mut file: File, maximum: u64) -> io::Result<String> {
    let mut value = String::new();
    Read::by_ref(&mut file)
        .take(maximum + 1)
        .read_to_string(&mut value)?;
    if value.len() as u64 > maximum {
        return Err(invalid("kernel metadata exceeds bound"));
    }
    Ok(value)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ProcessIdentity {
    pid: u32,
    comm: String,
    start_ticks: u64,
}

fn process_identity(directory: &File) -> io::Result<ProcessIdentity> {
    let stat = bounded_text(
        open_at(directory.as_raw_fd(), c"stat", libc::O_RDONLY)?,
        4096,
    )?;
    let (prefix, fields) = stat
        .rsplit_once(") ")
        .ok_or_else(|| invalid("malformed process stat"))?;
    let (pid, comm) = prefix
        .split_once(" (")
        .ok_or_else(|| invalid("malformed process identity"))?;
    let start_ticks = fields
        .split_ascii_whitespace()
        .nth(19)
        .ok_or_else(|| invalid("process start ticks absent"))?
        .parse()
        .map_err(|_| invalid("invalid process start ticks"))?;
    Ok(ProcessIdentity {
        pid: pid.parse().map_err(|_| invalid("invalid process PID"))?,
        comm: comm.into(),
        start_ticks,
    })
}

struct BoundProcess {
    directory: File,
    pidfd: OwnedFd,
    identity: ProcessIdentity,
}

impl BoundProcess {
    fn capture(pid: u32) -> io::Result<Self> {
        let directory = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(format!("/proc/{pid}"))?;
        let identity = process_identity(&directory)?;
        if identity.pid != pid {
            return Err(invalid("proc directory identity differs"));
        }
        let pidfd = open_pidfd(pid)?;
        let bound = Self {
            directory,
            pidfd,
            identity,
        };
        bound.validate()?;
        Ok(bound)
    }

    fn validate(&self) -> io::Result<()> {
        if pidfd_exited(&self.pidfd)? || process_identity(&self.directory)? != self.identity {
            return Err(invalid("bound process exited or changed identity"));
        }
        Ok(())
    }

    fn open(&self, name: &str, directory: bool) -> io::Result<File> {
        let name = CString::new(name).map_err(|_| invalid("invalid proc-relative path"))?;
        open_at(
            self.directory.as_raw_fd(),
            &name,
            if directory {
                libc::O_PATH | libc::O_DIRECTORY
            } else {
                libc::O_RDONLY
            },
        )
    }
}

fn same_file(left: &File, right: &File) -> io::Result<bool> {
    let a = left.metadata()?;
    let b = right.metadata()?;
    Ok(a.dev() == b.dev() && a.ino() == b.ino())
}

/// Held identities for an unreaped cell owner and its live system_server.
pub(super) struct NamespaceTarget {
    cell: BoundProcess,
    framework: BoundProcess,
    namespaces: Vec<(&'static str, &'static str, File)>,
    root: File,
    cwd: File,
}

impl NamespaceTarget {
    pub(super) fn capture(cell_pid: u32, framework_pid: u32, start_ticks: u64) -> io::Result<Self> {
        Self::capture_named(cell_pid, framework_pid, start_ticks, Some("system_server"))
    }

    fn capture_named(
        cell_pid: u32,
        framework_pid: u32,
        start_ticks: u64,
        comm: Option<&str>,
    ) -> io::Result<Self> {
        let cell = BoundProcess::capture(cell_pid)?;
        let framework = BoundProcess::capture(framework_pid)?;
        if framework.identity.start_ticks != start_ticks
            || comm.is_some_and(|c| framework.identity.comm != c)
        {
            return Err(invalid(
                "framework process identity differs before namespace binding",
            ));
        }
        let mut namespaces = Vec::new();
        for (option, name) in [
            ("mount", "ns/mnt"),
            ("uts", "ns/uts"),
            ("ipc", "ns/ipc"),
            ("net", "ns/net"),
            ("pid", "ns/pid"),
            ("cgroup", "ns/cgroup"),
            ("user", "ns/user"),
        ] {
            namespaces.push((option, name, framework.open(name, false)?));
        }
        if !same_file(
            &cell.open("ns/net", false)?,
            &framework.open("ns/net", false)?,
        )? || !same_file(
            &cell.open("ns/pid_for_children", false)?,
            &framework.open("ns/pid", false)?,
        )? {
            return Err(invalid(
                "framework does not belong to the held cell namespaces",
            ));
        }
        let root = framework.open("root", true)?;
        let cwd = framework.open("cwd", true)?;
        let target = Self {
            cell,
            framework,
            namespaces,
            root,
            cwd,
        };
        target.validate()?;
        Ok(target)
    }

    pub(super) fn validate(&self) -> io::Result<()> {
        self.cell.validate()?;
        self.framework.validate()?;
        for (_, name, held) in &self.namespaces {
            if !same_file(held, &self.framework.open(name, false)?)? {
                return Err(invalid("framework namespace changed after binding"));
            }
        }
        if !same_file(&self.root, &self.framework.open("root", true)?)?
            || !same_file(&self.cwd, &self.framework.open("cwd", true)?)?
        {
            return Err(invalid("framework root or cwd changed after binding"));
        }
        Ok(())
    }

    fn command(&self, args: &[String]) -> io::Result<(Command, Vec<RawFd>)> {
        self.validate()?;
        let mut command = droidloom_cpu_placement::command("/usr/bin/nsenter");
        command
            .env_clear()
            .env("PATH", "/system/bin:/system/xbin")
            .env("LANG", "C")
            .env("ANDROID_ROOT", "/system")
            .env("ANDROID_DATA", "/data");
        let mut inherit = Vec::new();
        let own_user = File::open("/proc/self/ns/user")?;
        for (option, _, held) in &self.namespaces {
            if *option == "user" && same_file(held, &own_user)? {
                continue;
            }
            command.arg(format!("--{option}=/proc/self/fd/{}", held.as_raw_fd()));
            inherit.push(held.as_raw_fd());
        }
        for (option, held) in [("root", &self.root), ("wd", &self.cwd)] {
            command.arg(format!("--{option}=/proc/self/fd/{}", held.as_raw_fd()));
            inherit.push(held.as_raw_fd());
        }
        command.arg("--").args(args);
        Ok((command, inherit))
    }

    pub(super) fn execute(&self, args: &[String], deadline: Instant) -> Result<Output, String> {
        let (command, inherit) = self.command(args).map_err(|e| e.to_string())?;
        let output = run_owned(
            command,
            &inherit,
            &[
                self.cell.pidfd.as_raw_fd(),
                self.framework.pidfd.as_raw_fd(),
            ],
            deadline,
        )?;
        self.validate().map_err(|e| e.to_string())?;
        Ok(output)
    }
}

struct OwnedCgroup {
    path: PathBuf,
    directory: File,
    procs: File,
    events: File,
    kill: File,
    gallery_scope: Option<gallery_resources::Scope>,
}

fn current_cgroup_parent() -> io::Result<PathBuf> {
    let raw = fs::read_to_string("/proc/self/cgroup")?;
    let paths: Vec<_> = raw.lines().filter_map(|s| s.strip_prefix("0::")).collect();
    let [value] = paths.as_slice() else {
        return Err(invalid("one cgroup v2 membership is required"));
    };
    let path = Path::new(value);
    if !path.is_absolute()
        || path
            .components()
            .any(|c| !matches!(c, Component::RootDir | Component::Normal(_)))
    {
        return Err(invalid("invalid current cgroup path"));
    }
    let parent = Path::new("/sys/fs/cgroup").join(
        path.strip_prefix("/")
            .map_err(|_| invalid("invalid cgroup path"))?,
    );
    if parent.canonicalize()? != parent {
        return Err(invalid("cgroup parent is not canonical"));
    }
    Ok(parent)
}

impl OwnedCgroup {
    fn create() -> io::Result<Self> {
        Self::create_owned(None)
    }

    fn create_owned(profile: Option<gallery_resources::Profile>) -> io::Result<Self> {
        let parent = current_cgroup_parent()?;
        let directory = File::open(&parent)?;
        let mut stat = std::mem::MaybeUninit::<libc::statfs>::uninit();
        // SAFETY: the FD is held; stat points to writable storage for statfs.
        if unsafe { libc::fstatfs(directory.as_raw_fd(), stat.as_mut_ptr()) } != 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: fstatfs succeeded and initialized stat.
        if unsafe { stat.assume_init() }.f_type != libc::CGROUP2_SUPER_MAGIC {
            return Err(invalid("writable cgroup v2 required"));
        }
        let gallery_scope = if let Some(profile) = profile {
            gallery_resources::require_original_cpu_available()?;
            Some(gallery_resources::Scope::capture(
                &parent, &directory, profile,
            )?)
        } else {
            None
        };
        let nonce = NEXT_GROUP.fetch_add(1, Ordering::Relaxed);
        let prefix = profile.map_or("droidloom-app-probe", gallery_resources::Profile::prefix);
        let path = parent.join(format!("{prefix}-{}-{nonce}", std::process::id()));
        // create_dir refuses an existing name; no existing group is adopted.
        fs::create_dir(&path)?;
        let result = (|| {
            let directory = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(&path)?;
            let procs = open_at(
                directory.as_raw_fd(),
                c"cgroup.procs",
                libc::O_WRONLY | libc::O_NOFOLLOW,
            )?;
            let events = open_at(
                directory.as_raw_fd(),
                c"cgroup.events",
                libc::O_RDONLY | libc::O_NOFOLLOW,
            )?;
            let kill = open_at(
                directory.as_raw_fd(),
                c"cgroup.kill",
                libc::O_WRONLY | libc::O_NOFOLLOW,
            )?;
            Ok(Self {
                path: path.clone(),
                directory,
                procs,
                events,
                kill,
                gallery_scope,
            })
        })();
        if result.is_err() {
            let _ = fs::remove_dir(&path);
        }
        result
    }

    fn prepare_resources(&self) -> io::Result<()> {
        if let Some(scope) = &self.gallery_scope {
            scope.validate()?;
            scope.configure_child(&self.directory)?;
            scope.validate()?;
        }
        Ok(())
    }

    fn validate_resources(&self) -> io::Result<()> {
        self.gallery_scope
            .as_ref()
            .map_or(Ok(()), gallery_resources::Scope::validate)
    }

    fn populated(&mut self) -> io::Result<bool> {
        self.events.seek(SeekFrom::Start(0))?;
        let mut raw = String::new();
        Read::by_ref(&mut self.events)
            .take(1025)
            .read_to_string(&mut raw)?;
        if raw.len() > 1024 {
            return Err(invalid("cgroup events exceeds bound"));
        }
        let values: Vec<_> = raw
            .lines()
            .filter_map(|s| s.strip_prefix("populated "))
            .collect();
        match values.as_slice() {
            ["0"] => Ok(false),
            ["1"] => Ok(true),
            _ => Err(invalid("cgroup populated state invalid")),
        }
    }

    fn kill(&mut self) -> io::Result<()> {
        self.kill.seek(SeekFrom::Start(0))?;
        self.kill.write_all(b"1\n")
    }

    fn remove(&mut self) -> io::Result<()> {
        if self.populated()? {
            return Err(invalid("owned invocation is still populated"));
        }
        let current = fs::symlink_metadata(&self.path)?;
        let held = self.directory.metadata()?;
        if !current.is_dir() || current.dev() != held.dev() || current.ino() != held.ino() {
            return Err(invalid("owned invocation cgroup path changed"));
        }
        fs::remove_dir(&self.path)
    }
}

struct Invocation {
    child: Option<Child>,
    status: Option<ExitStatus>,
    group: OwnedCgroup,
}

impl Invocation {
    fn poll(&mut self) -> io::Result<Option<ExitStatus>> {
        if self.status.is_none() {
            if let Some(child) = &mut self.child {
                self.status = child.try_wait()?;
            }
        }
        Ok(self.status)
    }

    fn retire(&mut self) -> io::Result<()> {
        self.group.kill()?;
        let deadline = Instant::now() + RETIRE_TIMEOUT;
        loop {
            let reaped = self.child.is_none() || self.poll()?.is_some();
            if reaped && !self.group.populated()? {
                return self.group.remove();
            }
            if Instant::now() >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "invocation retirement remains unproven",
                ));
            }
            thread::sleep(POLL_INTERVAL);
        }
    }
}

fn nonblocking(fd: RawFd) -> io::Result<()> {
    // SAFETY: callers hold an open pipe descriptor for both fcntl calls.
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn drain(stream: &mut impl Read, bytes: &mut Vec<u8>) -> io::Result<()> {
    drain_bounded(stream, bytes, OUTPUT_LIMIT)
}
fn drain_bounded(stream: &mut impl Read, bytes: &mut Vec<u8>, limit: usize) -> io::Result<()> {
    let mut buffer = [0_u8; 4096];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => return Ok(()),
            Ok(count) => {
                if count > limit.saturating_sub(bytes.len()) {
                    return Err(invalid("application command output bound exceeded"));
                }
                bytes.extend_from_slice(&buffer[..count]);
            }
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(()),
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
}

fn success_before_deadline(output: Output, deadline: Instant) -> Result<Output, String> {
    if Instant::now() >= deadline {
        return Err("application command deadline exceeded before accepting output".into());
    }
    Ok(output)
}

fn run_owned(
    command: Command,
    inherit: &[RawFd],
    alive_pidfds: &[RawFd],
    deadline: Instant,
) -> Result<Output, String> {
    run_owned_with_resources(command, inherit, alive_pidfds, deadline, None)
}

fn run_owned_with_resources(
    command: Command,
    inherit: &[RawFd],
    alive_pidfds: &[RawFd],
    deadline: Instant,
    profile: Option<gallery_resources::Profile>,
) -> Result<Output, String> {
    run_owned_observed(command, inherit, alive_pidfds, deadline, profile, None)
}

struct NativeLeafRun<'a, 'b> {
    observation: &'a mut crate::native_leaf_baseline::NativeLeafBaselineObservation<'b>,
    inspector: &'a mut super::NativeApplicationInspector,
    until: Instant,
    engines: Option<&'a mut crate::native_leaf_engine::PendingLeafEngines>,
}
impl NativeLeafRun<'_, '_> {
    fn work_deadline(&self, budget: Duration) -> Result<Instant, String> {
        let app = self.observation.application();
        let mut after =
            super::progress::response_timeout(&super::ControlRequest::InspectApplication {
                package: app.package.clone(),
                user: app.user,
            }) + super::progress::response_timeout(&super::ControlRequest::ObserveRuntimeMain {
                expected_epoch: app.epoch.clone(),
            }) + RETIRE_TIMEOUT;
        if self.observation.requires_inventory_bookend() {
            after += super::progress::response_timeout(&super::ControlRequest::ObserveUserZeroPackageInventory {
                expected_epoch: app.epoch.clone(),
            });
        }
        native_leaf_work_deadline(
            Instant::now(),
            self.until.min(self.observation.deadline()),
            budget,
            after,
        )
    }
}
fn native_leaf_work_deadline(
    now: Instant,
    original: Instant,
    route: Duration,
    after: Duration,
) -> Result<Instant, String> {
    let work = original.checked_sub(after).filter(|end| *end > now).ok_or(
        "native leaf original lease cannot cover its normal postcheck and retirement caps",
    )?;
    Ok((now + route).min(work))
}

fn run_owned_observed(
    command: Command,
    inherit: &[RawFd],
    alive_pidfds: &[RawFd],
    deadline: Instant,
    profile: Option<gallery_resources::Profile>,
    observation: Option<NativeLeafRun<'_, '_>>,
) -> Result<Output, String> {
    run_owned_bounded(command, inherit, alive_pidfds, deadline, profile, observation, OUTPUT_LIMIT, None)
}

#[derive(Clone, Copy)]
enum NativeUiOutput { Small, Helper, Image }
fn run_owned_native_ui(
    command: Command,
    inherit: &[RawFd],
    alive_pidfds: &[RawFd],
    deadline: Instant,
    output: NativeUiOutput,
    guard: &mut dyn FnMut() -> Result<(), String>,
) -> Result<Output, String> {
    let limit = match output {
        NativeUiOutput::Small => OUTPUT_LIMIT,
        NativeUiOutput::Helper => crate::native_application_ui_protocol::WIRE_REPLY_BYTES,
        NativeUiOutput::Image => 32 * 1024 * 1024,
    };
    run_owned_bounded(command, inherit, alive_pidfds, deadline,
        Some(gallery_resources::Profile::ApplicationUi), None, limit, Some(guard))
}

fn run_owned_bounded(
    mut command: Command,
    inherit: &[RawFd],
    alive_pidfds: &[RawFd],
    deadline: Instant,
    profile: Option<gallery_resources::Profile>,
    mut observation: Option<NativeLeafRun<'_, '_>>,
    stdout_limit: usize,
    mut guard: Option<&mut dyn FnMut() -> Result<(), String>>,
) -> Result<Output, String> {
    if let Some(check) = guard.as_mut() { check()?; }
    let mut channel = observation
        .as_mut()
        .map(|value| {
            crate::native_leaf_baseline_channel::NativeLeafChannel::new(
                value.observation,
                value.inspector,
                deadline,
            )
        })
        .transpose()?;
    let mut inherited = inherit.to_vec();
    if let Some(value) = &channel {
        inherited.extend(value.prepare(&mut command));
    }
    let inherit = inherited.as_slice();
    let gallery = profile.is_some();
    let mut retained = loop {
        match RETAINED.try_lock() {
            Ok(guard) => break guard,
            Err(TryLockError::Poisoned(_)) => {
                return Err("application invocation owner lock poisoned".into());
            }
            Err(TryLockError::WouldBlock) if Instant::now() < deadline => {
                thread::sleep(POLL_INTERVAL)
            }
            Err(TryLockError::WouldBlock) => {
                return Err("application invocation ownership deadline exceeded".into());
            }
        }
    };
    if let Some(pending) = retained.as_mut() {
        pending.retire().map_err(|e| {
            format!(
                "previous invocation retained at {}: {e}",
                pending.group.path.display()
            )
        })?;
        *retained = None;
    }
    if Instant::now() >= deadline {
        return Err("application command deadline exceeded before spawn".into());
    }
    let mut group = (if gallery {
        OwnedCgroup::create_owned(profile)
    } else {
        OwnedCgroup::create()
    })
    .map_err(|e| format!("invocation cgroup precondition failed: {e}"))?;
    if let Err(error) = group.prepare_resources() {
        let cleanup = group.remove();
        if let Err(cleanup) = cleanup {
            let path = group.path.clone();
            *retained = Some(Invocation {
                child: None,
                status: None,
                group,
            });
            return Err(format!(
                "Gallery resources changed before spawn: {error}; empty owned group retained at {}: {cleanup}",
                path.display()
            ));
        }
        return Err(format!(
            "Gallery resources changed before spawn: {error}; new empty group removed"
        ));
    }
    let group_fd = group.procs.as_raw_fd();
    let inherit = inherit.to_vec();
    let alive_pidfds = alive_pidfds.to_vec();
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    // SAFETY: the closure uses only async-signal-safe syscalls and fixed bytes.
    // The child joins its exclusively-created cgroup before any exec/fork by
    // nsenter. Every descendant therefore inherits invocation ownership.
    unsafe {
        command.pre_exec(move || {
            if gallery {
                let mut affinity: libc::cpu_set_t = std::mem::zeroed();
                libc::CPU_ZERO(&mut affinity);
                libc::CPU_SET(20, &mut affinity);
                if libc::sched_setaffinity(0, std::mem::size_of::<libc::cpu_set_t>(), &affinity)
                    != 0
                    || libc::setrlimit(
                        libc::RLIMIT_CORE,
                        &libc::rlimit {
                            rlim_cur: 0,
                            rlim_max: 0,
                        },
                    ) != 0
                {
                    return Err(io::Error::last_os_error());
                }
            }
            if libc::write(group_fd, b"0\n".as_ptr().cast(), 2) != 2 {
                return Err(io::Error::last_os_error());
            }
            for fd in &alive_pidfds {
                let mut poll = libc::pollfd {
                    fd: *fd,
                    events: libc::POLLIN,
                    revents: 0,
                };
                if libc::poll(&mut poll, 1, 0) < 0 {
                    return Err(io::Error::last_os_error());
                }
                if poll.revents != 0 {
                    return Err(io::Error::from_raw_os_error(libc::ESRCH));
                }
            }
            for fd in &inherit {
                let flags = libc::fcntl(*fd, libc::F_GETFD);
                if flags < 0 || libc::fcntl(*fd, libc::F_SETFD, flags & !libc::FD_CLOEXEC) < 0 {
                    return Err(io::Error::last_os_error());
                }
            }
            Ok(())
        });
    }
    let spawn = command.spawn();
    let mut invocation = Invocation {
        child: None,
        status: None,
        group,
    };
    let result = match spawn {
        Err(error) => Err(format!("application command spawn failed: {error}")),
        Ok(mut child) => {
            let pipes = (child.stdout.take(), child.stderr.take());
            invocation.child = Some(child);
            (|| -> Result<Output, String> {
                let (Some(mut stdout), Some(mut stderr)) = pipes else {
                    return Err("application pipes unavailable".into());
                };
                nonblocking(stdout.as_raw_fd())
                    .and_then(|_| nonblocking(stderr.as_raw_fd()))
                    .map_err(|e| e.to_string())?;
                let mut out = Vec::new();
                let mut err = Vec::new();
                let mut resource_bookend = Instant::now();
                let mut local_bookend = Instant::now();
                loop {
                    if Instant::now() >= local_bookend {
                        if let Some(check) = guard.as_mut() { check()?; }
                        local_bookend = Instant::now() + Duration::from_millis(100);
                    }
                    if gallery && Instant::now() >= resource_bookend {
                        invocation
                            .group
                            .validate_resources()
                            .map_err(|e| e.to_string())?;
                        resource_bookend = Instant::now() + Duration::from_millis(100);
                    }
                    if Instant::now() >= deadline {
                        return Err("application command deadline exceeded".into());
                    }
                    if let (Some(channel), Some(observation)) =
                        (channel.as_mut(), observation.as_mut())
                    {
                        channel.serve(
                            observation.observation, observation.inspector,
                            observation.engines.as_deref_mut(),
                        )?;
                    }
                    drain_bounded(&mut stdout, &mut out, stdout_limit)
                        .and_then(|_| drain(&mut stderr, &mut err))
                        .map_err(|e| e.to_string())?;
                    if let Some(status) = invocation.poll().map_err(|e| e.to_string())? {
                        if invocation.group.populated().map_err(|e| e.to_string())? {
                            return Err(
                                "command leader exited with live invocation descendants".into()
                            );
                        }
                        // The producer is reaped. Drain buffered bytes without
                        // waiting for EOF or joining a potentially stuck reader.
                        drain_bounded(&mut stdout, &mut out, stdout_limit)
                            .and_then(|_| drain(&mut stderr, &mut err))
                            .map_err(|e| e.to_string())?;
                        return success_before_deadline(
                            Output {
                                status,
                                stdout: out,
                                stderr: err,
                            },
                            deadline,
                        );
                    }
                    if Instant::now() >= deadline {
                        return Err("application command deadline exceeded".into());
                    }
                    thread::sleep(POLL_INTERVAL);
                }
            })()
        }
    };
    if let Err(error) = invocation.retire() {
        let path = invocation.group.path.clone();
        *retained = Some(invocation);
        return Err(format!(
            "{}; owned invocation retained at {}: {error}",
            result
                .err()
                .unwrap_or_else(|| "command output withheld".into()),
            path.display()
        ));
    }
    let resources = invocation
        .group
        .validate_resources()
        .map_err(|e| e.to_string());
    result
        .and_then(|output| resources.map(|()| output))
        .and_then(|output| {
            if let Some(check) = guard.as_mut() { check()?; }
            if let Some(channel) = &channel {
                channel.finish()?;
            }
            if let Some(observation) = observation.as_mut() {
                observation
                    .observation
                    .verify_local(observation.inspector, deadline)
                    .map_err(|e| e.to_string())?;
            }
            Ok(output)
        })
        .and_then(|output| success_before_deadline(output, deadline))
        .map_err(|error| format!("{error}; invocation cgroup empty and direct child reaped"))
}

/// Execute one already validated host leaf under the same owned cgroup
/// primitive as Android probes, while retaining the actual Main process FDs.
/// This is a library call from the finite applications dispatcher, not a socket
/// request accepting a general host command.
pub(super) fn run_prepared_host_leaf(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
    budget: Duration,
) -> Result<Output, String> {
    run_prepared_host_leaf_observed(command, epoch, budget, None)
}

fn run_prepared_host_leaf_observed(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
    budget: Duration,
    observation: Option<NativeLeafRun<'_, '_>>,
) -> Result<Output, String> {
    if let Some(value) = &observation {
        value.observation.require_epoch(epoch)?;
    }
    if budget.is_zero()
        || budget > Duration::from_secs(1200)
        || command.get_program() != "/usr/bin/python3"
    {
        return Err("invalid bounded prepared host-leaf command".into());
    }
    let deadline = if let Some(value) = &observation {
        value.work_deadline(budget)?
    } else {
        Instant::now() + budget
    };
    let check_boot = || -> Result<(), String> {
        if fs::read_to_string("/proc/sys/kernel/random/boot_id")
            .map_err(|e| e.to_string())?
            .trim()
            != epoch.boot_id
        {
            return Err("host boot differs from the admitted application Main".into());
        }
        Ok(())
    };
    check_boot()?;
    let target = NamespaceTarget::capture(
        epoch.cell_host_pid,
        epoch.framework_host_pid,
        epoch.framework_start_ticks,
    )
    .map_err(|e| e.to_string())?;
    let output = run_owned_observed(
        command,
        &[],
        &[
            target.cell.pidfd.as_raw_fd(),
            target.framework.pidfd.as_raw_fd(),
        ],
        deadline,
        None,
        observation,
    )?;
    target.validate().map_err(|e| e.to_string())?;
    check_boot()?;
    success_before_deadline(output, deadline)
}

fn baseline_capture_command(command: &Command) -> Result<(), String> {
    const COLLECTOR: &str = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/main/kernel_native_observation.py";
    const OUTPUT_PARENT: &str = "/var/lib/droidloom/qualification/pocket4";
    let args = command
        .get_args()
        .map(|v| v.to_str())
        .collect::<Option<Vec<_>>>()
        .ok_or("normal baseline collector argv is not UTF-8")?;
    if command.get_program() != "/usr/bin/python3"
        || args.len() != 6
        || args[..5] != ["-I", "-B", COLLECTOR, "--collect", "--output-directory"]
    {
        return Err(
            "only the exact source-owned normal baseline collector may use this profile".into(),
        );
    }
    let path = Path::new(args[5]);
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or("normal capture directory name absent")?;
    if path.parent() != Some(Path::new(OUTPUT_PARENT))
        || !name.starts_with("native-leaf-")
        || name.len() > 80
        || !name
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
        || fs::canonicalize(path).map_err(|e| e.to_string())? != path
    {
        return Err("normal baseline capture must use its fresh fixed private root".into());
    }
    use std::os::unix::fs::MetadataExt;
    let m = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o7777 != 0o700 {
        return Err("normal baseline capture output ownership differs".into());
    }
    Ok(())
}

fn gallery_command(command: &Command) -> Result<(), String> {
    const ROOT: &str =
        "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
    let args = command
        .get_args()
        .map(|v| v.to_str())
        .collect::<Option<Vec<_>>>()
        .ok_or("Gallery argv is not UTF-8")?;
    let hash = |v: &str| {
        v.len() == 64
            && v.bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    };
    let allowed_preparation = ["rotation", "video", "seek", "album"].iter().any(|name| {
        args.get(4)
            .is_some_and(|arg| *arg == format!("{ROOT}/preparations/gallery-{name}.json"))
    });
    if command.get_program() != "/usr/bin/python3"
        || args.len() != 12
        || args[..2] != ["-I", "-B"]
        || args[2] != format!("{ROOT}/source/gallery/source/gallery_image_entry.py")
        || args[3] != "--preparation"
        || !allowed_preparation
        || args[5] != "--expect-preparation-sha256"
        || !hash(args[6])
        || args[7] != "execute"
        || args[8] != "--request"
        || !Path::new(args[9]).is_absolute()
        || args[10] != "--expect-request-sha256"
        || !hash(args[11])
    {
        return Err(
            "only the exact selected current-image Gallery entry receives its fixed outer budget"
                .into(),
        );
    }
    Ok(())
}

fn calendar_command(command: &Command) -> Result<(), String> {
    const ROOT: &str =
        "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
    let args = command
        .get_args()
        .map(|v| v.to_str())
        .collect::<Option<Vec<_>>>()
        .ok_or("Calendar argv is not UTF-8")?;
    let hash = |value: &str| {
        value.len() == 64
            && value
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    };
    if command.get_program() != "/usr/bin/python3"
        || args.len() != 12
        || args[..2] != ["-I", "-B"]
        || args[2] != format!("{ROOT}/source/calendar-reminder/system_entry.py")
        || args[3] != "--preparation"
        || args[4] != format!("{ROOT}/preparations/calendar-reminder.json")
        || args[5] != "--expect-preparation-sha256"
        || !hash(args[6])
        || args[7] != "execute"
        || args[8] != "--request"
        || !Path::new(args[9]).is_absolute()
        || args[10] != "--expect-request-sha256"
        || !hash(args[11])
    {
        return Err(
            "only the exact current Calendar reminder entry receives its original resource profile"
                .into(),
        );
    }
    Ok(())
}

fn settings_command(command: &Command) -> Result<(), String> {
    const ROOT: &str =
        "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
    let args = command
        .get_args()
        .map(|value| value.to_str())
        .collect::<Option<Vec<_>>>()
        .ok_or("Settings argv is not UTF-8")?;
    let hash = |value: &str| {
        value.len() == 64
            && value
                .bytes()
                .all(|ch| ch.is_ascii_digit() || (b'a'..=b'f').contains(&ch))
    };
    if command.get_program() != "/usr/bin/python3"
        || args.len() != 12
        || args[..2] != ["-I", "-B"]
        || args[2] != format!("{ROOT}/source/settings/settings_entry.py")
        || args[3] != "--preparation"
        || args[4] != format!("{ROOT}/preparations/settings.json")
        || args[5] != "--expect-preparation-sha256"
        || !hash(args[6])
        || args[7] != "execute"
        || args[8] != "--request"
        || !Path::new(args[9]).is_absolute()
        || args[10] != "--expect-request-sha256"
        || !hash(args[11])
    {
        return Err(
            "only the exact current Settings pages entry receives its fixed resource profile"
                .into(),
        );
    }
    Ok(())
}

pub(super) fn run_prepared_settings_pages_leaf(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
) -> Result<Output, String> {
    settings_command(&command)?;
    // The consumer retains its exact 600-second business and 120-second cleanup
    // lease. The fixed outer reserve covers source/identity bookends only.
    run_prepared_resource_leaf(
        command,
        epoch,
        Duration::from_secs(900),
        gallery_resources::Profile::SettingsPages,
    )
}

pub(super) fn run_prepared_gallery_image_leaf(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
) -> Result<Output, String> {
    gallery_command(&command)?;
    run_prepared_resource_leaf(
        command,
        epoch,
        Duration::from_secs(1530),
        gallery_resources::Profile::Gallery,
    )
}

pub(super) fn run_prepared_calendar_reminder_leaf(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
) -> Result<Output, String> {
    calendar_command(&command)?;
    run_prepared_resource_leaf(
        command,
        epoch,
        Duration::from_secs(690),
        gallery_resources::Profile::CalendarReminder,
    )
}

fn run_prepared_resource_leaf(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
    budget: Duration,
    profile: gallery_resources::Profile,
) -> Result<Output, String> {
    run_prepared_resource_leaf_observed(command, epoch, budget, profile, None)
}

fn run_prepared_resource_leaf_observed(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
    budget: Duration,
    profile: gallery_resources::Profile,
    observation: Option<NativeLeafRun<'_, '_>>,
) -> Result<Output, String> {
    if let Some(value) = &observation {
        value.observation.require_epoch(epoch)?;
    }
    let deadline = if let Some(value) = &observation {
        value.work_deadline(budget)?
    } else {
        Instant::now() + budget
    };
    let check_boot = || -> Result<(), String> {
        if fs::read_to_string("/proc/sys/kernel/random/boot_id")
            .map_err(|e| e.to_string())?
            .trim()
            != epoch.boot_id
        {
            return Err("host boot differs from the admitted Gallery Main".into());
        }
        Ok(())
    };
    check_boot()?;
    let target = NamespaceTarget::capture(
        epoch.cell_host_pid,
        epoch.framework_host_pid,
        epoch.framework_start_ticks,
    )
    .map_err(|e| e.to_string())?;
    let output = run_owned_observed(
        command,
        &[],
        &[
            target.cell.pidfd.as_raw_fd(),
            target.framework.pidfd.as_raw_fd(),
        ],
        deadline,
        Some(profile),
        observation,
    )?;
    target.validate().map_err(|e| e.to_string())?;
    check_boot()?;
    success_before_deadline(output, deadline)
}

/// Exact existing profiles plus one real retained baseline; this does not
/// authorize a new command or widen any resource or namespace-entry boundary.
pub(super) fn run_prepared_native_leaf_until(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
    kind: super::NativeLeafCommandKind,
    inspector: &mut super::NativeApplicationInspector,
    baseline: &mut crate::native_leaf_baseline::NativeLeafBaselineObservation<'_>,
    until: Instant,
) -> Result<Output, String> {
    run_prepared_native_leaf_inner(command, epoch, kind, inspector, baseline, until, None)
}

pub(super) fn run_prepared_native_leaf_observed_until(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
    kind: super::NativeLeafCommandKind,
    inspector: &mut super::NativeApplicationInspector,
    baseline: &mut crate::native_leaf_baseline::NativeLeafBaselineObservation<'_>,
    until: Instant,
) -> Result<crate::native_leaf_engine::NativeLeafExecution, String> {
    if !matches!(&kind, super::NativeLeafCommandKind::Standard { .. }
        | super::NativeLeafCommandKind::GalleryImage
        | super::NativeLeafCommandKind::CalendarReminder
        | super::NativeLeafCommandKind::SettingsPages)
    {
        return Err("capture or preparation cannot request a running-engine checkpoint".into());
    }
    let mut engines = crate::native_leaf_engine::PendingLeafEngines::new(until)?;
    let output = run_prepared_native_leaf_inner(
        command, epoch, kind, inspector, baseline, until, Some(&mut engines),
    )?;
    engines.finish(output)
}

fn run_prepared_native_leaf_inner(
    command: Command,
    epoch: &super::application_probe::RuntimeEpoch,
    kind: super::NativeLeafCommandKind,
    inspector: &mut super::NativeApplicationInspector,
    baseline: &mut crate::native_leaf_baseline::NativeLeafBaselineObservation<'_>,
    until: Instant,
    engines: Option<&mut crate::native_leaf_engine::PendingLeafEngines>,
) -> Result<Output, String> {
    let observation = NativeLeafRun {
        observation: baseline,
        inspector,
        until,
        engines,
    };
    match kind {
        super::NativeLeafCommandKind::BaselineCapture => {
            baseline_capture_command(&command)?;
            run_prepared_host_leaf_observed(
                command,
                epoch,
                Duration::from_secs(240),
                Some(observation),
            )
        }
        super::NativeLeafCommandKind::IhgPreparation { mode } => {
            crate::native_ihg_preparation::check_command(&command, mode)?;
            run_prepared_host_leaf_observed(command, epoch, mode.budget(), Some(observation))
        }
        super::NativeLeafCommandKind::Standard { budget } => {
            run_prepared_host_leaf_observed(command, epoch, budget, Some(observation))
        }
        super::NativeLeafCommandKind::GalleryImage => {
            gallery_command(&command)?;
            run_prepared_resource_leaf_observed(
                command,
                epoch,
                Duration::from_secs(1530),
                gallery_resources::Profile::Gallery,
                Some(observation),
            )
        }
        super::NativeLeafCommandKind::CalendarReminder => {
            calendar_command(&command)?;
            run_prepared_resource_leaf_observed(
                command,
                epoch,
                Duration::from_secs(690),
                gallery_resources::Profile::CalendarReminder,
                Some(observation),
            )
        }
        super::NativeLeafCommandKind::SettingsPages => {
            settings_command(&command)?;
            run_prepared_resource_leaf_observed(
                command,
                epoch,
                Duration::from_secs(900),
                gallery_resources::Profile::SettingsPages,
                Some(observation),
            )
        }
    }
}

#[cfg(test)]
mod gallery_tests {
    use super::*;

    fn selected_command(preparation: &str) -> Command {
        let root = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
        let mut command = Command::new("/usr/bin/python3");
        command
            .args(["-I", "-B"])
            .arg(format!(
                "{root}/source/gallery/source/gallery_image_entry.py"
            ))
            .arg("--preparation")
            .arg(format!("{root}/preparations/gallery-{preparation}.json"))
            .arg("--expect-preparation-sha256")
            .arg("a".repeat(64))
            .arg("execute")
            .arg("--request")
            .arg("/fixture/request.json")
            .arg("--expect-request-sha256")
            .arg("b".repeat(64));
        command
    }

    #[test]
    fn native_leaf_stage_keeps_route_cap_and_reserves_original_postchecks() {
        let now = Instant::now();
        let route = Duration::from_secs(900);
        let after = Duration::from_secs(322);
        assert_eq!(
            native_leaf_work_deadline(now, now + Duration::from_secs(1300), route, after).unwrap(),
            now + route
        );
        assert_eq!(
            native_leaf_work_deadline(now, now + Duration::from_secs(1000), route, after).unwrap(),
            now + Duration::from_secs(678)
        );
        assert!(native_leaf_work_deadline(now, now + after, route, after).is_err());
    }

    #[test]
    fn settings_resource_profile_rejects_other_entries_and_extra_arguments() {
        let root = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
        let mut command = Command::new("/usr/bin/python3");
        command
            .args(["-I", "-B"])
            .arg(format!("{root}/source/settings/settings_entry.py"))
            .arg("--preparation")
            .arg(format!("{root}/preparations/settings.json"))
            .arg("--expect-preparation-sha256")
            .arg("a".repeat(64))
            .arg("execute")
            .arg("--request")
            .arg("/private/request.json")
            .arg("--expect-request-sha256")
            .arg("b".repeat(64));
        settings_command(&command).unwrap();
        assert!(gallery_command(&command).is_err());
        assert!(calendar_command(&command).is_err());
        assert!(settings_command(&selected_command("rotation")).is_err());
        command.arg("--resource-profile=gallery");
        assert!(settings_command(&command).is_err());
    }

    #[test]
    fn extended_budget_is_limited_to_four_exact_current_gallery_entries() {
        for name in ["rotation", "video", "seek", "album"] {
            gallery_command(&selected_command(name)).unwrap();
        }
        assert!(gallery_command(&selected_command("identity")).is_err());
        assert!(gallery_command(&selected_command("../rotation")).is_err());
        let mut extra = selected_command("rotation");
        extra.arg("--disable-source-check");
        assert!(gallery_command(&extra).is_err());
        assert!(gallery_command(&Command::new("/usr/bin/python3")).is_err());
    }

    #[test]
    fn calendar_resource_profile_cannot_be_selected_by_an_unrelated_entry() {
        let root = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
        let mut command = Command::new("/usr/bin/python3");
        command
            .args(["-I", "-B"])
            .arg(format!("{root}/source/calendar-reminder/system_entry.py"))
            .arg("--preparation")
            .arg(format!("{root}/preparations/calendar-reminder.json"))
            .arg("--expect-preparation-sha256")
            .arg("a".repeat(64))
            .arg("execute")
            .arg("--request")
            .arg("/fixture/request.json")
            .arg("--expect-request-sha256")
            .arg("b".repeat(64));
        calendar_command(&command).unwrap();
        assert!(gallery_command(&command).is_err());
        assert!(calendar_command(&selected_command("rotation")).is_err());
        command.arg("--resource-profile=gallery");
        assert!(calendar_command(&command).is_err());
    }
}

#[cfg(test)]
#[path = "application_command_tests.rs"]
mod tests;
