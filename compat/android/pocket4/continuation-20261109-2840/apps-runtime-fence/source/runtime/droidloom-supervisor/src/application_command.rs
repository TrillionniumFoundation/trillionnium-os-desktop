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
        let nonce = NEXT_GROUP.fetch_add(1, Ordering::Relaxed);
        let path = parent.join(format!(
            "droidloom-app-probe-{}-{nonce}",
            std::process::id()
        ));
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
            })
        })();
        if result.is_err() {
            let _ = fs::remove_dir(&path);
        }
        result
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
    let mut buffer = [0_u8; 4096];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => return Ok(()),
            Ok(count) => {
                if count > OUTPUT_LIMIT.saturating_sub(bytes.len()) {
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
    mut command: Command,
    inherit: &[RawFd],
    alive_pidfds: &[RawFd],
    deadline: Instant,
) -> Result<Output, String> {
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
    let group =
        OwnedCgroup::create().map_err(|e| format!("invocation cgroup precondition failed: {e}"))?;
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
                loop {
                    if Instant::now() >= deadline {
                        return Err("application command deadline exceeded".into());
                    }
                    drain(&mut stdout, &mut out)
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
                        drain(&mut stdout, &mut out)
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
    result
        .and_then(|output| success_before_deadline(output, deadline))
        .map_err(|error| format!("{error}; invocation cgroup empty and direct child reaped"))
}

#[cfg(test)]
#[path = "application_command_tests.rs"]
mod tests;
