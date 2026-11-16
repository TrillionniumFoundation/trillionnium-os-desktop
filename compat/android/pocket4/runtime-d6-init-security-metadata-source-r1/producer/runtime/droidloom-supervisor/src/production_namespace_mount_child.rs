//! Fixed, syscall-only consumer of the two admitted base mount descriptors.
//!
//! This is not an Android exec path. It builds an isolated empty-data root,
//! pivots away from every inherited host mount and parks at a second barrier.
//! Runtime, device and APEX authority are separate prerequisites.

use super::{CHILD_FD, Mode, Packet, Phase, fail, finish, receive, send};
use std::os::fd::RawFd;

const OPEN_TREE_CLONE: u32 = 1;
const MOVE_EMPTY: u32 = 0x04 | 0x40;
const AT_EMPTY_PATH: u32 = 0x1000;
const ATTR_RDONLY: u64 = 1;
const ATTR_NOSUID: u64 = 2;
const ATTR_NODEV: u64 = 4;
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const EXT4_MAGIC: libc::c_long = 0xef53;
const EROFS_MAGIC: libc::c_long = 0xe0f5_e1e2_u32 as libc::c_long;
const MAX_ROOT_ENTRIES: usize = 128;
const MAX_NAME: usize = 255;
const MAX_LINK: usize = 4096;

// Linux LP64 SYS_fstatfs UAPI, from asm-generic/statfs.h. The Rust libc
// type intentionally does not expose f_flags on every GNU target. Keep the
// raw syscall output complete instead of omitting the mount-flag checks.
#[repr(C)]
pub(super) struct KernelStatfs {
    pub(super) f_type: libc::c_long,
    pub(super) f_bsize: libc::c_long,
    pub(super) f_blocks: libc::c_long,
    pub(super) f_bfree: libc::c_long,
    pub(super) f_bavail: libc::c_long,
    pub(super) f_files: libc::c_long,
    pub(super) f_ffree: libc::c_long,
    pub(super) f_fsid: [i32; 2],
    pub(super) f_namelen: libc::c_long,
    pub(super) f_frsize: libc::c_long,
    pub(super) f_flags: libc::c_long,
    pub(super) f_spare: [libc::c_long; 4],
}
const _: () = {
    assert!(std::mem::size_of::<libc::c_long>() == 8);
    assert!(std::mem::size_of::<KernelStatfs>() == 120);
    assert!(std::mem::align_of::<KernelStatfs>() == 8);
    assert!(std::mem::offset_of!(KernelStatfs, f_fsid) == 56);
    assert!(std::mem::offset_of!(KernelStatfs, f_flags) == 80);
    assert!(std::mem::offset_of!(KernelStatfs, f_spare) == 88);
    assert!(std::mem::size_of::<KernelStatfs>() == std::mem::size_of::<libc::statfs>());
    assert!(std::mem::align_of::<KernelStatfs>() == std::mem::align_of::<libc::statfs>());
};

#[repr(C)]
struct MountAttr {
    attr_set: u64,
    attr_clr: u64,
    propagation: u64,
    userns_fd: u64,
}

unsafe fn protocol_failure(nonce: [u8; 16]) -> ! {
    unsafe {
        *libc::__errno_location() = libc::EPROTO;
        fail(nonce, 1)
    }
}

fn component(name: &[u8]) -> bool {
    !name.is_empty()
        && name.len() <= MAX_NAME
        && name != b"."
        && name != b".."
        && name
            .iter()
            .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(b))
}

fn link_target(value: &[u8]) -> bool {
    !value.is_empty()
        && value.len() < MAX_LINK
        && value.iter().all(|b| *b != 0 && (0x20..0x7f).contains(b))
        && value.split(|b| *b == b'/').all(|part| part != b"..")
}

/// The only transfer accepted at the first PID 1 barrier. The connected peer
/// is held exclusively by the creator; no pathname, process ID or JSON grants
/// access to this endpoint. Exact sender/receiver ownership was already bound.
unsafe fn receive_bases(nonce: [u8; 16], parent_pid: u32) -> [RawFd; 2] {
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
        unsafe { protocol_failure(nonce) }
    }
    let header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    if packet.phase == Phase::Stop as u32 {
        if !header.is_null() {
            unsafe { protocol_failure(nonce) }
        }
        unsafe { finish(0) }
    }
    if packet.phase != Phase::MountEmptyBase as u32 || header.is_null() {
        unsafe { protocol_failure(nonce) }
    }
    let h = unsafe { &*header };
    if h.cmsg_level != libc::SOL_SOCKET
        || h.cmsg_type != libc::SCM_RIGHTS
        || h.cmsg_len != unsafe { libc::CMSG_LEN(8) } as usize
        || !unsafe { libc::CMSG_NXTHDR(&msg, header) }.is_null()
    {
        unsafe { protocol_failure(nonce) }
    }
    let p = unsafe { libc::CMSG_DATA(header).cast::<i32>() };
    let raw = unsafe {
        [
            std::ptr::read_unaligned(p),
            std::ptr::read_unaligned(p.add(1)),
        ]
    };
    if raw[0] < 0 || raw[1] < 0 || raw[0] == raw[1] || raw.contains(&CHILD_FD) {
        unsafe { protocol_failure(nonce) }
    }
    // Stdio was closed before TreeReady. Received FDs may therefore be 0/1.
    // Duplicate both before closing either, never overwrite a live peer FD.
    let mut held = [-1; 2];
    for i in 0..2 {
        let fd = unsafe { libc::syscall(libc::SYS_fcntl, raw[i], libc::F_DUPFD_CLOEXEC, 4) };
        if fd < 4 || fd > i32::MAX as libc::c_long {
            unsafe { fail(nonce, 1) }
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

unsafe fn require_image(fd: RawFd, nonce: [u8; 16]) {
    let mut fs: KernelStatfs = unsafe { std::mem::zeroed() };
    let mut meta: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut fs) } != 0
        || unsafe { libc::syscall(libc::SYS_fstat, fd, &mut meta) } != 0
    {
        unsafe { fail(nonce, 1) }
    }
    if !matches!(fs.f_type, EXT4_MAGIC | EROFS_MAGIC)
        || fs.f_flags as u64 & (ATTR_RDONLY | ATTR_NOSUID | ATTR_NODEV)
            != ATTR_RDONLY | ATTR_NOSUID | ATTR_NODEV
        || meta.st_mode & libc::S_IFMT != libc::S_IFDIR
        || meta.st_uid != 0
        || meta.st_gid != 0
    {
        unsafe { protocol_failure(nonce) }
    }
}

unsafe fn make_tmpfs(
    mode: *const libc::c_char,
    size: *const libc::c_char,
    nonce: [u8; 16],
) -> RawFd {
    let context = unsafe { libc::syscall(libc::SYS_fsopen, c"tmpfs".as_ptr(), 1_u32) };
    if context < 0 || context > i32::MAX as libc::c_long {
        unsafe { fail(nonce, 1) }
    }
    let context = context as RawFd;
    for (key, value) in [(c"mode".as_ptr(), mode), (c"size".as_ptr(), size)] {
        if unsafe { libc::syscall(libc::SYS_fsconfig, context, 1_u32, key, value, 0) } != 0 {
            unsafe { fail(nonce, 1) }
        }
    }
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
        unsafe { fail(nonce, 1) }
    }
    let mounted = unsafe {
        libc::syscall(
            libc::SYS_fsmount,
            context,
            1_u32,
            (ATTR_NOSUID | ATTR_NODEV) as u32,
        )
    };
    if mounted < 0 || mounted > i32::MAX as libc::c_long {
        unsafe { fail(nonce, 1) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, context);
    }
    let mounted = mounted as RawFd;
    let mut fs: KernelStatfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, mounted, &mut fs) } != 0
        || fs.f_type != TMPFS_MAGIC
    {
        unsafe { fail(nonce, 1) }
    }
    mounted
}

unsafe fn directory_at(parent: RawFd, name: *const libc::c_char, nonce: [u8; 16]) -> RawFd {
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat,
            parent,
            name,
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

unsafe fn new_directory(parent: RawFd, name: *const libc::c_char, nonce: [u8; 16]) -> RawFd {
    if unsafe { libc::syscall(libc::SYS_mkdirat, parent, name, 0o755_u32) } != 0 {
        unsafe { fail(nonce, 1) }
    }
    let fd = unsafe { directory_at(parent, name, nonce) };
    if unsafe { libc::syscall(libc::SYS_fchmod, fd, 0o755_u32) } != 0 {
        unsafe { fail(nonce, 1) }
    }
    fd
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
        unsafe { fail(nonce, 1) }
    }
}

unsafe fn clone_readonly(source: RawFd, name: *const libc::c_char, target: RawFd, nonce: [u8; 16]) {
    let fd = unsafe {
        libc::syscall(
            libc::SYS_open_tree,
            source,
            name,
            OPEN_TREE_CLONE | libc::O_CLOEXEC as u32 | libc::AT_SYMLINK_NOFOLLOW as u32,
        )
    };
    if fd < 0 || fd > i32::MAX as libc::c_long {
        unsafe { fail(nonce, 1) }
    }
    let fd = fd as RawFd;
    let attrs = MountAttr {
        attr_set: ATTR_RDONLY | ATTR_NOSUID | ATTR_NODEV,
        attr_clr: 0,
        propagation: 0,
        userns_fd: 0,
    };
    if unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            fd,
            c"".as_ptr(),
            AT_EMPTY_PATH,
            &attrs,
            std::mem::size_of::<MountAttr>(),
        )
    } != 0
    {
        unsafe { fail(nonce, 1) }
    }
    unsafe {
        attach(fd, target, nonce);
        libc::syscall(libc::SYS_close, fd);
    }
}

unsafe fn source_directory(source: RawFd, name: *const libc::c_char, nonce: [u8; 16]) {
    let fd = unsafe { directory_at(source, name, nonce) };
    unsafe {
        libc::syscall(libc::SYS_close, fd);
    }
}

unsafe fn copy_root_entry(source: RawFd, target: RawFd, name: &[u8], nonce: [u8; 16]) {
    if !component(name) || name == b".oldroot" {
        unsafe { protocol_failure(nonce) }
    }
    let mut c_name = [0_u8; MAX_NAME + 1];
    for i in 0..name.len() {
        c_name[i] = name[i];
    }
    let name_ptr = c_name.as_ptr().cast::<libc::c_char>();
    let mut meta: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::syscall(
            libc::SYS_newfstatat,
            source,
            name_ptr,
            &mut meta,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    } != 0
    {
        unsafe { fail(nonce, 1) }
    }
    match meta.st_mode & libc::S_IFMT {
        libc::S_IFDIR => {
            let fd = unsafe { new_directory(target, name_ptr, nonce) };
            unsafe {
                clone_readonly(source, name_ptr, fd, nonce);
                libc::syscall(libc::SYS_close, fd);
            }
        }
        libc::S_IFREG => {
            let fd = unsafe {
                libc::syscall(
                    libc::SYS_openat,
                    target,
                    name_ptr,
                    libc::O_RDONLY
                        | libc::O_CREAT
                        | libc::O_EXCL
                        | libc::O_CLOEXEC
                        | libc::O_NOFOLLOW,
                    0o600_u32,
                )
            };
            if fd < 0 || fd > i32::MAX as libc::c_long {
                unsafe { fail(nonce, 1) }
            }
            unsafe {
                clone_readonly(source, name_ptr, fd as RawFd, nonce);
                libc::syscall(libc::SYS_close, fd);
            }
        }
        libc::S_IFLNK => {
            let mut value = [0_u8; MAX_LINK + 1];
            let n = unsafe {
                libc::syscall(
                    libc::SYS_readlinkat,
                    source,
                    name_ptr,
                    value.as_mut_ptr(),
                    MAX_LINK,
                )
            };
            if n <= 0 || n >= MAX_LINK as libc::c_long || !link_target(&value[..n as usize]) {
                unsafe { protocol_failure(nonce) }
            }
            let pointer = if name == b"product" {
                if &value[..n as usize] != b"system/product"
                    && &value[..n as usize] != b"/system/product"
                {
                    unsafe { protocol_failure(nonce) }
                }
                c"/system/product".as_ptr()
            } else if name == b"system_ext" {
                if &value[..n as usize] != b"system/system_ext"
                    && &value[..n as usize] != b"/system/system_ext"
                {
                    unsafe { protocol_failure(nonce) }
                }
                c"/system/system_ext".as_ptr()
            } else {
                value.as_ptr().cast::<libc::c_char>()
            };
            if unsafe { libc::syscall(libc::SYS_symlinkat, pointer, target, name_ptr) } != 0 {
                unsafe { fail(nonce, 1) }
            }
        }
        _ => unsafe { protocol_failure(nonce) },
    }
}

/// Parse exactly one getdents64 record without dereferencing a packed header.
pub(super) fn entry_record(bytes: &[u8]) -> Option<(usize, &[u8])> {
    if bytes.len() < 20 {
        return None;
    }
    let length = u16::from_ne_bytes([bytes[16], bytes[17]]) as usize;
    if length < 20 || length > bytes.len() || length % 8 != 0 {
        return None;
    }
    let tail = &bytes[19..length];
    let end = tail.iter().position(|value| *value == 0)?;
    Some((length, &tail[..end]))
}

unsafe fn populate(source: RawFd, target: RawFd, nonce: [u8; 16]) {
    // Require the supported official GSI layout before changing any guest root.
    for path in [
        c"system",
        c"system/product",
        c"system/system_ext",
        c"vendor",
    ] {
        unsafe {
            source_directory(source, path.as_ptr(), nonce);
        }
    }
    let entries = unsafe { directory_at(source, c".".as_ptr(), nonce) };
    let mut seen = 0_usize;
    let mut buffer = [0_u8; 8192];
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
                Some(record) => record,
                None => unsafe { protocol_failure(nonce) },
            };
            if name != b"." && name != b".." {
                seen += 1;
                if seen > MAX_ROOT_ENTRIES {
                    unsafe { protocol_failure(nonce) }
                }
                unsafe {
                    copy_root_entry(source, target, name, nonce);
                }
            }
            at += length;
        }
    }
    if seen == 0 {
        unsafe { protocol_failure(nonce) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, entries);
    }
    for (name, expected) in [
        (c"product", b"/system/product".as_slice()),
        (c"system_ext", b"/system/system_ext".as_slice()),
    ] {
        let mut actual = [0_u8; 64];
        let n = unsafe {
            libc::syscall(
                libc::SYS_readlinkat,
                target,
                name.as_ptr(),
                actual.as_mut_ptr(),
                actual.len(),
            )
        };
        if n != expected.len() as libc::c_long || &actual[..expected.len()] != expected {
            unsafe { protocol_failure(nonce) }
        }
    }
}

unsafe fn empty_data(
    root: RawFd,
    name: *const libc::c_char,
    mode: *const libc::c_char,
    size: *const libc::c_char,
    nonce: [u8; 16],
) {
    let target = unsafe { directory_at(root, name, nonce) };
    let data = unsafe { make_tmpfs(mode, size, nonce) };
    unsafe {
        attach(data, target, nonce);
        libc::syscall(libc::SYS_close, target);
        libc::syscall(libc::SYS_close, data);
    }
}

/// Called only after the actual owned PID 1 emitted TreeReady.
pub(super) unsafe fn run(nonce: [u8; 16], parent_pid: u32, _mode: Mode) -> ! {
    unsafe {
        let [system, vendor] = receive_bases(nonce, parent_pid);
        require_image(system, nonce);
        require_image(vendor, nonce);
        // Overmount an existing real directory only inside the already-private
        // child mount namespace. No host directory is created or modified.
        let old_tmp = directory_at(libc::AT_FDCWD, c"/tmp".as_ptr(), nonce);
        let stage = make_tmpfs(c"0700".as_ptr(), c"16M".as_ptr(), nonce);
        attach(stage, old_tmp, nonce);
        libc::syscall(libc::SYS_close, old_tmp);
        let lower = new_directory(stage, c"lower".as_ptr(), nonce);
        attach(system, lower, nonce);
        libc::syscall(libc::SYS_close, lower);
        let root_target = new_directory(stage, c"root".as_ptr(), nonce);
        let root = make_tmpfs(c"0755".as_ptr(), c"16M".as_ptr(), nonce);
        attach(root, root_target, nonce);
        libc::syscall(libc::SYS_close, root_target);
        populate(system, root, nonce);
        let vendor_target = directory_at(root, c"vendor".as_ptr(), nonce);
        attach(vendor, vendor_target, nonce);
        libc::syscall(libc::SYS_close, vendor_target);
        empty_data(
            root,
            c"data".as_ptr(),
            c"0771".as_ptr(),
            c"512M".as_ptr(),
            nonce,
        );
        empty_data(
            root,
            c"metadata".as_ptr(),
            c"0700".as_ptr(),
            c"16M".as_ptr(),
            nonce,
        );
        let oldroot = new_directory(root, c".oldroot".as_ptr(), nonce);
        libc::syscall(libc::SYS_close, oldroot);
        if libc::syscall(libc::SYS_fchdir, root) != 0
            || libc::syscall(libc::SYS_pivot_root, c".".as_ptr(), c".oldroot".as_ptr()) != 0
            || libc::syscall(libc::SYS_chdir, c"/".as_ptr()) != 0
            || libc::syscall(libc::SYS_umount2, c"/.oldroot".as_ptr(), libc::MNT_DETACH) != 0
            || libc::syscall(
                libc::SYS_unlinkat,
                root,
                c".oldroot".as_ptr(),
                libc::AT_REMOVEDIR,
            ) != 0
        {
            fail(nonce, 1);
        }
        // The image/host-root/namespace FDs are not inherited by a future exec.
        // At this barrier exactly the same private control descriptor remains.
        if libc::syscall(libc::SYS_close_range, 4_u32, u32::MAX, 0) != 0 {
            fail(nonce, 1);
        }
        libc::syscall(libc::SYS_close, 0);
        libc::syscall(libc::SYS_close, 1);
        libc::syscall(libc::SYS_close, 2);
        send(nonce, Phase::EmptyRootReady, 0, 1);
        #[cfg(test)]
        if matches!(
            _mode,
            Mode::EmptyRootControl
                | Mode::DeviceRootControl
                | Mode::ProcessFilesystemsControl
                | Mode::BinderControl
        ) {
            receive(nonce, parent_pid, Phase::ProbeEmptyRoot);
            private_root_io_control(nonce);
            send(nonce, Phase::EmptyRootChecked, 0, 1);
        }
        #[cfg(test)]
        if matches!(_mode, Mode::EmptyRootControl) {
            receive(nonce, parent_pid, Phase::Stop);
            finish(0);
        }
        // The independent DEV barrier has no runtime/APEX or exec authority.
        super::private_dev::run(nonce, parent_pid, _mode);
    }
}

#[cfg(test)]
unsafe fn private_root_io_control(nonce: [u8; 16]) {
    for path in [c"/system/readonly-probe", c"/vendor/readonly-probe"] {
        let fd = unsafe {
            libc::syscall(
                libc::SYS_openat,
                libc::AT_FDCWD,
                path.as_ptr(),
                libc::O_WRONLY | libc::O_TRUNC | libc::O_CLOEXEC | libc::O_NOFOLLOW,
                0,
            )
        };
        if fd != -1 || unsafe { *libc::__errno_location() } != libc::EROFS {
            unsafe { protocol_failure(nonce) }
        }
    }
    for path in [c"/data/private-control", c"/metadata/private-control"] {
        let fd = unsafe {
            libc::syscall(
                libc::SYS_openat,
                libc::AT_FDCWD,
                path.as_ptr(),
                libc::O_RDWR | libc::O_CREAT | libc::O_EXCL | libc::O_CLOEXEC | libc::O_NOFOLLOW,
                0o600_u32,
            )
        };
        if fd < 0 {
            unsafe { fail(nonce, 1) }
        }
        let payload = b"owned-empty-data";
        let mut got = [0_u8; 16];
        let mut meta: libc::stat = unsafe { std::mem::zeroed() };
        if unsafe { libc::syscall(libc::SYS_write, fd, payload.as_ptr(), payload.len()) }
            != payload.len() as libc::c_long
            || unsafe { libc::syscall(libc::SYS_lseek, fd, 0, libc::SEEK_SET) } != 0
            || unsafe { libc::syscall(libc::SYS_read, fd, got.as_mut_ptr(), got.len()) }
                != payload.len() as libc::c_long
            || &got[..payload.len()] != payload
            || unsafe { libc::syscall(libc::SYS_fstat, fd, &mut meta) } != 0
            || meta.st_uid != 0
            || meta.st_gid != 0
            || meta.st_nlink != 1
            || meta.st_mode & libc::S_IFMT != libc::S_IFREG
        {
            unsafe { protocol_failure(nonce) }
        }
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
        if unsafe { libc::syscall(libc::SYS_unlinkat, libc::AT_FDCWD, path.as_ptr(), 0) } != 0 {
            unsafe { fail(nonce, 1) }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn raw_statfs_layout_matches_same_fd_standard_observation() {
        use std::os::fd::AsRawFd;
        let file = std::fs::File::open("/").unwrap();
        let mut raw: KernelStatfs = unsafe { std::mem::zeroed() };
        let mut standard: libc::statfs = unsafe { std::mem::zeroed() };
        let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
        assert_eq!(
            unsafe { libc::syscall(libc::SYS_fstatfs, file.as_raw_fd(), &mut raw) },
            0
        );
        assert_eq!(unsafe { libc::fstatfs(file.as_raw_fd(), &mut standard) }, 0);
        assert_eq!(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) }, 0);
        assert_eq!(raw.f_type, standard.f_type);
        assert_eq!(raw.f_bsize, standard.f_bsize);
        assert_eq!(raw.f_namelen, standard.f_namelen);
        assert_eq!(raw.f_flags as u64 & 7, flags.f_flag as u64 & 7);
    }

    #[test]
    fn filesystem_names_never_introduce_paths_or_parent_traversal() {
        for value in [
            b"system".as_slice(),
            b"lost+found",
            b"file_contexts.bin",
            b"system_ext",
        ] {
            assert!(component(value));
        }
        for value in [
            b"".as_slice(),
            b".",
            b"..",
            b"/system",
            b"system/etc",
            b"name\0tail",
            b"has space",
        ] {
            assert!(!component(value));
        }
        assert!(!component(&[b'a'; MAX_NAME + 1]));
        assert!(link_target(b"/system/product"));
        assert!(!link_target(b"/system/../host"));
        assert!(!link_target(b"../host"));
        assert!(!link_target(b"system\0host"));
    }

    #[test]
    fn getdents64_record_requires_complete_aligned_record_and_terminated_name() {
        let mut record = [0_u8; 32];
        record[16..18].copy_from_slice(&32_u16.to_ne_bytes());
        record[19..25].copy_from_slice(b"system");
        let (n, name) = entry_record(&record).unwrap();
        assert_eq!(n, 32);
        assert_eq!(name, b"system");
        assert!(entry_record(&record[..31]).is_none());
        record[16..18].copy_from_slice(&31_u16.to_ne_bytes());
        assert!(entry_record(&record).is_none());
        record[16..18].copy_from_slice(&32_u16.to_ne_bytes());
        record[19..].fill(b'x');
        assert!(entry_record(&record).is_none());
    }
}
