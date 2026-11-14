//! Fixed syscall-only consumer of one opaque private /dev mount.
//!
//! This is a distinct barrier after the immutable bases and empty data root.
//! No device pathname on the host is opened and no Android exec is available.

use super::empty_root::{KernelStatfs, entry_record};
use super::{CHILD_FD, Mode, Packet, Phase, fail, finish, receive, send};
use std::ffi::CStr;
use std::os::fd::RawFd;

const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const ATTR_RDONLY: u64 = 1;
const ATTR_NOSUID: u64 = 2;
const ATTR_NODEV: u64 = 4;
const ATTR_NOEXEC: u64 = 8;
const MOVE_EMPTY: u32 = 0x04 | 0x40;

#[derive(Clone, Copy)]
struct DeviceSpec {
    name: &'static CStr,
    major: u32,
    minor: u32,
}
const DEVICES: [DeviceSpec; 7] = [
    DeviceSpec {
        name: c"null",
        major: 1,
        minor: 3,
    },
    DeviceSpec {
        name: c"zero",
        major: 1,
        minor: 5,
    },
    DeviceSpec {
        name: c"full",
        major: 1,
        minor: 7,
    },
    DeviceSpec {
        name: c"random",
        major: 1,
        minor: 8,
    },
    DeviceSpec {
        name: c"urandom",
        major: 1,
        minor: 9,
    },
    DeviceSpec {
        name: c"tty",
        major: 5,
        minor: 0,
    },
    DeviceSpec {
        name: c"fuse",
        major: 10,
        minor: 229,
    },
];

unsafe fn protocol_failure(nonce: [u8; 16]) -> ! {
    unsafe {
        *libc::__errno_location() = libc::EPROTO;
        fail(nonce, 1)
    }
}

/// An exact one-FD message from the same private, nonce-bound creator endpoint.
/// Extra rights, other ancillary records, truncated messages and wrong phases
/// cannot become a mount input. Failure exits this owned child, closing all FDs.
unsafe fn receive_device(nonce: [u8; 16], parent_pid: u32) -> RawFd {
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
    if packet.phase == Phase::Stop as u32 {
        if !header.is_null() {
            unsafe { protocol_failure(nonce) }
        }
        unsafe { finish(0) }
    }
    if packet.phase != Phase::MountPrivateDev as u32 || header.is_null() {
        unsafe { protocol_failure(nonce) }
    }
    let h = unsafe { &*header };
    if h.cmsg_level != libc::SOL_SOCKET
        || h.cmsg_type != libc::SCM_RIGHTS
        || h.cmsg_len != unsafe { libc::CMSG_LEN(4) } as usize
        || !unsafe { libc::CMSG_NXTHDR(&msg, header) }.is_null()
    {
        unsafe { protocol_failure(nonce) }
    }
    let raw = unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<i32>()) };
    if raw < 0 || raw == CHILD_FD {
        unsafe { protocol_failure(nonce) }
    }
    // Stdio is closed. Relocate a received 0/1/2 without touching the sole
    // control descriptor, then close the original descriptor exactly once.
    let fd = unsafe { libc::syscall(libc::SYS_fcntl, raw, libc::F_DUPFD_CLOEXEC, 4) };
    if fd < 4 || fd > i32::MAX as libc::c_long {
        unsafe { fail(nonce, 1) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, raw);
    }
    fd as RawFd
}

unsafe fn opened_directory(parent: RawFd, name: &CStr, nonce: [u8; 16]) -> RawFd {
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat,
            parent,
            name.as_ptr(),
            libc::O_RDONLY
                | libc::O_DIRECTORY
                | libc::O_NOFOLLOW
                | libc::O_CLOEXEC
                | libc::O_NONBLOCK,
            0,
        )
    };
    if fd < 0 || fd > i32::MAX as libc::c_long {
        unsafe { fail(nonce, 1) }
    }
    fd as RawFd
}

unsafe fn require_private_devices(fd: RawFd, nonce: [u8; 16]) {
    let mut fs: KernelStatfs = unsafe { std::mem::zeroed() };
    let mut meta: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut fs) } != 0
        || unsafe { libc::syscall(libc::SYS_fstat, fd, &mut meta) } != 0
    {
        unsafe { fail(nonce, 1) }
    }
    let flags = fs.f_flags as u64;
    if fs.f_type != TMPFS_MAGIC
        || flags & (ATTR_NOSUID | ATTR_NOEXEC) != ATTR_NOSUID | ATTR_NOEXEC
        || flags & (ATTR_RDONLY | ATTR_NODEV) != 0
        || fs.f_blocks < 0
        || fs.f_frsize <= 0
        || (fs.f_blocks as u64).checked_mul(fs.f_frsize as u64) != Some(64 * 1024 * 1024)
        || fs.f_files != 16_384
        || meta.st_mode != (libc::S_IFDIR | 0o755)
        || meta.st_uid != 0
        || meta.st_gid != 0
    {
        unsafe { protocol_failure(nonce) }
    }
    let entries = unsafe { opened_directory(fd, c".", nonce) };
    let mut seen = 0_u8;
    let mut buffer = [0_u8; 4096];
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
            unsafe { fail(nonce, 1) }
        }
        if n == 0 {
            break;
        }
        if n as usize > buffer.len() {
            unsafe { protocol_failure(nonce) }
        }
        let mut at = 0_usize;
        while at < n as usize {
            let (length, name) = match entry_record(&buffer[at..n as usize]) {
                Some(value) => value,
                None => unsafe { protocol_failure(nonce) },
            };
            at += length;
            if name == b"." || name == b".." {
                continue;
            }
            let index = match DEVICES.iter().position(|s| s.name.to_bytes() == name) {
                Some(value) => value,
                None => unsafe { protocol_failure(nonce) },
            };
            let bit = 1_u8 << index;
            if seen & bit != 0 {
                unsafe { protocol_failure(nonce) }
            }
            seen |= bit;
            let spec = DEVICES[index];
            // O_PATH checks the inode without opening a device driver.
            let node = unsafe {
                libc::syscall(
                    libc::SYS_openat,
                    fd,
                    spec.name.as_ptr(),
                    libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                    0,
                )
            };
            if node < 0 || node > i32::MAX as libc::c_long {
                unsafe { fail(nonce, 1) }
            }
            let mut got: libc::stat = unsafe { std::mem::zeroed() };
            if unsafe { libc::syscall(libc::SYS_fstat, node, &mut got) } != 0 {
                unsafe { fail(nonce, 1) }
            }
            if got.st_dev != meta.st_dev
                || got.st_mode != (libc::S_IFCHR | 0o666)
                || got.st_uid != 0
                || got.st_gid != 0
                || got.st_nlink != 1
                || got.st_rdev != libc::makedev(spec.major, spec.minor)
            {
                unsafe { protocol_failure(nonce) }
            }
            unsafe {
                libc::syscall(libc::SYS_close, node);
            }
        }
    }
    unsafe {
        libc::syscall(libc::SYS_close, entries);
    }
    if seen != 0x7f {
        unsafe { protocol_failure(nonce) }
    }
}

/// Runs only after EmptyRootReady. The existing root belongs exclusively to
/// this PID 1; creating its /dev placeholder cannot mutate an inherited host
/// mount. Neither the bases nor protected original account images are written.
pub(super) unsafe fn run(nonce: [u8; 16], parent_pid: u32, _mode: Mode) -> ! {
    unsafe {
        let devices = receive_device(nonce, parent_pid);
        require_private_devices(devices, nonce);
        let root = opened_directory(libc::AT_FDCWD, c"/", nonce);
        let mut fs: KernelStatfs = std::mem::zeroed();
        if libc::syscall(libc::SYS_fstatfs, root, &mut fs) != 0 || fs.f_type != TMPFS_MAGIC {
            protocol_failure(nonce);
        }
        if libc::syscall(libc::SYS_mkdirat, root, c"dev".as_ptr(), 0o755_u32) != 0
            && *libc::__errno_location() != libc::EEXIST
        {
            fail(nonce, 1);
        }
        // A symlink or non-directory placeholder is rejected even inside this
        // private root. Do not follow a base-provided link to another mount.
        let target = opened_directory(root, c"dev", nonce);
        if libc::syscall(
            libc::SYS_move_mount,
            devices,
            c"".as_ptr(),
            target,
            c"".as_ptr(),
            MOVE_EMPTY,
        ) != 0
        {
            fail(nonce, 1);
        }
        libc::syscall(libc::SYS_close, target);
        let attached = opened_directory(root, c"dev", nonce);
        require_private_devices(attached, nonce);
        // No source mount, root-directory or device descriptor escapes this
        // barrier; the sole descriptor is the original private control socket.
        if libc::syscall(libc::SYS_close_range, 4_u32, u32::MAX, 0) != 0 {
            fail(nonce, 1);
        }
        libc::syscall(libc::SYS_close, 0);
        libc::syscall(libc::SYS_close, 1);
        libc::syscall(libc::SYS_close, 2);
        send(nonce, Phase::PrivateDevReady, 0, 1);
        #[cfg(test)]
        if matches!(
            _mode,
            Mode::DeviceRootControl | Mode::ProcessFilesystemsControl | Mode::BinderControl
        ) {
            receive(nonce, parent_pid, Phase::ProbePrivateDev);
            harmless_device_control(nonce);
            send(nonce, Phase::PrivateDevChecked, 0, 1);
        }
        #[cfg(test)]
        if matches!(_mode, Mode::DeviceRootControl) {
            receive(nonce, parent_pid, Phase::Stop);
            finish(0);
        }
        super::process_filesystems::run(nonce, parent_pid, _mode);
    }
}

#[cfg(test)]
unsafe fn harmless_device_control(nonce: [u8; 16]) {
    for (path, write) in [(c"/dev/null", true), (c"/dev/zero", false)] {
        let fd = unsafe {
            libc::syscall(
                libc::SYS_openat,
                libc::AT_FDCWD,
                path.as_ptr(),
                (if write {
                    libc::O_WRONLY
                } else {
                    libc::O_RDONLY
                }) | libc::O_CLOEXEC
                    | libc::O_NOFOLLOW
                    | libc::O_NONBLOCK,
                0,
            )
        };
        if fd < 0 || fd > i32::MAX as libc::c_long {
            unsafe { fail(nonce, 1) }
        }
        let mut bytes = [0x5a_u8; 16];
        let n = if write {
            unsafe { libc::syscall(libc::SYS_write, fd, bytes.as_ptr(), bytes.len()) }
        } else {
            unsafe { libc::syscall(libc::SYS_read, fd, bytes.as_mut_ptr(), bytes.len()) }
        };
        if n != bytes.len() as libc::c_long || (!write && bytes != [0; 16]) {
            unsafe { protocol_failure(nonce) }
        }
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
    }
}
