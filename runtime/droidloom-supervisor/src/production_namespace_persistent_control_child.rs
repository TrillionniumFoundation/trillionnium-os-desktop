//! cfg(test), fixed syscall-only probe after the original four-FD root pivot.
//! The original PID1 keeps its credentials. A separately owned clone3 child
//! writes as guest10061, closes the control endpoint, and is reaped by pidfd.
use super::{CHILD_FD, CloneArgs, Phase, fail, finish, receive, send};

pub(crate) const REPORT_MAGIC: u64 = 0x5034_4441_5441_3031;
pub(crate) const APP_UID: u32 = 10061;

#[derive(Clone, Copy)]
#[repr(C)]
pub(crate) struct GuestFile {
    pub(crate) device: u64,
    pub(crate) inode: u64,
    pub(crate) bytes: u64,
    pub(crate) links: u64,
    pub(crate) uid: u32,
    pub(crate) gid: u32,
    pub(crate) mode: u32,
    pub(crate) reserved: u32,
}

#[derive(Clone, Copy)]
#[repr(C)]
pub(crate) struct GuestReport {
    pub(crate) magic: u64,
    pub(crate) nonce: [u8; 16],
    pub(crate) writer_pid: u32,
    pub(crate) writer_exit: i32,
    pub(crate) writer_pidfd_inode: u64,
    pub(crate) files: [GuestFile; 4],
}
const _: () = assert!(std::mem::size_of::<GuestFile>() == 48);
const _: () = assert!(std::mem::size_of::<GuestReport>() == 232);

unsafe fn rejected(nonce: [u8; 16]) -> ! {
    unsafe { *libc::__errno_location() = libc::EPROTO; fail(nonce, 1) }
}

unsafe fn stat_file(fd: i32, uid: u32, payload: &[u8], nonce: [u8; 16]) -> GuestFile {
    let mut stat: libc::stat = unsafe { std::mem::zeroed() };
    let mut body = [0u8; 64];
    unsafe {
        if payload.len() > body.len()
            || libc::syscall(libc::SYS_fstat, fd, &mut stat) != 0
            || stat.st_uid != uid || stat.st_gid != uid || stat.st_nlink != 1
            || stat.st_mode != libc::S_IFREG | 0o600 || stat.st_size != payload.len() as i64
            || libc::syscall(libc::SYS_pread64, fd, body.as_mut_ptr(), payload.len(), 0) != payload.len() as libc::c_long
            || &body[..payload.len()] != payload
        { rejected(nonce) }
    }
    GuestFile { device: stat.st_dev, inode: stat.st_ino, bytes: stat.st_size as u64,
        links: stat.st_nlink, uid: stat.st_uid, gid: stat.st_gid, mode: stat.st_mode, reserved: 0 }
}

unsafe fn write_new(path: &std::ffi::CStr, payload: &[u8], uid: u32, nonce: [u8; 16]) -> GuestFile {
    unsafe {
        let fd = libc::syscall(libc::SYS_openat, libc::AT_FDCWD, path.as_ptr(),
            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL | libc::O_CLOEXEC | libc::O_NOFOLLOW, 0o600_u32);
        if fd < 0 || fd > i32::MAX as libc::c_long { fail(nonce, 1) }
        let fd = fd as i32;
        if libc::syscall(libc::SYS_write, fd, payload.as_ptr(), payload.len()) != payload.len() as libc::c_long
            || libc::syscall(libc::SYS_fsync, fd) != 0 { fail(nonce, 1) }
        let observed = stat_file(fd, uid, payload, nonce);
        if libc::syscall(libc::SYS_close, fd) != 0 { fail(nonce, 1) }
        observed
    }
}

unsafe fn inspect(path: &std::ffi::CStr, payload: &[u8], uid: u32, nonce: [u8; 16]) -> GuestFile {
    unsafe {
        let fd = libc::syscall(libc::SYS_openat, libc::AT_FDCWD, path.as_ptr(), libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW, 0);
        if fd < 0 || fd > i32::MAX as libc::c_long { fail(nonce, 1) }
        let fd = fd as i32;
        let observed = stat_file(fd, uid, payload, nonce);
        if libc::syscall(libc::SYS_close, fd) != 0 { fail(nonce, 1) }
        observed
    }
}

unsafe fn app_writer(nonce: [u8; 16]) -> ! {
    unsafe {
        // The writer cannot impersonate its PID1 on the private endpoint.
        if libc::syscall(libc::SYS_close, CHILD_FD) != 0
            || libc::syscall(libc::SYS_prctl, libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) != 0
            || libc::syscall(libc::SYS_getppid) != 1
            || libc::syscall(libc::SYS_setgroups, 0, std::ptr::null::<libc::gid_t>()) != 0
            || libc::syscall(libc::SYS_setresgid, APP_UID, APP_UID, APP_UID) != 0
            || libc::syscall(libc::SYS_setresuid, APP_UID, APP_UID, APP_UID) != 0
            // Credential changes clear PDEATHSIG; restore it and bookend PPID.
            || libc::syscall(libc::SYS_prctl, libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) != 0
            || libc::syscall(libc::SYS_getppid) != 1
            || libc::syscall(libc::SYS_getuid) != APP_UID as libc::c_long
            || libc::syscall(libc::SYS_geteuid) != APP_UID as libc::c_long
            || libc::syscall(libc::SYS_getgid) != APP_UID as libc::c_long
            || libc::syscall(libc::SYS_getegid) != APP_UID as libc::c_long
            || libc::syscall(libc::SYS_getgroups, 0, std::ptr::null_mut::<libc::gid_t>()) != 0
        { finish(131) }
        for path in [c"/data/private-app/app-probe", c"/metadata/private-app/app-probe"] {
            // Failure cannot publish a positive phase: fd3 has been closed.
            write_new(path, b"fixture-guest-10061\n", APP_UID, nonce);
        }
        finish(0)
    }
}

unsafe fn writer(nonce: [u8; 16]) -> (u32, u64) {
    unsafe {
        let mut pidfd: i32 = -1;
        let args = CloneArgs { flags: libc::CLONE_PIDFD as u64, pidfd: (&mut pidfd as *mut i32) as u64,
            exit_signal: libc::SIGCHLD as u64, ..std::mem::zeroed() };
        let pid = libc::syscall(libc::SYS_clone3, &args, std::mem::size_of::<CloneArgs>());
        if pid < 0 { fail(nonce, 1) }
        if pid == 0 { app_writer(nonce) }
        if pid <= 1 || pid > u32::MAX as libc::c_long || pidfd < 0 { rejected(nonce) }
        let mut fd_stat: libc::stat = std::mem::zeroed();
        if libc::syscall(libc::SYS_fstat, pidfd, &mut fd_stat) != 0 { fail(nonce, 1) }
        let mut poll = libc::pollfd { fd: pidfd, events: libc::POLLIN, revents: 0 };
        let mut elapsed = 0;
        loop {
            let result = libc::syscall(libc::SYS_poll, &mut poll, 1, 20);
            if result > 0 && poll.revents & libc::POLLIN != 0 { break; }
            if result < 0 && *libc::__errno_location() != libc::EINTR { rejected(nonce) }
            elapsed += 20;
            if elapsed >= 3000 {
                libc::syscall(libc::SYS_pidfd_send_signal, pidfd, libc::SIGKILL, std::ptr::null::<libc::siginfo_t>(), 0);
                // The timeout is always a failure. Bound the cleanup attempt
                // on this same actual pidfd; never block indefinitely in waitid.
                // If exit is not observed, PID1 fails and the original owning
                // tree must retire the namespace before releasing its mounts.
                for _ in 0..100 {
                    poll.revents = 0;
                    let ready = libc::syscall(libc::SYS_poll, &mut poll, 1, 20);
                    if ready > 0 && poll.revents & libc::POLLIN != 0 {
                        let mut exit: libc::siginfo_t = std::mem::zeroed();
                        libc::syscall(libc::SYS_waitid, libc::P_PIDFD, pidfd, &mut exit,
                            libc::WEXITED | libc::WNOHANG, std::ptr::null::<libc::rusage>());
                        break;
                    }
                    if ready < 0 && *libc::__errno_location() != libc::EINTR { break; }
                }
                libc::syscall(libc::SYS_close, pidfd);
                rejected(nonce)
            }
        }
        let mut exit: libc::siginfo_t = std::mem::zeroed();
        if libc::syscall(libc::SYS_waitid, libc::P_PIDFD, pidfd, &mut exit, libc::WEXITED | libc::WNOHANG, std::ptr::null::<libc::rusage>()) != 0
            || exit.si_pid() != pid as i32 || exit.si_code != libc::CLD_EXITED || exit.si_status() != 0
        { rejected(nonce) }
        if libc::syscall(libc::SYS_close, pidfd) != 0 { fail(nonce, 1) }
        (pid as u32, fd_stat.st_ino)
    }
}

pub(super) unsafe fn run(nonce: [u8; 16], parent_pid: u32) -> ! {
    unsafe {
        receive(nonce, parent_pid, Phase::ProbePersistentData);
        if libc::syscall(libc::SYS_getpid) != 1 || libc::syscall(libc::SYS_getuid) != 0
            || libc::syscall(libc::SYS_geteuid) != 0 || libc::syscall(libc::SYS_getgid) != 0
            || libc::syscall(libc::SYS_getegid) != 0 { rejected(nonce) }
        let data_root = write_new(c"/data/root-seed", b"fixture-root-zero\n", 0, nonce);
        let metadata_root = write_new(c"/metadata/root-seed", b"fixture-root-zero\n", 0, nonce);
        for path in [c"/data/private-app", c"/metadata/private-app"] {
            if libc::syscall(libc::SYS_mkdirat, libc::AT_FDCWD, path.as_ptr(), 0o700_u32) != 0 { fail(nonce, 1) }
            let fd = libc::syscall(libc::SYS_openat, libc::AT_FDCWD, path.as_ptr(), libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW, 0);
            if fd < 0 || fd > i32::MAX as libc::c_long { fail(nonce, 1) }
            // Only the exclusively created test directory is assigned to the
            // guest app. No existing node or recursive tree is chowned.
            if libc::syscall(libc::SYS_fchown, fd, APP_UID, APP_UID) != 0
                || libc::syscall(libc::SYS_fsync, fd) != 0
                || libc::syscall(libc::SYS_close, fd) != 0 { fail(nonce, 1) }
        }
        let (pid, inode) = writer(nonce);
        let data_app = inspect(c"/data/private-app/app-probe", b"fixture-guest-10061\n", APP_UID, nonce);
        let metadata_app = inspect(c"/metadata/private-app/app-probe", b"fixture-guest-10061\n", APP_UID, nonce);
        let report = GuestReport { magic: REPORT_MAGIC, nonce, writer_pid: pid, writer_exit: 0,
            writer_pidfd_inode: inode, files: [data_root, data_app, metadata_root, metadata_app] };
        send(nonce, Phase::PersistentDataChecked, 0, 1);
        if libc::syscall(libc::SYS_sendto, CHILD_FD, &report, std::mem::size_of::<GuestReport>(),
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT, std::ptr::null::<libc::sockaddr>(), 0) != std::mem::size_of::<GuestReport>() as libc::c_long
        { finish(132) }
        receive(nonce, parent_pid, Phase::Stop);
        finish(0)
    }
}
