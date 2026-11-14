//! Exact child handles for util-linux namespace owners that do not relay TERM.
//!
//! The direct owner stays an unreaped `Child` while its only PID-namespace
//! child is bound. Signals then use the held pidfd, never a later PID lookup.

use std::fs;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::process::Child;
use std::thread;
use std::time::{Duration, Instant};

#[derive(Debug, PartialEq, Eq)]
struct Identity {
    parent: u32,
    start_ticks: u64,
}

fn identity(pid: u32) -> io::Result<Identity> {
    let value = fs::read_to_string(format!("/proc/{pid}/stat"))?;
    let (_, fields) = value
        .rsplit_once(") ")
        .ok_or_else(|| invalid("malformed process stat"))?;
    let fields: Vec<_> = fields.split_ascii_whitespace().collect();
    Ok(Identity {
        parent: fields
            .get(1)
            .ok_or_else(|| invalid("missing parent PID"))?
            .parse()
            .map_err(|_| invalid("invalid parent PID"))?,
        start_ticks: fields
            .get(19)
            .ok_or_else(|| invalid("missing process start time"))?
            .parse()
            .map_err(|_| invalid("invalid process start time"))?,
    })
}

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

/// A signal target bound while its original namespace owner is still unreaped.
pub(super) struct OwnedNamespaceChild {
    fd: OwnedFd,
    #[cfg(test)]
    pid: u32,
}

impl OwnedNamespaceChild {
    /// Bind the one namespace init created by this owned `unshare --fork`.
    pub(super) fn capture(owner: &mut Child, timeout: Duration) -> io::Result<Self> {
        let deadline = Instant::now() + timeout;
        loop {
            // Reaping releases a numeric PID. Do not inspect /proc after that
            // point or claim that an init whose identity was never bound died.
            if let Some(status) = owner.try_wait()? {
                return Err(io::Error::other(format!(
                    "namespace owner exited before its init identity was bound ({status}); inner retirement is unobserved"
                )));
            }
            match Self::capture_once(owner.id()) {
                Ok(Some(child)) => return Ok(child),
                Ok(None) => {}
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(error) => return Err(error),
            }
            if Instant::now() >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "namespace init identity was not available before the deadline",
                ));
            }
            thread::sleep(Duration::from_millis(5));
        }
    }

    fn capture_once(owner: u32) -> io::Result<Option<Self>> {
        let children = fs::read_to_string(format!("/proc/{owner}/task/{owner}/children"))?;
        let children: Vec<u32> = children
            .split_ascii_whitespace()
            .map(|value| {
                value
                    .parse()
                    .map_err(|_| invalid("invalid owned child PID"))
            })
            .collect::<io::Result<_>>()?;
        let pid = match children.as_slice() {
            [] => return Ok(None),
            [pid] => *pid,
            _ => return Err(invalid("namespace owner has more than one child")),
        };
        let before = identity(pid)?;
        if before.parent != owner {
            return Err(invalid("namespace init parent changed before binding"));
        }
        let fd = open_pidfd(pid)?;
        let namespace = fs::read_link(format!("/proc/{pid}/ns/pid"))?;
        if namespace != fs::read_link(format!("/proc/{owner}/ns/pid_for_children"))?
            || namespace == fs::read_link("/proc/self/ns/pid")?
        {
            return Err(invalid(
                "owned child is not in the owner's new PID namespace",
            ));
        }
        let status = fs::read_to_string(format!("/proc/{pid}/status"))?;
        let ids = status
            .lines()
            .find_map(|line| line.strip_prefix("NSpid:"))
            .ok_or_else(|| invalid("namespace PID identity unavailable"))?
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| invalid("invalid namespace PID identity"))?;
        if ids.len() < 2 || ids.last() != Some(&1) || identity(pid)? != before {
            return Err(invalid(
                "namespace init identity changed while opening pidfd",
            ));
        }
        Ok(Some(Self {
            fd,
            #[cfg(test)]
            pid,
        }))
    }

    pub(super) fn signal(&self, signal: libc::c_int) -> io::Result<()> {
        // SAFETY: fd is a held kernel pidfd; no siginfo pointer is supplied.
        let result = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.fd.as_raw_fd(),
                signal,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        };
        if result == 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if error.raw_os_error() == Some(libc::ESRCH) {
            Ok(())
        } else {
            Err(error)
        }
    }

    pub(super) fn exited(&self) -> io::Result<bool> {
        pidfd_exited(&self.fd)
    }

    /// Call only after the separately owned `unshare` Child has been reaped.
    /// POLLIN proves init exited; it does not claim to have reaped that init.
    pub(super) fn retire_after_owner_reaped(&self) -> io::Result<()> {
        if self.exited()? {
            return Ok(());
        }
        // The owner can die independently. Kill only the already-bound init;
        // the kernel then kills all remaining tasks in that PID namespace.
        self.signal(libc::SIGKILL)?;
        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline {
            if self.exited()? {
                return Ok(());
            }
            thread::sleep(Duration::from_millis(5));
        }
        Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "bound namespace init did not exit after its owner was reaped",
        ))
    }
}

fn open_pidfd(pid: u32) -> io::Result<OwnedFd> {
    let pid = i32::try_from(pid).map_err(|_| invalid("PID exceeds Linux pid_t"))?;
    // SAFETY: this syscall returns a new descriptor or -1; flags are zero.
    let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: the successful syscall transferred this new descriptor to us.
    Ok(unsafe { OwnedFd::from_raw_fd(fd as libc::c_int) })
}

fn pidfd_exited(fd: &OwnedFd) -> io::Result<bool> {
    let mut event = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: event is one initialized, writable pollfd and timeout is zero.
    let result = unsafe { libc::poll(&mut event, 1, 0) };
    if result < 0 {
        return Err(io::Error::last_os_error());
    }
    if event.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
        return Err(invalid("namespace pidfd poll failed"));
    }
    Ok(event.revents & (libc::POLLIN | libc::POLLHUP) != 0)
}

#[cfg(test)]
#[path = "development_process_tests.rs"]
mod tests;
