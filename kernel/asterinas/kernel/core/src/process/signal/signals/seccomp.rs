// SPDX-License-Identifier: MPL-2.0

use super::Signal;
use crate::{
    prelude::*,
    process::signal::{c_types::siginfo_t, constants::SIGSYS, sig_num::SigNum},
};

/// A kernel-created, thread-directed synchronous syscall trap. Its register
/// snapshot is retained outside the coalescing user-signal queues.
#[derive(Clone, Copy, Debug)]
pub(crate) struct SeccompSignal {
    pub(crate) data: u16,
    pub(crate) syscall: i32,
    pub(crate) arch: u32,
    pub(crate) call_addr: Vaddr,
}

impl Signal for SeccompSignal {
    fn num(&self) -> SigNum {
        SIGSYS
    }

    fn to_info(&self) -> siginfo_t {
        let mut info = siginfo_t::new(SIGSYS, 1); // SYS_SECCOMP
        info.si_errno = self.data as i32;
        info.set_seccomp(self.call_addr, self.syscall, self.arch);
        info
    }

    fn is_forced(&self) -> bool {
        true
    }
}

#[cfg(all(ktest, target_arch = "x86_64"))]
mod tests {
    use ostd::prelude::ktest;

    use super::*;

    #[ktest]
    fn seccomp_siginfo_matches_native_uapi_bytes() {
        let info = SeccompSignal {
            data: 0xabcd,
            syscall: 257,
            arch: 0xc000_003e,
            call_addr: 0x1234_5678_9abc_def0,
        }
        .to_info();
        let mut bytes = [0u8; 128];
        bytes[0..4].copy_from_slice(&31i32.to_ne_bytes());
        bytes[4..8].copy_from_slice(&0xabcdi32.to_ne_bytes());
        bytes[8..12].copy_from_slice(&1i32.to_ne_bytes());
        bytes[16..24].copy_from_slice(&0x1234_5678_9abc_def0u64.to_ne_bytes());
        bytes[24..28].copy_from_slice(&257i32.to_ne_bytes());
        bytes[28..32].copy_from_slice(&0xc000_003eu32.to_ne_bytes());
        assert_eq!(info.as_bytes(), bytes);
    }
}
