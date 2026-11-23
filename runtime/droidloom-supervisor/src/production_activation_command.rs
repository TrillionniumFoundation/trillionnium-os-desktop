//! Actual ownership of a short original activation command.
//!
//! This module provides an execution observation, never Android admission or
//! APEX activation. The caller must already own the admitted guest execution
//! context and keep its cgroup, namespace and input custody until retirement.
//! It is deliberately unsuitable for adopting a process created by stock init:
//! the PIDFD is returned atomically by this module's own clone operation and
//! only its original parent consumes waitid(P_PIDFD).

use std::ffi::CStr;
use std::fs::File;
use std::io;
use std::marker::PhantomData;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::{FileExt, MetadataExt};
use std::rc::Rc;
use std::time::{Duration, Instant};

use crate::production_activation_protocol::{
    PIDFD_GET_INFO, PIDFD_INFO_EXIT, PidfdInfo, raw_wait_status,
};
use sha2::{Digest, Sha256};
use thiserror::Error;

const OUTPUT_LIMIT: usize = 256 * 1024;
const RETIREMENT_LIMIT: Duration = Duration::from_secs(3);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum ProgramRole {
    Apexd,
    Linkerconfig,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum ShortStep {
    ApexBootstrap,
    LinkerBootstrap,
    LinkerDefault,
    ApexSnapshotDe,
}

impl ShortStep {
    fn role(self) -> ProgramRole {
        match self {
            Self::ApexBootstrap | Self::ApexSnapshotDe => ProgramRole::Apexd,
            Self::LinkerBootstrap | Self::LinkerDefault => ProgramRole::Linkerconfig,
        }
    }

    fn arguments(self) -> &'static [&'static CStr] {
        match self {
            Self::ApexBootstrap => &[c"/system/bin/apexd", c"--bootstrap"],
            Self::ApexSnapshotDe => &[c"/system/bin/apexd", c"--snapshotde"],
            Self::LinkerBootstrap | Self::LinkerDefault => {
                &[c"/system/bin/linkerconfig", c"--target", c"/linkerconfig"]
            }
        }
    }
}

#[derive(Debug, Error)]
pub(super) enum CommandError {
    #[error("activation command input: {0}")]
    Input(&'static str),
    #[error("activation command I/O: {0}")]
    Io(#[from] io::Error),
    #[error("activation command exceeded its original absolute deadline")]
    Deadline,
    #[error("activation command exec failed with errno {0}")]
    Exec(i32),
    #[error("activation command output exceeded its fixed bound")]
    OutputLimit,
    #[error("activation command exited with code {code}, status {status}")]
    Exit { code: i32, status: i32 },
    #[error("activation command original PIDFD retirement is unproven")]
    Retirement,
}

type Result<T> = std::result::Result<T, CommandError>;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct FileIdentity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    bytes: u64,
    mtime: i64,
    mtime_nsec: i64,
    ctime: i64,
    ctime_nsec: i64,
}

impl FileIdentity {
    fn of(file: &File) -> io::Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            dev: m.dev(),
            ino: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            nlink: m.nlink(),
            bytes: m.size(),
            mtime: m.mtime(),
            mtime_nsec: m.mtime_nsec(),
            ctime: m.ctime(),
            ctime_nsec: m.ctime_nsec(),
        })
    }
}

/// A held input, not permission to execute it. The declaration must already be
/// selected from the same original cohort by the caller's sealed-input owner.
/// Descriptor provenance is retained; a pathname is never reopened for exec.
pub(super) struct OriginalProgram {
    file: File,
    identity: FileIdentity,
    role: ProgramRole,
    digest: [u8; 32],
}

impl OriginalProgram {
    pub(super) fn seal(
        file: File,
        role: ProgramRole,
        bytes: u64,
        digest: [u8; 32],
    ) -> Result<Self> {
        let identity = FileIdentity::of(&file)?;
        if identity.mode & libc::S_IFMT != libc::S_IFREG
            || identity.uid != 0
            || identity.gid != 0
            || identity.nlink != 1
            || identity.mode & 0o6022 != 0
            || identity.mode & 0o111 == 0
            || !(64..=32 * 1024 * 1024).contains(&bytes)
            || identity.bytes != bytes
        {
            return Err(CommandError::Input(
                "original executable owner/type/mode/size",
            ));
        }
        let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
        if unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        if flags.f_flag & (libc::ST_RDONLY | libc::ST_NOSUID | libc::ST_NODEV)
            != (libc::ST_RDONLY | libc::ST_NOSUID | libc::ST_NODEV)
            || flags.f_flag & libc::ST_NOEXEC != 0
        {
            return Err(CommandError::Input("original executable mount policy"));
        }
        Self::seal_bytes(file, identity, role, digest)
    }

    fn seal_bytes(
        file: File,
        identity: FileIdentity,
        role: ProgramRole,
        digest: [u8; 32],
    ) -> Result<Self> {
        let mut header = [0_u8; 64];
        file.read_exact_at(&mut header, 0)?;
        if &header[..7] != b"\x7fELF\x02\x01\x01"
            || ![2, 3].contains(&u16::from_le_bytes([header[16], header[17]]))
            || u16::from_le_bytes([header[18], header[19]]) != 62
        {
            return Err(CommandError::Input("original executable ELF architecture"));
        }
        let mut hash = Sha256::new();
        let mut offset = 0;
        let mut body = [0_u8; 64 * 1024];
        while offset < identity.bytes {
            let n = usize::try_from((identity.bytes - offset).min(body.len() as u64)).unwrap();
            file.read_exact_at(&mut body[..n], offset)?;
            hash.update(&body[..n]);
            offset += n as u64;
        }
        if <[u8; 32]>::from(hash.finalize()) != digest || FileIdentity::of(&file)? != identity {
            return Err(CommandError::Input(
                "original executable digest or identity changed",
            ));
        }
        Ok(Self {
            file,
            identity,
            role,
            digest,
        })
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        if FileIdentity::of(&self.file)? != self.identity {
            return Err(CommandError::Input("held original executable changed"));
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ReapedExit {
    code: i32,
    status: i32,
}

fn kernel_info(pidfd: &OwnedFd) -> Result<PidfdInfo> {
    let mut info = PidfdInfo::request_exit();
    if unsafe {
        libc::ioctl(
            pidfd.as_raw_fd(),
            PIDFD_GET_INFO as libc::c_ulong,
            &mut info,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    Ok(info)
}

fn verify_final_kernel_exit(pidfd: &OwnedFd, exit: ReapedExit) -> Result<()> {
    let info = kernel_info(pidfd)?;
    if info.mask & PIDFD_INFO_EXIT == 0 {
        return Err(CommandError::Input(
            "original PIDFD has no final kernel exit record",
        ));
    }
    if raw_wait_status(exit.code, exit.status) != Some(info.exit_code) {
        return Err(CommandError::Input(
            "original PIDFD kernel exit differs from actual waitid",
        ));
    }
    Ok(())
}

/// Cannot be created from an exit-code record, PID or saved PIDFD number. It
/// retains the exact already-reaped PIDFD and original executable descriptor.
/// It is not sufficient evidence of either APEX activation or linker outputs.
pub(super) struct CompletedCommand {
    owner: CommandOwner,
    program: OriginalProgram,
    step: ShortStep,
    output: Vec<u8>,
}

impl CompletedCommand {
    pub(super) fn revalidate(&self, step: ShortStep) -> Result<()> {
        self.owner.same_thread()?;
        if self.step != step
            || self.owner.reaped
                != Some(ReapedExit {
                    code: libc::CLD_EXITED,
                    status: 0,
                })
            || pidfd_events(&self.owner.pidfd)? & libc::POLLHUP == 0
        {
            return Err(CommandError::Retirement);
        }
        verify_final_kernel_exit(&self.owner.pidfd, self.owner.reaped.unwrap())?;
        self.program.revalidate()
    }

    pub(super) fn output(&self) -> &[u8] {
        &self.output
    }

    pub(super) fn original_digest(&self) -> [u8; 32] {
        self.program.digest
    }
}

/// The error remains distinct from retirement. Even successful cleanup cannot
/// turn a failed exec, deadline, nonzero exit or input observation into success.
pub(super) struct CommandFailure {
    pub(super) error: CommandError,
    // Only this directly owned leader has been reaped. The surrounding
    // provider must retire its entire owned tree after every helper failure.
    pub(super) leader_reaped: bool,
    // If retirement fails, custody remains here instead of being reduced to
    // a serializable "cleanup attempted" declaration.
    owner: Option<CommandOwner>,
}

struct CommandOwner {
    pidfd: OwnedFd,
    creator_tid: i32,
    pid: i32,
    reaped: Option<ReapedExit>,
    _same_thread: PhantomData<Rc<()>>,
}

fn pipe() -> io::Result<(OwnedFd, OwnedFd)> {
    let mut fds = [-1; 2];
    if unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) })
}

fn pidfd_events(pidfd: &OwnedFd) -> io::Result<i16> {
    let mut event = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    loop {
        let rc = unsafe { libc::poll(&mut event, 1, 0) };
        if rc >= 0 {
            if event.revents & (libc::POLLNVAL | libc::POLLERR) != 0 {
                return Err(io::Error::from_raw_os_error(libc::EBADF));
            }
            return Ok(event.revents);
        }
        let e = io::Error::last_os_error();
        if e.kind() != io::ErrorKind::Interrupted {
            return Err(e);
        }
    }
}

impl CommandOwner {
    fn same_thread(&self) -> Result<()> {
        if unsafe { libc::syscall(libc::SYS_gettid) } != libc::c_long::from(self.creator_tid) {
            return Err(CommandError::Input(
                "original activation parent thread changed",
            ));
        }
        Ok(())
    }

    fn reap(&mut self) -> Result<ReapedExit> {
        self.same_thread()?;
        if let Some(exit) = self.reaped {
            return Ok(exit);
        }
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        if unsafe { info.si_pid() } != self.pid
            || ![libc::CLD_EXITED, libc::CLD_KILLED, libc::CLD_DUMPED].contains(&info.si_code)
        {
            return Err(CommandError::Retirement);
        }
        let exit = ReapedExit {
            code: info.si_code,
            status: unsafe { info.si_status() },
        };
        self.reaped = Some(exit);
        if pidfd_events(&self.pidfd)? & libc::POLLHUP == 0 {
            return Err(CommandError::Retirement);
        }
        verify_final_kernel_exit(&self.pidfd, exit)?;
        Ok(exit)
    }

    fn retire_until(&mut self, deadline: Instant) -> Result<()> {
        self.same_thread()?;
        if self.reaped.is_some() {
            return if pidfd_events(&self.pidfd)? & libc::POLLHUP != 0 {
                Ok(())
            } else {
                Err(CommandError::Retirement)
            };
        }
        let rc = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0_u32,
            )
        };
        if rc != 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
            return Err(io::Error::last_os_error().into());
        }
        loop {
            if Instant::now() >= deadline {
                return Err(CommandError::Retirement);
            }
            let mut event = libc::pollfd {
                fd: self.pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let remaining = deadline.saturating_duration_since(Instant::now());
            let rc = unsafe {
                libc::poll(
                    &mut event,
                    1,
                    remaining.as_millis().max(1).min(i32::MAX as u128) as i32,
                )
            };
            if Instant::now() >= deadline {
                return Err(CommandError::Retirement);
            }
            if rc < 0 {
                let error = io::Error::last_os_error();
                if error.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(error.into());
            }
            if event.revents & (libc::POLLNVAL | libc::POLLERR) != 0 {
                return Err(CommandError::Retirement);
            }
            if event.revents & libc::POLLIN != 0 {
                self.reap()?;
                return Ok(());
            }
        }
    }
}

impl Drop for CommandOwner {
    fn drop(&mut self) {
        if self.reaped.is_none()
            && self
                .retire_until(Instant::now() + RETIREMENT_LIMIT)
                .is_err()
        {
            // A diagnostic Drop cannot certify retirement. Retain the original
            // kernel handle if its owning error is itself discarded.
            if let Ok(held) = self.pidfd.try_clone() {
                std::mem::forget(held);
            }
        }
    }
}

fn drain(fd: &OwnedFd, out: &mut Vec<u8>, limit: usize) -> Result<bool> {
    let mut buffer = [0_u8; 4096];
    loop {
        let n = unsafe { libc::read(fd.as_raw_fd(), buffer.as_mut_ptr().cast(), buffer.len()) };
        if n == 0 {
            return Ok(true);
        }
        if n > 0 {
            let n = n as usize;
            if out.len().checked_add(n).is_none_or(|sum| sum > limit) {
                return Err(CommandError::OutputLimit);
            }
            out.extend_from_slice(&buffer[..n]);
            continue;
        }
        let e = io::Error::last_os_error();
        if e.kind() == io::ErrorKind::Interrupted {
            continue;
        }
        if e.kind() == io::ErrorKind::WouldBlock {
            return Ok(false);
        }
        return Err(e.into());
    }
}

/// Run only a fixed original short command. Namespace/cgroup admission is a
/// separate precondition owned by the surrounding activation provider; this
/// result cannot create an execution or Ready capability.
pub(super) fn run(
    program: OriginalProgram,
    step: ShortStep,
    deadline: Instant,
) -> std::result::Result<CompletedCommand, CommandFailure> {
    if program.role != step.role() {
        return Err(CommandFailure {
            error: CommandError::Input("original program role differs"),
            leader_reaped: true,
            owner: None,
        });
    }
    let args = step
        .arguments()
        .iter()
        .map(|arg| arg.as_ptr())
        .chain([std::ptr::null()])
        .collect::<Vec<_>>();
    let env = [
        c"PATH=/system/bin".as_ptr(),
        c"ANDROID_ROOT=/system".as_ptr(),
        c"ANDROID_DATA=/data".as_ptr(),
        std::ptr::null(),
    ];
    run_held(program, step, &args, &env, deadline)
}

fn run_held(
    program: OriginalProgram,
    step: ShortStep,
    args: &[*const libc::c_char],
    env: &[*const libc::c_char],
    deadline: Instant,
) -> std::result::Result<CompletedCommand, CommandFailure> {
    let prepare = || -> Result<_> {
        if Instant::now() >= deadline {
            return Err(CommandError::Deadline);
        }
        program.revalidate()?;
        let (errors, error_writer) = pipe()?;
        let (diagnostics, diagnostic_writer) = pipe()?;
        let input = File::open("/dev/null")?;
        let writer_flags = unsafe { libc::fcntl(diagnostic_writer.as_raw_fd(), libc::F_GETFL) };
        if writer_flags < 0
            || unsafe {
                libc::fcntl(
                    diagnostic_writer.as_raw_fd(),
                    libc::F_SETFL,
                    writer_flags & !libc::O_NONBLOCK,
                )
            } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        Ok((errors, error_writer, diagnostics, diagnostic_writer, input))
    };
    let (errors, error_writer, diagnostics, diagnostic_writer, input) = match prepare() {
        Ok(value) => value,
        Err(error) => {
            return Err(CommandFailure {
                error,
                leader_reaped: true,
                owner: None,
            });
        }
    };
    if [
        program.file.as_raw_fd(),
        errors.as_raw_fd(),
        error_writer.as_raw_fd(),
        diagnostics.as_raw_fd(),
        diagnostic_writer.as_raw_fd(),
        input.as_raw_fd(),
    ]
    .iter()
    .any(|fd| *fd < 3)
    {
        return Err(CommandFailure {
            error: CommandError::Input("activation standard descriptors absent"),
            leader_reaped: true,
            owner: None,
        });
    }
    if Instant::now() >= deadline {
        return Err(CommandFailure {
            error: CommandError::Deadline,
            leader_reaped: true,
            owner: None,
        });
    }
    let parent = unsafe { libc::getpid() };
    let mut pidfd = -1_i32;
    let clone_args = [
        libc::CLONE_PIDFD as u64,
        (&mut pidfd as *mut i32) as u64,
        0,
        0,
        libc::SIGCHLD as u64,
        0,
        0,
        0,
    ];
    let mut pid = unsafe { libc::syscall(libc::SYS_clone3, clone_args.as_ptr(), 64_usize) };
    if pid == -1 && io::Error::last_os_error().raw_os_error() == Some(libc::ENOSYS) {
        // The fixed runtime seccomp filter returns ENOSYS for clone3. Legacy
        // clone(CLONE_PIDFD) still obtains the handle atomically, without a
        // later pidfd_open lookup or any namespace-creation flags.
        pid = unsafe {
            libc::syscall(
                libc::SYS_clone,
                libc::CLONE_PIDFD | libc::SIGCHLD,
                0_usize,
                &mut pidfd,
                0_usize,
                0_usize,
            )
        };
    }
    if pid == -1 {
        return Err(CommandFailure {
            error: io::Error::last_os_error().into(),
            leader_reaped: true,
            owner: None,
        });
    }
    if pid == 0 {
        // Only raw async-signal-safe syscalls after clone in a threaded host.
        unsafe {
            let mut error = 0_i32;
            if libc::syscall(
                libc::SYS_prctl,
                libc::PR_SET_PDEATHSIG,
                libc::SIGKILL,
                0,
                0,
                0,
            ) != 0
                || libc::syscall(libc::SYS_getppid) != libc::c_long::from(parent)
                || libc::syscall(libc::SYS_prctl, libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
            {
                error = libc::EPERM;
            }
            for (source, target) in [
                (input.as_raw_fd(), 0),
                (diagnostic_writer.as_raw_fd(), 1),
                (diagnostic_writer.as_raw_fd(), 2),
            ] {
                if error == 0 && libc::syscall(libc::SYS_dup3, source, target, 0) < 0 {
                    error = *libc::__errno_location();
                }
            }
            if error == 0 && libc::syscall(libc::SYS_close_range, 3_u32, u32::MAX, 4_u32) != 0 {
                error = *libc::__errno_location();
            }
            if error == 0 {
                libc::syscall(
                    libc::SYS_execveat,
                    program.file.as_raw_fd(),
                    c"".as_ptr(),
                    args.as_ptr(),
                    env.as_ptr(),
                    0x1000_u32,
                );
                error = *libc::__errno_location();
            }
            libc::syscall(
                libc::SYS_write,
                error_writer.as_raw_fd(),
                &error as *const i32,
                4_usize,
            );
            libc::syscall(libc::SYS_exit_group, 127);
            std::hint::unreachable_unchecked();
        }
    }
    // CLONE_PIDFD success without a handle is a kernel-contract violation. No
    // numeric-PID signaling or recovery constructor is introduced here.
    assert!(pidfd >= 0, "atomic CLONE_PIDFD returned no descriptor");
    let mut owner = CommandOwner {
        pidfd: unsafe { OwnedFd::from_raw_fd(pidfd) },
        creator_tid: unsafe { libc::syscall(libc::SYS_gettid) } as i32,
        pid: pid as i32,
        reaped: None,
        _same_thread: PhantomData,
    };
    drop(error_writer);
    drop(diagnostic_writer);
    drop(input);
    let observed = (|| -> Result<Vec<u8>> {
        let mut exec_error = Vec::new();
        let mut output = Vec::new();
        loop {
            if Instant::now() >= deadline {
                return Err(CommandError::Deadline);
            }
            let exec_closed = drain(&errors, &mut exec_error, 4)?;
            let diagnostics_closed = drain(&diagnostics, &mut output, OUTPUT_LIMIT)?;
            if exec_error.len() == 4 {
                let errno = i32::from_ne_bytes(exec_error[..4].try_into().unwrap());
                return if (1..4096).contains(&errno) {
                    Err(CommandError::Exec(errno))
                } else {
                    Err(CommandError::Input("invalid raw exec errno"))
                };
            }
            if exec_closed && !exec_error.is_empty() {
                return Err(CommandError::Input("short raw exec error record"));
            }
            if pidfd_events(&owner.pidfd)? & libc::POLLIN != 0 {
                let exit = owner.reap()?;
                if Instant::now() >= deadline {
                    return Err(CommandError::Deadline);
                }
                if exit
                    != (ReapedExit {
                        code: libc::CLD_EXITED,
                        status: 0,
                    })
                {
                    return Err(CommandError::Exit {
                        code: exit.code,
                        status: exit.status,
                    });
                }
                if !exec_closed || !diagnostics_closed {
                    // Re-read once after reap: buffered bytes/EOF may become
                    // visible in the same scheduler turn as PIDFD readiness.
                    if !drain(&errors, &mut exec_error, 4)?
                        || !exec_error.is_empty()
                        || !drain(&diagnostics, &mut output, OUTPUT_LIMIT)?
                    {
                        return Err(CommandError::Input("short helper left open output custody"));
                    }
                }
                program.revalidate()?;
                if Instant::now() >= deadline {
                    return Err(CommandError::Deadline);
                }
                return Ok(output);
            }
            let mut fds = [
                libc::pollfd {
                    fd: owner.pidfd.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: if exec_closed { -1 } else { errors.as_raw_fd() },
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: if diagnostics_closed {
                        -1
                    } else {
                        diagnostics.as_raw_fd()
                    },
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Err(CommandError::Deadline);
            }
            let rc = unsafe {
                libc::poll(
                    fds.as_mut_ptr(),
                    fds.len() as libc::nfds_t,
                    remaining.as_millis().max(1).min(i32::MAX as u128) as i32,
                )
            };
            if Instant::now() >= deadline {
                return Err(CommandError::Deadline);
            }
            if rc < 0 {
                let error = io::Error::last_os_error();
                if error.kind() != io::ErrorKind::Interrupted {
                    return Err(error.into());
                }
            }
            if fds.iter().any(|fd| fd.revents & libc::POLLNVAL != 0) {
                return Err(CommandError::Input(
                    "activation command descriptor became invalid",
                ));
            }
        }
    })();
    match observed {
        Ok(output) => Ok(CompletedCommand {
            owner,
            program,
            step,
            output,
        }),
        Err(error) => {
            let leader_reaped = owner
                .retire_until(Instant::now() + RETIREMENT_LIMIT)
                .is_ok();
            Err(CommandFailure {
                error,
                leader_reaped,
                owner: Some(owner),
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::CString;

    const CONTROL: &str = "DROIDLOOM_ACTIVATION_OWNED_COMMAND_CONTROL";
    const THIS: &str = "production_activation_command::tests::production_activation_short_helper_uses_actual_exec_wait_and_retirement";

    fn wait_ready(owner: &CommandOwner) {
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            assert!(Instant::now() < deadline);
            let mut event = libc::pollfd {
                fd: owner.pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let millis = deadline
                .saturating_duration_since(Instant::now())
                .as_millis()
                .max(1) as i32;
            let n = unsafe { libc::poll(&mut event, 1, millis) };
            assert!(Instant::now() < deadline);
            if n < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            assert_eq!(n, 1);
            assert_eq!(event.revents & (libc::POLLNVAL | libc::POLLERR), 0);
            assert_ne!(event.revents & libc::POLLIN, 0);
            return;
        }
    }

    fn observe_as_nonparent(target: &OwnedFd, expected_raw: i32) {
        let mut pidfd = -1_i32;
        let args = [
            libc::CLONE_PIDFD as u64,
            (&mut pidfd as *mut i32) as u64,
            0,
            0,
            libc::SIGCHLD as u64,
            0,
            0,
            0,
        ];
        let pid = unsafe { libc::syscall(libc::SYS_clone3, args.as_ptr(), 64_usize) };
        assert!(pid >= 0, "{}", io::Error::last_os_error());
        if pid == 0 {
            // A real sibling process, not the target's parent. It can query
            // the inherited original PIDFD but cannot consume waitid on it.
            unsafe {
                let mut info = PidfdInfo::request_exit();
                let query = libc::syscall(
                    libc::SYS_ioctl,
                    target.as_raw_fd(),
                    PIDFD_GET_INFO as libc::c_ulong,
                    &mut info,
                );
                let mut waited: libc::siginfo_t = std::mem::zeroed();
                let wait = libc::syscall(
                    libc::SYS_waitid,
                    libc::P_PIDFD,
                    target.as_raw_fd() as u32,
                    &mut waited,
                    libc::WEXITED | libc::WNOHANG,
                    std::ptr::null_mut::<libc::rusage>(),
                );
                let no_wait_right = wait == -1 && *libc::__errno_location() == libc::ECHILD;
                let mut event = libc::pollfd {
                    fd: target.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                };
                let poll = libc::syscall(libc::SYS_poll, &mut event, 1, 0);
                let valid = query == 0
                    && info.mask & PIDFD_INFO_EXIT != 0
                    && info.exit_code == expected_raw
                    && no_wait_right
                    && poll == 1
                    && event.revents & libc::POLLHUP != 0
                    && event.revents & (libc::POLLERR | libc::POLLNVAL) == 0;
                libc::syscall(libc::SYS_exit_group, if valid { 0 } else { 113 });
                std::hint::unreachable_unchecked();
            }
        }
        assert!(pidfd >= 0);
        let mut observer = CommandOwner {
            pidfd: unsafe { OwnedFd::from_raw_fd(pidfd) },
            creator_tid: unsafe { libc::syscall(libc::SYS_gettid) } as i32,
            pid: pid as i32,
            reaped: None,
            _same_thread: PhantomData,
        };
        wait_ready(&observer);
        assert_eq!(
            observer.reap().unwrap(),
            ReapedExit {
                code: libc::CLD_EXITED,
                status: 0
            }
        );
    }

    #[test]
    fn production_activation_kernel_exit_is_absent_at_wnowait_and_observed_by_nonparent_after_reap()
    {
        let mut pidfd = -1_i32;
        let args = [
            libc::CLONE_PIDFD as u64,
            (&mut pidfd as *mut i32) as u64,
            0,
            0,
            libc::SIGCHLD as u64,
            0,
            0,
            0,
        ];
        let pid = unsafe { libc::syscall(libc::SYS_clone3, args.as_ptr(), 64_usize) };
        assert!(pid >= 0, "{}", io::Error::last_os_error());
        if pid == 0 {
            unsafe {
                libc::_exit(17);
            }
        }
        assert!(pidfd >= 0);
        let mut owner = CommandOwner {
            pidfd: unsafe { OwnedFd::from_raw_fd(pidfd) },
            creator_tid: unsafe { libc::syscall(libc::SYS_gettid) } as i32,
            pid: pid as i32,
            reaped: None,
            _same_thread: PhantomData,
        };
        wait_ready(&owner);
        let mut peek: libc::siginfo_t = unsafe { std::mem::zeroed() };
        assert_eq!(
            unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    owner.pidfd.as_raw_fd() as u32,
                    &mut peek,
                    libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
                )
            },
            0
        );
        assert_eq!(unsafe { peek.si_pid() }, pid as i32);
        assert_eq!(
            (peek.si_code, unsafe { peek.si_status() }),
            (libc::CLD_EXITED, 17)
        );
        assert_eq!(kernel_info(&owner.pidfd).unwrap().mask & PIDFD_INFO_EXIT, 0);
        assert!(matches!(
            verify_final_kernel_exit(
                &owner.pidfd,
                ReapedExit {
                    code: libc::CLD_EXITED,
                    status: 0
                }
            ),
            Err(CommandError::Input(
                "original PIDFD has no final kernel exit record"
            ))
        ));
        assert_eq!(
            owner.reap().unwrap(),
            ReapedExit {
                code: libc::CLD_EXITED,
                status: 17
            }
        );
        observe_as_nonparent(&owner.pidfd, 17 << 8);
    }

    fn fixture_program() -> OriginalProgram {
        let file = File::open(std::env::current_exe().unwrap()).unwrap();
        let identity = FileIdentity::of(&file).unwrap();
        let digest =
            Sha256::digest(std::fs::read(std::env::current_exe().unwrap()).unwrap()).into();
        // Test-only input selection. It creates no MAC/preflight/activation
        // capability and is never accepted by the production sealed mount path.
        OriginalProgram::seal_bytes(file, identity, ProgramRole::Linkerconfig, digest).unwrap()
    }

    #[test]
    fn production_activation_short_helper_uses_actual_exec_wait_and_retirement() {
        if let Some(mode) = std::env::var_os(CONTROL) {
            match mode.to_str().unwrap() {
                "success" => {
                    println!("actual owned helper output");
                    return;
                }
                "failure" => unsafe { libc::_exit(17) },
                "blocked" => loop {
                    unsafe {
                        libc::pause();
                    }
                },
                "output" => {
                    use std::io::Write;
                    let mut out = std::io::stdout().lock();
                    for _ in 0..128 {
                        out.write_all(&[b'x'; 4096]).unwrap();
                    }
                    return;
                }
                _ => panic!("unknown actual helper control"),
            }
        }
        for mode in ["success", "failure", "blocked", "output"] {
            let program = fixture_program();
            let args = [
                CString::new("ordinary-owned-helper").unwrap(),
                CString::new("--exact").unwrap(),
                CString::new(THIS).unwrap(),
                CString::new("--nocapture").unwrap(),
                CString::new("--test-threads=1").unwrap(),
            ];
            let argv = args
                .iter()
                .map(|v| v.as_ptr())
                .chain([std::ptr::null()])
                .collect::<Vec<_>>();
            let variable = CString::new(format!("{CONTROL}={mode}")).unwrap();
            let env = [variable.as_ptr(), std::ptr::null()];
            let limit = if mode == "blocked" {
                Duration::from_millis(200)
            } else {
                Duration::from_secs(3)
            };
            let result = run_held(
                program,
                ShortStep::LinkerDefault,
                &argv,
                &env,
                Instant::now() + limit,
            );
            match (mode, result) {
                ("success", Ok(completed)) => {
                    completed.revalidate(ShortStep::LinkerDefault).unwrap();
                    assert!(
                        std::str::from_utf8(completed.output())
                            .unwrap()
                            .contains("actual owned helper output")
                    );
                    assert_ne!(completed.original_digest(), [0; 32]);
                }
                ("failure", Err(failed)) => {
                    assert!(matches!(
                        failed.error,
                        CommandError::Exit {
                            code: libc::CLD_EXITED,
                            status: 17
                        }
                    ));
                    assert!(failed.leader_reaped);
                    assert_eq!(
                        failed.owner.as_ref().unwrap().reaped,
                        Some(ReapedExit {
                            code: libc::CLD_EXITED,
                            status: 17
                        })
                    );
                    observe_as_nonparent(&failed.owner.as_ref().unwrap().pidfd, 17 << 8);
                }
                ("blocked", Err(failed)) => {
                    assert!(matches!(failed.error, CommandError::Deadline));
                    assert!(failed.leader_reaped);
                    assert_eq!(
                        failed.owner.as_ref().unwrap().reaped,
                        Some(ReapedExit {
                            code: libc::CLD_KILLED,
                            status: libc::SIGKILL
                        })
                    );
                    observe_as_nonparent(&failed.owner.as_ref().unwrap().pidfd, libc::SIGKILL);
                }
                ("output", Err(failed)) => {
                    assert!(matches!(failed.error, CommandError::OutputLimit));
                    assert!(failed.leader_reaped);
                }
                (_, Err(failed)) => panic!(
                    "{mode}: {} leader_reaped={}",
                    failed.error, failed.leader_reaped
                ),
                (_, Ok(_)) => panic!("{mode}: unexpected successful original helper"),
            }
        }
    }
}
