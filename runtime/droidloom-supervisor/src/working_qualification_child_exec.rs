//! Fixed child transitions of the one normal working owner.
//! This module has no public path/context/UID selector. It is used only inside
//! the parent's pre_exec closure, before the same held applications ELF runs.
use std::{ffi::CStr, io, mem};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum Kind { Preparation, Physical }
impl Kind {
    fn exec_target(self) -> crate::production_mac::self_attr::ExecTarget {
        use crate::production_mac::self_attr::ExecTarget;
        match self {
            Self::Preparation => ExecTarget::WorkingPreparation,
            Self::Physical => ExecTarget::WorkingApplication,
        }
    }
    fn apparmor_exec(self) -> &'static [u8] {
        match self {
            Self::Preparation => b"exec droidloom-working-privateprep\0",
            Self::Physical => b"exec droidloom-working-application\0",
        }
    }
}
// Same bounded procfs-only attribute primitive used by the existing normal
// private query helper. No allocator, locks or library state after fork.
unsafe fn attribute(path: &CStr, expected: &[u8], write: bool) -> bool {
    unsafe {
        let raw = libc::syscall(libc::SYS_openat, libc::AT_FDCWD, path.as_ptr(),
            (if write { libc::O_WRONLY } else { libc::O_RDONLY })
                | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK, 0);
        if raw < 0 { return false; }
        let mut fs: libc::statfs = mem::zeroed();
        let mut node: libc::stat = mem::zeroed();
        let valid = libc::syscall(libc::SYS_fstatfs, raw, &mut fs) == 0
            && libc::syscall(libc::SYS_fstat, raw, &mut node) == 0
            && fs.f_type == libc::PROC_SUPER_MAGIC
            && node.st_mode & libc::S_IFMT == libc::S_IFREG;
        let mut bytes = [0_u8; 256];
        let count = if !valid { -1 } else if write {
            libc::syscall(libc::SYS_write, raw, expected.as_ptr(), expected.len())
        } else { libc::syscall(libc::SYS_read, raw, bytes.as_mut_ptr(), bytes.len()) };
        let good = if write { count == expected.len() as libc::c_long } else {
            count >= 0 && count as usize == expected.len()
                && bytes.get(..expected.len()) == Some(expected)
        };
        let tail = if !write && good {
            libc::syscall(libc::SYS_read, raw, bytes.as_mut_ptr(), 1)
        } else { 0 };
        let closed = libc::syscall(libc::SYS_close, raw);
        valid && good && tail == 0 && closed == 0
    }
}
/// Close the inherited sole watchdog description before replacing any fixed
/// channel FD. Set only the source-selected child contexts. Exec and the child's
/// BootOwner subsequently check the real resulting labels independently.
pub(crate) unsafe fn prepare(kind: Kind, watchdog: libc::c_int) -> io::Result<()> {
    unsafe {
        if watchdog < 0 || libc::close(watchdog) != 0 {
            return Err(io::Error::last_os_error());
        }
        let aa = b"droidloom-working-qualification (enforce)\n";
        if libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 0
            || !attribute(c"/proc/thread-self/attr/apparmor/current", aa, false)
            || !crate::production_mac::self_attr::prepare_selinux_exec(kind.exec_target())
            || !attribute(c"/proc/thread-self/attr/apparmor/exec", kind.apparmor_exec(), true)
            || !crate::production_mac::self_attr::working_parent_current()
            || !attribute(c"/proc/thread-self/attr/apparmor/current", aa, false) {
            return Err(io::Error::from_raw_os_error(libc::EPERM));
        }
        Ok(())
    }
}
