//! Original Session process lifetime only; this capability grants no effect,
//! Root role, principal or reconnect permission. The Notes two-FD wire is unchanged.
use crate::notes::NotesTargetIdentity;
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

pub const FD_ENV_V1: &str = "TRILL_NOTES_SESSION_LIFETIME_FD_V1";
pub const META_ENV_V1: &str = "TRILL_NOTES_SESSION_LIFETIME_META_V1";
static INHERITED_CONSUMED: AtomicBool = AtomicBool::new(false);

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum StorageRequirement {
    Optional,
    DurableRequired,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum Purpose {
    TerminateNotesWithOriginalSession,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Metadata {
    schema_version: u16,
    purpose: Purpose,
    target: NotesTargetIdentity,
    uid: u32,
    gid: u32,
    pid: u32,
    boot_id: String,
    process_start_ticks: u64,
    storage: StorageRequirement,
}

/// Captured from this actual process, not deserializable or reconstructable
/// from a numeric PID supplied by a renderer or a disk record.
pub struct SessionLifetimeSource {
    descriptor: OwnedFd,
    metadata: Metadata,
}

impl SessionLifetimeSource {
    pub fn capture_current(
        target: NotesTargetIdentity,
        storage: StorageRequirement,
    ) -> io::Result<Self> {
        target
            .validate()
            .map_err(|_| invalid("invalid Notes lifetime target"))?;
        // SAFETY: read actual process credentials, not the spawning thread ID.
        let (pid, uid, gid) = unsafe { (libc::getpid() as u32, libc::getuid(), libc::getgid()) };
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        if raw < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: adopt exactly the new kernel descriptor.
        let mut descriptor = unsafe { OwnedFd::from_raw_fd(raw as i32) };
        if raw < 3 {
            // Keep stdin/stdout/stderr separate even if this Session started
            // with a standard descriptor closed.
            let duplicated =
                unsafe { libc::fcntl(descriptor.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 3) };
            if duplicated < 0 {
                return Err(io::Error::last_os_error());
            }
            descriptor = unsafe { OwnedFd::from_raw_fd(duplicated) };
        }
        let metadata = Metadata {
            schema_version: 1,
            purpose: Purpose::TerminateNotesWithOriginalSession,
            target,
            uid,
            gid,
            pid,
            boot_id: bounded("/proc/sys/kernel/random/boot_id", 128)?
                .trim()
                .into(),
            process_start_ticks: start_ticks(pid)?,
            storage,
        };
        verify_kernel(&descriptor, &metadata, /*require_parent*/ false)?;
        Ok(Self {
            descriptor,
            metadata,
        })
    }

    /// Only this FD becomes inheritable in the forked child. The parent's
    /// flags are untouched even when another Session thread launches an app.
    pub fn inherit_into(self, command: &mut Command) -> io::Result<()> {
        let encoded = serde_json::to_string(&self.metadata).map_err(io::Error::other)?;
        if encoded.len() > 1024 {
            return Err(invalid("Notes lifetime metadata bound"));
        }
        let raw = self.descriptor.as_raw_fd();
        command
            .env(FD_ENV_V1, raw.to_string())
            .env(META_ENV_V1, encoded);
        // SAFETY: the owned descriptor remains captured until child exec.
        // Only async-signal-safe fcntl executes in the child; no PDEATHSIG,
        // allocation, parent flag mutation or thread-parent assumption is used.
        unsafe {
            command.pre_exec(move || {
                let flags = libc::fcntl(self.descriptor.as_raw_fd(), libc::F_GETFD);
                if flags < 0
                    || libc::fcntl(
                        self.descriptor.as_raw_fd(),
                        libc::F_SETFD,
                        flags & !libc::FD_CLOEXEC,
                    ) < 0
                {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        Ok(())
    }
}

/// Read-only liveness fence shared by GUI and its sole document worker.
#[derive(Clone)]
pub struct SessionLifetime {
    descriptor: Arc<OwnedFd>,
    storage: StorageRequirement,
}

impl SessionLifetime {
    /// Both parameters absent retain the old direct two-FD fixture profile.
    /// Partial/new malformed parameters fail before any Notes store is opened.
    pub fn from_environment(target: &NotesTargetIdentity) -> io::Result<Option<Self>> {
        let descriptor = std::env::var_os(FD_ENV_V1);
        let metadata = std::env::var_os(META_ENV_V1);
        let (descriptor, metadata) = match (descriptor, metadata) {
            (None, None) => return Ok(None),
            (Some(fd), Some(meta)) => (fd, meta),
            _ => return Err(invalid("incomplete versioned Notes lifetime parameters")),
        };
        if INHERITED_CONSUMED.swap(true, Ordering::AcqRel) {
            return Err(invalid("inherited Notes lifetime already consumed"));
        }
        let raw = descriptor
            .to_str()
            .and_then(|s| s.parse::<i32>().ok())
            .filter(|fd| *fd >= 3)
            .ok_or_else(|| invalid("invalid inherited Notes lifetime descriptor"))?;
        let encoded = metadata
            .to_str()
            .filter(|s| !s.is_empty() && s.len() <= 1024)
            .ok_or_else(|| invalid("invalid Notes lifetime metadata encoding"))?;
        let metadata: Metadata = serde_json::from_str(encoded).map_err(io::Error::other)?;
        if metadata.schema_version != 1 || metadata.target != *target {
            return Err(invalid("Notes lifetime purpose/target/version mismatch"));
        }
        if std::fs::read_link(format!("/proc/self/fd/{raw}"))? != Path::new("anon_inode:[pidfd]") {
            return Err(invalid("Notes lifetime is not an inherited pidfd"));
        }
        // SAFETY: validated inherited live descriptor is consumed exactly once.
        let descriptor = unsafe { OwnedFd::from_raw_fd(raw) };
        let flags = unsafe { libc::fcntl(raw, libc::F_GETFD) };
        if flags < 0 || unsafe { libc::fcntl(raw, libc::F_SETFD, flags | libc::FD_CLOEXEC) } < 0 {
            return Err(io::Error::last_os_error());
        }
        verify_kernel(&descriptor, &metadata, /*require_parent*/ true)?;
        Ok(Some(Self {
            descriptor: Arc::new(descriptor),
            storage: metadata.storage,
        }))
    }

    pub fn storage_requirement(&self) -> StorageRequirement {
        self.storage
    }
    pub fn check_alive(&self) -> io::Result<()> {
        live(&self.descriptor)
    }
    pub fn has_ended(&self) -> bool {
        self.check_alive().is_err()
    }
}

fn verify_kernel(
    descriptor: &OwnedFd,
    metadata: &Metadata,
    require_parent: bool,
) -> io::Result<()> {
    // SAFETY: only observe actual current process IDs and credentials.
    let (uid, gid, ppid) = unsafe { (libc::geteuid(), libc::getegid(), libc::getppid() as u32) };
    if metadata.pid <= 1
        || metadata.process_start_ticks == 0
        || metadata.uid != uid
        || metadata.gid != gid
        || (require_parent && ppid != metadata.pid)
        || bounded("/proc/sys/kernel/random/boot_id", 128)?.trim() != metadata.boot_id
        || start_ticks(metadata.pid)? != metadata.process_start_ticks
    {
        return Err(invalid(
            "Notes lifetime differs from actual original Session parent/birth",
        ));
    }
    let info = bounded(
        &format!("/proc/self/fdinfo/{}", descriptor.as_raw_fd()),
        4096,
    )?;
    if info
        .lines()
        .find_map(|s| s.strip_prefix("Pid:")?.trim().parse::<u32>().ok())
        != Some(metadata.pid)
    {
        return Err(invalid("Notes lifetime descriptor names another process"));
    }
    let status = bounded(&format!("/proc/{}/status", metadata.pid), 16384)?;
    let expected_uid = format!("Uid:\t{uid}\t{uid}\t{uid}\t{uid}");
    let expected_gid = format!("Gid:\t{gid}\t{gid}\t{gid}\t{gid}");
    if !status.lines().any(|s| s == expected_uid) || !status.lines().any(|s| s == expected_gid) {
        return Err(invalid("Notes Session parent credential mismatch"));
    }
    live(descriptor)
}

fn live(descriptor: &OwnedFd) -> io::Result<()> {
    let mut item = libc::pollfd {
        fd: descriptor.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: one initialized kernel poll descriptor, observation only.
    let result = unsafe { libc::poll(&mut item, 1, 0) };
    if result != 0 {
        return Err(invalid(
            "original Notes Session lifetime ended or unavailable",
        ));
    }
    Ok(())
}

fn start_ticks(pid: u32) -> io::Result<u64> {
    bounded(&format!("/proc/{pid}/stat"), 8192)?
        .rsplit_once(") ")
        .and_then(|(_, s)| s.split_whitespace().nth(19))
        .and_then(|s| s.parse().ok())
        .filter(|n| *n > 0)
        .ok_or_else(|| invalid("Notes Session birth is missing"))
}
fn bounded(path: &str, max: u64) -> io::Result<String> {
    let mut text = String::new();
    File::open(path)?.take(max + 1).read_to_string(&mut text)?;
    if text.len() as u64 > max {
        return Err(invalid("Notes lifetime metadata exceeds bound"));
    }
    Ok(text)
}
fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, message)
}
