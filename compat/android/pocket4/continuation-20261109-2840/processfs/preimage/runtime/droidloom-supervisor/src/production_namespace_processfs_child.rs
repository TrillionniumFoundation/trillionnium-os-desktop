//! Fixed raw child construction of PID-bound proc and a fresh devpts instance.
//!
//! This runs only after the private empty root and private DEV barriers. It
//! creates no host mounts and cannot exec Android. Only its own authenticated
//! proc fs_context and the broker's fixed detached proc mount cross the channel.
//! Proc is read-only at this preparation stage; any later runtime write policy
//! needs a separately admitted transition rather than silently clearing RO.

use super::empty_root::{KernelStatfs, entry_record};
use super::{CHILD_FD, Mode, Packet, Phase, fail, finish, send};
use std::ffi::CStr;
use std::os::fd::RawFd;

const PROC_MAGIC: libc::c_long = 0x9fa0;
const DEVPTS_MAGIC: libc::c_long = 0x1cd1;
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const ATTR_RDONLY: u32 = 1;
const ATTR_NOSUID: u32 = 2;
const ATTR_NODEV: u32 = 4;
const ATTR_NOEXEC: u32 = 8;
const PROC_FLAGS: u32 = ATTR_RDONLY | ATTR_NOSUID | ATTR_NODEV | ATTR_NOEXEC;
const PTS_FLAGS: u32 = ATTR_NOSUID | ATTR_NOEXEC;
const MOVE_EMPTY: u32 = 0x04 | 0x40;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const TIOCGPTN: libc::c_ulong = 0x8004_5430;
const TIOCSPTLCK: libc::c_ulong = 0x4004_5431;
const TIOCGPTPEER: libc::c_ulong = 0x5441;
const MAX_DIRECTORY_BYTES: usize = 256 * 1024;

// Test diagnostics travel only in an authenticated Failed packet, never Ready.
// No extra descriptor or operation is accepted and every original rejection
// still terminates this exact owned child. The production build keeps errno.
#[cfg(test)]
const DIAGNOSTIC_FAILURE_BASE: u32 = 0x1000_0000;
#[cfg(test)]
static DIAGNOSTIC_STAGE: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);

#[cfg(test)]
pub(super) fn decode_private_failure(value: i32) -> Option<(u32, u32, i32)> {
    let bits = value as u32;
    if bits >> 28 != 1 {
        return None;
    }
    let stage = (bits >> 24) & 15;
    let line = (bits >> 12) & 4095;
    let errno = (bits & 4095) as i32;
    if stage > 3 || line == 0 || errno == 0 {
        return None;
    }
    Some((stage, line, errno))
}

unsafe fn syscall_failure(nonce: [u8; 16], source_line: u32) -> ! {
    #[cfg(test)]
    {
        let raw = unsafe { *libc::__errno_location() };
        let errno = if raw > 0 && raw < 4096 {
            raw as u32
        } else {
            libc::EIO as u32
        };
        let stage = DIAGNOSTIC_STAGE.load(std::sync::atomic::Ordering::Relaxed);
        // The raw child is one post-clone thread. This lock-free atomic is
        // private COW memory; no parent thread or external input sets its tag.
        let value = DIAGNOSTIC_FAILURE_BASE | (stage << 24) | (source_line << 12) | errno;
        unsafe {
            send(nonce, Phase::Failed, value as i32, 1);
            finish(127)
        }
    }
    #[cfg(not(test))]
    {
        let _ = source_line;
        unsafe { fail(nonce, 1) }
    }
}

unsafe fn protocol_failure(nonce: [u8; 16]) -> ! {
    unsafe {
        *libc::__errno_location() = libc::EPROTO;
        syscall_failure(nonce, line!())
    }
}

/// Commands carry no descriptors. Only the separate, fixed proc-context
/// round trip below accepts one FD in each authenticated, ordered phase.
unsafe fn command(nonce: [u8; 16], parent_pid: u32, wanted: Phase) {
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
        unsafe { protocol_failure(nonce) }
    }
    if packet.phase == Phase::Stop as u32 {
        unsafe { finish(0) }
    }
    if packet.phase != wanted as u32 {
        unsafe { protocol_failure(nonce) }
    }
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
        unsafe { syscall_failure(nonce, line!()) }
    }
    fd as RawFd
}

unsafe fn meta(fd: RawFd, nonce: [u8; 16]) -> libc::stat {
    let mut value: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstat, fd, &mut value) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    value
}

unsafe fn filesystem(
    fd: RawFd,
    kind: libc::c_long,
    required: u32,
    forbidden: u32,
    nonce: [u8; 16],
) {
    let mut value: KernelStatfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut value) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    if value.f_type != kind
        || value.f_flags as u64 & required as u64 != required as u64
        || value.f_flags as u64 & forbidden as u64 != 0
    {
        unsafe { protocol_failure(nonce) }
    }
}

unsafe fn empty_directory(fd: RawFd, nonce: [u8; 16]) {
    let directory = unsafe { opened(fd, c".", libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
    let mut buffer = [0_u8; 4096];
    loop {
        let n = unsafe {
            libc::syscall(
                libc::SYS_getdents64,
                directory,
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        if n < 0 {
            unsafe { syscall_failure(nonce, line!()) }
        }
        if n == 0 {
            break;
        }
        if n as usize > buffer.len() {
            unsafe { protocol_failure(nonce) }
        }
        let mut at = 0;
        while at < n as usize {
            let (length, name) = match entry_record(&buffer[at..n as usize]) {
                Some(value) => value,
                None => unsafe { protocol_failure(nonce) },
            };
            at += length;
            if name != b"." && name != b".." {
                unsafe { protocol_failure(nonce) }
            }
        }
    }
    unsafe {
        libc::syscall(libc::SYS_close, directory);
    }
}

unsafe fn target(parent: RawFd, name: &CStr, allow_empty_existing: bool, nonce: [u8; 16]) -> RawFd {
    let created =
        unsafe { libc::syscall(libc::SYS_mkdirat, parent, name.as_ptr(), 0o755_u32) } == 0;
    if !created && !(allow_empty_existing && unsafe { *libc::__errno_location() } == libc::EEXIST) {
        unsafe { syscall_failure(nonce, line!()) }
    }
    let fd = unsafe { opened(parent, name, libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
    // Inherited umask does not determine an owned new mountpoint's mode. Never
    // chmod an existing base directory: it remains an immutable lower mount.
    if created && unsafe { libc::syscall(libc::SYS_fchmod, fd, 0o755_u32) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    let got = unsafe { meta(fd, nonce) };
    let original = unsafe { meta(parent, nonce) };
    if got.st_mode & libc::S_IFMT != libc::S_IFDIR
        || got.st_mode & 0o7022 != 0
        || got.st_uid != 0
        || got.st_gid != 0
    {
        unsafe { protocol_failure(nonce) }
    }
    if got.st_dev != original.st_dev {
        // The GSI's empty /proc directory can already be an admitted RO clone.
        // Permit only that same verified system filesystem, not any inherited
        // host mount or arbitrary cross-filesystem path.
        if !allow_empty_existing || name.to_bytes() != b"proc" {
            unsafe { protocol_failure(nonce) }
        }
        let system =
            unsafe { opened(parent, c"system", libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
        let system_meta = unsafe { meta(system, nonce) };
        let mut fs: KernelStatfs = unsafe { std::mem::zeroed() };
        if got.st_dev != system_meta.st_dev
            || unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut fs) } != 0
            || ![0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&fs.f_type)
            || fs.f_flags as u64 & 7 != 7
        {
            unsafe { protocol_failure(nonce) }
        }
        unsafe {
            libc::syscall(libc::SYS_close, system);
        }
    }
    unsafe {
        empty_directory(fd, nonce);
    }
    fd
}

unsafe fn context(kind: &CStr, nonce: [u8; 16]) -> RawFd {
    let raw = unsafe { libc::syscall(libc::SYS_fsopen, kind.as_ptr(), 1_u32) };
    if raw < 0 || raw > i32::MAX as libc::c_long {
        unsafe { syscall_failure(nonce, line!()) }
    }
    raw as RawFd
}

unsafe fn option(context: RawFd, key: &CStr, value: Option<&CStr>, nonce: [u8; 16]) {
    let (command, pointer) = match value {
        Some(text) => (1_u32, text.as_ptr()),
        None => (0_u32, std::ptr::null()),
    };
    if unsafe {
        libc::syscall(
            libc::SYS_fsconfig,
            context,
            command,
            key.as_ptr(),
            pointer,
            0,
        )
    } != 0
    {
        unsafe { syscall_failure(nonce, line!()) }
    }
}

unsafe fn create_context(context: RawFd, nonce: [u8; 16]) {
    if unsafe {
        libc::syscall(
            libc::SYS_fsconfig,
            context,
            6_u32,
            std::ptr::null::<libc::c_char>(),
            std::ptr::null::<libc::c_char>(),
            0,
        )
    } != 0
    {
        unsafe { syscall_failure(nonce, line!()) }
    }
}

unsafe fn attach(context: RawFd, target: RawFd, flags: u32, nonce: [u8; 16]) {
    unsafe {
        create_context(context, nonce);
    }
    let mount = unsafe { libc::syscall(libc::SYS_fsmount, context, 1_u32, flags) };
    if mount < 0 || mount > i32::MAX as libc::c_long {
        unsafe { syscall_failure(nonce, line!()) }
    }
    if unsafe {
        libc::syscall(
            libc::SYS_move_mount,
            mount,
            c"".as_ptr(),
            target,
            c"".as_ptr(),
            MOVE_EMPTY,
        )
    } != 0
    {
        unsafe { syscall_failure(nonce, line!()) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, mount);
        libc::syscall(libc::SYS_close, context);
        libc::syscall(libc::SYS_close, target);
    }
}

// The context is created by this exact PID 1 before crossing the private
// channel. The initial-userns broker only materializes its detached mount;
// no external descriptor, pathname, filesystem kind or flags are accepted.
unsafe fn send_proc_context(context: RawFd, nonce: [u8; 16]) {
    let packet = Packet::new(nonce, Phase::ProcContextReady, 0, 1);
    let mut iov = libc::iovec {
        iov_base: (&packet as *const Packet).cast_mut().cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 8];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = ancillary.as_mut_ptr().cast();
    msg.msg_controllen = unsafe { libc::CMSG_SPACE(std::mem::size_of::<i32>() as u32) } as usize;
    let header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    unsafe {
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of::<i32>() as u32) as usize;
        std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<i32>(), context);
    }
    let n = unsafe {
        libc::syscall(
            libc::SYS_sendmsg,
            CHILD_FD,
            &msg,
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
        )
    };
    if n != std::mem::size_of::<Packet>() as libc::c_long {
        unsafe { syscall_failure(nonce, line!()) }
    }
    // Do not retain a second fs_context after delivering this single phase.
    if unsafe { libc::syscall(libc::SYS_close, context) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
}

unsafe fn receive_proc_mount(nonce: [u8; 16], parent_pid: u32) -> RawFd {
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
    {
        unsafe { protocol_failure(nonce) }
    }
    let header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    if packet.phase == Phase::Stop as u32 && header.is_null() {
        unsafe { finish(0) }
    }
    if packet.phase != Phase::ProcMountReady as u32 || header.is_null() {
        unsafe { protocol_failure(nonce) }
    }
    let h = unsafe { &*header };
    if h.cmsg_level != libc::SOL_SOCKET
        || h.cmsg_type != libc::SCM_RIGHTS
        || h.cmsg_len != unsafe { libc::CMSG_LEN(std::mem::size_of::<i32>() as u32) } as usize
        || !unsafe { libc::CMSG_NXTHDR(&msg, header) }.is_null()
    {
        unsafe { protocol_failure(nonce) }
    }
    let raw = unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<i32>()) };
    if raw < 0 || raw == CHILD_FD {
        unsafe { protocol_failure(nonce) }
    }
    // Keep the control endpoint at 3 and avoid assumptions about closed stdio.
    let mount = unsafe { libc::syscall(libc::SYS_fcntl, raw, libc::F_DUPFD_CLOEXEC, 4) };
    if mount < 4 || mount > i32::MAX as libc::c_long {
        unsafe { syscall_failure(nonce, line!()) }
    }
    if unsafe { libc::syscall(libc::SYS_close, raw) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    mount as RawFd
}

unsafe fn attach_brokered_proc(
    context: RawFd,
    target: RawFd,
    dev: RawFd,
    nonce: [u8; 16],
    parent_pid: u32,
    _mode: Mode,
) {
    unsafe {
        create_context(context, nonce);
    }
    #[cfg(test)]
    let context = if matches!(_mode, Mode::ProcessFilesystemsBadContext) {
        // The separately reviewed private control substitutes only this new
        // private DEV inode; there is no production caller-selected FD hook.
        if unsafe { libc::syscall(libc::SYS_close, context) } != 0 {
            unsafe { syscall_failure(nonce, line!()) }
        }
        unsafe { opened(dev, c"null", libc::O_PATH, nonce) }
    } else {
        context
    };
    #[cfg(not(test))]
    let _ = dev;
    unsafe {
        send_proc_context(context, nonce);
        let mount = receive_proc_mount(nonce, parent_pid);
        verify_proc(mount, nonce);
        if libc::syscall(
            libc::SYS_move_mount,
            mount,
            c"".as_ptr(),
            target,
            c"".as_ptr(),
            MOVE_EMPTY,
        ) != 0
        {
            syscall_failure(nonce, line!());
        }
        libc::syscall(libc::SYS_close, mount);
        libc::syscall(libc::SYS_close, target);
    }
}

pub(super) fn numeric_pid_name(name: &[u8]) -> bool {
    !name.is_empty() && name.iter().all(u8::is_ascii_digit)
}

unsafe fn verify_proc(proc: RawFd, nonce: [u8; 16]) {
    unsafe {
        filesystem(proc, PROC_MAGIC, PROC_FLAGS, 0, nonce);
    }
    if unsafe { libc::syscall(libc::SYS_getpid) } != 1 {
        unsafe { protocol_failure(nonce) }
    }
    let directory = unsafe { opened(proc, c".", libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
    let mut buffer = [0_u8; 4096];
    let mut total = 0_usize;
    let mut saw_one = false;
    loop {
        let n = unsafe {
            libc::syscall(
                libc::SYS_getdents64,
                directory,
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        if n < 0 {
            unsafe { syscall_failure(nonce, line!()) }
        }
        if n == 0 {
            break;
        }
        if n as usize > buffer.len() || total + n as usize > MAX_DIRECTORY_BYTES {
            unsafe { protocol_failure(nonce) }
        }
        total += n as usize;
        let mut at = 0;
        while at < n as usize {
            let (length, name) = match entry_record(&buffer[at..n as usize]) {
                Some(value) => value,
                None => unsafe { protocol_failure(nonce) },
            };
            at += length;
            if numeric_pid_name(name) {
                if name != b"1" || saw_one {
                    unsafe { protocol_failure(nonce) }
                }
                saw_one = true;
            }
        }
    }
    unsafe {
        libc::syscall(libc::SYS_close, directory);
    }
    if !saw_one {
        unsafe { protocol_failure(nonce) }
    }
    for (link, wanted) in [
        (c"self", b"1".as_slice()),
        (c"thread-self", b"1/task/1".as_slice()),
    ] {
        let mut got = [0_u8; 32];
        let n = unsafe {
            libc::syscall(
                libc::SYS_readlinkat,
                proc,
                link.as_ptr(),
                got.as_mut_ptr(),
                got.len(),
            )
        };
        if n != wanted.len() as libc::c_long || &got[..wanted.len()] != wanted {
            unsafe { protocol_failure(nonce) }
        }
    }
    // Follow only a fixed procfs-generated namespace link. The parent then
    // matches this inode to its independently PIDFD-held exact PID namespace.
    let one = unsafe { opened(proc, c"1", libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
    let ns = unsafe { opened(one, c"ns", libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
    let pid = unsafe {
        libc::syscall(
            libc::SYS_openat,
            ns,
            c"pid".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
            0,
        )
    };
    if pid < 0
        || pid > i32::MAX as libc::c_long
        || unsafe { libc::syscall(libc::SYS_ioctl, pid, NS_GET_NSTYPE, 0 as libc::c_ulong) }
            != libc::CLONE_NEWPID as libc::c_long
    {
        unsafe { protocol_failure(nonce) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, pid);
        libc::syscall(libc::SYS_close, ns);
        libc::syscall(libc::SYS_close, one);
    }
}

unsafe fn verify_pts(pts: RawFd, nonce: [u8; 16]) {
    unsafe {
        filesystem(
            pts,
            DEVPTS_MAGIC,
            PTS_FLAGS,
            ATTR_RDONLY | ATTR_NODEV,
            nonce,
        );
    }
    let root = unsafe { meta(pts, nonce) };
    if root.st_mode != (libc::S_IFDIR | 0o755) {
        unsafe { protocol_failure(nonce) }
    }
    let fd = unsafe { opened(pts, c"ptmx", libc::O_PATH, nonce) };
    let got = unsafe { meta(fd, nonce) };
    if got.st_dev != root.st_dev
        || got.st_mode != (libc::S_IFCHR | 0o666)
        || got.st_uid != 0
        || got.st_gid != 0
        || got.st_rdev != libc::makedev(5, 2)
        || got.st_nlink != 1
    {
        unsafe { protocol_failure(nonce) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, fd);
    }
    let entries = unsafe { opened(pts, c".", libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
    let mut buffer = [0_u8; 4096];
    let mut seen = false;
    loop {
        let n = unsafe {
            libc::syscall(
                libc::SYS_getdents64,
                entries,
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        if n < 0 {
            unsafe { syscall_failure(nonce, line!()) }
        }
        if n == 0 {
            break;
        }
        if n as usize > buffer.len() {
            unsafe { protocol_failure(nonce) }
        }
        let mut at = 0;
        while at < n as usize {
            let (length, name) = match entry_record(&buffer[at..n as usize]) {
                Some(value) => value,
                None => unsafe { protocol_failure(nonce) },
            };
            at += length;
            if name == b"." || name == b".." {
                continue;
            }
            if name != b"ptmx" || seen {
                unsafe { protocol_failure(nonce) }
            }
            seen = true;
        }
    }
    unsafe {
        libc::syscall(libc::SYS_close, entries);
    }
    if !seen {
        unsafe { protocol_failure(nonce) }
    }
}

unsafe fn descriptor_barrier(nonce: [u8; 16]) {
    if unsafe { libc::syscall(libc::SYS_close_range, 4_u32, u32::MAX, 0) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, 0);
        libc::syscall(libc::SYS_close, 1);
        libc::syscall(libc::SYS_close, 2);
    }
}

pub(super) unsafe fn run(nonce: [u8; 16], parent_pid: u32, _mode: Mode) -> ! {
    unsafe {
        command(nonce, parent_pid, Phase::PrepareProcessFilesystems);
        let root = opened(
            libc::AT_FDCWD,
            c"/",
            libc::O_RDONLY | libc::O_DIRECTORY,
            nonce,
        );
        let dev = opened(root, c"dev", libc::O_RDONLY | libc::O_DIRECTORY, nonce);
        filesystem(
            root,
            TMPFS_MAGIC,
            ATTR_NOSUID | ATTR_NODEV,
            ATTR_RDONLY,
            nonce,
        );
        filesystem(dev, TMPFS_MAGIC, PTS_FLAGS, ATTR_RDONLY | ATTR_NODEV, nonce);
        let root_dev = meta(root, nonce).st_dev;
        let dev_dev = meta(dev, nonce).st_dev;
        if root_dev == dev_dev {
            protocol_failure(nonce);
        }

        #[cfg(test)]
        DIAGNOSTIC_STAGE.store(1, std::sync::atomic::Ordering::Relaxed);
        let proc_target = target(root, c"proc", true, nonce);
        let proc_context = context(c"proc", nonce);
        option(proc_context, c"hidepid", Some(c"2"), nonce);
        option(proc_context, c"gid", Some(c"3009"), nonce);
        attach_brokered_proc(proc_context, proc_target, dev, nonce, parent_pid, _mode);
        let proc = opened(root, c"proc", libc::O_RDONLY | libc::O_DIRECTORY, nonce);
        verify_proc(proc, nonce);

        #[cfg(test)]
        DIAGNOSTIC_STAGE.store(2, std::sync::atomic::Ordering::Relaxed);
        let pts_target = target(dev, c"pts", false, nonce);
        let pts_context = context(c"devpts", nonce);
        option(pts_context, c"newinstance", None, nonce);
        option(pts_context, c"uid", Some(c"0"), nonce);
        option(pts_context, c"gid", Some(c"5"), nonce);
        option(pts_context, c"mode", Some(c"0620"), nonce);
        option(pts_context, c"ptmxmode", Some(c"0666"), nonce);
        option(pts_context, c"max", Some(c"1024"), nonce);
        attach(pts_context, pts_target, PTS_FLAGS, nonce);
        let pts = opened(dev, c"pts", libc::O_RDONLY | libc::O_DIRECTORY, nonce);
        verify_pts(pts, nonce);
        let proc_dev = meta(proc, nonce).st_dev;
        let pts_dev = meta(pts, nonce).st_dev;
        if proc_dev == pts_dev
            || [root_dev, dev_dev].contains(&proc_dev)
            || [root_dev, dev_dev].contains(&pts_dev)
        {
            protocol_failure(nonce);
        }

        // The only newly created link is relative and cannot reach any host
        // terminal. It targets the just-attached instance in this private /dev.
        if libc::syscall(
            libc::SYS_symlinkat,
            c"pts/ptmx".as_ptr(),
            dev,
            c"ptmx".as_ptr(),
        ) != 0
        {
            syscall_failure(nonce, line!());
        }
        let link = opened(dev, c"ptmx", libc::O_PATH, nonce);
        let link_meta = meta(link, nonce);
        let mut link_value = [0_u8; 32];
        let n = libc::syscall(
            libc::SYS_readlinkat,
            dev,
            c"ptmx".as_ptr(),
            link_value.as_mut_ptr(),
            link_value.len(),
        );
        if n != 8
            || &link_value[..8] != b"pts/ptmx"
            || link_meta.st_mode != (libc::S_IFLNK | 0o777)
            || link_meta.st_dev != dev_dev
            || link_meta.st_uid != 0
            || link_meta.st_gid != 0
        {
            protocol_failure(nonce);
        }
        descriptor_barrier(nonce);
        send(nonce, Phase::ProcessFilesystemsReady, 0, 1);
        #[cfg(test)]
        if matches!(_mode, Mode::ProcessFilesystemsControl) {
            command(nonce, parent_pid, Phase::ProbeProcessFilesystems);
            #[cfg(test)]
            DIAGNOSTIC_STAGE.store(3, std::sync::atomic::Ordering::Relaxed);
            private_pty_control(nonce);
            descriptor_barrier(nonce);
            send(nonce, Phase::ProcessFilesystemsChecked, 0, 1);
        }
        // Binder, runtime/APEX, sysctl/write policy, seccomp and exec remain
        // absent. Parked namespace preparation is never a Running cell.
        command(nonce, parent_pid, Phase::Stop);
        finish(0);
    }
}

#[cfg(test)]
unsafe fn private_pty_control(nonce: [u8; 16]) {
    unsafe {
        let proc = opened(
            libc::AT_FDCWD,
            c"/proc",
            libc::O_RDONLY | libc::O_DIRECTORY,
            nonce,
        );
        verify_proc(proc, nonce);
        let pts = opened(
            libc::AT_FDCWD,
            c"/dev/pts",
            libc::O_RDONLY | libc::O_DIRECTORY,
            nonce,
        );
        verify_pts(pts, nonce);
        let root = meta(pts, nonce);
        let master = opened(pts, c"ptmx", libc::O_RDWR | libc::O_NOCTTY, nonce);
        let mut index = u32::MAX;
        let mut unlock = 0_i32;
        if libc::syscall(libc::SYS_ioctl, master, TIOCGPTN, &mut index) != 0
            || index != 0
            || libc::syscall(libc::SYS_ioctl, master, TIOCSPTLCK, &mut unlock) != 0
        {
            protocol_failure(nonce);
        }
        // The kernel returns this exact master's peer. No host /dev/pts lookup,
        // grantpt helper, session change, controlling terminal or extra process.
        let slave = libc::syscall(
            libc::SYS_ioctl,
            master,
            TIOCGPTPEER,
            libc::O_RDWR | libc::O_NOCTTY | libc::O_NONBLOCK | libc::O_CLOEXEC,
        );
        if slave < 0 || slave > i32::MAX as libc::c_long {
            syscall_failure(nonce, line!());
        }
        let got = meta(slave as RawFd, nonce);
        if got.st_dev != root.st_dev
            || got.st_mode != (libc::S_IFCHR | 0o620)
            || got.st_uid != 0
            || got.st_gid != 5
            || got.st_rdev != libc::makedev(136, 0)
            || got.st_nlink != 1
        {
            protocol_failure(nonce);
        }
        let payload = b"droidloom-pty";
        if libc::syscall(libc::SYS_write, slave, payload.as_ptr(), payload.len())
            != payload.len() as libc::c_long
        {
            protocol_failure(nonce);
        }
        let mut poll = libc::pollfd {
            fd: master,
            events: libc::POLLIN,
            revents: 0,
        };
        if libc::syscall(libc::SYS_poll, &mut poll, 1_usize, 1000_i32) != 1
            || poll.revents != libc::POLLIN
        {
            protocol_failure(nonce);
        }
        let mut bytes = [0_u8; 32];
        let n = libc::syscall(libc::SYS_read, master, bytes.as_mut_ptr(), bytes.len());
        if n != payload.len() as libc::c_long || &bytes[..payload.len()] != payload {
            protocol_failure(nonce);
        }
        libc::syscall(libc::SYS_close, slave);
        libc::syscall(libc::SYS_close, master);
        // Closing both ends must remove the only allocated slave inode.
        verify_pts(pts, nonce);
        libc::syscall(libc::SYS_close, pts);
        libc::syscall(libc::SYS_close, proc);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn private_failure_site_is_error_only_and_bounded() {
        let code = DIAGNOSTIC_FAILURE_BASE | (1 << 24) | (317 << 12) | libc::EPERM as u32;
        assert_eq!(
            decode_private_failure(code as i32),
            Some((1, 317, libc::EPERM))
        );
        for value in [
            libc::EPERM,
            0,
            -1,
            (DIAGNOSTIC_FAILURE_BASE | (4 << 24) | (1 << 12) | 1) as i32,
            (DIAGNOSTIC_FAILURE_BASE | 1) as i32,
            (DIAGNOSTIC_FAILURE_BASE | (1 << 12)) as i32,
        ] {
            assert_eq!(decode_private_failure(value), None);
        }
    }

    #[test]
    fn proc_numeric_names_do_not_treat_non_pid_entries_as_processes() {
        for value in [b"1".as_slice(), b"2", b"0001", b"999999999999999999999"] {
            assert!(numeric_pid_name(value));
        }
        for value in [
            b"".as_slice(),
            b"self",
            b"thread-self",
            b"1/status",
            b"-1",
            b"1\0",
        ] {
            assert!(!numeric_pid_name(value));
        }
    }
}
