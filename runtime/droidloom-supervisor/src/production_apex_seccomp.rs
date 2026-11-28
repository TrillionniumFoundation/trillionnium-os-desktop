//! Fixed inherited syscall transport for original init/APEX operations.
//!
//! This filter grants no operation. The listener is created by the original
//! raw PID 1, transferred before exec, and never left open in Android. The
//! existing global-operation filter and all ordinary capability/MAC checks
//! remain. A notification is not an executable, namespace or input witness.

pub(crate) const RECV: libc::c_ulong = 0xc050_2100;
pub(crate) const SEND: libc::c_ulong = 0xc018_2101;
pub(crate) const ID_VALID: libc::c_ulong = 0x4008_2102;
// Fixed same-listener, same-task native exit observer; zero flags/reserved only.
pub(crate) const ARM_NATIVE_EXIT: libc::c_ulong = 0x4018_2150;

#[repr(C)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct ArmNativeExit {
    pub(crate) id: u64,
    pub(crate) pidfd: i32,
    pub(crate) mntns_fd: i32,
    pub(crate) flags: u32,
    pub(crate) reserved: u32,
}
const _: [(); 24] = [(); std::mem::size_of::<ArmNativeExit>()];
const ARCH: u32 = 0xc000_003e;
const NOTIFY: u32 = 0x7fc0_0000;
const ALLOW: u32 = 0x7fff_0000;
const KILL: u32 = 0x8000_0000;
const DENY: u32 = 0x0005_0000 | libc::EPERM as u32;
// Final pinned 6.18.64 x86-64 syscall table (ae37c498...): common 467.
const SYS_OPEN_TREE_ATTR: libc::c_long = 467;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub(crate) struct Data {
    pub(crate) nr: i32,
    pub(crate) arch: u32,
    pub(crate) instruction_pointer: u64,
    pub(crate) args: [u64; 6],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub(crate) struct Notification {
    pub(crate) id: u64,
    pub(crate) pid: u32,
    pub(crate) flags: u32,
    pub(crate) data: Data,
}

#[repr(C)]
#[derive(Default)]
pub(crate) struct Response {
    pub(crate) id: u64,
    pub(crate) value: i64,
    pub(crate) error: i32,
    pub(crate) flags: u32,
}

#[repr(C)]
#[derive(Default)]
struct Sizes {
    notification: u16,
    response: u16,
    data: u16,
}
const _: [(); 80] = [(); std::mem::size_of::<Notification>()];
const _: [(); 24] = [(); std::mem::size_of::<Response>()];
const _: [(); 64] = [(); std::mem::size_of::<Data>()];

const fn op(code: u16, jt: u8, jf: u8, k: u32) -> libc::sock_filter {
    libc::sock_filter { code, jt, jf, k }
}
const fn eq(value: libc::c_long, skip: u8) -> libc::sock_filter {
    op(0x15, 0, skip, value as u32)
}
const fn result(value: u32) -> libc::sock_filter {
    op(0x06, 0, 0, value)
}
const FILTER: &[libc::sock_filter] = &[
    op(0x20, 0, 0, 4),
    op(0x15, 1, 0, ARCH),
    result(KILL),
    op(0x20, 0, 0, 0),
    op(0x45, 0, 1, 0x4000_0000),
    result(KILL),
    eq(libc::SYS_mount, 1),
    result(NOTIFY),
    eq(libc::SYS_umount2, 1),
    result(NOTIFY),
    eq(libc::SYS_unshare, 1),
    result(NOTIFY),
    eq(libc::SYS_setns, 1),
    result(NOTIFY),
    // Serialize all supported modern mount entry points through the same
    // listener. No native-namespace continuation can authorize these calls.
    eq(libc::SYS_fsopen, 1),
    result(NOTIFY),
    eq(libc::SYS_fsconfig, 1),
    result(NOTIFY),
    eq(libc::SYS_fsmount, 1),
    result(NOTIFY),
    eq(libc::SYS_fspick, 1),
    result(NOTIFY),
    eq(libc::SYS_open_tree, 1),
    result(NOTIFY),
    eq(libc::SYS_move_mount, 1),
    result(NOTIFY),
    eq(libc::SYS_mount_setattr, 1),
    result(NOTIFY),
    eq(libc::SYS_pivot_root, 1),
    result(NOTIFY),
    eq(libc::SYS_chroot, 1),
    result(NOTIFY),
    eq(SYS_OPEN_TREE_ATTR, 1),
    result(NOTIFY),
    // A later same-priority USER_NOTIF listener must not supersede this
    // original owner. Only FILTER + NEW_LISTENER is denied. GET_* operations,
    // ordinary Android filters and TSYNC retain native kernel behavior.
    eq(libc::SYS_seccomp, 6),
    op(0x20, 0, 0, 16),
    op(0x15, 0, 3, 1), // SECCOMP_SET_MODE_FILTER
    op(0x20, 0, 0, 24),
    op(0x45, 0, 1, 0x8), // SECCOMP_FILTER_FLAG_NEW_LISTENER
    result(DENY),
    result(ALLOW),
    eq(libc::SYS_clone, 4),
    op(0x20, 0, 0, 16),
    op(0x45, 0, 1, libc::CLONE_NEWNS as u32),
    result(NOTIFY),
    result(ALLOW),
    eq(libc::SYS_ioctl, 8),
    op(0x20, 0, 0, 24),
    op(0x54, 0, 0, 0xff00),
    eq(0x4c00, 1),
    result(NOTIFY),
    eq(0xfd00, 1),
    result(NOTIFY),
    eq(0x1200, 1),
    result(NOTIFY),
    result(ALLOW),
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum Operation {
    Mount,
    Unmount,
    Unshare,
    SetNamespace,
    CloneMountNamespace,
    MountApi,
    LoopIoctl,
    DeviceMapperIoctl,
    BlockIoctl,
}

impl Notification {
    pub(crate) fn operation(&self) -> Option<Operation> {
        if self.pid <= 1 || self.flags != 0 || self.data.arch != ARCH {
            return None;
        }
        match self.data.nr as libc::c_long {
            libc::SYS_mount => Some(Operation::Mount),
            libc::SYS_umount2 => Some(Operation::Unmount),
            libc::SYS_unshare => Some(Operation::Unshare),
            libc::SYS_setns => Some(Operation::SetNamespace),
            libc::SYS_fsopen
            | libc::SYS_fsconfig
            | libc::SYS_fsmount
            | libc::SYS_fspick
            | libc::SYS_open_tree
            | libc::SYS_move_mount
            | libc::SYS_mount_setattr
            | libc::SYS_pivot_root
            | libc::SYS_chroot
            | SYS_OPEN_TREE_ATTR => Some(Operation::MountApi),
            libc::SYS_clone if self.data.args[0] & libc::CLONE_NEWNS as u64 != 0 => {
                Some(Operation::CloneMountNamespace)
            }
            libc::SYS_ioctl => match self.data.args[1] & 0xff00 {
                0x4c00 => Some(Operation::LoopIoctl),
                0xfd00 => Some(Operation::DeviceMapperIoctl),
                0x1200 => Some(Operation::BlockIoctl),
                _ => None,
            },
            _ => None,
        }
    }
}

/// Raw child only, after the existing fixed global filter and stdio setup.
/// No TSYNC: the original fixed PID 1 is still the single pre-exec thread.
/// Nonfatal signals cannot cancel a notification once the broker received it;
/// fatal exit still invalidates its ID and never authorizes a stale operation.
pub(crate) unsafe fn install() -> std::result::Result<i32, i32> {
    #[cfg(not(target_arch = "x86_64"))]
    {
        return Err(libc::EOPNOTSUPP);
    }
    #[cfg(target_arch = "x86_64")]
    unsafe {
        if libc::syscall(libc::SYS_prctl, libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1 {
            return Err(libc::EPERM);
        }
        let mut sizes = Sizes::default();
        if libc::syscall(libc::SYS_seccomp, 3, 0, &mut sizes) != 0 {
            return Err(*libc::__errno_location());
        }
        if (sizes.notification, sizes.response, sizes.data) != (80, 24, 64) {
            return Err(libc::EOPNOTSUPP);
        }
        let program = libc::sock_fprog {
            len: FILTER.len() as u16,
            filter: FILTER.as_ptr().cast_mut(),
        };
        let raw = libc::syscall(libc::SYS_seccomp, 1, 0x8_u32 | 0x20_u32, &program);
        if raw < 0 {
            return Err(*libc::__errno_location());
        }
        if raw > i32::MAX as libc::c_long {
            libc::syscall(libc::SYS_close, raw);
            return Err(libc::EPROTO);
        }
        let flags = libc::syscall(libc::SYS_fcntl, raw, libc::F_GETFD);
        if flags < 0 || flags & libc::FD_CLOEXEC as libc::c_long == 0 {
            libc::syscall(libc::SYS_close, raw);
            return Err(libc::EPROTO);
        }
        Ok(raw as i32)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn decision(nr: u32, arch: u32, first: u64, second: u64) -> u32 {
        let mut pc = 0;
        let mut value = 0;
        for _ in 0..FILTER.len() * 2 {
            let i = FILTER[pc];
            match i.code {
                0x20 => {
                    value = match i.k {
                        0 => nr,
                        4 => arch,
                        16 => first as u32,
                        24 => second as u32,
                        _ => panic!("unexpected load"),
                    };
                    pc += 1;
                }
                0x15 => pc += 1 + if value == i.k { i.jt } else { i.jf } as usize,
                0x45 => pc += 1 + if value & i.k != 0 { i.jt } else { i.jf } as usize,
                0x54 => {
                    value &= i.k;
                    pc += 1;
                }
                0x06 => return i.k,
                _ => panic!("unexpected instruction"),
            }
        }
        panic!("unterminated fixed filter")
    }

    #[test]
    fn apex_notification_rejects_only_new_filter_listeners_preserving_native_seccomp_operations() {
        for flags in [0x8, 0x9, 0xa, 0x28, u32::MAX as u64] {
            assert_eq!(decision(libc::SYS_seccomp as u32, ARCH, 1, flags), DENY);
        }
        for flags in [0, 1, 2, 4, 0x10, 0x20] {
            assert_eq!(decision(libc::SYS_seccomp as u32, ARCH, 1, flags), ALLOW);
        }
        for operation in [0, 2, 3, u32::MAX as u64] {
            for flags in [0, 1, 8, u32::MAX as u64] {
                assert_eq!(
                    decision(libc::SYS_seccomp as u32, ARCH, operation, flags),
                    ALLOW
                );
            }
        }
        // PR_SET_SECCOMP has no NEW_LISTENER path; native strict/filter
        // validation and Android's own no-listener filters remain untouched.
        assert_eq!(
            decision(libc::SYS_prctl as u32, ARCH, libc::PR_SET_SECCOMP as u64, 2),
            ALLOW
        );
        assert_eq!(decision(libc::SYS_chroot as u32, ARCH, 0, 0), NOTIFY);
    }

    #[test]
    fn apex_notification_filter_preserves_native_io_and_catches_privileged_abi_families() {
        for nr in [
            libc::SYS_mount,
            libc::SYS_umount2,
            libc::SYS_unshare,
            libc::SYS_setns,
            libc::SYS_fsopen,
            libc::SYS_fsconfig,
            libc::SYS_fsmount,
            libc::SYS_fspick,
            libc::SYS_open_tree,
            libc::SYS_move_mount,
            libc::SYS_mount_setattr,
            libc::SYS_pivot_root,
            libc::SYS_chroot,
            SYS_OPEN_TREE_ATTR,
        ] {
            assert_eq!(decision(nr as u32, ARCH, 0, 0), NOTIFY);
        }
        for request in [
            0x4c00,
            0x4c01,
            0x4c05,
            0x4c0a,
            0x4c82,
            0xc138_fd00,
            0xc138_fd09,
            0x1261,
            0x8008_1272,
        ] {
            assert_eq!(decision(libc::SYS_ioctl as u32, ARCH, 42, request), NOTIFY);
            assert_eq!(
                decision(libc::SYS_ioctl as u32, ARCH, 42, request | 0x1000_0000_0000),
                NOTIFY
            );
        }
        for (nr, a, b) in [
            (libc::SYS_read, 0, 0),
            (libc::SYS_openat, 0, 0),
            (libc::SYS_ioctl, 42, 0xc030_6201),
            (libc::SYS_clone, libc::SIGCHLD as u64, 0),
        ] {
            assert_eq!(decision(nr as u32, ARCH, a, b), ALLOW);
        }
        assert_eq!(
            decision(
                libc::SYS_clone as u32,
                ARCH,
                libc::CLONE_NEWNS as u64 | libc::SIGCHLD as u64,
                0
            ),
            NOTIFY
        );
        assert_eq!(
            decision(libc::SYS_ioctl as u32, 0x4000_0003, 0, 0x4c82),
            KILL
        );
        assert_eq!(
            decision(0x4000_0000 | libc::SYS_ioctl as u32, ARCH, 0, 0x4c82),
            KILL
        );
    }
}

#[cfg(test)]
#[path = "production_apex_seccomp_controls.rs"]
mod controls;
