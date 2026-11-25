//! The camera can neither create tasks nor execute another image after entry.
use std::os::fd::RawFd;
pub(super) fn program(executable: Option<RawFd>) -> Vec<libc::sock_filter> {
    let ins = |code, jt, jf, k| libc::sock_filter { code, jt, jf, k };
    let allow = 0x7fff0000;
    let deny = 0x00050000 | libc::EPERM as u32;
    let mut f = vec![
        ins(0x20, 0, 0, 4),
        ins(0x15, 1, 0, 0xc000003e),
        ins(0x06, 0, 0, 0x80000000),
        ins(0x20, 0, 0, 0),
        ins(0x35, 0, 1, 0x40000000),
        ins(0x06, 0, 0, deny),
    ];
    if let Some(fd) = executable {
        f.extend([
            ins(0x15, 0, 6, libc::SYS_execveat as u32),
            ins(0x20, 0, 0, 16),
            ins(0x15, 0, 3, fd as u32),
            ins(0x20, 0, 0, 48),
            ins(0x15, 0, 1, libc::AT_EMPTY_PATH as u32),
            ins(0x06, 0, 0, allow),
            ins(0x06, 0, 0, deny),
        ]);
    }
    // No Internet family and no public connection initiated by the capture role.
    f.extend([
        ins(0x15, 0, 4, libc::SYS_socketpair as u32),
        ins(0x20, 0, 0, 16),
        ins(0x15, 0, 1, libc::AF_UNIX as u32),
        ins(0x06, 0, 0, allow),
        ins(0x06, 0, 0, deny),
    ]);
    let ioctls: [u32; 16] = [
        0x80685600, 0xc0405602, 0xc02c564a, 0xc034564b, 0xc0d05605, 0xc0cc5616, 0xc0145608,
        0xc0585609, 0xc058560f, 0xc0585611, 0x40045612, 0x40045613, 0xc050ff0b, 0xff09, 0xff05,
        0xb703,
    ];
    f.push(ins(
        0x15,
        0,
        (2 * ioctls.len() + 5) as u8,
        libc::SYS_ioctl as u32,
    ));
    f.extend([
        ins(0x20, 0, 0, 28),
        ins(0x15, 1, 0, 0),
        ins(0x06, 0, 0, deny),
        ins(0x20, 0, 0, 24),
    ]);
    for ioctl in ioctls {
        f.extend([ins(0x15, 0, 1, ioctl), ins(0x06, 0, 0, allow)]);
    }
    // Nonmatching ioctl must be rejected, never fall through using its argument.
    f.push(ins(0x06, 0, 0, deny));
    for syscall in [
        libc::SYS_read,
        libc::SYS_write,
        libc::SYS_readv,
        libc::SYS_writev,
        libc::SYS_close,
        libc::SYS_fstat,
        libc::SYS_newfstatat,
        libc::SYS_statx,
        libc::SYS_fstatfs,
        libc::SYS_openat,
        libc::SYS_readlink,
        libc::SYS_readlinkat,
        libc::SYS_fcntl,
        libc::SYS_lseek,
        libc::SYS_pread64,
        libc::SYS_mmap,
        libc::SYS_mprotect,
        libc::SYS_munmap,
        libc::SYS_brk,
        libc::SYS_madvise,
        libc::SYS_rt_sigaction,
        libc::SYS_rt_sigprocmask,
        libc::SYS_rt_sigreturn,
        libc::SYS_arch_prctl,
        libc::SYS_prlimit64,
        libc::SYS_getrlimit,
        libc::SYS_getrandom,
        libc::SYS_set_tid_address,
        libc::SYS_set_robust_list,
        libc::SYS_rseq,
        libc::SYS_access,
        libc::SYS_faccessat,
        libc::SYS_faccessat2,
        libc::SYS_futex,
        libc::SYS_clock_gettime,
        libc::SYS_clock_nanosleep,
        libc::SYS_nanosleep,
        libc::SYS_poll,
        libc::SYS_ppoll,
        libc::SYS_getpid,
        libc::SYS_getppid,
        libc::SYS_getuid,
        libc::SYS_geteuid,
        libc::SYS_getgid,
        libc::SYS_getegid,
        libc::SYS_getgroups,
        libc::SYS_capget,
        libc::SYS_prctl,
        libc::SYS_getsockopt,
        libc::SYS_setsockopt,
        libc::SYS_accept4,
        libc::SYS_recvmsg,
        libc::SYS_sendmsg,
        libc::SYS_recvfrom,
        libc::SYS_sendto,
        libc::SYS_shutdown,
        libc::SYS_fgetxattr,
        libc::SYS_sched_getaffinity,
        libc::SYS_pidfd_open,
        457,
        459,
        464,
        libc::SYS_exit_group,
        libc::SYS_exit,
    ] {
        f.extend([ins(0x15, 0, 1, syscall as u32), ins(0x06, 0, 0, allow)]);
    }
    f.push(ins(0x06, 0, 0, deny));
    f
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::File;
    use std::os::fd::{AsRawFd, FromRawFd};
    fn status(pid: i32) -> i32 {
        let mut value = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut value, 0) }, pid);
        assert!(libc::WIFEXITED(value), "child status {value}");
        libc::WEXITSTATUS(value)
    }
    #[test]
    fn native_camera_filter_allows_actual_pidfd_metadata_but_denies_execution_namespaces_and_foreign_ioctl()
     {
        let policy = program(None);
        let p = libc::sock_fprog {
            len: policy.len() as u16,
            filter: policy.as_ptr().cast_mut(),
        };
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            unsafe {
                if libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                    || libc::prctl(libc::PR_SET_SECCOMP, 2, &p) != 0
                {
                    libc::_exit(20);
                }
                let mine = libc::getpid();
                let raw = libc::syscall(libc::SYS_pidfd_open, mine, 0u32);
                if raw < 0 {
                    libc::_exit(21);
                }
                let mut info = [0u64; 10];
                info[0] = 3;
                if libc::ioctl(
                    raw as i32,
                    0xc050ff0bu64 as libc::c_ulong,
                    info.as_mut_ptr(),
                ) != 0
                {
                    libc::_exit(22);
                }
                if libc::ioctl(raw as i32, 0xdeadbeefu64 as libc::c_ulong, 0usize) != -1
                    || *libc::__errno_location() != libc::EPERM
                {
                    libc::_exit(23);
                }
                if libc::socket(libc::AF_INET, libc::SOCK_STREAM, 0) != -1
                    || *libc::__errno_location() != libc::EPERM
                {
                    libc::_exit(24);
                }
                if libc::syscall(libc::SYS_unshare, libc::CLONE_NEWUSER) != -1
                    || *libc::__errno_location() != libc::EPERM
                {
                    libc::_exit(25);
                }
                if libc::syscall(
                    libc::SYS_execveat,
                    -1,
                    c"".as_ptr(),
                    0usize,
                    0usize,
                    libc::AT_EMPTY_PATH,
                ) != -1
                    || *libc::__errno_location() != libc::EPERM
                {
                    libc::_exit(26);
                }
                if libc::syscall(libc::SYS_clone3, 0usize, 0usize) != -1
                    || *libc::__errno_location() != libc::EPERM
                {
                    libc::_exit(27);
                }
                libc::_exit(0);
            }
        }
        assert_eq!(status(pid), 0);
    }
    #[test]
    fn fixed_camera_preexec_filter_runs_a_real_fresh_rust_image_with_eof_stdio() {
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("probe.rs");
        let output = directory.path().join("probe");
        std::fs::write(&source,
            "unsafe extern \"C\" { fn getpid() -> i32; fn _exit(c:i32)->!; }\nfn main(){unsafe{_exit(if getpid()>1 {0}else{41})}}\n").unwrap();
        let rustc = std::env::var_os("RUSTC").unwrap_or_else(|| "/home/qq/.cargo/bin/rustc".into());
        let built = std::process::Command::new(rustc)
            .args(["--edition=2024", "-C", "opt-level=1"])
            .arg(&source)
            .arg("-o")
            .arg(&output)
            .output()
            .unwrap();
        assert!(
            built.status.success(),
            "{}",
            String::from_utf8_lossy(&built.stderr)
        );
        let executable = File::open(&output).unwrap();
        let executable =
            crate::production_application::query_io::above_reserved(&executable).unwrap();
        let stdio = crate::production_application::query_io::fixed_stdio().unwrap();
        let policy = program(Some(executable.as_raw_fd()));
        let p = libc::sock_fprog {
            len: policy.len() as u16,
            filter: policy.as_ptr().cast_mut(),
        };
        let argv = [c"camera-fresh-rust".as_ptr(), std::ptr::null()];
        let environment = [c"LC_ALL=C".as_ptr(), std::ptr::null()];
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            unsafe {
                for fd in 0..3 {
                    if libc::dup2(stdio.as_raw_fd(), fd) != fd {
                        libc::_exit(30);
                    }
                }
                if libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                    || libc::prctl(libc::PR_SET_SECCOMP, 2, &p) != 0
                {
                    libc::_exit(31);
                }
                libc::syscall(
                    libc::SYS_execveat,
                    executable.as_raw_fd(),
                    c"".as_ptr(),
                    argv.as_ptr(),
                    environment.as_ptr(),
                    libc::AT_EMPTY_PATH,
                );
                libc::_exit(32);
            }
        }
        assert_eq!(status(pid), 0);
    }
}
