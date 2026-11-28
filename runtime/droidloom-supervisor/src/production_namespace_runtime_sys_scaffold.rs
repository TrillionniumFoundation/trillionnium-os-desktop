//! Candidate native-only child mount preparation for the exact empty CP3A /sys.
use super::super::{empty_root, guest_cgroup::ActivatedPayload};
use super::{
    EMPTY_PATH, NOEXEC, RO_IMAGE, TMPFS_MAGIC, attach, close, directory, exact_names, failed, fs,
    meta, rejected, require_root, same_inode,
};
use std::os::fd::RawFd;

const RESTRICTED_READONLY: u64 = RO_IMAGE | NOEXEC;

#[repr(C)]
struct MountAttr {
    attr_set: u64,
    attr_clr: u64,
    propagation: u64,
    userns_fd: u64,
}

unsafe fn mount_id(fd: RawFd, nonce: [u8; 16]) -> u64 {
    let mut stat: libc::statx = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::syscall(
            libc::SYS_statx,
            fd,
            c"".as_ptr(),
            EMPTY_PATH,
            libc::STATX_MNT_ID,
            &mut stat,
        )
    } != 0
    {
        unsafe { failed(nonce, line!()) }
    }
    if stat.stx_mask & libc::STATX_MNT_ID == 0 || stat.stx_mnt_id == 0 {
        unsafe { rejected(nonce) }
    }
    stat.stx_mnt_id
}

unsafe fn verify_scaffold(sys: RawFd, nonce: [u8; 16]) -> libc::stat {
    let metadata = unsafe { meta(sys, nonce) };
    let flags = unsafe { fs(sys, nonce) };
    if metadata.st_mode != libc::S_IFDIR | 0o755
        || metadata.st_uid != 0
        || metadata.st_gid != 0
        || flags.f_type != TMPFS_MAGIC
        || flags.f_flags as u64 & RESTRICTED_READONLY != RESTRICTED_READONLY
    {
        unsafe { rejected(nonce) }
    }
    unsafe { exact_names(sys, &[b"fs"], nonce) };
    metadata
}

/// The caller owns the original private PID1 root and enters only on NativeV2.
/// All descriptor work ends before RuntimeReady. For an error the existing
/// child failure path exits and the owner retains teardown custody.
pub(super) unsafe fn attach_native_scaffold(
    root: RawFd,
    payload: &ActivatedPayload,
    nonce: [u8; 16],
) {
    let lower = unsafe { directory(root, c"sys", nonce) };
    unsafe { require_root(lower, nonce) };
    let lower_identity = unsafe { meta(lower, nonce) };
    if lower_identity.st_mode != libc::S_IFDIR | 0o755 {
        unsafe { rejected(nonce) }
    }
    unsafe { exact_names(lower, &[], nonce) };

    let scaffold = unsafe { empty_root::make_tmpfs(c"0755".as_ptr(), c"64K".as_ptr(), nonce) };
    let fs_dir = unsafe { empty_root::new_directory(scaffold, c"fs".as_ptr(), nonce) };
    let placeholder = unsafe { empty_root::new_directory(fs_dir, c"cgroup".as_ptr(), nonce) };
    let placeholder_identity = unsafe { meta(placeholder, nonce) };
    unsafe {
        close(placeholder);
        close(fs_dir)
    };
    let flags = MountAttr {
        attr_set: RESTRICTED_READONLY,
        attr_clr: 0,
        propagation: 0,
        userns_fd: 0,
    };
    if unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            scaffold,
            c"".as_ptr(),
            EMPTY_PATH,
            &flags,
            std::mem::size_of::<MountAttr>(),
        )
    } != 0
    {
        unsafe { failed(nonce, line!()) }
    }
    let held_sys = unsafe { verify_scaffold(scaffold, nonce) };
    let held_sys_mount_id = unsafe { mount_id(scaffold, nonce) };
    if held_sys.st_dev == lower_identity.st_dev {
        unsafe { rejected(nonce) }
    }
    // The two detached sources are created inside the same owned PID1.
    let cgroup = match unsafe { payload.stage_detached() } {
        Ok(value) => value,
        Err(error) => unsafe {
            *libc::__errno_location() = error;
            failed(nonce, line!())
        },
    };
    let held_cgroup_mount_id = unsafe { mount_id(cgroup.descriptor(), nonce) };
    unsafe {
        attach(scaffold, lower, nonce);
        close(scaffold);
        close(lower)
    };
    let sys = unsafe { directory(root, c"sys", nonce) };
    let mounted_sys = unsafe { verify_scaffold(sys, nonce) };
    if !same_inode(&held_sys, &mounted_sys) || unsafe { mount_id(sys, nonce) } != held_sys_mount_id
    {
        unsafe { rejected(nonce) }
    }
    let fs_dir = unsafe { directory(sys, c"fs", nonce) };
    unsafe { exact_names(fs_dir, &[b"cgroup"], nonce) };
    let target = unsafe { directory(fs_dir, c"cgroup", nonce) };
    if !same_inode(&placeholder_identity, &unsafe { meta(target, nonce) })
        || unsafe { mount_id(target, nonce) } != held_sys_mount_id
    {
        unsafe { rejected(nonce) }
    }
    unsafe {
        attach(cgroup.descriptor(), target, nonce);
        close(target)
    };
    drop(cgroup);
    let visible = unsafe { directory(fs_dir, c"cgroup", nonce) };
    if unsafe { mount_id(visible, nonce) } != held_cgroup_mount_id
        || unsafe { payload.verify_projection(visible) }.is_err()
    {
        unsafe { rejected(nonce) }
    }
    unsafe {
        close(visible);
        close(fs_dir);
        close(sys)
    };
}
