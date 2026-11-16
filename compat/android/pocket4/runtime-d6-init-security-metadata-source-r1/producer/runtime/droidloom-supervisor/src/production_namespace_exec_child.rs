//! Final raw execution boundary shared by the fixed private probe and the
//! future Android entry. A private zero-capability profile does not select an
//! Android capability contract. The latter remains explicitly unqualified.
use std::os::fd::RawFd;

#[derive(Clone, Copy)]
pub(super) enum FinalCapabilityProfile {
    AndroidUnqualified,
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
        #[cfg(test)]
        FinalCapabilityProfile::PrivateZero => true,
    }
}

unsafe fn errno() -> i32 {
    unsafe { *libc::__errno_location() }
}

/// Raw child only, before exec. This function never changes UID/GID, raises
/// dumpability, adopts a PID, or acquires an executable by pathname. Returns
/// zero only after the actual kernel has read back the entire zero profile.
pub(super) unsafe fn prepare(profile: FinalCapabilityProfile) -> i32 {
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
        // Rejection occurs before any syscall or mutation for this profile.
        assert_eq!(
            unsafe { prepare(FinalCapabilityProfile::AndroidUnqualified) },
            libc::EOPNOTSUPP
        );
        assert_eq!(ZERO_SECUREBITS, 0xef);
        assert_eq!(ZERO_SECUREBITS & 16, 0);
    }
}
