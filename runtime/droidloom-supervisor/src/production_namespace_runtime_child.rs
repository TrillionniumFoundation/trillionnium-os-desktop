//! Fixed runtime-tree and original-init consumer in the actually owned PID 1.
//! No path, mount flags, environment or executable can be supplied in a packet.
//! A prepared runtime is not execution admission; the parent must separately
//! possess the same-tree execution authority before sending the exec phase.
use super::empty_root::{KernelStatfs, entry_record};
use super::{CHILD_FD, Mode, Packet, Phase, finish, send};
use std::ffi::CStr;
use std::os::fd::RawFd;

const EMPTY_PATH: u32 = 0x1000;
const MOVE_EMPTY: u32 = 0x04 | 0x40;
const RO_IMAGE: u64 = 1 | 2 | 4;
const NOEXEC: u64 = 8;
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const EXT4_MAGIC: libc::c_long = 0xef53;
const EROFS_MAGIC: libc::c_long = 0xe0f5_e1e2_u32 as libc::c_long;
const EXEC_FD: RawFd = 4;

#[repr(C)]
struct MountAttr {
    set: u64,
    clear: u64,
    propagation: u64,
    userns: u64,
}

#[cfg(test)]
static STAGE: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
#[cfg(test)]
pub(super) fn decode_private_failure(value: i32) -> Option<(u32, u32, i32)> {
    let v = value as u32;
    let stage = (v >> 24) & 15;
    let line = (v >> 12) & 4095;
    let errno = (v & 4095) as i32;
    (v >> 28 == 4 && (1..=5).contains(&stage) && line != 0 && errno != 0)
        .then_some((stage, line, errno))
}
unsafe fn failed(nonce: [u8; 16], line: u32) -> ! {
    #[cfg(test)]
    unsafe {
        let errno = *libc::__errno_location();
        let errno = if (1..4096).contains(&errno) {
            errno as u32
        } else {
            libc::EIO as u32
        };
        let stage = STAGE.load(std::sync::atomic::Ordering::Relaxed);
        send(
            nonce,
            Phase::Failed,
            (0x4000_0000 | stage << 24 | line << 12 | errno) as i32,
            1,
        );
        finish(127)
    }
    #[cfg(not(test))]
    unsafe {
        let _ = line;
        super::fail(nonce, 1)
    }
}
unsafe fn rejected(nonce: [u8; 16]) -> ! {
    unsafe {
        *libc::__errno_location() = libc::EPROTO;
        failed(nonce, line!())
    }
}

unsafe fn receive_runtime(nonce: [u8; 16], parent_pid: u32) -> [RawFd; 2] {
    let mut packet = Packet::zeroed();
    let mut iov = libc::iovec {
        iov_base: (&mut packet as *mut Packet).cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut control = [0_usize; 16];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = control.as_mut_ptr().cast();
    msg.msg_controllen = std::mem::size_of_val(&control);
    let n = unsafe {
        libc::syscall(
            libc::SYS_recvmsg,
            CHILD_FD,
            &mut msg,
            libc::MSG_CMSG_CLOEXEC,
        )
    };
    if n == 0 {
        unsafe { finish(0) }
    }
    if n != std::mem::size_of::<Packet>() as libc::c_long
        || msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
        || !packet.matches(nonce, parent_pid)
        || packet.errno != 0
    {
        unsafe { rejected(nonce) }
    }
    let header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    if packet.phase == Phase::Stop as u32 {
        if !header.is_null() {
            unsafe { rejected(nonce) }
        }
        unsafe { finish(0) }
    }
    if packet.phase != Phase::MountRuntime as u32 || header.is_null() {
        unsafe { rejected(nonce) }
    }
    let h = unsafe { &*header };
    if h.cmsg_level != libc::SOL_SOCKET
        || h.cmsg_type != libc::SCM_RIGHTS
        || h.cmsg_len != unsafe { libc::CMSG_LEN(8) } as usize
        || !unsafe { libc::CMSG_NXTHDR(&msg, header) }.is_null()
    {
        unsafe { rejected(nonce) }
    }
    let p = unsafe { libc::CMSG_DATA(header).cast::<i32>() };
    let raw = unsafe {
        [
            std::ptr::read_unaligned(p),
            std::ptr::read_unaligned(p.add(1)),
        ]
    };
    if raw[0] < 0 || raw[1] < 0 || raw[0] == raw[1] || raw.contains(&CHILD_FD) {
        unsafe { rejected(nonce) }
    }
    // Stdio was closed before TreeReady. Received FDs may therefore be 0/1.
    // Duplicate both before closing either, never overwrite a live peer FD.
    let mut held = [-1; 2];
    for i in 0..2 {
        let fd = unsafe { libc::syscall(libc::SYS_fcntl, raw[i], libc::F_DUPFD_CLOEXEC, 4) };
        if fd < 4 || fd > i32::MAX as libc::c_long {
            unsafe { failed(nonce, line!()) }
        }
        held[i] = fd as i32;
    }
    for fd in raw {
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
    }
    held
}

unsafe fn meta(fd: RawFd, nonce: [u8; 16]) -> libc::stat {
    let mut st: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstat, fd, &mut st) } != 0 {
        unsafe { failed(nonce, line!()) }
    }
    st
}
fn same_inode(a: &libc::stat, b: &libc::stat) -> bool {
    (
        a.st_dev,
        a.st_ino,
        a.st_mode,
        a.st_uid,
        a.st_gid,
        a.st_nlink,
        a.st_size,
        a.st_mtime,
        a.st_mtime_nsec,
        a.st_ctime,
        a.st_ctime_nsec,
    ) == (
        b.st_dev,
        b.st_ino,
        b.st_mode,
        b.st_uid,
        b.st_gid,
        b.st_nlink,
        b.st_size,
        b.st_mtime,
        b.st_mtime_nsec,
        b.st_ctime,
        b.st_ctime_nsec,
    )
}
unsafe fn fs(fd: RawFd, nonce: [u8; 16]) -> KernelStatfs {
    let mut v: KernelStatfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut v) } != 0 {
        unsafe { failed(nonce, line!()) }
    }
    v
}
unsafe fn opened(parent: RawFd, name: &CStr, flags: i32, nonce: [u8; 16]) -> RawFd {
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat,
            parent,
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
            0,
        )
    };
    if fd < 0 || fd > i32::MAX as libc::c_long {
        unsafe { failed(nonce, line!()) }
    }
    fd as RawFd
}
unsafe fn directory(parent: RawFd, name: &CStr, nonce: [u8; 16]) -> RawFd {
    unsafe { opened(parent, name, libc::O_PATH | libc::O_DIRECTORY, nonce) }
}
unsafe fn close(fd: RawFd) {
    unsafe {
        libc::syscall(libc::SYS_close, fd);
    }
}
unsafe fn require_image(fd: RawFd, kind: u32, nonce: [u8; 16]) {
    let v = unsafe { fs(fd, nonce) };
    let s = unsafe { meta(fd, nonce) };
    if !matches!(v.f_type, EXT4_MAGIC | EROFS_MAGIC)
        || v.f_flags as u64 & RO_IMAGE != RO_IMAGE
        || v.f_flags as u64 & NOEXEC != 0
        || s.st_mode & libc::S_IFMT != kind
    {
        unsafe { rejected(nonce) }
    }
}
unsafe fn require_root(fd: RawFd, nonce: [u8; 16]) {
    unsafe { require_image(fd, libc::S_IFDIR, nonce) };
    let s = unsafe { meta(fd, nonce) };
    if s.st_uid != 0 || s.st_gid != 0 || s.st_mode & 0o022 != 0 {
        unsafe { rejected(nonce) }
    }
}
unsafe fn exact_names(dir: RawFd, expected: &[&[u8]], nonce: [u8; 16]) {
    if expected.len() > 63 {
        unsafe { rejected(nonce) }
    }
    let fd = unsafe { opened(dir, c".", libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
    let mut seen = 0_u64;
    let mut data = [0_u8; 4096];
    loop {
        let n = unsafe { libc::syscall(libc::SYS_getdents64, fd, data.as_mut_ptr(), data.len()) };
        if n < 0 || n > data.len() as libc::c_long {
            unsafe { failed(nonce, line!()) }
        }
        if n == 0 {
            break;
        }
        let mut pos = 0;
        while pos < n as usize {
            let (length, name) = match entry_record(&data[pos..n as usize]) {
                Some(v) => v,
                None => unsafe { rejected(nonce) },
            };
            pos += length;
            if name == b"." || name == b".." {
                continue;
            }
            let i = match expected.iter().position(|v| *v == name) {
                Some(i) => i,
                None => unsafe { rejected(nonce) },
            };
            if seen & (1 << i) != 0 {
                unsafe { rejected(nonce) }
            }
            seen |= 1 << i;
        }
    }
    unsafe { close(fd) };
    if seen != (1_u64 << expected.len()) - 1 {
        unsafe { rejected(nonce) }
    }
}
unsafe fn attach(source: RawFd, target: RawFd, nonce: [u8; 16]) {
    if unsafe {
        libc::syscall(
            libc::SYS_move_mount,
            source,
            c"".as_ptr(),
            target,
            c"".as_ptr(),
            MOVE_EMPTY,
        )
    } != 0
    {
        unsafe { failed(nonce, line!()) }
    }
}
unsafe fn project(source: RawFd, target: RawFd, noexec: bool, nonce: [u8; 16]) {
    // source is already attached inside this exact private mount namespace.
    // Never clone a host-origin regular file descriptor in the mapped child.
    let raw = unsafe {
        libc::syscall(
            libc::SYS_open_tree,
            source,
            c"".as_ptr(),
            1_u32 | libc::O_CLOEXEC as u32 | EMPTY_PATH,
        )
    };
    if raw < 0 || raw > i32::MAX as libc::c_long {
        unsafe { failed(nonce, line!()) }
    }
    let fd = raw as RawFd;
    let attr = MountAttr {
        set: RO_IMAGE | if noexec { NOEXEC } else { 0 },
        clear: 0,
        propagation: 0,
        userns: 0,
    };
    if unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            fd,
            c"".as_ptr(),
            EMPTY_PATH,
            &attr,
            std::mem::size_of::<MountAttr>(),
        )
    } != 0
    {
        unsafe { failed(nonce, line!()) }
    }
    unsafe {
        attach(fd, target, nonce);
        close(fd)
    }
}
unsafe fn check_projection(
    parent: RawFd,
    name: &CStr,
    source: &libc::stat,
    noexec: bool,
    nonce: [u8; 16],
) -> RawFd {
    let fd = unsafe { opened(parent, name, libc::O_PATH, nonce) };
    let v = unsafe { fs(fd, nonce) };
    if !same_inode(source, &unsafe { meta(fd, nonce) })
        || v.f_flags as u64 & RO_IMAGE != RO_IMAGE
        || (v.f_flags as u64 & NOEXEC != 0) != noexec
    {
        unsafe { rejected(nonce) }
    }
    fd
}
unsafe fn project_dir(runtime: RawFd, root: RawFd, name: &CStr, nonce: [u8; 16]) {
    let source = unsafe { directory(runtime, name, nonce) };
    let target = unsafe { directory(root, name, nonce) };
    unsafe { require_root(source, nonce) };
    let before = unsafe { meta(source, nonce) };
    unsafe {
        project(source, target, false, nonce);
        close(target)
    };
    let after = unsafe { check_projection(root, name, &before, false, nonce) };
    unsafe {
        close(after);
        close(source)
    }
}
unsafe fn project_rc(
    rc: RawFd,
    source_name: &CStr,
    target_dir: RawFd,
    target_name: &CStr,
    nonce: [u8; 16],
) {
    let source = unsafe { opened(rc, source_name, libc::O_PATH, nonce) };
    let before = unsafe { meta(source, nonce) };
    if before.st_mode & libc::S_IFMT != libc::S_IFREG
        || before.st_nlink != 1
        || before.st_uid != 0
        || before.st_gid != 0
        || before.st_mode & 0o022 != 0
        || before.st_size < 0
    {
        unsafe { rejected(nonce) }
    }
    let target = unsafe { opened(target_dir, target_name, libc::O_PATH, nonce) };
    if unsafe { meta(target, nonce) }.st_mode & libc::S_IFMT != libc::S_IFREG {
        unsafe { rejected(nonce) }
    }
    unsafe {
        project(source, target, true, nonce);
        close(target)
    };
    let after = unsafe { check_projection(target_dir, target_name, &before, true, nonce) };
    unsafe {
        close(after);
        close(source)
    }
}
unsafe fn retain_init(fd: RawFd, nonce: [u8; 16]) {
    if fd != EXEC_FD
        && unsafe { libc::syscall(libc::SYS_dup3, fd, EXEC_FD, libc::O_CLOEXEC) }
            != EXEC_FD as libc::c_long
    {
        unsafe { failed(nonce, line!()) }
    }
    if unsafe { libc::syscall(libc::SYS_close_range, 5_u32, u32::MAX, 0) } != 0 {
        unsafe { failed(nonce, line!()) }
    }
    for n in 0..3 {
        unsafe { close(n) }
    }
    if unsafe { libc::syscall(libc::SYS_fcntl, CHILD_FD, libc::F_GETFD) }
        != libc::FD_CLOEXEC as libc::c_long
        || unsafe { libc::syscall(libc::SYS_fcntl, EXEC_FD, libc::F_GETFD) }
            != libc::FD_CLOEXEC as libc::c_long
    {
        unsafe { rejected(nonce) }
    }
}
unsafe fn command(nonce: [u8; 16], parent_pid: u32, expected: Phase) {
    // Descriptor-free command; the connected capability is the original
    // inherited broker endpoint, not a pathname or caller-chosen PID.
    let mut packet = Packet::zeroed();
    let mut iov = libc::iovec {
        iov_base: (&mut packet as *mut Packet).cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 16];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = ancillary.as_mut_ptr().cast();
    msg.msg_controllen = std::mem::size_of_val(&ancillary);
    let n = unsafe {
        libc::syscall(
            libc::SYS_recvmsg,
            CHILD_FD,
            &mut msg,
            libc::MSG_CMSG_CLOEXEC,
        )
    };
    if n == 0 {
        unsafe { finish(0) }
    }
    if n != std::mem::size_of::<Packet>() as libc::c_long
        || msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
        || !packet.matches(nonce, parent_pid)
        || packet.errno != 0
        || !unsafe { libc::CMSG_FIRSTHDR(&msg) }.is_null()
    {
        unsafe { rejected(nonce) }
    }
    if packet.phase == Phase::Stop as u32 {
        unsafe { finish(0) }
    }
    if packet.phase != expected as u32 {
        unsafe { rejected(nonce) }
    }
}

pub(super) unsafe fn run(nonce: [u8; 16], parent_pid: u32, _mode: Mode) -> ! {
    unsafe {
        #[cfg(test)]
        STAGE.store(1, std::sync::atomic::Ordering::Relaxed);
        let inputs = receive_runtime(nonce, parent_pid);
        if libc::syscall(libc::SYS_getpid) != 1
            || libc::syscall(libc::SYS_geteuid) != 0
            || libc::syscall(libc::SYS_getegid) != 0
        {
            rejected(nonce)
        }
        require_root(inputs[0], nonce);
        let initial_init = meta(inputs[1], nonce);
        let init_fs = fs(inputs[1], nonce);
        if initial_init.st_mode != libc::S_IFREG | 0o555
            || initial_init.st_nlink != 1
            || initial_init.st_uid != 0
            || initial_init.st_gid != 0
            || initial_init.st_size < 64
            || init_fs.f_flags as u64 & RO_IMAGE != RO_IMAGE
            || init_fs.f_flags as u64 & NOEXEC != 0
        {
            rejected(nonce)
        }
        exact_names(inputs[0], &[b"apex", b"linkerconfig", b"rc"], nonce);
        let root = directory(libc::AT_FDCWD, c"/", nonce);
        if fs(root, nonce).f_type != TMPFS_MAGIC {
            rejected(nonce)
        }
        if libc::syscall(
            libc::SYS_mkdirat,
            root,
            c".droidloom-runtime".as_ptr(),
            0o700_u32,
        ) != 0
        {
            failed(nonce, line!())
        }
        let runtime_target = directory(root, c".droidloom-runtime", nonce);
        attach(inputs[0], runtime_target, nonce);
        close(runtime_target);
        let runtime = directory(root, c".droidloom-runtime", nonce);
        if !same_inode(&meta(inputs[0], nonce), &meta(runtime, nonce)) {
            rejected(nonce)
        }
        #[cfg(test)]
        STAGE.store(2, std::sync::atomic::Ordering::Relaxed);
        project_dir(runtime, root, c"apex", nonce);
        project_dir(runtime, root, c"linkerconfig", nonce);
        let rc = directory(runtime, c"rc", nonce);
        require_root(rc, nonce);
        exact_names(
            rc,
            &[
                b"init.rc",
                b"bootconfig",
                b"cgroups.json",
                b"task_profiles.json",
            ],
            nonce,
        );
        let system = directory(root, c"system", nonce);
        let bin = directory(system, c"bin", nonce);
        let etc = directory(system, c"etc", nonce);
        let init_dir = directory(etc, c"init", nonce);
        let hw = directory(init_dir, c"hw", nonce);
        let proc = directory(root, c"proc", nonce);
        project_rc(rc, c"init.rc", hw, c"init.rc", nonce);
        project_rc(rc, c"bootconfig", proc, c"bootconfig", nonce);
        project_rc(rc, c"cgroups.json", etc, c"cgroups.json", nonce);
        project_rc(rc, c"task_profiles.json", etc, c"task_profiles.json", nonce);
        #[cfg(test)]
        STAGE.store(3, std::sync::atomic::Ordering::Relaxed);
        let target = opened(bin, c"init", libc::O_PATH, nonce);
        if meta(target, nonce).st_mode & libc::S_IFMT != libc::S_IFREG {
            rejected(nonce)
        }
        // Already an anonymous detached file mount from the initial-root broker.
        attach(inputs[1], target, nonce);
        close(target);
        let executable = check_projection(bin, c"init", &initial_init, false, nonce);
        // Keep the original held identity through actual exec. Do not execute
        // the host-origin pathname, or independently reopen an untrusted path.
        retain_init(executable, nonce);
        send(nonce, Phase::RuntimeReady, 0, 1);
        command(nonce, parent_pid, Phase::ExecInit);
        #[cfg(test)]
        STAGE.store(4, std::sync::atomic::Ordering::Relaxed);
        let current = meta(EXEC_FD, nonce);
        if !same_inode(&initial_init, &current) {
            rejected(nonce)
        }
        // A private zero-cap test cannot authorize Android. This actual
        // production exec path shares the same raw helper but fails before
        // capability mutation until a reviewed Android contract exists.
        let final_caps = super::final_exec::prepare(
            super::final_exec::FinalCapabilityProfile::AndroidUnqualified,
        );
        if final_caps != 0 {
            *libc::__errno_location() = final_caps;
            failed(nonce, line!())
        }
        let policy = crate::production_runtime_seccomp::install();
        if policy != 0 {
            *libc::__errno_location() = policy;
            failed(nonce, line!())
        }
        // Stdio is private /dev/null, never the host journal, console or kmsg.
        let null = opened(libc::AT_FDCWD, c"/dev/null", libc::O_RDWR, nonce);
        let null_meta = meta(null, nonce);
        if null_meta.st_mode & libc::S_IFMT != libc::S_IFCHR
            || null_meta.st_rdev != libc::makedev(1, 3)
        {
            rejected(nonce)
        }
        for fd in 0..3 {
            if null != fd && libc::syscall(libc::SYS_dup3, null, fd, 0) != fd as libc::c_long {
                failed(nonce, line!())
            }
            // openat can reuse fd 0. In that case dup3 is deliberately skipped,
            // so explicitly remove the original O_CLOEXEC and verify every
            // standard descriptor before the fixed executable is entered.
            if libc::syscall(libc::SYS_fcntl, fd, libc::F_SETFD, 0) != 0
                || libc::syscall(libc::SYS_fcntl, fd, libc::F_GETFD) != 0
            {
                failed(nonce, line!())
            }
        }
        if null > 2 {
            close(null)
        }
        // No success is claimed here. The parent must observe CLOEXEC plus
        // live exact pidfd/exe identity and later genuine property readiness.
        send(nonce, Phase::ExecArmed, 0, 1);
        #[cfg(test)]
        STAGE.store(5, std::sync::atomic::Ordering::Relaxed);
        let argv = [
            c"/system/bin/init".as_ptr(),
            c"second_stage".as_ptr(),
            std::ptr::null(),
        ];
        let env = [
            c"PATH=/system/bin:/system/xbin".as_ptr(),
            c"ANDROID_ROOT=/system".as_ptr(),
            c"ANDROID_DATA=/data".as_ptr(),
            c"ANDROID_RUNTIME_ROOT=/apex/com.android.runtime".as_ptr(),
            std::ptr::null(),
        ];
        *libc::__errno_location() =
            super::final_exec::exec_held(EXEC_FD, argv.as_ptr(), env.as_ptr());
        failed(nonce, line!())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn production_runtime_diagnostics_are_disjoint_from_previous_phases() {
        let v = 0x4000_0000 | (5 << 24) | (123 << 12) | libc::EACCES as u32;
        assert_eq!(
            decode_private_failure(v as i32),
            Some((5, 123, libc::EACCES))
        );
        for v in [0, -1, libc::EACCES, 0x31001001, 0x45000001, 0x46001001] {
            assert_eq!(decode_private_failure(v), None)
        }
    }
}
