//! Actual child lifetimes; no PID from a file is adopted or signalled.
use super::Result;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::process::CommandExt;
use std::process::{Child, Command, ExitStatus};
use std::time::{Duration, Instant};

pub(super) struct ChildOwner {
    child: Child,
    pub pidfd: OwnedFd,
}

impl ChildOwner {
    pub(super) fn spawn(command: &mut Command) -> Result<Self> {
        let mut child = command.spawn()?;
        match pin(child.id()) {
            Ok(pidfd) => Ok(Self { child, pidfd }),
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                Err(error)
            }
        }
    }
    pub(super) fn pid(&self) -> u32 {
        self.child.id()
    }
    pub(super) fn wait_before(&mut self, end: Instant) -> Result<ExitStatus> {
        loop {
            if let Some(status) = self.child.try_wait()? {
                return Ok(status);
            }
            if Instant::now() >= end {
                return Err("actual child did not exit within its bound".into());
            }
            std::thread::sleep(Duration::from_millis(10));
        }
    }
    pub(super) fn terminate(&mut self) -> Result<()> {
        if self.child.try_wait()?.is_some() {
            return Ok(());
        }
        signal(&self.pidfd, libc::SIGTERM)?;
        let status = self.wait_before(Instant::now() + Duration::from_secs(10))?;
        if !status.success() {
            return Err("seed owner did not finish a graceful successful shutdown".into());
        }
        Ok(())
    }
}

impl Drop for ChildOwner {
    fn drop(&mut self) {
        if self.child.try_wait().ok().flatten().is_some() {
            return;
        }
        let _ = signal(&self.pidfd, libc::SIGTERM);
        if self
            .wait_before(Instant::now() + Duration::from_secs(5))
            .is_err()
        {
            let _ = signal(&self.pidfd, libc::SIGKILL);
            let _ = self.child.wait();
        }
    }
}

pub(super) fn pin(pid: u32) -> Result<OwnedFd> {
    // SAFETY: caller retains Child (or names its own current process), so no
    // numeric PID is recovered from disk or allowed to recycle before pinning.
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: adopts precisely the newly returned descriptor.
    Ok(unsafe { OwnedFd::from_raw_fd(raw as i32) })
}

pub(super) fn alive(pidfd: &OwnedFd) -> Result<()> {
    let mut poll = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: points at exactly one initialized live descriptor observation.
    let result = unsafe { libc::poll(&mut poll, 1, 0) };
    if result != 0 {
        return Err("held original process lifetime ended".into());
    }
    Ok(())
}

fn signal(pidfd: &OwnedFd, signal: i32) -> Result<()> {
    // SAFETY: pins the actual child; null siginfo with zero flags is supported.
    if unsafe {
        libc::syscall(
            libc::SYS_pidfd_send_signal,
            pidfd.as_raw_fd(),
            signal,
            std::ptr::null::<libc::siginfo_t>(),
            0,
        )
    } < 0
    {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

pub(super) fn drop_to_owner(command: &mut Command, uid: u32, gid: u32) {
    // SAFETY: only async-signal-safe scalar credential/prctl syscalls run in
    // the child, before exec; no allocator, locks, environment or Rust IO.
    unsafe {
        command.pre_exec(move || {
            if libc::setgroups(0, std::ptr::null()) != 0 {
                return Err(io::Error::last_os_error());
            }
            for cap in 0..64 {
                if libc::prctl(libc::PR_CAPBSET_DROP, cap, 0, 0, 0) != 0 {
                    let error = io::Error::last_os_error();
                    if error.raw_os_error() != Some(libc::EINVAL) {
                        return Err(error);
                    }
                }
            }
            if libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                || libc::setresgid(gid, gid, gid) != 0
                || libc::setresuid(uid, uid, uid) != 0
            {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        });
    }
}

pub(super) fn actual_credentials(pid: u32, uid: u32, gid: u32) -> Result<()> {
    let status = std::fs::read_to_string(format!("/proc/{pid}/status"))?;
    let expected_uid = format!("Uid:\t{uid}\t{uid}\t{uid}\t{uid}");
    let expected_gid = format!("Gid:\t{gid}\t{gid}\t{gid}\t{gid}");
    if !status.lines().any(|s| s == expected_uid)
        || !status.lines().any(|s| s == expected_gid)
        || !status.lines().any(|s| s == "NoNewPrivs:\t1")
        || !status.lines().any(|s| {
            s.strip_prefix("Groups:")
                .is_some_and(|v| v.trim().is_empty())
        })
        || status.lines().filter(|s| s.starts_with("Cap")).any(|s| {
            s.split_once(':')
                .is_none_or(|(_, value)| !value.trim().bytes().all(|b| b == b'0'))
        })
    {
        return Err("actual child credential drop is incomplete".into());
    }
    Ok(())
}
