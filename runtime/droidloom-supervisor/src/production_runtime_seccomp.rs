//! Fixed additional syscall boundary for the owned Android PID 1 and heirs.
//!
//! The private namespace and admitted FD tree remain the resource authority.
//! This filter does not claim to replace Android's own SELinux or app filters.
//! It blocks host administration interfaces, and
//! prevents creating another user/PID/cgroup/network namespace after handoff.
//! Private mount namespaces remain available to Android init and zygote.

const AUDIT_ARCH_X86_64: u32 = 0xc000_003e;
const BPF_LD_W_ABS: u16 = 0x20;
const BPF_JMP_JEQ_K: u16 = 0x15;
const BPF_JMP_JSET_K: u16 = 0x45;
const BPF_RET_K: u16 = 0x06;
const RET_KILL_PROCESS: u32 = 0x8000_0000;
const RET_ERRNO: u32 = 0x0005_0000;
const RET_ALLOW: u32 = 0x7fff_0000;
const NEW_AUTHORITY_NAMESPACES: u32 = (libc::CLONE_NEWUSER
    | libc::CLONE_NEWPID
    | libc::CLONE_NEWCGROUP
    | libc::CLONE_NEWNET
    | libc::CLONE_NEWUTS
    | libc::CLONE_NEWIPC) as u32;

const fn instruction(code: u16, jt: u8, jf: u8, k: u32) -> libc::sock_filter {
    libc::sock_filter { code, jt, jf, k }
}
const fn load(offset: u32) -> libc::sock_filter {
    instruction(BPF_LD_W_ABS, 0, 0, offset)
}
const fn equal(number: libc::c_long, no: u8) -> libc::sock_filter {
    instruction(BPF_JMP_JEQ_K, 0, no, number as u32)
}
const fn denied() -> libc::sock_filter {
    instruction(BPF_RET_K, 0, 0, RET_ERRNO | libc::EPERM as u32)
}

// seccomp_data: int nr at 0, __u32 arch at 4, __u64 ip at 8,
// __u64 args[6] at 16. The x86-64 ABI is checked before any argument load;
// x32 is rejected rather than accidentally using x86-64 syscall numbers.
const FILTER: &[libc::sock_filter] = &[
    load(4),
    instruction(BPF_JMP_JEQ_K, 1, 0, AUDIT_ARCH_X86_64),
    instruction(BPF_RET_K, 0, 0, RET_KILL_PROCESS),
    load(0),
    instruction(BPF_JMP_JSET_K, 0, 1, 0x4000_0000),
    instruction(BPF_RET_K, 0, 0, RET_KILL_PROCESS),
    // clone3 pointer arguments cannot be inspected by classic BPF. ENOSYS is
    // the normal libc fallback signal; legacy clone retains the mask below.
    equal(libc::SYS_clone3, 1),
    instruction(BPF_RET_K, 0, 0, RET_ERRNO | libc::ENOSYS as u32),
    equal(libc::SYS_clone, 4),
    load(16),
    instruction(BPF_JMP_JSET_K, 0, 1, NEW_AUTHORITY_NAMESPACES),
    denied(),
    instruction(BPF_RET_K, 0, 0, RET_ALLOW),
    equal(libc::SYS_unshare, 4),
    load(16),
    instruction(BPF_JMP_JSET_K, 0, 1, NEW_AUTHORITY_NAMESPACES),
    denied(),
    instruction(BPF_RET_K, 0, 0, RET_ALLOW),
    equal(libc::SYS_bpf, 1),
    denied(),
    equal(libc::SYS_perf_event_open, 1),
    denied(),
    equal(libc::SYS_userfaultfd, 1),
    denied(),
    equal(libc::SYS_kexec_load, 1),
    denied(),
    equal(libc::SYS_kexec_file_load, 1),
    denied(),
    equal(libc::SYS_init_module, 1),
    denied(),
    equal(libc::SYS_finit_module, 1),
    denied(),
    equal(libc::SYS_delete_module, 1),
    denied(),
    equal(libc::SYS_reboot, 1),
    denied(),
    equal(libc::SYS_swapon, 1),
    denied(),
    equal(libc::SYS_swapoff, 1),
    denied(),
    equal(libc::SYS_iopl, 1),
    denied(),
    equal(libc::SYS_ioperm, 1),
    denied(),
    equal(libc::SYS_open_by_handle_at, 1),
    denied(),
    equal(libc::SYS_fanotify_init, 1),
    denied(),
    equal(libc::SYS_acct, 1),
    denied(),
    equal(libc::SYS_settimeofday, 1),
    denied(),
    equal(libc::SYS_clock_settime, 1),
    denied(),
    equal(libc::SYS_adjtimex, 1),
    denied(),
    equal(libc::SYS_clock_adjtime, 1),
    denied(),
    instruction(BPF_RET_K, 0, 0, RET_ALLOW),
];

/// Raw child only: install on its one current thread immediately before the
/// fixed init exec. The ancestor broker is never filtered. Returns 0 or a
/// positive errno without allocating or using a libc credential wrapper.
pub(crate) unsafe fn install() -> i32 {
    #[cfg(not(target_arch = "x86_64"))]
    {
        return libc::EOPNOTSUPP;
    }
    #[cfg(target_arch = "x86_64")]
    unsafe {
        if libc::syscall(libc::SYS_prctl, libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1 {
            return libc::EPERM;
        }
        let program = libc::sock_fprog {
            len: FILTER.len() as u16,
            filter: FILTER.as_ptr().cast_mut(),
        };
        if libc::syscall(libc::SYS_seccomp, 1, 0, &program) != 0 {
            return *libc::__errno_location();
        }
        if libc::syscall(libc::SYS_prctl, libc::PR_GET_SECCOMP, 0, 0, 0, 0) != 2 {
            return libc::EPROTO;
        }
        0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn decision(nr: u32, arch: u32, first_arg: u64) -> u32 {
        let mut accumulator = 0;
        let mut position = 0;
        let mut steps = 0;
        loop {
            assert!(position < FILTER.len() && steps < FILTER.len() * 2);
            let op = FILTER[position];
            steps += 1;
            match op.code {
                BPF_LD_W_ABS => {
                    accumulator = match op.k {
                        0 => nr,
                        4 => arch,
                        16 => first_arg as u32,
                        _ => panic!("unexpected seccomp_data load"),
                    };
                    position += 1;
                }
                BPF_JMP_JEQ_K => {
                    position += 1 + if accumulator == op.k { op.jt } else { op.jf } as usize
                }
                BPF_JMP_JSET_K => {
                    position += 1 + if accumulator & op.k != 0 {
                        op.jt
                    } else {
                        op.jf
                    } as usize
                }
                BPF_RET_K => return op.k,
                _ => panic!("unexpected BPF instruction"),
            }
        }
    }

    #[test]
    fn production_seccomp_rejects_compat_abi_and_new_authority_namespaces() {
        assert_eq!(
            decision(libc::SYS_getpid as u32, 0x4000_0003, 0),
            RET_KILL_PROCESS
        );
        assert_eq!(
            decision(0x4000_0000 | libc::SYS_getpid as u32, AUDIT_ARCH_X86_64, 0),
            RET_KILL_PROCESS
        );
        for syscall in [libc::SYS_clone, libc::SYS_unshare] {
            for flag in [
                libc::CLONE_NEWUSER,
                libc::CLONE_NEWPID,
                libc::CLONE_NEWCGROUP,
                libc::CLONE_NEWNET,
                libc::CLONE_NEWUTS,
                libc::CLONE_NEWIPC,
            ] {
                assert_eq!(
                    decision(syscall as u32, AUDIT_ARCH_X86_64, flag as u64),
                    RET_ERRNO | libc::EPERM as u32
                );
            }
            assert_eq!(
                decision(syscall as u32, AUDIT_ARCH_X86_64, libc::CLONE_NEWNS as u64),
                RET_ALLOW
            );
        }
        assert_eq!(
            decision(libc::SYS_clone3 as u32, AUDIT_ARCH_X86_64, 0),
            RET_ERRNO | libc::ENOSYS as u32
        );
    }

    #[test]
    fn production_seccomp_blocks_global_operations_preserving_guest_io() {
        for syscall in [
            libc::SYS_bpf,
            libc::SYS_kexec_load,
            libc::SYS_finit_module,
            libc::SYS_reboot,
            libc::SYS_open_by_handle_at,
            libc::SYS_clock_settime,
        ] {
            assert_eq!(
                decision(syscall as u32, AUDIT_ARCH_X86_64, 0),
                RET_ERRNO | libc::EPERM as u32
            );
        }
        // Android debuggerd needs these operations against its own PID-ns
        // tasks. No ancestor PID or host process descriptor is handed off.
        for syscall in [
            libc::SYS_getpid,
            libc::SYS_read,
            libc::SYS_write,
            libc::SYS_ioctl,
            libc::SYS_futex,
            libc::SYS_execveat,
            libc::SYS_mount,
            libc::SYS_setns,
            libc::SYS_ptrace,
            libc::SYS_process_vm_readv,
            libc::SYS_process_vm_writev,
            libc::SYS_kcmp,
        ] {
            assert_eq!(decision(syscall as u32, AUDIT_ARCH_X86_64, 0), RET_ALLOW);
        }
        assert_eq!(
            decision(
                libc::SYS_clone as u32,
                AUDIT_ARCH_X86_64,
                (libc::CLONE_VM | libc::CLONE_THREAD | libc::CLONE_SIGHAND) as u64
            ),
            RET_ALLOW
        );
    }

    #[test]
    fn production_seccomp_actual_filter_changes_invalid_clone3_to_enosys() {
        const CHILD: &str = "DROIDLOOM_SECCOMP_ORDINARY_CONTROL";
        if std::env::var_os(CHILD).is_some() {
            // This is an ordinary fresh test process. The deliberately invalid
            // clone3 call cannot create a child; the valid x86-64 kernel result
            // before filtering must be EINVAL, not an inherited ENOSYS filter.
            unsafe {
                assert_eq!(
                    libc::syscall(libc::SYS_clone3, std::ptr::null::<u8>(), 0),
                    -1
                );
                assert_eq!(*libc::__errno_location(), libc::EINVAL);
                assert_eq!(
                    libc::syscall(libc::SYS_prctl, libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0),
                    0
                );
                assert_eq!(install(), 0);
                assert_eq!(
                    libc::syscall(libc::SYS_clone3, std::ptr::null::<u8>(), 0),
                    -1
                );
                assert_eq!(*libc::__errno_location(), libc::ENOSYS);
                assert!(libc::syscall(libc::SYS_getpid) > 1);
            }
            return;
        }
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "production_runtime_seccomp::tests::production_seccomp_actual_filter_changes_invalid_clone3_to_enosys", "--test-threads=1"])
            .env(CHILD, "1")
            .output().unwrap();
        assert!(
            output.status.success(),
            "isolated seccomp control failed: stdout={:?}, stderr={:?}",
            output.stdout,
            output.stderr
        );
    }
}
