//! Fixed AppArmor stack-on-exec action in the original raw Android PID 1.
//!
//! The caller has already passed the independent Android capability gate.
//! This only arms the fixed additional profile; it does not replace the
//! broker profile, relax NNP, change SELinux, or authorize execution. The
//! parent must observe the actual complete stack after original-init exec.
//! No path, profile, command, FD or label is supplied in a control packet.

use std::ffi::CStr;
use std::os::fd::RawFd;

const PROC_MAGIC: libc::c_long = 0x9fa0;
const BROKER: &[u8] = b"droidloom-production-broker (enforce)\n";
const ANDROID_PENDING: &[u8] = b"droidloom-production-android (enforce)\n";
const STACK: &[u8] = b"stack droidloom-production-android";
const ACTION_NS: u64 = 3_000_000_000;
type Result<T> = std::result::Result<T, i32>;

unsafe fn errno() -> i32 {
    unsafe { *libc::__errno_location() }
}

unsafe fn now() -> Result<u64> {
    let mut value: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_clock_gettime, libc::CLOCK_MONOTONIC, &mut value) } != 0 {
        return Err(unsafe { errno() });
    }
    if value.tv_sec < 0 || !(0..1_000_000_000).contains(&value.tv_nsec) {
        return Err(libc::EPROTO);
    }
    (value.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(value.tv_nsec as u64))
        .ok_or(libc::EOVERFLOW)
}

unsafe fn before(deadline: u64) -> Result<()> {
    if unsafe { now()? } >= deadline {
        return Err(libc::ETIMEDOUT);
    }
    Ok(())
}

unsafe fn proc_node(fd: RawFd, kind: u32) -> Result<()> {
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    let mut node: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut fs) } != 0
        || unsafe { libc::syscall(libc::SYS_fstat, fd, &mut node) } != 0
    {
        return Err(unsafe { errno() });
    }
    if fs.f_type != PROC_MAGIC || node.st_mode & libc::S_IFMT != kind {
        return Err(libc::EPROTO);
    }
    Ok(())
}

unsafe fn opened(parent: RawFd, name: &CStr, flags: i32, deadline: u64) -> Result<RawFd> {
    unsafe {
        before(deadline)?;
    }
    let result = unsafe {
        libc::syscall(
            libc::SYS_openat,
            parent,
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
            0,
        )
    };
    if result < 0 {
        return Err(unsafe { errno() });
    }
    let fd = result as RawFd;
    let checked = unsafe {
        proc_node(
            fd,
            if flags & libc::O_DIRECTORY != 0 {
                libc::S_IFDIR
            } else {
                libc::S_IFREG
            },
        )
        .and_then(|_| before(deadline))
    };
    if let Err(error) = checked {
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
        return Err(error);
    }
    Ok(fd)
}

/// Reading the pending exec attribute with no pending label returns exactly
/// EINVAL on the target AppArmor implementation. Empty bytes or another label
/// are not accepted as an unarmed state. All attributes use the explicit LSM
/// directory, independent of the generic attr/current LSM display order.
unsafe fn label(
    directory: RawFd,
    name: &CStr,
    expected: Option<&[u8]>,
    deadline: u64,
) -> Result<()> {
    let fd = unsafe { opened(directory, name, libc::O_RDONLY, deadline)? };
    let mut bytes = [0_u8; 256];
    let count = unsafe { libc::syscall(libc::SYS_read, fd, bytes.as_mut_ptr(), bytes.len()) };
    let read_errno = if count < 0 { unsafe { errno() } } else { 0 };
    let result = match expected {
        None if count == -1 && read_errno == libc::EINVAL => Ok(()),
        None if count < 0 => Err(read_errno),
        None => Err(libc::EPROTO),
        Some(_) if count < 0 => Err(read_errno),
        Some(value) if count as usize != value.len() || &bytes[..count as usize] != value => {
            Err(libc::EPROTO)
        }
        Some(_) => {
            let count = unsafe { libc::syscall(libc::SYS_read, fd, bytes.as_mut_ptr(), 1) };
            if count < 0 {
                Err(unsafe { errno() })
            } else if count != 0 {
                Err(libc::EPROTO)
            } else {
                Ok(())
            }
        }
    };
    let closed = unsafe { libc::syscall(libc::SYS_close, fd) };
    let close_errno = if closed < 0 { unsafe { errno() } } else { 0 };
    result?;
    if closed != 0 {
        return Err(close_errno);
    }
    unsafe { before(deadline) }
}

unsafe fn credentials() -> Result<()> {
    if unsafe { libc::syscall(libc::SYS_getpid) } != 1
        || unsafe { libc::syscall(libc::SYS_getppid) } != 0
        || unsafe { libc::syscall(libc::SYS_getuid) } != 0
        || unsafe { libc::syscall(libc::SYS_geteuid) } != 0
        || unsafe { libc::syscall(libc::SYS_getgid) } != 0
        || unsafe { libc::syscall(libc::SYS_getegid) } != 0
        || unsafe { libc::syscall(libc::SYS_getgroups, 0, std::ptr::null::<u32>()) } != 0
        || unsafe { libc::syscall(libc::SYS_prctl, libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } != 1
        || unsafe { libc::syscall(libc::SYS_prctl, libc::PR_GET_DUMPABLE, 0, 0, 0, 0) } != 0
    {
        return Err(libc::EPERM);
    }
    let mut death = 0_i32;
    if unsafe { libc::syscall(libc::SYS_prctl, libc::PR_GET_PDEATHSIG, &mut death, 0, 0, 0) } != 0 {
        return Err(unsafe { errno() });
    }
    if death != libc::SIGKILL {
        return Err(libc::EPROTO);
    }
    Ok(())
}

/// Allocation-free and current-task only. The original raw child owns every
/// descriptor opened here; all are closed before ExecArmed. A rejected action
/// leaves the existing failure/whole-tree retirement path in control.
///
/// This is a pending action, not proof of an actual MAC transition or of
/// post-exec PDEATHSIG: AppArmor clears that signal on a label-changing exec.
pub(super) unsafe fn arm_android_stack() -> i32 {
    if let Err(error) = unsafe { credentials() } {
        return error;
    }
    let deadline =
        match unsafe { now() }.and_then(|now| now.checked_add(ACTION_NS).ok_or(libc::EOVERFLOW)) {
            Ok(value) => value,
            Err(error) => return error,
        };
    let mut held = [-1; 4];
    let result = (|| -> Result<()> {
        held[0] = unsafe {
            opened(
                libc::AT_FDCWD,
                c"/proc",
                libc::O_PATH | libc::O_DIRECTORY,
                deadline,
            )?
        };
        let mut own_pid = [0_u8; 16];
        let count = unsafe {
            libc::syscall(
                libc::SYS_readlinkat,
                held[0],
                c"self".as_ptr(),
                own_pid.as_mut_ptr(),
                own_pid.len(),
            )
        };
        if count < 0 {
            return Err(unsafe { errno() });
        }
        if count != 1 || own_pid[0] != b'1' {
            return Err(libc::EPROTO);
        }
        // The constant 1 is validated as this current task in its actually
        // mounted proc instance. No externally supplied numeric PID is opened.
        held[1] = unsafe { opened(held[0], c"1", libc::O_PATH | libc::O_DIRECTORY, deadline)? };
        held[2] = unsafe { opened(held[1], c"attr", libc::O_PATH | libc::O_DIRECTORY, deadline)? };
        held[3] = unsafe {
            opened(
                held[2],
                c"apparmor",
                libc::O_PATH | libc::O_DIRECTORY,
                deadline,
            )?
        };
        unsafe {
            label(held[3], c"current", Some(BROKER), deadline)?;
            label(held[3], c"exec", None, deadline)?;
        }
        let fd = unsafe { opened(held[3], c"exec", libc::O_WRONLY, deadline)? };
        // One complete kernel command. A partial or interrupted write is
        // failure, never retried as a second authority-changing operation.
        let written = unsafe { libc::syscall(libc::SYS_write, fd, STACK.as_ptr(), STACK.len()) };
        let write_errno = if written < 0 { unsafe { errno() } } else { 0 };
        let closed = unsafe { libc::syscall(libc::SYS_close, fd) };
        let close_errno = if closed < 0 { unsafe { errno() } } else { 0 };
        if written < 0 {
            return Err(write_errno);
        }
        if written as usize != STACK.len() {
            return Err(libc::EPROTO);
        }
        if closed != 0 {
            return Err(close_errno);
        }
        unsafe {
            before(deadline)?;
            label(held[3], c"current", Some(BROKER), deadline)?;
            // ctx->onexec stores the target profile alone. Only after exec
            // does the kernel merge it with the retained broker profile.
            label(held[3], c"exec", Some(ANDROID_PENDING), deadline)?;
            credentials()?;
            before(deadline)
        }
    })();
    let mut close_errno = 0;
    for fd in held.into_iter().rev().filter(|fd| *fd >= 0) {
        if unsafe { libc::syscall(libc::SYS_close, fd) } != 0 && close_errno == 0 {
            close_errno = unsafe { errno() };
        }
    }
    match result {
        Err(error) => error,
        Ok(()) if close_errno != 0 => close_errno,
        Ok(()) => match unsafe { before(deadline) } {
            Ok(()) => 0,
            Err(error) => error,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn android_stack_action_rejects_non_init_before_any_mutation() {
        assert_ne!(unsafe { libc::getpid() }, 1);
        let nnp = unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) };
        let dumpable = unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) };
        assert_eq!(unsafe { arm_android_stack() }, libc::EPERM);
        assert_eq!(
            unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) },
            nnp
        );
        assert_eq!(
            unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) },
            dumpable
        );
    }
}
