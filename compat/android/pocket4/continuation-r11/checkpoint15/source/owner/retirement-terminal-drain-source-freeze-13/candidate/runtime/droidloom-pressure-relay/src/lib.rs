// Copyright 2026 Droidloom contributors
// SPDX-License-Identifier: Apache-2.0
//! Production-callable cell relay owner, not an installed supervisor patch.
//!
//! This module authenticates one accepted Unix peer against lifecycle-owned
//! handles and retains a revocable notification capability. Optional monitors
//! register only the exact held cgroup; no victim is chosen or signaled here.
//! psi.rs owns real registration/events; enrollment.rs owns the finite Android
//! request/grant; lifecycle_relay.rs owns the single admission service and
//! explicit retirement barrier. Platform lifecycle must supply its held
//! handles, socket projection and LMKD startup barrier. No deployment occurs.
#![deny(unsafe_op_in_unsafe_fn)]

use sha2::{Digest, Sha256};
use std::ffi::CString;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read};
use std::mem::{size_of, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

mod ancestry;
mod psi;
pub use psi::{PressureConfig, PressureLevel, RegisteredLease, ScopeRequest, WorkerDiagnostics};
mod pressure_audit;
pub use pressure_audit::{EventAuditTrail, PressureAudit, QueuedEventRecord, RegistrationAudit, RegistrationRecord};
mod enrollment;
pub use enrollment::{EnrollmentRequest, PendingGrant};
mod lifecycle_relay;
pub use lifecycle_relay::{CellRelay, PreparedRelay, RelayPhase, RetirementReceipt};
mod lifecycle_bootstrap;
pub use lifecycle_bootstrap::{run_inherited_lifecycle, BootstrapSpec, BootstrapStatus, BootstrapState, LifecycleBroker, LifecycleProcessObservation, MAX_LIFECYCLE_IO_TIMEOUT};

const CGROUP2_MAGIC: libc::c_long = 0x6367_7270;
const PROC_MAGIC: libc::c_long = 0x9fa0;
const SO_PEERPIDFD: libc::c_int = 77;
const RESOLVE_NO_MAGICLINKS: u64 = 0x02;
const RESOLVE_NO_SYMLINKS: u64 = 0x04;
const RESOLVE_BENEATH: u64 = 0x08;
const MAX_PROC_BYTES: usize = 65_536;
const MAX_EXE_BYTES: u64 = 64 * 1024 * 1024;
const NS_NAMES: [&str; 10] = [
    "pid", "pid_for_children", "mnt", "cgroup", "user", "net", "ipc", "uts",
    "time", "time_for_children",
];

#[derive(Debug)]
pub enum Error {
    Io(&'static str, io::Error),
    RelativeIo { name: String, flags: libc::c_int, base: Option<FileId>, error: io::Error },
    Context(&'static str, Box<Error>),
    Reject(&'static str),
}
pub type Result<T> = std::result::Result<T, Error>;
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(context, error) => write!(f, "{context}: {error}"),
            Self::RelativeIo { name, flags, base, error } => write!(f,
                "open relative pinned directory name={name:?} flags={flags:#x} base={base:?}: {error}"),
            Self::Context(context, error) => write!(f, "{context}: {error}"),
            Self::Reject(reason) => write!(f, "rejected: {reason}"),
        }
    }
}
impl std::error::Error for Error {}
impl Error {
    // Adds provenance only. The original typed I/O error/errno remains owned;
    // no retry, fallback, authority change or success conversion is introduced.
    fn context(self, context: &'static str) -> Self { Self::Context(context, Box::new(self)) }
}
fn err(context: &'static str) -> Error { Error::Io(context, io::Error::last_os_error()) }
fn io_err(context: &'static str, error: io::Error) -> Error { Error::Io(context, error) }

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FileId { pub device: u64, pub inode: u64 }
impl FileId {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata().map_err(|e| io_err("fstat pinned file", e))?;
        Ok(Self { device: m.dev(), inode: m.ino() })
    }
    fn path(path: &Path) -> Result<Self> {
        let m = fs::symlink_metadata(path).map_err(|e| io_err("lstat endpoint", e))?;
        Ok(Self { device: m.dev(), inode: m.ino() })
    }
}

fn duplicate(fd: RawFd) -> Result<OwnedFd> {
    let n = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 0) };
    if n < 0 { return Err(err("duplicate owned fd")); }
    Ok(unsafe { OwnedFd::from_raw_fd(n) })
}
fn require_fs(file: &File, magic: libc::c_long) -> Result<()> {
    let mut s: libc::statfs = unsafe { zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut s) } < 0 { return Err(err("fstatfs")); }
    if s.f_type != magic { return Err(Error::Reject("wrong filesystem type")); }
    Ok(())
}
fn open_dir(path: &Path) -> Result<File> {
    OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path).map_err(|e| io_err("open trusted directory", e))
}
fn open_at(base: &File, name: &str, flags: libc::c_int) -> Result<File> {
    let c = CString::new(name).map_err(|_| Error::Reject("embedded NUL"))?;
    let fd = unsafe { libc::openat(base.as_raw_fd(), c.as_ptr(), flags | libc::O_CLOEXEC) };
    if fd < 0 {
        // Capture errno BEFORE the diagnostic fstat. Failure to observe the
        // held base identity does not replace the original openat failure.
        let error = io::Error::last_os_error();
        return Err(Error::RelativeIo { name: name.to_owned(), flags: flags | libc::O_CLOEXEC,
            base: FileId::of(base).ok(), error });
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
#[repr(C)]
struct OpenHow { flags: u64, mode: u64, resolve: u64 }
fn beneath_dir(base: &File, relative: &str) -> Result<File> {
    if relative.starts_with('/') || relative.split('/').any(|s| s == ".." || s.is_empty()) {
        return Err(Error::Reject("non-relative or traversing directory"));
    }
    let c = CString::new(relative).map_err(|_| Error::Reject("embedded NUL"))?;
    let how = OpenHow {
        flags: (libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC) as u64,
        mode: 0,
        resolve: RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS,
    };
    let fd = unsafe { libc::syscall(libc::SYS_openat2, base.as_raw_fd(), c.as_ptr(), &how, size_of::<OpenHow>()) };
    if fd < 0 { return Err(err("openat2 beneath trusted root")); }
    Ok(unsafe { File::from_raw_fd(fd as RawFd) })
}
fn read_at(base: &File, name: &str, maximum: usize) -> Result<String> {
    let file = open_at(base, name, libc::O_RDONLY | libc::O_NOFOLLOW)?;
    let mut data = Vec::new();
    file.take((maximum + 1) as u64).read_to_end(&mut data)
        .map_err(|e| io_err("read bounded metadata", e))?;
    if data.len() > maximum { return Err(Error::Reject("metadata exceeds bound")); }
    String::from_utf8(data).map_err(|_| Error::Reject("metadata is not UTF-8"))
}
fn numeric(s: &str) -> Result<u64> {
    if s.is_empty() || !s.bytes().all(|c| c.is_ascii_digit()) {
        return Err(Error::Reject("non-canonical integer"));
    }
    s.parse().map_err(|_| Error::Reject("integer overflow"))
}
fn process_birth(text: &str, pid: libc::pid_t) -> Result<u64> {
    let left = text.find('(').ok_or(Error::Reject("invalid proc stat"))?;
    let right = text.rfind(')').ok_or(Error::Reject("invalid proc stat"))?;
    if left >= right || numeric(text[..left].trim())? != pid as u64 {
        return Err(Error::Reject("proc PID view mismatch"));
    }
    let fields: Vec<_> = text[right + 1..].split_whitespace().collect();
    if fields.len() < 20 { return Err(Error::Reject("short proc stat")); }
    let start = numeric(fields[19])?;
    if start == 0 { return Err(Error::Reject("zero process birth")); }
    // State, counters and scheduler fields are intentionally not identities.
    Ok(start)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Status {
    uids: [u32; 4], gids: [u32; 4], namespace_pids: Vec<u32>,
}
fn parse_status(text: &str, pid: libc::pid_t) -> Result<Status> {
    fn values(text: &str, key: &str) -> Result<Vec<u32>> {
        let mut lines = text.lines().filter_map(|l| l.strip_prefix(key));
        let line = lines.next().ok_or(Error::Reject("missing status identity"))?;
        if lines.next().is_some() { return Err(Error::Reject("duplicate status identity")); }
        line.split_whitespace().map(|s| u32::try_from(numeric(s)?).map_err(|_| Error::Reject("status integer overflow"))).collect()
    }
    let uids: [u32; 4] = values(text, "Uid:")?.try_into().map_err(|_| Error::Reject("UID tuple length"))?;
    let gids: [u32; 4] = values(text, "Gid:")?.try_into().map_err(|_| Error::Reject("GID tuple length"))?;
    let namespace_pids = values(text, "NSpid:")?;
    if namespace_pids.is_empty() || namespace_pids.len() > 32 || namespace_pids[0] != pid as u32 {
        return Err(Error::Reject("status PID view mismatch"));
    }
    Ok(Status { uids, gids, namespace_pids })
}

/// All namespace descriptors remain open to pin their inode generations.
pub struct NamespacePins { files: Vec<File>, ids: Vec<FileId> }
impl NamespacePins {
    fn capture(proc_dir: &File) -> Result<Self> {
        let mut files = Vec::with_capacity(NS_NAMES.len());
        let mut ids = Vec::with_capacity(NS_NAMES.len());
        for name in NS_NAMES {
            // These are the kernel's proc namespace magic links, never client paths.
            let file = open_at(proc_dir, &format!("ns/{name}"), libc::O_RDONLY)?;
            ids.push(FileId::of(&file)?);
            files.push(file);
        }
        Ok(Self { files, ids })
    }
    pub fn try_clone(&self) -> Result<Self> {
        let files = self.files.iter().map(|f| duplicate(f.as_raw_fd()).map(File::from)).collect::<Result<Vec<_>>>()?;
        Ok(Self { files, ids: self.ids.clone() })
    }
    pub fn identity(&self, name: &str) -> Option<FileId> {
        NS_NAMES.iter().position(|n| *n == name).map(|n| self.ids[n])
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ExecutableStamp { id: FileId, size: u64, mode: u32, uid: u32, gid: u32, mtime: (i64, i64), ctime: (i64, i64) }
fn executable_stamp(f: &File) -> Result<ExecutableStamp> {
    let m = f.metadata().map_err(|e| io_err("stat executable", e))?;
    if !m.is_file() || m.size() == 0 || m.size() > MAX_EXE_BYTES || m.mode() & 0o111 == 0 {
        return Err(Error::Reject("invalid executable file"));
    }
    Ok(ExecutableStamp { id: FileId { device: m.dev(), inode: m.ino() }, size: m.size(), mode: m.mode(), uid: m.uid(), gid: m.gid(), mtime: (m.mtime(), m.mtime_nsec()), ctime: (m.ctime(), m.ctime_nsec()) })
}
fn executable_digest(f: &File) -> Result<[u8; 32]> {
    use std::os::unix::fs::FileExt;
    let mut hash = Sha256::new();
    let mut offset = 0u64;
    let mut buffer = [0u8; 16 * 1024];
    loop {
        let n = f.read_at(&mut buffer, offset).map_err(|e| io_err("hash executable pin", e))?;
        if n == 0 { break; }
        offset += n as u64;
        if offset > MAX_EXE_BYTES { return Err(Error::Reject("executable grew beyond bound")); }
        hash.update(&buffer[..n]);
    }
    Ok(hash.finalize().into())
}
pub struct ExecutablePin { file: File, stamp: ExecutableStamp, digest: [u8; 32] }
impl ExecutablePin {
    /// `file` and expected SHA come from verified cell image/build provenance.
    /// They must never come from the enrollment request or a discovered process.
    pub fn from_lifecycle(file: File, expected_sha256: [u8; 32]) -> Result<Self> {
        let stamp = executable_stamp(&file)?;
        let digest = executable_digest(&file)?;
        if digest != expected_sha256 || executable_stamp(&file)? != stamp {
            return Err(Error::Reject("executable pin hash or generation changed"));
        }
        Ok(Self { file, stamp, digest })
    }
    pub fn hash_file_for_receipt(file: &File) -> Result<[u8; 32]> { executable_digest(file) }
    fn matches(&self, other: &File, hash: bool) -> Result<()> {
        if executable_stamp(&self.file)? != self.stamp || executable_stamp(other)? != self.stamp {
            return Err(Error::Reject("executable identity differs"));
        }
        if hash && (executable_digest(other)? != self.digest || executable_stamp(other)? != self.stamp) {
            return Err(Error::Reject("executable content changed"));
        }
        Ok(())
    }
}

/// A retained pidfd plus a pinned proc directory. Numeric pidfd_open is used
/// only by the lifecycle-owned Child/self constructor, never for peer fallback.
pub struct ProcessPin { pid: libc::pid_t, pidfd: OwnedFd, proc_dir: File, start: u64 }
impl ProcessPin {
    pub fn pid(&self) -> libc::pid_t { self.pid }
    pub fn birth(&self) -> u64 { self.start }
    pub fn namespace_pins(&self) -> Result<NamespacePins> {
        self.live()?;
        let pins = NamespacePins::capture(&self.proc_dir)?;
        self.live()?;
        Ok(pins)
    }
    pub fn live(&self) -> Result<()> {
        let mut p = libc::pollfd { fd: self.pidfd.as_raw_fd(), events: libc::POLLIN, revents: 0 };
        let n = unsafe { libc::poll(&mut p, 1, 0) };
        if n < 0 { return Err(err("poll pinned process")); }
        if n != 0 || p.revents != 0 { return Err(Error::Reject("process generation is dead")); }
        if process_birth(&read_at(&self.proc_dir, "stat", MAX_PROC_BYTES)?, self.pid)? != self.start {
            return Err(Error::Reject("process birth changed"));
        }
        Ok(())
    }
}

struct LifecycleSnapshot {
    status: Status, namespaces: NamespacePins, executable: File,
    executable_stamp: ExecutableStamp, root: File, membership: String,
}
impl LifecycleSnapshot {
    fn capture(pin: &ProcessPin) -> Result<Self> {
        pin.live()?;
        let status = parse_status(&read_at(&pin.proc_dir, "status", MAX_PROC_BYTES)?, pin.pid)?;
        let namespaces = NamespacePins::capture(&pin.proc_dir)?;
        let executable = open_at(&pin.proc_dir, "exe", libc::O_RDONLY)?;
        let executable_stamp = executable_stamp(&executable)?;
        let root = open_at(&pin.proc_dir, "root", libc::O_PATH | libc::O_DIRECTORY)?;
        let membership = read_at(&pin.proc_dir, "cgroup", MAX_PROC_BYTES)?;
        pin.live()?;
        Ok(Self { status, namespaces, executable, executable_stamp, root, membership })
    }
    fn matches(&self, pin: &ProcessPin) -> Result<()> {
        let current = Self::capture(pin)?;
        if current.status != self.status || current.namespaces.ids != self.namespaces.ids ||
            current.executable_stamp != self.executable_stamp || executable_stamp(&self.executable)? != self.executable_stamp ||
            FileId::of(&current.root)? != FileId::of(&self.root)? || current.membership != self.membership {
            return Err(Error::Reject("lifecycle process identity changed"));
        }
        Ok(())
    }
}

/// Host-only context; the proc view must agree with getpid before any peer work.
pub struct HostContext {
    proc_root: File, cgroup_mount: File, self_proc: File, self_pid: libc::pid_t,
    self_birth: u64, host_namespaces: NamespacePins,
}
impl HostContext {
    pub fn open() -> Result<Self> {
        let proc_root = open_dir(Path::new("/proc"))?;
        require_fs(&proc_root, PROC_MAGIC)?;
        let pid = unsafe { libc::getpid() };
        if unsafe { libc::syscall(libc::SYS_gettid) } != pid as libc::c_long {
            return Err(Error::Reject("host context must originate in lifecycle process leader"));
        }
        let self_birth = process_birth(&read_at(&proc_root, "self/stat", MAX_PROC_BYTES)?, pid)?;
        let self_proc = open_at(&proc_root, &pid.to_string(), libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
        let host_namespaces = NamespacePins::capture(&self_proc)?;
        let cgroup_mount = open_dir(Path::new("/sys/fs/cgroup"))?;
        require_fs(&cgroup_mount, CGROUP2_MAGIC)?;
        let context = Self { proc_root, cgroup_mount, self_proc, self_pid: pid, self_birth, host_namespaces };
        context.validate_host_view()?;
        Ok(context)
    }
    fn validate_host_view(&self) -> Result<()> {
        if unsafe { libc::getpid() } != self.self_pid ||
            process_birth(&read_at(&self.self_proc, "stat", MAX_PROC_BYTES)?, self.self_pid)? != self.self_birth ||
            NamespacePins::capture(&self.self_proc)?.ids != self.host_namespaces.ids {
            return Err(Error::Reject("trusted host process or namespace view changed"));
        }
        let tid = unsafe { libc::syscall(libc::SYS_gettid) };
        let current = open_at(&self.self_proc, &format!("task/{tid}"),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
        if NamespacePins::capture(&current)?.ids != self.host_namespaces.ids {
            return Err(Error::Reject("lifecycle worker thread namespace view differs"));
        }
        Ok(())
    }
    /// Revalidates the process-leader origin and this calling thread's actual
    /// namespace view. A worker may receive, but cannot manufacture, this token.
    pub fn validate_current_thread(&self) -> Result<()> { self.validate_host_view() }
    fn pin(&self, pid: libc::pid_t, pidfd: OwnedFd) -> Result<ProcessPin> {
        if pid <= 0 { return Err(Error::Reject("invalid peer PID")); }
        let flags = unsafe { libc::fcntl(pidfd.as_raw_fd(), libc::F_GETFD) };
        if flags < 0 || flags & libc::FD_CLOEXEC == 0 { return Err(Error::Reject("pidfd is not CLOEXEC")); }
        let mut p = libc::pollfd { fd: pidfd.as_raw_fd(), events: libc::POLLIN, revents: 0 };
        if unsafe { libc::poll(&mut p, 1, 0) } != 0 || p.revents != 0 { return Err(Error::Reject("dead peer before proc open")); }
        let proc_dir = open_at(&self.proc_root, &pid.to_string(), libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
        let start = process_birth(&read_at(&proc_dir, "stat", MAX_PROC_BYTES)?, pid)?;
        let pin = ProcessPin { pid, pidfd, proc_dir, start };
        pin.live()?;
        Ok(pin)
    }
    /// Caller must hold the exact live std::process::Child owned by lifecycle.
    pub fn pin_owned_child(&self, child: &mut std::process::Child) -> Result<ProcessPin> {
        if child.try_wait().map_err(|e| io_err("poll owned child", e))?.is_some() {
            return Err(Error::Reject("owned child already exited"));
        }
        let pid = libc::pid_t::try_from(child.id()).map_err(|_| Error::Reject("child PID overflow"))?;
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        if fd < 0 { return Err(err("pin owned child")); }
        let pin = self.pin(pid, unsafe { OwnedFd::from_raw_fd(fd as RawFd) })?;
        if child.try_wait().map_err(|e| io_err("recheck owned child", e))?.is_some() {
            return Err(Error::Reject("owned child exited during pin"));
        }
        Ok(pin)
    }
    pub fn pin_self(&self) -> Result<ProcessPin> {
        let pid = unsafe { libc::getpid() };
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        if fd < 0 { return Err(err("pin lifecycle owner self")); }
        self.pin(pid, unsafe { OwnedFd::from_raw_fd(fd as RawFd) })
    }
    fn membership(&self, proc_dir: &File) -> Result<File> {
        let text = read_at(proc_dir, "cgroup", MAX_PROC_BYTES)?;
        let mut lines = text.lines();
        let path = lines.next().and_then(|s| s.strip_prefix("0::/")).ok_or(Error::Reject("not one unified membership"))?;
        if lines.next().is_some() { return Err(Error::Reject("multiple cgroup memberships")); }
        let dir = if path.is_empty() { File::from(duplicate(self.cgroup_mount.as_raw_fd())?) } else { beneath_dir(&self.cgroup_mount, path)? };
        require_fs(&dir, CGROUP2_MAGIC)?;
        Ok(dir)
    }
    pub fn owned_self_cgroup(&self) -> Result<File> {
        let p = self.pin_self()?;
        self.membership(&p.proc_dir)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Budget { pub maximum: u64, pub high: Option<u64>, pub swap_maximum: Option<u64> }
impl Budget {
    fn read(root: &File) -> Result<Self> {
        fn limit(root: &File, name: &str) -> Result<Option<u64>> {
            let text = read_at(root, name, 64)?;
            let s = text.strip_suffix('\n').ok_or(Error::Reject("non-canonical budget newline"))?;
            if s == "max" { return Ok(None); }
            let n = numeric(s)?;
            if n > i64::MAX as u64 { return Err(Error::Reject("budget overflow")); }
            Ok(Some(n))
        }
        let maximum = limit(root, "memory.max")?.ok_or(Error::Reject("unbounded memory maximum"))?;
        let high = limit(root, "memory.high")?;
        let swap_maximum = limit(root, "memory.swap.max")?;
        let page = unsafe { libc::sysconf(libc::_SC_PAGESIZE) };
        if page <= 0 || maximum < page as u64 || high.is_some_and(|h| h < page as u64 || h > maximum) {
            return Err(Error::Reject("invalid finite budget"));
        }
        Ok(Self { maximum, high, swap_maximum })
    }
    pub fn canonical(self) -> [u8; 32] {
        let mut bytes = [0u8; 32];
        bytes[..8].copy_from_slice(&self.maximum.to_le_bytes());
        bytes[8..16].copy_from_slice(&self.high.unwrap_or(0).to_le_bytes());
        bytes[16..24].copy_from_slice(&self.swap_maximum.unwrap_or(0).to_le_bytes());
        let flags = u32::from(self.high.is_none()) | (u32::from(self.swap_maximum.is_none()) << 1);
        bytes[24..28].copy_from_slice(&flags.to_le_bytes());
        bytes[28..32].copy_from_slice(&1u32.to_le_bytes());
        bytes
    }
}

pub struct RolePolicy { pub uid: u32, pub gid: u32, pub namespaces: NamespacePins, pub executable: ExecutablePin }
/// Constructed only by trusted lifecycle code from its already held handles.
/// A request can provide neither a cgroup path nor any of these authorities.
pub struct CellAuthority {
    root: File, root_id: FileId, budget: Budget, generation: [u8; 32],
    owner: ProcessPin, init: ProcessPin, owner_snapshot: LifecycleSnapshot,
    init_snapshot: LifecycleSnapshot, role: RolePolicy,
    service_claimed: lifecycle_relay::OnceClaim,
    enrollment_attempted: lifecycle_relay::OnceClaim,
}
impl CellAuthority {
    pub fn from_lifecycle(root: File, owner: ProcessPin, init: ProcessPin, role: RolePolicy) -> Result<Self> {
        require_fs(&root, CGROUP2_MAGIC)?;
        if !root.metadata().map_err(|e| io_err("stat held cgroup", e))?.is_dir() {
            return Err(Error::Reject("held cgroup is not a directory"));
        }
        let root_id = FileId::of(&root)?;
        let budget = Budget::read(&root)?;
        owner.live()?;
        init.live()?;
        let owner_snapshot = LifecycleSnapshot::capture(&owner)?;
        let init_snapshot = LifecycleSnapshot::capture(&init)?;
        let mut generation = [0u8; 32];
        let got = unsafe { libc::getrandom(generation.as_mut_ptr().cast(), generation.len(), 0) };
        if got != generation.len() as isize || generation.iter().all(|b| *b == 0) { return Err(err("fresh cell relay nonce")); }
        let authority = Self { root, root_id, budget, generation, owner, init, owner_snapshot, init_snapshot, role,
            service_claimed: lifecycle_relay::OnceClaim::default(),
            enrollment_attempted: lifecycle_relay::OnceClaim::default() };
        authority.validate()?;
        Ok(authority)
    }
    pub fn budget(&self) -> Budget { self.budget }
    pub fn root_id(&self) -> FileId { self.root_id }
    pub fn validate(&self) -> Result<()> {
        self.owner.live().map_err(|error| error.context("lifecycle owner liveness"))?;
        self.init.live().map_err(|error| error.context("lifecycle init liveness"))?;
        self.owner_snapshot.matches(&self.owner).map_err(|error| error.context("lifecycle owner identity"))?;
        self.init_snapshot.matches(&self.init).map_err(|error| error.context("lifecycle init identity"))?;
        if FileId::of(&self.root)? != self.root_id || Budget::read(&self.root)? != self.budget {
            return Err(Error::Reject("cell cgroup generation or budget changed"));
        }
        if executable_stamp(&self.role.executable.file)? != self.role.executable.stamp {
            return Err(Error::Reject("lifecycle executable pin changed"));
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PeerCredentials { pub pid: libc::pid_t, pub uid: u32, pub gid: u32 }
fn socket_integer(fd: RawFd, option: libc::c_int) -> Result<libc::c_int> {
    let mut value = 0;
    let mut len = size_of::<libc::c_int>() as libc::socklen_t;
    if unsafe { libc::getsockopt(fd, libc::SOL_SOCKET, option, (&mut value as *mut libc::c_int).cast(), &mut len) } < 0 {
        return Err(err("socket integer option"));
    }
    if len as usize != size_of::<libc::c_int>() { return Err(Error::Reject("socket integer size")); }
    Ok(value)
}
fn credentials(fd: RawFd) -> Result<PeerCredentials> {
    let mut value: libc::ucred = unsafe { zeroed() };
    let mut len = size_of::<libc::ucred>() as libc::socklen_t;
    if unsafe { libc::getsockopt(fd, libc::SOL_SOCKET, libc::SO_PEERCRED, (&mut value as *mut libc::ucred).cast(), &mut len) } < 0 { return Err(err("accepted peer credentials")); }
    if len as usize != size_of::<libc::ucred>() || value.pid <= 0 { return Err(Error::Reject("invalid accepted credentials")); }
    Ok(PeerCredentials { pid: value.pid, uid: value.uid, gid: value.gid })
}
fn no_unexpected_peer_data(fd: RawFd) -> Result<()> {
    let mut p = libc::pollfd { fd, events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
    if unsafe { libc::poll(&mut p, 1, 0) } < 0 { return Err(err("poll enrollment control")); }
    if p.revents != 0 { return Err(Error::Reject("control disconnected or unexpected data")); }
    Ok(())
}

/// Only Listener::accept constructs this marker; socketpair creator credentials
/// cannot accidentally be substituted for accepted-client authentication.
pub struct AcceptedConnection { socket: OwnedFd }
pub struct Listener { socket: OwnedFd, path: PathBuf, path_id: FileId, _parent_pin: Option<File> }
impl Listener {
    /// A lifecycle-owned private directory is required. Android would see only
    /// the selected bind-mounted socket, not this host directory or cgroup FDs.
    pub fn bind(path: &Path) -> Result<Self> {
        Self::bind_for_role(path, unsafe { libc::geteuid() }, unsafe { libc::getegid() })
    }
    /// UID/GID are supplied by trusted lifecycle policy, never a request.
    pub fn bind_for_role(path: &Path, uid: u32, gid: u32) -> Result<Self> {
        let parent = path.parent().ok_or(Error::Reject("endpoint lacks parent"))?;
        let m = fs::symlink_metadata(parent).map_err(|e| io_err("stat endpoint parent", e))?;
        if !m.is_dir() || m.uid() != unsafe { libc::geteuid() } || m.mode() & 0o077 != 0 {
            return Err(Error::Reject("endpoint parent is not private and owned"));
        }
        Self::bind_checked_path(path, uid, gid, None)
    }
    // The path is through this process's pinned descriptor; no caller-provided
    // string is resolved. Retain the directory until Listener::drop unlinks
    // only the original socket inode, including across thread ownership moves.
    fn bind_in_directory(directory: File, uid: u32, gid: u32) -> Result<Self> {
        let m = directory.metadata().map_err(|e| io_err("stat held endpoint directory", e))?;
        if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o077 != 0 {
            return Err(Error::Reject("held endpoint directory is not private root-owned"));
        }
        let path = PathBuf::from(format!("/proc/self/fd/{}/droidloom-lmkd-psi", directory.as_raw_fd()));
        Self::bind_checked_path(&path, uid, gid, Some(directory))
    }
    fn bind_checked_path(path: &Path, uid: u32, gid: u32, parent_pin: Option<File>) -> Result<Self> {
        let bytes = path.as_os_str().as_bytes();
        let mut address: libc::sockaddr_un = unsafe { zeroed() };
        if bytes.is_empty() || bytes.len() >= address.sun_path.len() || bytes.contains(&0) { return Err(Error::Reject("Unix endpoint path length")); }
        address.sun_family = libc::AF_UNIX as libc::sa_family_t;
        for (to, from) in address.sun_path.iter_mut().zip(bytes) { *to = *from as libc::c_char; }
        let n = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK, 0) };
        if n < 0 { return Err(err("create enrollment listener")); }
        let socket = unsafe { OwnedFd::from_raw_fd(n) };
        if unsafe { libc::bind(socket.as_raw_fd(), (&address as *const libc::sockaddr_un).cast(), size_of::<libc::sockaddr_un>() as libc::socklen_t) } < 0 { return Err(err("bind enrollment listener")); }
        let path_id = FileId::path(path)?;
        let listener = Self { socket, path: path.to_owned(), path_id, _parent_pin: parent_pin };
        let pathname = CString::new(bytes).map_err(|_| Error::Reject("endpoint embedded NUL"))?;
        if unsafe { libc::chown(pathname.as_ptr(), uid, gid) } < 0 { return Err(err("own enrollment endpoint for role")); }
        fs::set_permissions(path, fs::Permissions::from_mode(0o600)).map_err(|e| io_err("restrict enrollment endpoint", e))?;
        let buffer: libc::c_int = 4096;
        if unsafe { libc::setsockopt(listener.socket.as_raw_fd(), libc::SOL_SOCKET, libc::SO_RCVBUF, (&buffer as *const libc::c_int).cast(), size_of::<libc::c_int>() as libc::socklen_t) } < 0 ||
            socket_integer(listener.socket.as_raw_fd(), libc::SO_RCVBUF)? > 8192 {
            return Err(Error::Reject("enrollment receive buffer is not bounded"));
        }
        if unsafe { libc::listen(listener.socket.as_raw_fd(), 1) } < 0 { return Err(err("listen enrollment endpoint")); }
        Ok(listener)
    }
    pub fn accept(&self) -> Result<Option<AcceptedConnection>> {
        let n = unsafe { libc::accept4(self.socket.as_raw_fd(), std::ptr::null_mut(), std::ptr::null_mut(), libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK) };
        if n < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::WouldBlock { return Ok(None); }
            return Err(io_err("accept enrollment peer", e));
        }
        Ok(Some(AcceptedConnection { socket: unsafe { OwnedFd::from_raw_fd(n) } }))
    }
}
impl Drop for Listener {
    fn drop(&mut self) { if FileId::path(&self.path).ok() == Some(self.path_id) { let _ = fs::remove_file(&self.path); } }
}

struct PeerSnapshot { status: Status, namespaces: NamespacePins, executable: File, root: File, membership: File, projection: File, ancestry: ancestry::CgroupAncestry }
impl HostContext {
    fn snapshot(&self, pin: &ProcessPin, authority: &CellAuthority, hash: bool) -> Result<PeerSnapshot> {
        self.validate_host_view()?;
        pin.live()?;
        let status = parse_status(&read_at(&pin.proc_dir, "status", MAX_PROC_BYTES)?, pin.pid)?;
        if status.uids != [authority.role.uid; 4] || status.gids != [authority.role.gid; 4] { return Err(Error::Reject("peer real/effective/saved/fs credentials differ")); }
        let namespaces = NamespacePins::capture(&pin.proc_dir)?;
        if namespaces.ids != authority.role.namespaces.ids { return Err(Error::Reject("peer namespace identity differs")); }
        if namespaces.identity("time") != self.host_namespaces.identity("time") { return Err(Error::Reject("host and peer monotonic namespaces differ")); }
        let executable = open_at(&pin.proc_dir, "exe", libc::O_RDONLY)?;
        authority.role.executable.matches(&executable, hash)?;
        let membership = self.membership(&pin.proc_dir)?;
        let ancestry = ancestry::CgroupAncestry::capture(&authority.root, &membership)?;
        let root = open_at(&pin.proc_dir, "root", libc::O_PATH | libc::O_DIRECTORY)?;
        let projection = beneath_dir(&root, "sys/fs/cgroup")?;
        require_fs(&projection, CGROUP2_MAGIC)?;
        if FileId::of(&projection)? != authority.root_id { return Err(Error::Reject("peer cgroup projection differs")); }
        pin.live()?;
        authority.validate()?;
        self.validate_host_view()?;
        Ok(PeerSnapshot { status, namespaces, executable, root, membership, projection, ancestry })
    }
    /// No client PID, namespace, path or descriptor is accepted as authority.
    pub fn authenticate(&self, connection: AcceptedConnection, authority: &CellAuthority) -> Result<VerifiedPeer> {
        authority.validate()?;
        let fd = connection.socket.as_raw_fd();
        if socket_integer(fd, libc::SO_TYPE)? != libc::SOCK_SEQPACKET || socket_integer(fd, libc::SO_DOMAIN)? != libc::AF_UNIX { return Err(Error::Reject("wrong enrollment transport")); }
        let peer = credentials(fd)?;
        if peer.uid != authority.role.uid || peer.gid != authority.role.gid { return Err(Error::Reject("accepted peer credentials differ")); }
        let raw_pidfd = socket_integer(fd, SO_PEERPIDFD)?;
        if raw_pidfd < 0 { return Err(Error::Reject("invalid peer pidfd")); }
        // Failure has no numeric-PID fallback. The kernel retained connection
        // identity is required even when its process generation is already dead.
        let pin = self.pin(peer.pid, unsafe { OwnedFd::from_raw_fd(raw_pidfd) })?;
        let first = self.snapshot(&pin, authority, true)?;
        let second = self.snapshot(&pin, authority, false)?;
        if credentials(fd)? != peer || first.status != second.status || first.namespaces.ids != second.namespaces.ids ||
            FileId::of(&first.root)? != FileId::of(&second.root)? || FileId::of(&first.membership)? != FileId::of(&second.membership)? || FileId::of(&first.projection)? != FileId::of(&second.projection)? || !first.ancestry.same_as(&second.ancestry) {
            return Err(Error::Reject("peer identity changed during authentication"));
        }
        first.ancestry.validate()?; second.ancestry.validate()?;
        no_unexpected_peer_data(fd)?;
        pin.live()?;
        Ok(VerifiedPeer { connection, pin, credentials: peer, snapshot: second, authority_generation: authority.generation })
    }
}
/// Non-forgeable outside this module; admission retains every pinned handle.
pub struct VerifiedPeer { connection: AcceptedConnection, pin: ProcessPin, credentials: PeerCredentials, snapshot: PeerSnapshot, authority_generation: [u8; 32] }
impl VerifiedPeer {
    pub fn credentials(&self) -> PeerCredentials { self.credentials }
    pub fn birth(&self) -> u64 { self.pin.start }
    pub fn revalidate(&self, host: &HostContext, authority: &CellAuthority) -> Result<()> {
        if self.authority_generation != authority.generation { return Err(Error::Reject("cell authority generation changed")); }
        let current = host.snapshot(&self.pin, authority, false)?;
        if credentials(self.connection.socket.as_raw_fd())? != self.credentials || current.status != self.snapshot.status ||
            current.namespaces.ids != self.snapshot.namespaces.ids || FileId::of(&current.root)? != FileId::of(&self.snapshot.root)? ||
            FileId::of(&current.membership)? != FileId::of(&self.snapshot.membership)? ||
            FileId::of(&current.projection)? != FileId::of(&self.snapshot.projection)? ||
            !current.ancestry.same_as(&self.snapshot.ancestry) {
            return Err(Error::Reject("admitted peer identity changed"));
        }
        self.snapshot.ancestry.validate()?; current.ancestry.validate()?;
        authority.role.executable.matches(&self.snapshot.executable, false)?;
        no_unexpected_peer_data(self.connection.socket.as_raw_fd())?;
        self.pin.live()
    }
}

struct LeaseState { active: AtomicBool, send_ends: Mutex<Vec<OwnedFd>> }
impl LeaseState {
    fn lock_for_prepare(&self) -> Result<MutexGuard<'_, Vec<OwnedFd>>> {
        match self.send_ends.lock() {
            Ok(guard) => Ok(guard),
            Err(poisoned) => {
                // PoisonError owns the acquired guard. Release it before
                // revoke reacquires this mutex; otherwise retirement deadlocks.
                drop(poisoned.into_inner());
                self.revoke();
                Err(Error::Reject("poisoned lease state"))
            }
        }
    }
    fn revoke(&self) {
        self.active.store(false, Ordering::Release);
        let mut guard = self.send_ends.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        let ends = std::mem::take(&mut *guard);
        drop(guard);
        for sender in ends.iter() { unsafe { libc::shutdown(sender.as_raw_fd(), libc::SHUT_WR) }; }
        drop(ends);
    }
}

/// Actual generation owner plus independent, bounded-poll revocation worker.
/// The optional PSI monitors share this worker; enrollment owns the grant codec.
/// Explicit retirement must complete before lifecycle may replace a cell.
pub struct LeaseOwner {
    peer: Option<Arc<VerifiedPeer>>, generation: [u8; 32], state: Arc<LeaseState>,
    cancel: OwnedFd, worker: Option<JoinHandle<()>>, counters: Arc<psi::Counters>, slots_sealed: bool,
    retirement_poisoned: bool,
}
impl LeaseOwner {
    pub fn new(peer: VerifiedPeer, host: Arc<HostContext>, authority: Arc<CellAuthority>) -> Result<Self> {
        peer.revalidate(&host, &authority)?;
        let mut generation = [0u8; 32];
        let got = unsafe { libc::getrandom(generation.as_mut_ptr().cast(), generation.len(), 0) };
        if got != generation.len() as isize || generation.iter().all(|b| *b == 0) { return Err(err("fresh process lease nonce")); }
        Self::start_with_monitors(peer, host, authority, generation, Vec::new(), Vec::with_capacity(2))
    }
    fn start_with_monitors(peer: VerifiedPeer, host: Arc<HostContext>, authority: Arc<CellAuthority>,
        generation: [u8; 32], monitors: Vec<psi::WorkerMonitor>, send_ends: Vec<OwnedFd>) -> Result<Self> {
        peer.revalidate(&host, &authority)?;
        let slots_sealed = !monitors.is_empty();
        let raw_cancel = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) };
        if raw_cancel < 0 { return Err(err("create owned cancellation fd")); }
        let cancel = unsafe { OwnedFd::from_raw_fd(raw_cancel) };
        let worker_cancel = duplicate(cancel.as_raw_fd())?;
        let state = Arc::new(LeaseState { active: AtomicBool::new(true), send_ends: Mutex::new(send_ends) });
        let counters = Arc::new(psi::Counters::default());
        let worker_counters = Arc::clone(&counters);
        let peer = Arc::new(peer);
        let worker_peer = Arc::clone(&peer);
        let worker_state = Arc::clone(&state);
        let worker = thread::Builder::new().name("p4-psi-lease".into()).spawn(move || {
            // One worker owns both identity/liveness and actual PSI monitors.
            // No lifecycle CLI lock is acquired and no victim is selected here.
            psi::run_worker(&worker_peer, &host, &authority, generation,
                &worker_cancel, &worker_state, &worker_counters, monitors);
            worker_state.revoke();
        }).map_err(|e| io_err("spawn owned revocation worker", e))?;
        Ok(Self { peer: Some(peer), generation, state, cancel, worker: Some(worker), counters, slots_sealed,
            retirement_poisoned: false })
    }
    pub fn diagnostics(&self) -> WorkerDiagnostics { self.counters.snapshot() }
    pub fn generation(&self) -> [u8; 32] { if self.is_retired() { [0; 32] } else { self.generation } }
    /// Return only the permanently read-only recipient capability. The owner
    /// retains both the sole sender and the authority to shutdown all aliases.
    pub fn prepare_recipient(&mut self, host: &HostContext, authority: &CellAuthority) -> Result<OwnedFd> {
        if self.is_retired() || self.slots_sealed { self.retire(); return Err(Error::Reject("inactive or sealed lease")); }
        if let Err(e) = self.refresh(host, authority) { self.retire(); return Err(e); }
        let mut pair = [-1; 2];
        if unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC, 0, pair.as_mut_ptr()) } < 0 { self.retire(); return Err(err("prepare notification socketpair")); }
        let sender = unsafe { OwnedFd::from_raw_fd(pair[0]) };
        let recipient = unsafe { OwnedFd::from_raw_fd(pair[1]) };
        let size: libc::c_int = 4096;
        let setup = || -> Result<()> {
            if unsafe { libc::setsockopt(sender.as_raw_fd(), libc::SOL_SOCKET, libc::SO_SNDBUF, (&size as *const libc::c_int).cast(), size_of::<libc::c_int>() as libc::socklen_t) } < 0 ||
                socket_integer(sender.as_raw_fd(), libc::SO_SNDBUF)? > 8192 ||
                unsafe { libc::shutdown(sender.as_raw_fd(), libc::SHUT_RD) } < 0 ||
                unsafe { libc::shutdown(recipient.as_raw_fd(), libc::SHUT_WR) } < 0 {
                return Err(Error::Reject("one-way bounded capability setup failed"));
            }
            Ok(())
        };
        if let Err(e) = setup() {
            self.retire(); return Err(e);
        }
        {
            let state = Arc::clone(&self.state);
            let mut ends = match state.lock_for_prepare() {
                Ok(ends) => ends,
                Err(error) => { self.retire(); return Err(error); }
            };
            if !self.state.active.load(Ordering::Acquire) || ends.len() == 2 {
                drop(ends);
                self.retire();
                return Err(Error::Reject("inactive lease or monitor slot limit"));
            }
            ends.push(sender);
        }
        if let Err(e) = self.refresh(host, authority) { self.retire(); return Err(e); }
        Ok(recipient)
    }
    pub fn refresh(&mut self, host: &HostContext, authority: &CellAuthority) -> Result<()> {
        if self.is_retired() { self.retire(); return Err(Error::Reject("lease already retired")); }
        let result = self.peer.as_ref().ok_or(Error::Reject("lease peer missing"))?.revalidate(host, authority);
        if let Err(e) = result { self.retire(); return Err(e); }
        Ok(())
    }
    pub fn retire(&mut self) {
        self.state.revoke();
        self.generation.fill(0);
        let wake = 1u64;
        // EAGAIN means a cancellation notification is already pending.
        unsafe { libc::write(self.cancel.as_raw_fd(), (&wake as *const u64).cast(), size_of::<u64>()) };
        self.peer.take();
    }
    /// A false result retains the worker handle and forbids replacement. No
    /// infinite join or successful-cleanup claim is made after a kernel stall.
    pub fn finish_retirement(&mut self, timeout: Duration) -> Result<bool> {
        self.retire();
        if self.retirement_poisoned { return Err(Error::Reject("revocation worker retirement is permanently poisoned")); }
        let deadline = Instant::now().checked_add(timeout).ok_or(Error::Reject("retirement deadline overflow"))?;
        while self.worker.as_ref().is_some_and(|h| !h.is_finished()) {
            if Instant::now() >= deadline { return Ok(false); }
            thread::sleep(Duration::from_millis(1));
        }
        if let Some(handle) = self.worker.take() {
            if handle.join().is_err() {
                self.retirement_poisoned = true;
                return Err(Error::Reject("revocation worker panicked"));
            }
        }
        Ok(true)
    }
    pub fn is_retired(&self) -> bool { !self.state.active.load(Ordering::Acquire) }
}
impl Drop for LeaseOwner {
    fn drop(&mut self) {
        self.retire();
        // Lifecycle integration must call finish_retirement and require true.
        // Drop requests revocation but cannot certify bounded worker cleanup.
        if self.worker.as_ref().is_some_and(|h| h.is_finished()) {
            if let Some(handle) = self.worker.take() { let _ = handle.join(); }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct RelativeIoDirectory(PathBuf);
    impl RelativeIoDirectory {
        fn create() -> Self {
            use std::os::unix::fs::DirBuilderExt;
            let mut nonce = [0u8; 8];
            assert_eq!(unsafe { libc::getrandom(nonce.as_mut_ptr().cast(), nonce.len(), 0) }, nonce.len() as isize);
            let path = std::env::temp_dir().join(format!("p4-relative-io-{}-{:016x}",
                unsafe { libc::getpid() }, u64::from_le_bytes(nonce)));
            fs::DirBuilder::new().mode(0o700).create(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for RelativeIoDirectory {
        fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); }
    }
    #[test]
    fn missing_relative_entry_retains_real_errno_name_and_held_base() {
        let directory = RelativeIoDirectory::create();
        let base = open_dir(&directory.0).unwrap();
        let expected = FileId::of(&base).unwrap();
        let name = "absent\n\"entry";
        let error = open_at(&base, name, libc::O_RDONLY | libc::O_NOFOLLOW).unwrap_err();
        // A later failing syscall must not overwrite the retained open errno.
        assert_eq!(unsafe { libc::close(-1) }, -1);
        let message = error.to_string();
        assert!(!message.contains('\n'));
        assert!(message.contains("absent\\n\\\"entry"));
        match error {
            Error::RelativeIo { name: observed, flags, base, error } => {
                assert_eq!(observed, name);
                assert_eq!(flags, libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC);
                assert_eq!(base, Some(expected));
                assert_eq!(error.raw_os_error(), Some(libc::ENOENT));
            }
            other => panic!("unexpected error: {other}"),
        }
    }
    #[test]
    fn relative_error_does_not_follow_a_rejected_symlink() {
        let directory = RelativeIoDirectory::create();
        fs::write(directory.0.join("target"), b"owned unchanged target").unwrap();
        std::os::unix::fs::symlink("target", directory.0.join("link")).unwrap();
        let base = open_dir(&directory.0).unwrap();
        match open_at(&base, "link", libc::O_RDONLY | libc::O_NOFOLLOW).unwrap_err() {
            Error::RelativeIo { name, flags, base: observed, error } => {
                assert_eq!(name, "link");
                assert_eq!(flags, libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC);
                assert_eq!(observed, Some(FileId::of(&base).unwrap()));
                assert_eq!(error.raw_os_error(), Some(libc::ELOOP));
            }
            other => panic!("unexpected error: {other}"),
        }
        assert_eq!(fs::read(directory.0.join("target")).unwrap(), b"owned unchanged target");
    }
    struct RelativeIoChild(std::process::Child);
    impl Drop for RelativeIoChild {
        fn drop(&mut self) {
            if self.0.try_wait().ok().flatten().is_none() { let _ = self.0.kill(); }
            let _ = self.0.wait();
        }
    }
    #[test]
    fn exited_owned_child_retains_exact_proc_base_and_role_without_revival() {
        use std::process::{Command, Stdio};
        let mut child = RelativeIoChild(Command::new("/bin/cat").stdin(Stdio::piped())
            .stdout(Stdio::null()).stderr(Stdio::null()).spawn().unwrap());
        let pid = child.0.id() as libc::pid_t;
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        assert!(raw >= 0);
        let pidfd = unsafe { OwnedFd::from_raw_fd(raw as RawFd) };
        let proc_dir = open_dir(&PathBuf::from(format!("/proc/{pid}"))).unwrap();
        let proc_id = FileId::of(&proc_dir).unwrap();
        let start = process_birth(&read_at(&proc_dir, "stat", MAX_PROC_BYTES).unwrap(), pid).unwrap();
        let pin = ProcessPin { pid, pidfd, proc_dir, start };
        pin.live().unwrap();
        drop(child.0.stdin.take());
        let deadline = Instant::now() + Duration::from_secs(2);
        loop {
            if let Some(status) = child.0.try_wait().unwrap() { assert!(status.success()); break; }
            assert!(Instant::now() < deadline, "owned child did not exit within test bound");
            thread::sleep(Duration::from_millis(1));
        }
        assert!(matches!(pin.live(), Err(Error::Reject("process generation is dead"))));
        let error = open_at(&pin.proc_dir, "ns/mnt", libc::O_RDONLY).unwrap_err()
            .context("lifecycle init identity");
        assert!(error.to_string().starts_with("lifecycle init identity: open relative pinned directory"));
        match error {
            Error::Context("lifecycle init identity", inner) => match *inner {
                Error::RelativeIo { name, base, error, .. } => {
                    assert_eq!(name, "ns/mnt");
                    assert_eq!(base, Some(proc_id));
                    assert_eq!(error.raw_os_error(), Some(libc::ENOENT));
                }
                other => panic!("unexpected nested error: {other}"),
            },
            other => panic!("unexpected error: {other}"),
        }
        // No authenticate, replacement PID lookup, retry or namespace action.
    }
    #[test]
    fn retirement_panic_cannot_be_retried_into_success() {
        let raw = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) }; assert!(raw >= 0);
        let mut owner = LeaseOwner { peer: None, generation: [7; 32],
            state: Arc::new(LeaseState { active: AtomicBool::new(true), send_ends: Mutex::new(Vec::new()) }),
            cancel: unsafe { OwnedFd::from_raw_fd(raw) },
            worker: Some(thread::spawn(|| panic!("owned retirement failure control"))),
            counters: Arc::new(psi::Counters::default()), slots_sealed: true, retirement_poisoned: false };
        assert!(owner.finish_retirement(Duration::from_secs(1)).is_err());
        assert!(owner.worker.is_none());
        assert!(owner.finish_retirement(Duration::from_secs(1)).is_err());
        assert!(owner.retirement_poisoned);
        assert!(owner.is_retired());
    }
    #[test]
    fn poisoned_sender_lock_revokes_existing_real_capability_without_deadlock() {
        let mut pair = [-1; 2];
        assert_eq!(unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC, 0, pair.as_mut_ptr()) }, 0);
        let sender = unsafe { OwnedFd::from_raw_fd(pair[0]) };
        let recipient = unsafe { OwnedFd::from_raw_fd(pair[1]) };
        let state = Arc::new(LeaseState { active: AtomicBool::new(true), send_ends: Mutex::new(vec![sender]) });
        let child_state = Arc::clone(&state);
        assert!(thread::spawn(move || {
            let _guard = child_state.send_ends.lock().unwrap();
            panic!("owned poison negative control");
        }).join().is_err());
        assert!(state.lock_for_prepare().is_err());
        assert!(!state.active.load(Ordering::Acquire));
        let mut p = libc::pollfd { fd: recipient.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
        assert_eq!(unsafe { libc::poll(&mut p, 1, 0) }, 1);
        assert_ne!(p.revents & (libc::POLLHUP | libc::POLLRDHUP), 0);
        // Failure closes old capabilities and cannot be retried as healthy.
        assert!(state.lock_for_prepare().is_err());
    }
}
