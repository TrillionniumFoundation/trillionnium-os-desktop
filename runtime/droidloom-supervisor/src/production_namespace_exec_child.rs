//! Final raw execution boundary shared by the fixed private probe and the
//! exact-image Android entry. The scoped profile is distinct from the private
//! zero-capability probe and cannot grant initial-userns authority.
use crate::production_execution_profile as android;
use std::os::fd::RawFd;

#[path = "production_namespace_mac_child.rs"]
mod mac;

/// Arm only the additional fixed Android AppArmor profile on the current
/// owned init's next exec. The separate Android capability gate must already
/// have passed; this pending action cannot produce execution admission.
pub(super) unsafe fn arm_android_stack() -> i32 {
    unsafe { mac::arm_android_stack() }
}

#[derive(Clone, Copy)]
pub(super) enum FinalCapabilityProfile {
    AndroidUnqualified,
    AndroidCp3aScoped,
    #[cfg(test)]
    PrivateZero,
}

// Linux capability ABI v3 consists of two 32-bit records, including the
// inheritable set. No caller-supplied bitset or serialized profile is accepted.
#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Clone, Copy, Default, Eq, PartialEq)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}
const _: () = assert!(std::mem::size_of::<CapHeader>() == 8);
const _: () = assert!(std::mem::size_of::<CapData>() == 12);
const CAP_VERSION_3: u32 = 0x2008_0522;
const CAP_LAST: u32 = 40;
const PR_CAP_AMBIENT: i32 = 47;
const AMBIENT_IS_SET: i32 = 1;
const AMBIENT_CLEAR_ALL: i32 = 4;
// NOROOT + locked; NO_SETUID_FIXUP + locked; KEEP_CAPS off + locked;
// NO_CAP_AMBIENT_RAISE + locked. KEEP_CAPS itself is deliberately absent.
const ZERO_SECUREBITS: u32 = 1 | 2 | 4 | 8 | 32 | 64 | 128;

fn selected_zero(profile: FinalCapabilityProfile) -> bool {
    match profile {
        FinalCapabilityProfile::AndroidUnqualified => false,
        FinalCapabilityProfile::AndroidCp3aScoped => false,
        #[cfg(test)]
        FinalCapabilityProfile::PrivateZero => true,
    }
}

unsafe fn errno() -> i32 {
    unsafe { *libc::__errno_location() }
}

/// Raw child only, before exec. This function never changes UID/GID, raises
/// dumpability, adopts a PID, or acquires an executable by pathname. Returns
/// zero only after the actual kernel has read back the entire selected profile.
pub(super) unsafe fn prepare(profile: FinalCapabilityProfile) -> i32 {
    if matches!(profile, FinalCapabilityProfile::AndroidCp3aScoped) {
        return unsafe { prepare_android() };
    }
    if !selected_zero(profile) {
        return libc::EOPNOTSUPP;
    }
    unsafe {
        if libc::syscall(libc::SYS_getpid) != 1
            || libc::syscall(libc::SYS_getppid) != 0
            || libc::syscall(libc::SYS_getuid) != 0
            || libc::syscall(libc::SYS_geteuid) != 0
            || libc::syscall(libc::SYS_getgid) != 0
            || libc::syscall(libc::SYS_getegid) != 0
            || libc::syscall(libc::SYS_getgroups, 0, std::ptr::null::<u32>()) != 0
            || libc::syscall(libc::SYS_prctl, libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1
        {
            return libc::EPERM;
        }
        let mut death = 0_i32;
        if libc::syscall(libc::SYS_prctl, libc::PR_GET_PDEATHSIG, &mut death, 0, 0, 0) != 0 {
            return errno();
        }
        if death != libc::SIGKILL {
            return libc::EPROTO;
        }
        // A different capability ABI must receive a separate reviewed profile.
        // Do not silently omit a newly introduced bounding capability.
        if libc::syscall(
            libc::SYS_prctl,
            libc::PR_CAPBSET_READ,
            CAP_LAST + 1,
            0,
            0,
            0,
        ) != -1
            || errno() != libc::EINVAL
        {
            return libc::EOPNOTSUPP;
        }
        for cap in 0..=CAP_LAST {
            let value = libc::syscall(libc::SYS_prctl, libc::PR_CAPBSET_READ, cap, 0, 0, 0);
            if value != 0 && value != 1 {
                return if value == -1 { errno() } else { libc::EPROTO };
            }
        }
        if libc::syscall(libc::SYS_prctl, PR_CAP_AMBIENT, AMBIENT_CLEAR_ALL, 0, 0, 0) != 0 {
            return errno();
        }
        if libc::syscall(
            libc::SYS_prctl,
            libc::PR_SET_SECUREBITS,
            ZERO_SECUREBITS,
            0,
            0,
            0,
        ) != 0
        {
            return errno();
        }
        for cap in 0..=CAP_LAST {
            if libc::syscall(libc::SYS_prctl, libc::PR_CAPBSET_DROP, cap, 0, 0, 0) != 0 {
                return errno();
            }
        }
        let header = CapHeader {
            version: CAP_VERSION_3,
            pid: 0,
        };
        let zero = [CapData::default(); 2];
        if libc::syscall(libc::SYS_capset, &header, zero.as_ptr()) != 0 {
            return errno();
        }
        let mut observed = [CapData::default(); 2];
        if libc::syscall(libc::SYS_capget, &header, observed.as_mut_ptr()) != 0 {
            return errno();
        }
        if observed != zero
            || libc::syscall(libc::SYS_prctl, libc::PR_GET_SECUREBITS, 0, 0, 0, 0)
                != ZERO_SECUREBITS as libc::c_long
            || libc::syscall(libc::SYS_prctl, libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1
        {
            return libc::EPROTO;
        }
        for cap in 0..=CAP_LAST {
            if libc::syscall(libc::SYS_prctl, libc::PR_CAPBSET_READ, cap, 0, 0, 0) != 0
                || libc::syscall(libc::SYS_prctl, PR_CAP_AMBIENT, AMBIENT_IS_SET, cap, 0, 0) != 0
            {
                return libc::EPROTO;
            }
        }
        // Credential transitions must not silently discard the original
        // actually-parented death signal. We do not re-arm it without the
        // original parent-thread PIDFD race proof; a mismatch fails closed.
        death = 0;
        if libc::syscall(libc::SYS_prctl, libc::PR_GET_PDEATHSIG, &mut death, 0, 0, 0) != 0 {
            return errno();
        }
        if death != libc::SIGKILL {
            return libc::EPROTO;
        }
        0
    }
}

unsafe fn mapped_proc_file(path: &std::ffi::CStr) -> i32 {
    unsafe {
        let fd = libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            path.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
        );
        if fd < 0 {
            return errno();
        }
        let mut fs: libc::statfs = std::mem::zeroed();
        let mut bytes = [0_u8; 257];
        let result = if libc::syscall(libc::SYS_fstatfs, fd, &mut fs) != 0 {
            errno()
        } else if fs.f_type != 0x9fa0 {
            libc::EPROTO
        } else {
            let n = libc::syscall(libc::SYS_read, fd, bytes.as_mut_ptr(), bytes.len());
            if n < 0 {
                errno()
            } else if n == 0 || n > 256 || !android::subordinate_map(&bytes[..n as usize]) {
                libc::EPERM
            } else {
                let mut trailing = 0_u8;
                match libc::syscall(libc::SYS_read, fd, &mut trailing, 1_usize) {
                    0 => 0,
                    -1 => errno(),
                    _ => libc::EPROTO,
                }
            }
        };
        libc::syscall(libc::SYS_close, fd);
        result
    }
}

unsafe fn private_namespaces() -> i32 {
    unsafe {
        for path in [c"/proc/self/uid_map", c"/proc/self/gid_map"] {
            let rc = mapped_proc_file(path);
            if rc != 0 {
                return rc;
            }
        }
        let user = libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            c"/proc/self/ns/user".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        );
        if user < 0 {
            return errno();
        }
        let mut expected: libc::stat = std::mem::zeroed();
        let mut fs: libc::statfs = std::mem::zeroed();
        let mut result = 0;
        if libc::syscall(libc::SYS_fstat, user, &mut expected) != 0
            || libc::syscall(libc::SYS_fstatfs, user, &mut fs) != 0
        {
            result = errno();
        } else if fs.f_type != 0x6e73_6673
            || libc::syscall(libc::SYS_ioctl, user, 0xb703_u64)
                != libc::CLONE_NEWUSER as libc::c_long
        {
            result = libc::EPROTO;
        }
        for (path, kind) in [
            (c"/proc/self/ns/mnt", libc::CLONE_NEWNS),
            (c"/proc/self/ns/pid", libc::CLONE_NEWPID),
            (c"/proc/self/ns/net", libc::CLONE_NEWNET),
            (c"/proc/self/ns/ipc", libc::CLONE_NEWIPC),
            (c"/proc/self/ns/uts", libc::CLONE_NEWUTS),
            (c"/proc/self/ns/cgroup", libc::CLONE_NEWCGROUP),
        ] {
            if result != 0 {
                break;
            }
            let namespace = libc::syscall(
                libc::SYS_openat,
                libc::AT_FDCWD,
                path.as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC,
            );
            if namespace < 0 {
                result = errno();
                break;
            }
            if libc::syscall(libc::SYS_ioctl, namespace, 0xb703_u64) != kind as libc::c_long {
                result = libc::EPROTO;
            } else {
                // NS_GET_USERNS returns the kernel's owning user namespace;
                // every retained authority namespace must belong to this one.
                let owner = libc::syscall(libc::SYS_ioctl, namespace, 0xb701_u64);
                if owner < 0 {
                    result = errno();
                } else {
                    let mut actual: libc::stat = std::mem::zeroed();
                    if libc::syscall(libc::SYS_fstat, owner, &mut actual) != 0 {
                        result = errno();
                    } else if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino) {
                        result = libc::EPERM;
                    }
                    libc::syscall(libc::SYS_close, owner);
                }
            }
            libc::syscall(libc::SYS_close, namespace);
        }
        libc::syscall(libc::SYS_close, user);
        result
    }
}

/// One fixed Android profile inside the already attested private namespaces.
/// It deliberately preserves normal setuid/ambient transitions used by AOSP
/// init. Bounding caps can only be removed; NNP and the separate inherited
/// seccomp/MAC layers remain mandatory. No user-supplied mask is accepted.
unsafe fn prepare_android() -> i32 {
    unsafe {
        if libc::syscall(libc::SYS_getpid) != 1
            || libc::syscall(libc::SYS_getppid) != 0
            || libc::syscall(libc::SYS_getuid) != 0
            || libc::syscall(libc::SYS_geteuid) != 0
            || libc::syscall(libc::SYS_getgid) != 0
            || libc::syscall(libc::SYS_getegid) != 0
            || libc::syscall(libc::SYS_getgroups, 0, std::ptr::null::<u32>()) != 0
            || libc::syscall(libc::SYS_prctl, libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1
            || libc::syscall(libc::SYS_prctl, libc::PR_GET_SECUREBITS, 0, 0, 0, 0) != 0
        {
            return libc::EPERM;
        }
        let mut death = 0_i32;
        if libc::syscall(libc::SYS_prctl, libc::PR_GET_PDEATHSIG, &mut death, 0, 0, 0) != 0 {
            return errno();
        }
        if death != libc::SIGKILL {
            return libc::EPROTO;
        }
        let rc = private_namespaces();
        if rc != 0 {
            return rc;
        }
        if libc::syscall(
            libc::SYS_prctl,
            libc::PR_CAPBSET_READ,
            android::CAP_LAST + 1,
            0,
            0,
            0,
        ) != -1
            || errno() != libc::EINVAL
        {
            return libc::EOPNOTSUPP;
        }
        for cap in 0..=android::CAP_LAST {
            let observed = libc::syscall(libc::SYS_prctl, libc::PR_CAPBSET_READ, cap, 0, 0, 0);
            if observed != 0 && observed != 1 {
                return if observed < 0 { errno() } else { libc::EPROTO };
            }
            if android::CAPABILITIES & (1_u64 << cap) != 0 && observed != 1 {
                return libc::EPERM;
            }
        }
        let header = CapHeader {
            version: CAP_VERSION_3,
            pid: 0,
        };
        let desired = [
            CapData {
                effective: android::CAPABILITIES as u32,
                permitted: android::CAPABILITIES as u32,
                inheritable: 0,
            },
            CapData {
                effective: (android::CAPABILITIES >> 32) as u32,
                permitted: (android::CAPABILITIES >> 32) as u32,
                inheritable: 0,
            },
        ];
        let mut current = [CapData::default(); 2];
        if libc::syscall(libc::SYS_capget, &header, current.as_mut_ptr()) != 0 {
            return errno();
        }
        if current
            .iter()
            .zip(desired)
            .any(|(have, want)| have.permitted & want.permitted != want.permitted)
        {
            return libc::EPERM;
        }
        if libc::syscall(libc::SYS_prctl, PR_CAP_AMBIENT, AMBIENT_CLEAR_ALL, 0, 0, 0) != 0 {
            return errno();
        }
        for cap in 0..=android::CAP_LAST {
            if android::CAPABILITIES & (1_u64 << cap) == 0
                && libc::syscall(libc::SYS_prctl, libc::PR_CAPBSET_DROP, cap, 0, 0, 0) != 0
            {
                return errno();
            }
        }
        if libc::syscall(libc::SYS_capset, &header, desired.as_ptr()) != 0 {
            return errno();
        }
        if libc::syscall(libc::SYS_capget, &header, current.as_mut_ptr()) != 0 {
            return errno();
        }
        if current != desired
            || libc::syscall(libc::SYS_prctl, libc::PR_GET_SECUREBITS, 0, 0, 0, 0) != 0
            || libc::syscall(libc::SYS_prctl, libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1
        {
            return libc::EPROTO;
        }
        for cap in 0..=android::CAP_LAST {
            let wanted = i64::from(android::CAPABILITIES & (1_u64 << cap) != 0);
            if libc::syscall(libc::SYS_prctl, libc::PR_CAPBSET_READ, cap, 0, 0, 0) != wanted
                || libc::syscall(libc::SYS_prctl, PR_CAP_AMBIENT, AMBIENT_IS_SET, cap, 0, 0) != 0
            {
                return libc::EPROTO;
            }
        }
        if libc::syscall(libc::SYS_prctl, libc::PR_GET_PDEATHSIG, &mut death, 0, 0, 0) != 0 {
            return errno();
        }
        if death != libc::SIGKILL {
            return libc::EPROTO;
        }
        private_namespaces()
    }
}

/// Both callers hold the same previously authenticated executable descriptor.
/// The fixed call sites supply their compile-time argv/env layout; no packet
/// carries a pathname, command string, environment, or exec flags.
pub(super) unsafe fn exec_held(
    fd: RawFd,
    argv: *const *const libc::c_char,
    env: *const *const libc::c_char,
) -> i32 {
    unsafe {
        libc::syscall(libc::SYS_execveat, fd, c"".as_ptr(), argv, env, 0x1000_u32);
        errno()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn production_final_exec_does_not_infer_android_capabilities_from_private_profile() {
        assert!(!selected_zero(FinalCapabilityProfile::AndroidUnqualified));
        assert!(selected_zero(FinalCapabilityProfile::PrivateZero));
        assert!(!selected_zero(FinalCapabilityProfile::AndroidCp3aScoped));
        // Rejection occurs before any syscall or mutation for this profile.
        assert_eq!(
            unsafe { prepare(FinalCapabilityProfile::AndroidUnqualified) },
            libc::EOPNOTSUPP
        );
        assert_eq!(ZERO_SECUREBITS, 0xef);
        assert_eq!(ZERO_SECUREBITS & 16, 0);
    }

    #[test]
    fn scoped_android_profile_rejects_an_ordinary_process_before_any_capability_change() {
        assert_ne!(unsafe { libc::getpid() }, 1);
        let header = CapHeader {
            version: CAP_VERSION_3,
            pid: 0,
        };
        let mut before = [CapData::default(); 2];
        let mut after = [CapData::default(); 2];
        assert_eq!(
            unsafe { libc::syscall(libc::SYS_capget, &header, before.as_mut_ptr()) },
            0
        );
        assert_eq!(
            unsafe { prepare(FinalCapabilityProfile::AndroidCp3aScoped) },
            libc::EPERM
        );
        assert_eq!(
            unsafe { libc::syscall(libc::SYS_capget, &header, after.as_mut_ptr()) },
            0
        );
        assert!(before == after);
    }
}
