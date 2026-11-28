//! Calendar-only helpers born by the original single-threaded factory.
//!
//! Anonymous stdio remains kernel-origin and never crosses to the broker.
//! The separate metadata child enters its fixed high MLS role before reading
//! the stopped Calendar query. Both actual PIDFDs are reaped within the one
//! inherited query end; neither helper executes another image.
use super::{ApplicationError, Result, external, protocol, query_io, reject, require};
use std::fs::File;
use std::io::{self, Read};
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::time::{Duration, Instant};

pub(super) const METADATA_CONTEXT: &[u8] = b"u:r:droidloom_calendar_metadata:s0:c512,c768";
const KERNEL: &[u8] = b"u:r:kernel:s0";
const FACTORY_AA: &[u8] = b"droidloom-instance-factory (enforce)\n";
const LIMIT: Duration = Duration::from_secs(5);
static UNRETIRED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

#[derive(Clone, Copy)]
enum Purpose {
    Stdio = 0,
    Metadata = 1,
}

unsafe extern "C" {
    fn droidloom_factory_context() -> libc::c_int;
    fn droidloom_factory_calendar_bootstrap(
        purpose: u32,
        parent: i32,
        channel: i32,
        stdio: i32,
        deadline_ns: u64,
        filter: *const libc::sock_fprog,
    ) -> libc::c_int;
}

fn proc_body(path: &std::ffi::CStr, limit: u64) -> Result<Vec<u8>> {
    let raw = unsafe {
        libc::open(
            path.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(raw) };
    let mut fs: libc::statfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        fs.f_type == libc::PROC_SUPER_MAGIC && file.metadata()?.is_file(),
        "Calendar factory attribute is not procfs",
    )?;
    let mut body = Vec::new();
    file.take(limit + 1).read_to_end(&mut body)?;
    require(
        body.len() as u64 <= limit,
        "Calendar factory attribute exceeds bound",
    )?;
    Ok(body)
}
pub(super) fn context(metadata: bool) -> Result<()> {
    let expected = if metadata { METADATA_CONTEXT } else { KERNEL };
    let actual = crate::production_mac::self_attr::selinux_current().map_err(external)?;
    require(
        actual.strip_suffix(b"\0") == Some(expected),
        "Calendar helper actual SELinux origin differs",
    )?;
    require(
        proc_body(c"/proc/thread-self/attr/apparmor/current", 256)? == FACTORY_AA,
        "Calendar helper actual factory AppArmor profile differs",
    )
}
pub(super) fn channel() -> Result<()> {
    for (option, expected) in [
        (libc::SO_TYPE, libc::SOCK_SEQPACKET),
        (libc::SO_DOMAIN, libc::AF_UNIX),
        (libc::SO_PASSCRED, 1),
    ] {
        let mut value = 0_i32;
        let mut bytes = mem::size_of_val(&value) as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                3,
                libc::SOL_SOCKET,
                option,
                (&mut value as *mut i32).cast(),
                &mut bytes,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        require(
            bytes as usize == mem::size_of_val(&value) && value == expected,
            "Calendar helper private socket differs",
        )?;
    }
    Ok(())
}
fn single_factory() -> Result<()> {
    if UNRETIRED.load(std::sync::atomic::Ordering::Acquire) {
        return Err(ApplicationError::RetirementUnproven);
    }
    require(
        unsafe { droidloom_factory_context() } == 0
            && unsafe { libc::syscall(libc::SYS_gettid) } == unsafe { libc::getpid() } as i64,
        "Calendar helpers require the original factory main thread",
    )?;
    context(false)?;
    let status = String::from_utf8(proc_body(c"/proc/self/status", 8192)?).map_err(external)?;
    let threads: Vec<_> = status
        .lines()
        .filter_map(|x| x.strip_prefix("Threads:"))
        .collect();
    require(
        threads.len() == 1 && threads[0].trim() == "1",
        "Calendar helper fork requires a single-threaded original factory",
    )?;
    super::worker::require_wait_semantics()
}

/// The guard owns one actual direct child; it never accepts a numeric PID.
pub(super) struct Helper {
    child: query_io::Child,
    socket: File,
    owner: File,
    end: Instant,
    phase_end: Instant,
}
impl Helper {
    pub(super) fn socket(&self) -> &File {
        &self.socket
    }
    pub(super) fn owner(&self) -> &File {
        &self.owner
    }
    pub(super) fn pid(&self) -> u32 {
        self.child.pid
    }
    pub(super) fn deadline(&self) -> Instant {
        self.phase_end
    }
    pub(super) fn finish(&mut self) -> Result<(u32, i32, i32)> {
        self.child.finish(self.phase_end)?;
        let (code, status) = self
            .child
            .terminal
            .ok_or(ApplicationError::RetirementUnproven)?;
        require(
            code == libc::CLD_EXITED && status == 0,
            "Calendar helper did not really exit zero",
        )?;
        Ok((self.child.pid, code, status))
    }
    fn retire(&mut self) -> Result<()> {
        if self.child.observe()? {
            return Ok(());
        }
        let fd = self
            .child
            .pidfd
            .as_ref()
            .ok_or(ApplicationError::RetirementUnproven)?
            .as_raw_fd();
        if unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                fd,
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0_u32,
            )
        } != 0
            && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
        {
            return Err(ApplicationError::RetirementUnproven);
        }
        // Cleanup consumes only the existing query end, including failure.
        while !self.child.observe()? {
            crate::production_host_admission::check_observation_before(self.end)?;
            let mut p = libc::pollfd {
                fd,
                events: libc::POLLIN,
                revents: 0,
            };
            let left = self.end.saturating_duration_since(Instant::now());
            if unsafe { libc::poll(&mut p, 1, left.as_millis().clamp(1, 20) as i32) } < 0
                && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted
            {
                return Err(ApplicationError::RetirementUnproven);
            }
        }
        Ok(())
    }
    pub(super) fn failed(&mut self) -> Result<()> {
        if self.retire().is_err() {
            UNRETIRED.store(true, std::sync::atomic::Ordering::Release);
            if let Some(fd) = self.child.pidfd.take() {
                mem::forget(fd);
            }
            return Err(ApplicationError::RetirementUnproven);
        }
        Ok(())
    }
}
impl Drop for Helper {
    fn drop(&mut self) {
        if self.child.terminal.is_none() {
            let _ = self.failed();
        }
    }
}

fn spawn(purpose: Purpose, original_end: Instant) -> Result<Helper> {
    single_factory()?;
    crate::production_host_admission::check_observation_before(original_end)?;
    let phase_end = original_end.min(Instant::now() + LIMIT);
    let (socket, child_socket) = protocol::socketpair()?;
    let child_socket = query_io::above_reserved(&File::from(child_socket))?;
    let stdio = query_io::fixed_stdio()?;
    let raw_owner = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0_u32) };
    if raw_owner < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let owner = unsafe { File::from_raw_fd(raw_owner as RawFd) };
    query_io::alive(&owner)?;
    let filter = query_io::filter(None, matches!(purpose, Purpose::Metadata));
    let program = libc::sock_fprog {
        len: filter.len() as u16,
        filter: filter.as_ptr().cast_mut(),
    };
    let deadline_ns = protocol::monotonic_ns()?
        .checked_add(
            phase_end
                .saturating_duration_since(Instant::now())
                .as_nanos() as u64,
        )
        .ok_or_else(|| reject("Calendar helper deadline overflow"))?;
    let parent = unsafe { libc::getpid() };
    let mut raw_pidfd = -1_i32;
    let args = super::worker::CloneArgs {
        flags: libc::CLONE_PIDFD as u64,
        pidfd: (&mut raw_pidfd as *mut i32) as u64,
        exit_signal: libc::SIGCHLD as u64,
        ..super::worker::CloneArgs::default()
    };
    let mut mask = super::worker::SignalMask::block()?;
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
    if pid < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if pid == 0 {
        // No Rust allocation occurs until this async-signal-safe fixed C
        // boundary has closed every inherited descriptor except 0..3 and
        // removed capabilities. The parent was proved single-threaded.
        if unsafe {
            droidloom_factory_calendar_bootstrap(
                purpose as u32,
                parent,
                child_socket.as_raw_fd(),
                stdio.as_raw_fd(),
                deadline_ns,
                &program,
            )
        } != 0
        {
            unsafe {
                libc::_exit(125);
            }
        }
        let result = match purpose {
            Purpose::Stdio => query_io::calendar_creator_entry(phase_end),
            Purpose::Metadata => super::metadata_observer::calendar_factory_entry(phase_end),
        };
        unsafe {
            libc::_exit(if result.is_ok() { 0 } else { 125 });
        }
    }
    if raw_pidfd < 0 {
        UNRETIRED.store(true, std::sync::atomic::Ordering::Release);
        return Err(ApplicationError::RetirementUnproven);
    }
    let mut helper = Helper {
        child: query_io::Child {
            pid: pid as u32,
            pidfd: Some(unsafe { File::from_raw_fd(raw_pidfd) }),
            terminal: None,
        },
        socket: File::from(socket),
        owner,
        end: original_end,
        phase_end,
    };
    drop(child_socket);
    let verified = (|| -> Result<()> {
        mask.restore()?;
        let actual = query_io::pidfd_info(helper.child.pidfd.as_ref().unwrap())?;
        require(
            actual.pid == helper.child.pid
                && actual.ppid == parent as u32
                && actual.pid != parent as u32,
            "Calendar helper is not its owned direct child",
        )?;
        context(false)?;
        Ok(crate::production_host_admission::check_observation_before(
            phase_end,
        )?)
    })();
    if let Err(error) = verified {
        helper.failed()?;
        return Err(error);
    }
    Ok(helper)
}
pub(super) fn spawn_stdio(end: Instant) -> Result<Helper> {
    spawn(Purpose::Stdio, end)
}
pub(super) fn spawn_metadata(end: Instant) -> Result<Helper> {
    spawn(Purpose::Metadata, end)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn calendar_factory_helpers_reject_non_factory_before_clone() {
        let end = Instant::now() + Duration::from_secs(1);
        assert!(spawn_stdio(end).is_err());
        assert!(spawn_metadata(end).is_err());
        assert!(context(false).is_err());
        assert!(context(true).is_err());
    }
}
