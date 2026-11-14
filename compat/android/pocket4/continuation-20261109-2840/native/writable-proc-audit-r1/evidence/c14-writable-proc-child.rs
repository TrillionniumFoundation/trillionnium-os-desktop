//! Fixed preparation of writable per-process proc state in the owned PID namespace.
//!
//! The global proc views receive private read-only or empty projections before
//! the proc root becomes writable. This is construction evidence only: these
//! mounts are not claimed to be MNT_LOCKED, and an eventual exec requires the
//! independently reviewed mount-syscall/LSM boundary. No host sysctl is written.

use super::empty_root::{KernelStatfs, entry_record};
use super::{CHILD_FD, Mode, Packet, Phase, fail, finish, send};
use std::ffi::CStr;
use std::os::fd::RawFd;

const PROC_MAGIC: libc::c_long = 0x9fa0;
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const RO: u64 = 1;
const BASE_FLAGS: u64 = 2 | 4 | 8;
const EMPTY_PATH: u32 = 0x1000;
const MOVE_EMPTY: u32 = 0x04 | 0x40;

pub(super) const READ_ONLY: [&CStr; 5] = [c"bus", c"fs", c"irq", c"sys", c"sysrq-trigger"];
pub(super) const MASKED: [&CStr; 10] = [
    c"acpi",
    c"asound",
    c"kcore",
    c"keys",
    c"latency_stats",
    c"timer_list",
    c"timer_stats",
    c"sched_debug",
    c"scsi",
    c"interrupts",
];

#[repr(C)]
struct MountAttr {
    set: u64,
    clear: u64,
    propagation: u64,
    userns_fd: u64,
}

#[cfg(test)]
const DIAGNOSTIC_FAILURE_BASE: u32 = 0x3000_0000;
#[cfg(test)]
static STAGE: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);

#[cfg(test)]
pub(super) fn decode_private_failure(value: i32) -> Option<(u32, u32, i32)> {
    let bits = value as u32;
    let stage = (bits >> 24) & 15;
    let line = (bits >> 12) & 4095;
    let errno = (bits & 4095) as i32;
    (bits >> 28 == 3 && stage <= 4 && line != 0 && errno != 0).then_some((stage, line, errno))
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
            (DIAGNOSTIC_FAILURE_BASE | stage << 24 | line << 12 | errno) as i32,
            1,
        );
        finish(127)
    }
    #[cfg(not(test))]
    unsafe {
        let _ = line;
        fail(nonce, 1)
    }
}

unsafe fn rejected(nonce: [u8; 16]) -> ! {
    unsafe {
        *libc::__errno_location() = libc::EPROTO;
        failed(nonce, line!())
    }
}

unsafe fn command(nonce: [u8; 16], parent_pid: u32, expected: Phase) {
    let mut packet = Packet::zeroed();
    let mut iov = libc::iovec {
        iov_base: (&mut packet as *mut Packet).cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 16];
    let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = ancillary.as_mut_ptr().cast();
    message.msg_controllen = std::mem::size_of_val(&ancillary);
    let count = unsafe {
        libc::syscall(
            libc::SYS_recvmsg,
            CHILD_FD,
            &mut message,
            libc::MSG_CMSG_CLOEXEC,
        )
    };
    if count == 0 {
        unsafe { finish(0) }
    }
    if count != std::mem::size_of::<Packet>() as libc::c_long
        || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
        || !packet.matches(nonce, parent_pid)
        || packet.errno != 0
        || !unsafe { libc::CMSG_FIRSTHDR(&message) }.is_null()
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

unsafe fn path(parent: RawFd, name: &CStr, optional: bool, nonce: [u8; 16]) -> RawFd {
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat,
            parent,
            name.as_ptr(),
            libc::O_PATH | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0,
        )
    };
    if raw < 0 {
        if optional && unsafe { *libc::__errno_location() } == libc::ENOENT {
            return -1;
        }
        unsafe { failed(nonce, line!()) }
    }
    if raw > i32::MAX as libc::c_long {
        unsafe { rejected(nonce) }
    }
    raw as RawFd
}

unsafe fn metadata(fd: RawFd, nonce: [u8; 16]) -> libc::stat {
    let mut value: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstat, fd, &mut value) } != 0 {
        unsafe { failed(nonce, line!()) }
    }
    value
}

unsafe fn fs(fd: RawFd, kind: libc::c_long, required: u64, forbidden: u64, nonce: [u8; 16]) {
    let mut value: KernelStatfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut value) } != 0 {
        unsafe { failed(nonce, line!()) }
    }
    if value.f_type != kind
        || value.f_flags as u64 & required != required
        || value.f_flags as u64 & forbidden != 0
    {
        unsafe { rejected(nonce) }
    }
}

unsafe fn attributes(fd: RawFd, set: u64, clear: u64, nonce: [u8; 16]) {
    let attr = MountAttr {
        set,
        clear,
        propagation: 0,
        userns_fd: 0,
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
}

unsafe fn project(source: RawFd, target: RawFd, nonce: [u8; 16]) {
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
    let mount = raw as RawFd;
    unsafe {
        attributes(mount, RO | BASE_FLAGS, 0, nonce);
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
        unsafe { failed(nonce, line!()) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, mount);
    }
}

unsafe fn new_mask_file(metadata_dir: RawFd, nonce: [u8; 16]) -> RawFd {
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat,
            metadata_dir,
            c"proc-mask-file".as_ptr(),
            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0o000_u32,
        )
    };
    if raw < 0 || raw > i32::MAX as libc::c_long {
        unsafe { failed(nonce, line!()) }
    }
    let fd = raw as RawFd;
    let got = unsafe { metadata(fd, nonce) };
    if got.st_mode != libc::S_IFREG
        || got.st_size != 0
        || got.st_nlink != 1
        || got.st_uid != 0
        || got.st_gid != 0
    {
        unsafe { rejected(nonce) }
    }
    fd
}

unsafe fn new_mask_directory(metadata_dir: RawFd, nonce: [u8; 16]) -> RawFd {
    if unsafe {
        libc::syscall(
            libc::SYS_mkdirat,
            metadata_dir,
            c"proc-mask-directory".as_ptr(),
            0o000_u32,
        )
    } != 0
    {
        unsafe { failed(nonce, line!()) }
    }
    let fd = unsafe { path(metadata_dir, c"proc-mask-directory", false, nonce) };
    let got = unsafe { metadata(fd, nonce) };
    if got.st_mode != libc::S_IFDIR || got.st_uid != 0 || got.st_gid != 0 {
        unsafe { rejected(nonce) }
    }
    fd
}

unsafe fn readonly_globals(proc: RawFd, proc_dev: u64, nonce: [u8; 16]) {
    for name in READ_ONLY {
        let target = unsafe { path(proc, name, true, nonce) };
        if target < 0 {
            continue;
        }
        let before = unsafe { metadata(target, nonce) };
        if before.st_dev != proc_dev
            || ![libc::S_IFDIR, libc::S_IFREG].contains(&(before.st_mode & libc::S_IFMT))
        {
            unsafe { rejected(nonce) }
        }
        unsafe {
            project(target, target, nonce);
            libc::syscall(libc::SYS_close, target);
        }
        let after = unsafe { path(proc, name, false, nonce) };
        let current = unsafe { metadata(after, nonce) };
        if (before.st_dev, before.st_ino, before.st_mode)
            != (current.st_dev, current.st_ino, current.st_mode)
        {
            unsafe { rejected(nonce) }
        }
        unsafe {
            fs(after, PROC_MAGIC, RO | BASE_FLAGS, 0, nonce);
            libc::syscall(libc::SYS_close, after);
        }
    }
}

unsafe fn masked_globals(proc: RawFd, proc_dev: u64, metadata_dir: RawFd, nonce: [u8; 16]) {
    let file = unsafe { new_mask_file(metadata_dir, nonce) };
    let directory = unsafe { new_mask_directory(metadata_dir, nonce) };
    for name in MASKED {
        let target = unsafe { path(proc, name, true, nonce) };
        if target < 0 {
            continue;
        }
        let before = unsafe { metadata(target, nonce) };
        if before.st_dev != proc_dev {
            unsafe { rejected(nonce) }
        }
        let source = match before.st_mode & libc::S_IFMT {
            libc::S_IFDIR => directory,
            libc::S_IFREG => file,
            _ => unsafe { rejected(nonce) },
        };
        let original = unsafe { metadata(source, nonce) };
        unsafe {
            project(source, target, nonce);
            libc::syscall(libc::SYS_close, target);
        }
        let after = unsafe { path(proc, name, false, nonce) };
        let got = unsafe { metadata(after, nonce) };
        if (got.st_dev, got.st_ino, got.st_mode)
            != (original.st_dev, original.st_ino, original.st_mode)
        {
            unsafe { rejected(nonce) }
        }
        unsafe {
            fs(after, TMPFS_MAGIC, RO | BASE_FLAGS, 0, nonce);
            libc::syscall(libc::SYS_close, after);
        }
    }
    unsafe {
        libc::syscall(libc::SYS_close, file);
        libc::syscall(libc::SYS_close, directory);
    }
}

unsafe fn descriptor_barrier(nonce: [u8; 16]) {
    if unsafe { libc::syscall(libc::SYS_close_range, 4_u32, u32::MAX, 0) } != 0 {
        unsafe { failed(nonce, line!()) }
    }
    for fd in 0..3 {
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
    }
    // The only retained descriptor is the original private control endpoint.
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            c"/proc/1/fd".as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0,
        )
    };
    if fd != 0 {
        unsafe { rejected(nonce) }
    }
    let mut names = 0_u8;
    let mut buffer = [0_u8; 4096];
    loop {
        let count =
            unsafe { libc::syscall(libc::SYS_getdents64, fd, buffer.as_mut_ptr(), buffer.len()) };
        if count < 0 {
            unsafe { failed(nonce, line!()) }
        }
        if count == 0 {
            break;
        }
        if count as usize > buffer.len() {
            unsafe { rejected(nonce) }
        }
        let mut offset = 0;
        while offset < count as usize {
            let (length, name) = match entry_record(&buffer[offset..count as usize]) {
                Some(row) => row,
                None => unsafe { rejected(nonce) },
            };
            offset += length;
            match name {
                b"." | b".." => {}
                b"0" => {
                    if names & 1 != 0 {
                        unsafe { rejected(nonce) }
                    }
                    names |= 1;
                }
                b"3" => {
                    if names & 2 != 0 {
                        unsafe { rejected(nonce) }
                    }
                    names |= 2;
                }
                _ => unsafe { rejected(nonce) },
            }
        }
    }
    if names != 3 {
        unsafe { rejected(nonce) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, fd);
    }
}

pub(super) unsafe fn run(nonce: [u8; 16], parent_pid: u32, mode: Mode) -> ! {
    unsafe {
        command(nonce, parent_pid, Phase::PrepareWritableProc);
        if libc::syscall(libc::SYS_getpid) != 1
            || libc::syscall(libc::SYS_geteuid) != 0
            || libc::syscall(libc::SYS_getegid) != 0
        {
            rejected(nonce);
        }
        #[cfg(test)]
        STAGE.store(1, std::sync::atomic::Ordering::Relaxed);
        let root = path(libc::AT_FDCWD, c"/", false, nonce);
        let proc = path(root, c"proc", false, nonce);
        let metadata_dir = path(root, c"metadata", false, nonce);
        fs(root, TMPFS_MAGIC, 2 | 4, RO, nonce);
        fs(proc, PROC_MAGIC, RO | BASE_FLAGS, 0, nonce);
        fs(metadata_dir, TMPFS_MAGIC, 2 | 4, RO, nonce);
        let proc_dev = metadata(proc, nonce).st_dev;
        let metadata_dev = metadata(metadata_dir, nonce).st_dev;
        if proc_dev == metadata_dev || metadata_dev == metadata(root, nonce).st_dev {
            rejected(nonce);
        }
        readonly_globals(proc, proc_dev, nonce);
        #[cfg(test)]
        STAGE.store(2, std::sync::atomic::Ordering::Relaxed);
        masked_globals(proc, proc_dev, metadata_dir, nonce);
        #[cfg(test)]
        STAGE.store(3, std::sync::atomic::Ordering::Relaxed);
        attributes(proc, BASE_FLAGS, RO, nonce);
        fs(proc, PROC_MAGIC, BASE_FLAGS, RO, nonce);
        descriptor_barrier(nonce);
        send(nonce, Phase::WritableProcReady, 0, 1);
        #[cfg(test)]
        if matches!(mode, Mode::WritableProcControl) {
            command(nonce, parent_pid, Phase::ProbeWritableProc);
            STAGE.store(4, std::sync::atomic::Ordering::Relaxed);
            let observed = private_write_and_xattr_observation(nonce);
            descriptor_barrier(nonce);
            // errno carries only this fixed observation at this test-only phase.
            // It never grants execution, changes an identity or reports MAC.
            send(nonce, Phase::WritableProcChecked, observed, 1);
        }
        let _ = mode;
        command(nonce, parent_pid, Phase::Stop);
        finish(0)
    }
}

#[cfg(test)]
unsafe fn private_write_and_xattr_observation(nonce: [u8; 16]) -> i32 {
    unsafe {
        // Write back only this owned PID 1's original score. No global proc
        // file is opened for a successful write or receives any contents.
        let score = libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            c"/proc/1/oom_score_adj".as_ptr(),
            libc::O_RDWR | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
            0,
        );
        if score < 0 || score > i32::MAX as libc::c_long {
            failed(nonce, line!());
        }
        let mut before = [0_u8; 32];
        let n = libc::syscall(libc::SYS_read, score, before.as_mut_ptr(), before.len());
        if n <= 0 || n >= before.len() as libc::c_long || before[n as usize - 1] != b'\n' {
            rejected(nonce);
        }
        if libc::syscall(libc::SYS_lseek, score, 0, libc::SEEK_SET) != 0
            || libc::syscall(libc::SYS_write, score, before.as_ptr(), n) != n
            || libc::syscall(libc::SYS_lseek, score, 0, libc::SEEK_SET) != 0
        {
            failed(nonce, line!());
        }
        let mut after = [0_u8; 32];
        if libc::syscall(libc::SYS_read, score, after.as_mut_ptr(), after.len()) != n
            || before[..n as usize] != after[..n as usize]
        {
            rejected(nonce);
        }
        libc::syscall(libc::SYS_close, score);
        for protected in [c"/proc/sys/kernel/hostname", c"/proc/sysrq-trigger"] {
            let raw = libc::syscall(
                libc::SYS_openat,
                libc::AT_FDCWD,
                protected.as_ptr(),
                libc::O_WRONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
                0,
            );
            if raw >= 0 {
                libc::syscall(libc::SYS_close, raw);
                rejected(nonce);
            }
            if ![libc::EROFS, libc::EACCES, libc::EPERM].contains(&*libc::__errno_location()) {
                failed(nonce, line!());
            }
        }
        let dev = path(libc::AT_FDCWD, c"/dev", false, nonce);
        fs(dev, TMPFS_MAGIC, 2 | 8, RO | 4, nonce);
        let fd = libc::syscall(
            libc::SYS_openat,
            dev,
            c"selinux-xattr-private-observation".as_ptr(),
            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0o600_u32,
        );
        if fd < 0 || fd > i32::MAX as libc::c_long {
            failed(nonce, line!());
        }
        let st = metadata(fd as RawFd, nonce);
        if st.st_dev != metadata(dev, nonce).st_dev
            || st.st_mode != libc::S_IFREG | 0o600
            || st.st_nlink != 1
            || st.st_uid != 0
            || st.st_gid != 0
            || st.st_size != 0
        {
            rejected(nonce);
        }
        let label = b"u:object_r:boot_status_prop:s0\0";
        let rc = libc::syscall(
            libc::SYS_fsetxattr,
            fd,
            c"security.selinux".as_ptr(),
            label.as_ptr(),
            label.len(),
            0,
        );
        let observed = if rc == 0 {
            let mut got = [0_u8; 64];
            let n = libc::syscall(
                libc::SYS_fgetxattr,
                fd,
                c"security.selinux".as_ptr(),
                got.as_mut_ptr(),
                got.len(),
            );
            if n != label.len() as libc::c_long || got[..label.len()] != *label {
                rejected(nonce);
            }
            0
        } else if rc == -1 {
            let errno = *libc::__errno_location();
            if !(1..4096).contains(&errno) {
                rejected(nonce);
            }
            errno
        } else {
            rejected(nonce)
        };
        if libc::syscall(
            libc::SYS_unlinkat,
            dev,
            c"selinux-xattr-private-observation".as_ptr(),
            0,
        ) != 0
        {
            failed(nonce, line!());
        }
        libc::syscall(libc::SYS_close, fd);
        libc::syscall(libc::SYS_close, dev);
        observed
    }
}
