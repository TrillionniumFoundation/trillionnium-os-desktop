//! Original Session process lifetime only; this capability grants no effect,
//! Root role, principal or reconnect permission. The Calculator two-FD wire is unchanged.
use crate::calculator::CalculatorTargetIdentity;
pub use crate::notes_lifetime::StorageRequirement;
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

pub const FD_ENV_V1: &str = "TRILL_CALCULATOR_SESSION_LIFETIME_FD_V1";
pub const META_ENV_V1: &str = "TRILL_CALCULATOR_SESSION_LIFETIME_META_V1";
static INHERITED_CONSUMED: AtomicBool = AtomicBool::new(false);

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum Purpose {
    TerminateCalculatorWithOriginalSession,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Metadata {
    schema_version: u16,
    purpose: Purpose,
    target: CalculatorTargetIdentity,
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
    pub fn capture_current(target: CalculatorTargetIdentity) -> io::Result<Self> {
        Self::capture_current_with_storage(target, StorageRequirement::Optional)
    }

    pub fn capture_current_with_storage(
        target: CalculatorTargetIdentity,
        storage: StorageRequirement,
    ) -> io::Result<Self> {
        target
            .validate()
            .map_err(|_| invalid("invalid Calculator lifetime target"))?;
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
            purpose: Purpose::TerminateCalculatorWithOriginalSession,
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
            return Err(invalid("Calculator lifetime metadata bound"));
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
    /// Absence reports no capability; the production Calculator entry refuses it.
    /// Partial/malformed parameters fail before the app channel is opened.
    pub fn from_environment(target: &CalculatorTargetIdentity) -> io::Result<Option<Self>> {
        let descriptor = std::env::var_os(FD_ENV_V1);
        let metadata = std::env::var_os(META_ENV_V1);
        let (descriptor, metadata) = match (descriptor, metadata) {
            (None, None) => return Ok(None),
            (Some(fd), Some(meta)) => (fd, meta),
            _ => {
                return Err(invalid(
                    "incomplete versioned Calculator lifetime parameters",
                ))
            }
        };
        if INHERITED_CONSUMED.swap(true, Ordering::AcqRel) {
            return Err(invalid("inherited Calculator lifetime already consumed"));
        }
        let raw = descriptor
            .to_str()
            .and_then(|s| s.parse::<i32>().ok())
            .filter(|fd| *fd >= 3)
            .ok_or_else(|| invalid("invalid inherited Calculator lifetime descriptor"))?;
        let encoded = metadata
            .to_str()
            .filter(|s| !s.is_empty() && s.len() <= 1024)
            .ok_or_else(|| invalid("invalid Calculator lifetime metadata encoding"))?;
        let metadata: Metadata = serde_json::from_str(encoded).map_err(io::Error::other)?;
        if metadata.schema_version != 1 || metadata.target != *target {
            return Err(invalid(
                "Calculator lifetime purpose/target/version mismatch",
            ));
        }
        if std::fs::read_link(format!("/proc/self/fd/{raw}"))? != Path::new("anon_inode:[pidfd]") {
            return Err(invalid("Calculator lifetime is not an inherited pidfd"));
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
            "Calculator lifetime differs from actual original Session parent/birth",
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
        return Err(invalid(
            "Calculator lifetime descriptor names another process",
        ));
    }
    let status = bounded(&format!("/proc/{}/status", metadata.pid), 16384)?;
    let expected_uid = format!("Uid:\t{uid}\t{uid}\t{uid}\t{uid}");
    let expected_gid = format!("Gid:\t{gid}\t{gid}\t{gid}\t{gid}");
    if !status.lines().any(|s| s == expected_uid) || !status.lines().any(|s| s == expected_gid) {
        return Err(invalid("Calculator Session parent credential mismatch"));
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
            "original Calculator Session lifetime ended or unavailable",
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
        .ok_or_else(|| invalid("Calculator Session birth is missing"))
}
fn bounded(path: &str, max: u64) -> io::Result<String> {
    let mut text = String::new();
    File::open(path)?.take(max + 1).read_to_string(&mut text)?;
    if text.len() as u64 > max {
        return Err(invalid("Calculator lifetime metadata exceeds bound"));
    }
    Ok(text)
}
fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, message)
}

/// A transport budget includes host suspend. This clock grants no authority.
pub fn boottime_nanos() -> io::Result<u64> {
    let mut now = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // SAFETY: a live writable timespec of the required size.
    if unsafe { libc::clock_gettime(libc::CLOCK_BOOTTIME, &mut now) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let seconds = u64::try_from(now.tv_sec).map_err(|_| invalid("negative BOOTTIME"))?;
    let nanos = u64::try_from(now.tv_nsec).map_err(|_| invalid("negative BOOTTIME fraction"))?;
    if nanos >= 1_000_000_000 {
        return Err(invalid("invalid BOOTTIME fraction"));
    }
    seconds
        .checked_mul(1_000_000_000)
        .and_then(|n| n.checked_add(nanos))
        .ok_or_else(|| invalid("BOOTTIME overflow"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn concurrent_spawn_does_not_clear_session_parent_descriptor_cloexec() {
        let source = SessionLifetimeSource::capture_current(CalculatorTargetIdentity {
            session_instance: "9".repeat(32),
            task_id: 1,
            incarnation: "a".repeat(32),
        })
        .unwrap();
        let raw = source.descriptor.as_raw_fd();
        let before = unsafe { libc::fcntl(raw, libc::F_GETFD) };
        assert!(before >= 0 && before & libc::FD_CLOEXEC != 0);
        let mut command = Command::new("/bin/true");
        source.inherit_into(&mut command).unwrap();
        assert_eq!(unsafe { libc::fcntl(raw, libc::F_GETFD) }, before);
        assert!(std::thread::spawn(move || {
            assert!(command.status().unwrap().success());
            assert_eq!(unsafe { libc::fcntl(raw, libc::F_GETFD) }, before);
        })
        .join()
        .is_ok());
    }
}
