//! Fixed raw child creation of one private Binder filesystem and three contexts.
//!
//! Entry is allowed only after the owned PID1 has completed the private root,
//! DEV and process-filesystem barriers. No descriptor or host path is accepted.
//! This preparation stage proves device construction and the kernel version;
//! it does not execute Android, install a context manager, or grant IPC/runtime
//! qualification. The later fixed IPC control must prove transactions separately.

use super::empty_root::{KernelStatfs, entry_record};
use super::{CHILD_FD, Mode, Packet, Phase, fail, finish, send};
use std::ffi::CStr;
use std::os::fd::RawFd;

const BINDERFS_MAGIC: libc::c_long = 0x6c6f_6f70;
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const PROC_MAGIC: libc::c_long = 0x9fa0;
const ATTR_RDONLY: u32 = 1;
const ATTR_NOSUID: u32 = 2;
const ATTR_NODEV: u32 = 4;
const ATTR_NOEXEC: u32 = 8;
const BINDER_FLAGS: u32 = ATTR_NOSUID | ATTR_NOEXEC;
const MOVE_EMPTY: u32 = 0x04 | 0x40;
const BINDER_CTL_ADD: libc::c_ulong = 0xc108_6201;
const BINDER_VERSION: libc::c_ulong = 0xc004_6209;
const MAX_DIRECTORY_BYTES: usize = 64 * 1024;

#[repr(C)]
struct BinderDevice {
    name: [u8; 256],
    major: u32,
    minor: u32,
}

#[repr(C)]
struct BinderVersion {
    protocol_version: i32,
}

const _: [(); 264] = [(); std::mem::size_of::<BinderDevice>()];
const _: [(); 4] = [(); std::mem::size_of::<BinderVersion>()];

#[cfg(test)]
const DIAGNOSTIC_FAILURE_BASE: u32 = 0x2000_0000;
#[cfg(test)]
static DIAGNOSTIC_STAGE: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);

#[cfg(test)]
pub(super) fn decode_private_failure(value: i32) -> Option<(u32, u32, i32)> {
    let bits = value as u32;
    let stage = (bits >> 24) & 15;
    let source_line = (bits >> 12) & 4095;
    let errno = (bits & 4095) as i32;
    if bits >> 28 != 2 || stage > 3 || source_line == 0 || errno == 0 {
        return None;
    }
    Some((stage, source_line, errno))
}

pub(super) unsafe fn syscall_failure(nonce: [u8; 16], source_line: u32) -> ! {
    #[cfg(test)]
    {
        let raw = unsafe { *libc::__errno_location() };
        let errno = if raw > 0 && raw < 4096 {
            raw as u32
        } else {
            libc::EIO as u32
        };
        let stage = DIAGNOSTIC_STAGE.load(std::sync::atomic::Ordering::Relaxed);
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

pub(super) unsafe fn protocol_failure(nonce: [u8; 16]) -> ! {
    unsafe {
        *libc::__errno_location() = libc::EPROTO;
        syscall_failure(nonce, line!())
    }
}

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

unsafe fn exact_names(parent: RawFd, expected: &[&[u8]], nonce: [u8; 16]) {
    if expected.len() > 16 {
        unsafe { protocol_failure(nonce) }
    }
    let fd = unsafe { opened(parent, c".", libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
    let mut buffer = [0_u8; 4096];
    let mut total = 0_usize;
    let mut seen = 0_u32;
    loop {
        let n =
            unsafe { libc::syscall(libc::SYS_getdents64, fd, buffer.as_mut_ptr(), buffer.len()) };
        if n < 0 {
            unsafe { syscall_failure(nonce, line!()) }
        }
        if n == 0 {
            break;
        }
        if n as usize > buffer.len() || total > MAX_DIRECTORY_BYTES - n as usize {
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
            if name == b"." || name == b".." {
                continue;
            }
            let index = match expected.iter().position(|entry| *entry == name) {
                Some(value) => value,
                None => unsafe { protocol_failure(nonce) },
            };
            let bit = 1_u32 << index;
            if seen & bit != 0 {
                unsafe { protocol_failure(nonce) }
            }
            seen |= bit;
        }
    }
    if seen != (1_u32 << expected.len()) - 1 {
        unsafe { protocol_failure(nonce) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, fd);
    }
}

unsafe fn new_target(dev: RawFd, nonce: [u8; 16]) -> RawFd {
    // Existing names, links or mounts are rejected. This is a new guest node.
    if unsafe { libc::syscall(libc::SYS_mkdirat, dev, c"binderfs".as_ptr(), 0o755) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    let fd = unsafe { opened(dev, c"binderfs", libc::O_RDONLY | libc::O_DIRECTORY, nonce) };
    if unsafe { libc::syscall(libc::SYS_fchmod, fd, 0o755) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    let made = unsafe { meta(fd, nonce) };
    let parent = unsafe { meta(dev, nonce) };
    if made.st_dev != parent.st_dev
        || made.st_mode != (libc::S_IFDIR | 0o755)
        || made.st_uid != 0
        || made.st_gid != 0
    {
        unsafe { protocol_failure(nonce) }
    }
    unsafe {
        empty_directory(fd, nonce);
    }
    fd
}

unsafe fn verify_features(binder: RawFd, nonce: [u8; 16]) {
    let root = unsafe { meta(binder, nonce) };
    let fd = unsafe {
        opened(
            binder,
            c"features",
            libc::O_RDONLY | libc::O_DIRECTORY,
            nonce,
        )
    };
    let directory = unsafe { meta(fd, nonce) };
    // inode_init_always_gfp initializes ordinary inode IDs through s_user_ns.
    // The held Binder root and features must therefore belong to guest root.
    if directory.st_dev != root.st_dev
        || directory.st_mode != (libc::S_IFDIR | 0o755)
        || directory.st_uid != 0
        || directory.st_gid != 0
    {
        unsafe { protocol_failure(nonce) }
    }
    unsafe {
        exact_names(
            fd,
            &[
                b"oneway_spam_detection",
                b"extended_error",
                b"freeze_notification",
                b"transaction_report",
            ],
            nonce,
        );
    }
    for name in [
        c"oneway_spam_detection",
        c"extended_error",
        c"freeze_notification",
        c"transaction_report",
    ] {
        let file = unsafe { opened(fd, name, libc::O_RDONLY, nonce) };
        let before = unsafe { meta(file, nonce) };
        if before.st_dev != root.st_dev
            || before.st_mode != (libc::S_IFREG | 0o444)
            || before.st_nlink != 1
            || before.st_uid != 0
            || before.st_gid != 0
        {
            unsafe { protocol_failure(nonce) }
        }
        let mut bytes = [0_u8; 3];
        let n = unsafe { libc::syscall(libc::SYS_read, file, bytes.as_mut_ptr(), bytes.len()) };
        if n != 2
            || &bytes[..2] != b"1\n"
            || unsafe { libc::syscall(libc::SYS_read, file, bytes.as_mut_ptr(), bytes.len()) } != 0
        {
            unsafe { protocol_failure(nonce) }
        }
        let after = unsafe { meta(file, nonce) };
        if before.st_dev != after.st_dev
            || before.st_ino != after.st_ino
            || before.st_mode != after.st_mode
            || before.st_uid != after.st_uid
            || before.st_gid != after.st_gid
        {
            unsafe { protocol_failure(nonce) }
        }
        unsafe {
            libc::syscall(libc::SYS_close, file);
        }
    }
    unsafe {
        libc::syscall(libc::SYS_close, fd);
    }
}

unsafe fn request(name: &CStr, nonce: [u8; 16]) -> BinderDevice {
    let mut value = BinderDevice {
        name: [0; 256],
        major: 0,
        minor: 0,
    };
    let bytes = name.to_bytes();
    if bytes.is_empty() || bytes.len() > 255 || bytes.contains(&b'/') {
        unsafe { protocol_failure(nonce) }
    }
    value.name[..bytes.len()].copy_from_slice(bytes);
    value
}

unsafe fn create_device(binder: RawFd, control: RawFd, name: &CStr, nonce: [u8; 16]) -> libc::stat {
    let root = unsafe { meta(binder, nonce) };
    let ctl = unsafe { meta(control, nonce) };
    let mut value = unsafe { request(name, nonce) };
    if unsafe { libc::syscall(libc::SYS_ioctl, control, BINDER_CTL_ADD, &mut value) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    let device = unsafe { opened(binder, name, libc::O_RDWR, nonce) };
    let before = unsafe { meta(device, nonce) };
    if before.st_dev != root.st_dev
        || before.st_mode != (libc::S_IFCHR | 0o600)
        || before.st_uid != 0
        || before.st_gid != 0
        || before.st_nlink != 1
        || before.st_rdev != libc::makedev(value.major, value.minor)
        || before.st_rdev == ctl.st_rdev
        || before.st_ino != value.minor as u64 + 3
        || libc::major(before.st_rdev) != libc::major(ctl.st_rdev)
    {
        unsafe { protocol_failure(nonce) }
    }
    let mut version = BinderVersion {
        protocol_version: -1,
    };
    if unsafe { libc::syscall(libc::SYS_ioctl, device, BINDER_VERSION, &mut version) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    if version.protocol_version != 8 {
        unsafe { protocol_failure(nonce) }
    }
    if unsafe { libc::syscall(libc::SYS_fchmod, device, 0o666) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    let after = unsafe { meta(device, nonce) };
    if before.st_dev != after.st_dev
        || before.st_ino != after.st_ino
        || before.st_rdev != after.st_rdev
        || after.st_mode != (libc::S_IFCHR | 0o666)
        || after.st_uid != 0
        || after.st_gid != 0
        || after.st_nlink != 1
    {
        unsafe { protocol_failure(nonce) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, device);
    }
    after
}

unsafe fn relative_link(dev: RawFd, name: &CStr, target: &CStr, nonce: [u8; 16]) {
    if unsafe { libc::syscall(libc::SYS_symlinkat, target.as_ptr(), dev, name.as_ptr()) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    let link = unsafe { opened(dev, name, libc::O_PATH, nonce) };
    let info = unsafe { meta(link, nonce) };
    if info.st_dev != unsafe { meta(dev, nonce) }.st_dev
        || info.st_mode != (libc::S_IFLNK | 0o777)
        || info.st_uid != 0
        || info.st_gid != 0
    {
        unsafe { protocol_failure(nonce) }
    }
    let mut bytes = [0_u8; 64];
    let n = unsafe {
        libc::syscall(
            libc::SYS_readlinkat,
            dev,
            name.as_ptr(),
            bytes.as_mut_ptr(),
            bytes.len(),
        )
    };
    let expected = target.to_bytes();
    if n != expected.len() as libc::c_long || &bytes[..expected.len()] != expected {
        unsafe { protocol_failure(nonce) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, link);
    }
}

pub(super) unsafe fn run(nonce: [u8; 16], parent_pid: u32, _mode: Mode) -> ! {
    unsafe {
        command(nonce, parent_pid, Phase::PrepareBinder);
        if libc::syscall(libc::SYS_getpid) != 1
            || libc::syscall(libc::SYS_geteuid) != 0
            || libc::syscall(libc::SYS_getegid) != 0
        {
            protocol_failure(nonce);
        }
        let root = opened(
            libc::AT_FDCWD,
            c"/",
            libc::O_RDONLY | libc::O_DIRECTORY,
            nonce,
        );
        let dev = opened(root, c"dev", libc::O_RDONLY | libc::O_DIRECTORY, nonce);
        let proc = opened(root, c"proc", libc::O_RDONLY | libc::O_DIRECTORY, nonce);
        filesystem(
            root,
            TMPFS_MAGIC,
            ATTR_NOSUID | ATTR_NODEV,
            ATTR_RDONLY,
            nonce,
        );
        filesystem(
            dev,
            TMPFS_MAGIC,
            BINDER_FLAGS,
            ATTR_RDONLY | ATTR_NODEV,
            nonce,
        );
        filesystem(
            proc,
            PROC_MAGIC,
            ATTR_RDONLY | ATTR_NOSUID | ATTR_NODEV | ATTR_NOEXEC,
            0,
            nonce,
        );
        let root_dev = meta(root, nonce).st_dev;
        let dev_dev = meta(dev, nonce).st_dev;
        let proc_dev = meta(proc, nonce).st_dev;
        if root_dev == dev_dev || root_dev == proc_dev || dev_dev == proc_dev {
            protocol_failure(nonce);
        }
        #[cfg(test)]
        DIAGNOSTIC_STAGE.store(1, std::sync::atomic::Ordering::Relaxed);
        let target = new_target(dev, nonce);
        let context = context(c"binder", nonce);
        option(context, c"max", Some(c"3"), nonce);
        // stats=global requires initial-userns CAP_SYS_ADMIN. It is deliberately
        // absent: there is no shared host Binder view in this private instance.
        attach(context, target, BINDER_FLAGS, nonce);
        let binder = opened(dev, c"binderfs", libc::O_RDONLY | libc::O_DIRECTORY, nonce);
        filesystem(
            binder,
            BINDERFS_MAGIC,
            BINDER_FLAGS,
            ATTR_RDONLY | ATTR_NODEV,
            nonce,
        );
        let binder_root = meta(binder, nonce);
        if binder_root.st_mode != (libc::S_IFDIR | 0o755)
            || binder_root.st_ino != 1
            || binder_root.st_uid != 0
            || binder_root.st_gid != 0
            || [root_dev, dev_dev, proc_dev].contains(&binder_root.st_dev)
        {
            protocol_failure(nonce);
        }
        // A nonempty runtime binder.devices parameter would auto-create device
        // nodes in fill_super. Reject it here, before adopting or allocating any.
        exact_names(binder, &[b"binder-control", b"features"], nonce);
        verify_features(binder, nonce);
        let control = opened(binder, c"binder-control", libc::O_RDWR, nonce);
        let ctl = meta(control, nonce);
        if ctl.st_dev != binder_root.st_dev
            || ctl.st_ino != 2
            || ctl.st_mode != (libc::S_IFCHR | 0o600)
            || ctl.st_uid != 0
            || ctl.st_gid != 0
            || ctl.st_nlink != 1
        {
            protocol_failure(nonce);
        }
        #[cfg(test)]
        DIAGNOSTIC_STAGE.store(2, std::sync::atomic::Ordering::Relaxed);
        let devices = [
            create_device(binder, control, c"binder", nonce),
            create_device(binder, control, c"hwbinder", nonce),
            create_device(binder, control, c"vndbinder", nonce),
        ];
        for left in 0..devices.len() {
            for right in (left + 1)..devices.len() {
                if devices[left].st_rdev == devices[right].st_rdev
                    || devices[left].st_ino == devices[right].st_ino
                {
                    protocol_failure(nonce);
                }
            }
        }
        let mut fourth = request(c"rejected-fourth", nonce);
        if libc::syscall(libc::SYS_ioctl, control, BINDER_CTL_ADD, &mut fourth) != -1
            || *libc::__errno_location() != libc::ENOSPC
        {
            protocol_failure(nonce);
        }
        exact_names(
            binder,
            &[
                b"binder-control",
                b"features",
                b"binder",
                b"hwbinder",
                b"vndbinder",
            ],
            nonce,
        );
        relative_link(dev, c"binder", c"binderfs/binder", nonce);
        relative_link(dev, c"hwbinder", c"binderfs/hwbinder", nonce);
        relative_link(dev, c"vndbinder", c"binderfs/vndbinder", nonce);
        descriptor_barrier(nonce);
        send(nonce, Phase::BinderReady, 0, 1);
        #[cfg(test)]
        if matches!(_mode, Mode::BinderControl) {
            command(nonce, parent_pid, Phase::ProbeBinder);
            DIAGNOSTIC_STAGE.store(3, std::sync::atomic::Ordering::Relaxed);
            super::private_binder_ipc::run(nonce);
            descriptor_barrier(nonce);
            send(nonce, Phase::BinderChecked, 0, 1);
        }
        // Production construction never registers a context manager or execs.
        // The private IPC test's owned child has been actually reaped before
        // Checked. Parent retains this TreeChild's namespace custody.
        #[cfg(test)]
        if matches!(_mode, Mode::BinderControl) {
            command(nonce, parent_pid, Phase::Stop);
            finish(0);
        }
        super::writable_proc::run(nonce, parent_pid, _mode);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exact_kernel_binder_ioctl_layouts() {
        assert_eq!(std::mem::size_of::<BinderDevice>(), 264);
        assert_eq!(std::mem::offset_of!(BinderDevice, major), 256);
        assert_eq!(std::mem::offset_of!(BinderDevice, minor), 260);
        assert_eq!(
            BINDER_CTL_ADD,
            (3 << 30) | (264 << 16) | (b'b' as u64) << 8 | 1
        );
        assert_eq!(
            BINDER_VERSION,
            (3 << 30) | (4 << 16) | (b'b' as u64) << 8 | 9
        );
    }

    #[test]
    fn binder_diagnostics_do_not_accept_proc_stage_or_ready() {
        let value = DIAGNOSTIC_FAILURE_BASE | (2 << 24) | (330 << 12) | libc::ENOSPC as u32;
        assert_eq!(
            decode_private_failure(value as i32),
            Some((2, 330, libc::ENOSPC))
        );
        for value in [
            0,
            -1,
            libc::EPERM,
            0x1100_1001,
            (DIAGNOSTIC_FAILURE_BASE | (4 << 24) | (1 << 12) | 1) as i32,
        ] {
            assert_eq!(decode_private_failure(value), None);
        }
    }
}
