//! Fixed pending MAC actions in the original, parked query child.
//!
//! This arms only this current task, before its UID/capability drop. It does
//! not prove execution or a domain transition. The original broker must hold
//! the real TRACEEXEC stop and verify both actual labels before CONT.
//! AppArmor's label-changing exec clears PDEATHSIG; no postexec lifetime
//! guarantee is inferred from that preexec signal.
use crate::production_application::OperationDomain;
use std::ffi::CStr;
use std::os::fd::RawFd;

const BROKER: &[u8] = b"u:r:droidloom_broker:s0";
const AA_BROKER: &[u8] = b"droidloom-production-broker (enforce)\n";
const AA_PENDING: &[u8] = b"droidloom-production-android (enforce)\n";
const AA_STACK: &[u8] = b"stack droidloom-production-android";
type Result<T> = std::result::Result<T, i32>;

/// Replace the bootstrap's host null descriptor with this same owned guest
/// device before any Binder command can inherit stdin. The file is opened
/// while still in broker context, so its FD-use provenance remains broker;
/// its actual inode label is the fixed Android null_device type.
pub(super) unsafe fn guest_stdin(root: RawFd, deadline: u64) -> i32 {
    let result = (|| -> Result<()> {
        unsafe {
            before(deadline)?;
        }
        let dev = unsafe {
            libc::syscall(
                libc::SYS_openat,
                root,
                c"dev".as_ptr(),
                libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0,
            )
        };
        if dev < 0 {
            return Err(unsafe { errno() });
        }
        let dev = dev as RawFd;
        let fd = unsafe {
            libc::syscall(
                libc::SYS_openat,
                dev,
                c"null".as_ptr(),
                libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
                0,
            )
        };
        let saved = unsafe { errno() };
        unsafe {
            libc::syscall(libc::SYS_close, dev);
        }
        if fd < 0 {
            return Err(saved);
        }
        let fd = fd as RawFd;
        let checked = (|| -> Result<()> {
            let mut node: libc::stat = unsafe { std::mem::zeroed() };
            if unsafe { libc::syscall(libc::SYS_fstat, fd, &mut node) } != 0 {
                return Err(unsafe { errno() });
            }
            if node.st_mode != libc::S_IFCHR | 0o666
                || node.st_rdev != 259
                || node.st_uid != 0
                || node.st_gid != 0
            {
                return Err(libc::EPROTO);
            }
            let expected = b"u:object_r:null_device:s0\0";
            let mut label = [0_u8; 64];
            let size = unsafe {
                libc::syscall(
                    libc::SYS_fgetxattr,
                    fd,
                    c"security.selinux".as_ptr(),
                    label.as_mut_ptr(),
                    label.len(),
                )
            };
            if size < 0 {
                return Err(unsafe { errno() });
            }
            if size != expected.len() as libc::c_long {
                return Err(libc::EPROTO);
            }
            let mut at = 0;
            while at < expected.len() {
                if label[at] != expected[at] {
                    return Err(libc::EPROTO);
                }
                at += 1;
            }
            if unsafe { libc::syscall(libc::SYS_dup2, fd, 0) } != 0 {
                return Err(unsafe { errno() });
            }
            let mut actual: libc::stat = unsafe { std::mem::zeroed() };
            if unsafe { libc::syscall(libc::SYS_fstat, 0, &mut actual) } != 0 {
                return Err(unsafe { errno() });
            }
            if node.st_dev != actual.st_dev
                || node.st_ino != actual.st_ino
                || actual.st_rdev != 259
                || actual.st_mode != node.st_mode
            {
                return Err(libc::EPROTO);
            }
            unsafe { before(deadline) }
        })();
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
        checked
    })();
    match result {
        Ok(()) => 0,
        Err(error) => error,
    }
}

unsafe fn errno() -> i32 {
    unsafe { *libc::__errno_location() }
}

unsafe fn before(deadline: u64) -> Result<()> {
    let mut value: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_clock_gettime, libc::CLOCK_MONOTONIC, &mut value) } != 0 {
        return Err(unsafe { errno() });
    }
    if value.tv_sec < 0 || !(0..1_000_000_000).contains(&value.tv_nsec) {
        return Err(libc::EPROTO);
    }
    let now = (value.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(value.tv_nsec as u64))
        .ok_or(libc::EOVERFLOW)?;
    if now >= deadline {
        return Err(libc::ETIMEDOUT);
    }
    Ok(())
}

unsafe fn credentials() -> Result<()> {
    // The query is a CLONE_PARENT child inside the original Android PID
    // namespace. Its broker parent is outside that namespace, hence PPid=0.
    // It cannot be PID 1 or an ordinary initial-namespace host invocation.
    if unsafe { libc::syscall(libc::SYS_getpid) } <= 1
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
    Ok(())
}

unsafe fn opened(parent: RawFd, name: &CStr, flags: i32, deadline: u64) -> Result<RawFd> {
    unsafe {
        before(deadline)?;
    }
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat,
            parent,
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
            0,
        )
    };
    if fd < 0 {
        return Err(unsafe { errno() });
    }
    let fd = fd as RawFd;
    let checked = (|| -> Result<()> {
        let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
        let mut node: libc::stat = unsafe { std::mem::zeroed() };
        if unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut fs) } != 0
            || unsafe { libc::syscall(libc::SYS_fstat, fd, &mut node) } != 0
        {
            return Err(unsafe { errno() });
        }
        let kind = if flags & libc::O_DIRECTORY != 0 {
            libc::S_IFDIR
        } else {
            libc::S_IFREG
        };
        if fs.f_type != 0x9fa0 || node.st_mode & libc::S_IFMT != kind {
            return Err(libc::EPROTO);
        }
        unsafe { before(deadline) }
    })();
    if let Err(error) = checked {
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
        return Err(error);
    }
    Ok(fd)
}

#[derive(Clone, Copy)]
enum Expected<'a> {
    Selinux(&'a [u8]),
    Exact(&'a [u8]),
    Empty,
    AppArmorUnarmed,
}

unsafe fn label(
    directory: RawFd,
    name: &CStr,
    expected: Expected<'_>,
    deadline: u64,
) -> Result<()> {
    let fd = unsafe { opened(directory, name, libc::O_RDONLY, deadline)? };
    let mut bytes = [0_u8; 256];
    let count = unsafe { libc::syscall(libc::SYS_read, fd, bytes.as_mut_ptr(), bytes.len()) };
    let read_errno = if count < 0 { unsafe { errno() } } else { 0 };
    let result = (|| -> Result<()> {
        if let Expected::AppArmorUnarmed = expected {
            return if count == -1 && read_errno == libc::EINVAL {
                Ok(())
            } else if count < 0 {
                Err(read_errno)
            } else {
                Err(libc::EPROTO)
            };
        }
        if count < 0 {
            return Err(read_errno);
        }
        let actual = &bytes[..count as usize];
        let valid = match expected {
            Expected::Selinux(value) => {
                actual == value || actual.strip_suffix(b"\0") == Some(value)
            }
            Expected::Exact(value) => actual == value,
            Expected::Empty => actual.is_empty(),
            Expected::AppArmorUnarmed => false,
        };
        if !valid {
            return Err(libc::EPROTO);
        }
        let tail = unsafe { libc::syscall(libc::SYS_read, fd, bytes.as_mut_ptr(), 1) };
        if tail < 0 {
            Err(unsafe { errno() })
        } else if tail != 0 {
            Err(libc::EPROTO)
        } else {
            Ok(())
        }
    })();
    let closed = unsafe { libc::syscall(libc::SYS_close, fd) };
    let close_errno = if closed < 0 { unsafe { errno() } } else { 0 };
    result?;
    if closed != 0 {
        return Err(close_errno);
    }
    unsafe { before(deadline) }
}

unsafe fn write_once(directory: RawFd, value: &[u8], deadline: u64) -> Result<()> {
    let fd = unsafe { opened(directory, c"exec", libc::O_WRONLY, deadline)? };
    // A partial/interrupted authority-changing write is a failure, not a
    // second attempt with another command. This child then exits and retires.
    let written = unsafe { libc::syscall(libc::SYS_write, fd, value.as_ptr(), value.len()) };
    let write_errno = if written < 0 { unsafe { errno() } } else { 0 };
    let closed = unsafe { libc::syscall(libc::SYS_close, fd) };
    let close_errno = if closed < 0 { unsafe { errno() } } else { 0 };
    if written < 0 {
        return Err(write_errno);
    }
    if written as usize != value.len() {
        return Err(libc::EPROTO);
    }
    if closed != 0 {
        return Err(close_errno);
    }
    unsafe { before(deadline) }
}

/// The original four reads and package resolver retain the query role.
pub(super) unsafe fn arm_query_mac(deadline: u64) -> i32 {
    unsafe { arm_operation_mac(deadline, OperationDomain::Query) }
}

/// Only the finite implicit browser Start operation requests this role.
/// No fallback to query, shell, or broker is permitted if policy rejects it.
pub(super) unsafe fn arm_browser_mac(deadline: u64) -> i32 {
    unsafe { arm_operation_mac(deadline, OperationDomain::Browser) }
}

/// Read-only Contacts provider Java role; no fallback to query/shell.
pub(super) unsafe fn arm_contacts_read_mac(deadline: u64) -> i32 {
    unsafe { arm_operation_mac(deadline, OperationDomain::ContactsRead) }
}

/// Closed task list / permission and alias resolvers. Never borrows Browser.
pub(super) unsafe fn arm_launch_read_mac(deadline: u64) -> i32 {
    unsafe { arm_operation_mac(deadline, OperationDomain::LaunchRead) }
}

/// Only the exact bound Launch start command may request this domain.
pub(super) unsafe fn arm_launch_start_mac(deadline: u64) -> i32 {
    unsafe { arm_operation_mac(deadline, OperationDomain::LaunchStart) }
}

/// Raw-child, allocation-free operation, with no caller label/path input.
unsafe fn arm_operation_mac(deadline: u64, domain: OperationDomain) -> i32 {
    if let Err(error) = unsafe { credentials().and_then(|_| before(deadline)) } {
        return error;
    }
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
        let mut name = [0_u8; 16];
        let count = unsafe {
            libc::syscall(
                libc::SYS_readlinkat,
                held[0],
                c"self".as_ptr(),
                name.as_mut_ptr(),
                name.len() - 1,
            )
        };
        if count < 0 {
            return Err(unsafe { errno() });
        }
        if !(1..=10).contains(&count) {
            return Err(libc::EPROTO);
        }
        let mut own_pid = 0_u32;
        for byte in &name[..count as usize] {
            if !byte.is_ascii_digit() {
                return Err(libc::EPROTO);
            }
            own_pid = own_pid
                .checked_mul(10)
                .and_then(|v| v.checked_add(u32::from(*byte - b'0')))
                .ok_or(libc::EOVERFLOW)?;
        }
        if own_pid <= 1
            || own_pid != unsafe { libc::syscall(libc::SYS_getpid) } as u32
            || name[0] == b'0'
        {
            return Err(libc::EPROTO);
        }
        name[count as usize] = 0;
        // Only the kernel's /proc/self spelling, verified against this task,
        // is opened. There is no external or caller-selected numeric PID.
        let own = unsafe { CStr::from_bytes_with_nul_unchecked(&name[..count as usize + 1]) };
        held[1] = unsafe { opened(held[0], own, libc::O_PATH | libc::O_DIRECTORY, deadline)? };
        held[2] = unsafe { opened(held[1], c"attr", libc::O_PATH | libc::O_DIRECTORY, deadline)? };
        // This query requires the SELinux-first MAC provider contract.
        // On the selected kernel, SELinux current/exec live directly in attr;
        // AppArmor retains its explicit provider directory.
        held[3] = unsafe {
            opened(
                held[2],
                c"apparmor",
                libc::O_PATH | libc::O_DIRECTORY,
                deadline,
            )?
        };
        unsafe {
            label(held[2], c"current", Expected::Selinux(BROKER), deadline)?;
            label(held[2], c"exec", Expected::Empty, deadline)?;
            label(held[3], c"current", Expected::Exact(AA_BROKER), deadline)?;
            label(held[3], c"exec", Expected::AppArmorUnarmed, deadline)?;
            write_once(held[2], domain.terminated(), deadline)?;
            label(
                held[2],
                c"exec",
                Expected::Selinux(domain.context().as_bytes()),
                deadline,
            )?;
            write_once(held[3], AA_STACK, deadline)?;
            label(held[3], c"exec", Expected::Exact(AA_PENDING), deadline)?;
            label(held[2], c"current", Expected::Selinux(BROKER), deadline)?;
            label(held[3], c"current", Expected::Exact(AA_BROKER), deadline)?;
            label(
                held[2],
                c"exec",
                Expected::Selinux(domain.context().as_bytes()),
                deadline,
            )?;
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
    fn query_mac_action_rejects_ordinary_host_before_any_attribute_write() {
        assert!(unsafe { libc::getpid() } == 1 || unsafe { libc::getppid() } != 0);
        let nnp = unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) };
        let dumpable = unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) };
        assert_eq!(unsafe { arm_query_mac(u64::MAX) }, libc::EPERM);
        assert_eq!(
            unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) },
            nnp
        );
        assert_eq!(
            unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) },
            dumpable
        );
    }
    #[test]
    fn browser_mac_action_rejects_ordinary_host_before_any_attribute_write() {
        assert!(unsafe { libc::getpid() } == 1 || unsafe { libc::getppid() } != 0);
        let nnp = unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) };
        let dumpable = unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) };
        assert_eq!(unsafe { arm_browser_mac(u64::MAX) }, libc::EPERM);
        assert_eq!(
            unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) },
            nnp
        );
        assert_eq!(
            unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) },
            dumpable
        );
    }
    #[test]
    fn launch_mac_actions_reject_ordinary_host_without_changing_attributes() {
        assert!(unsafe { libc::getpid() } == 1 || unsafe { libc::getppid() } != 0);
        let nnp = unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) };
        let dumpable = unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) };
        assert_eq!(unsafe { arm_launch_read_mac(u64::MAX) }, libc::EPERM);
        assert_eq!(unsafe { arm_launch_start_mac(u64::MAX) }, libc::EPERM);
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
