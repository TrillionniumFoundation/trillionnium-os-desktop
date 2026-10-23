// SPDX-License-Identifier: MPL-2.0

//! Bounds the argument and environment storage admitted by one program load.

use crate::{
    prelude::*,
    process::process_vm::{INIT_STACK_SIZE, MAX_LEN_STRING_ARG},
};

/// The combined string (including nul) and pointer budget for one program load.
///
/// The limit follows Linux's stack-derived ARG_MAX rule. Asterinas does not
/// copy an extra executable filename onto the initial stack, so this budget
/// covers the actual argv/envp entries, including shebang replacements.
pub(in crate::process) struct ArgBudget {
    remaining_bytes: usize,
}

impl ArgBudget {
    pub(in crate::process) fn new(stack_limit_bytes: u64) -> Self {
        // Linux's ARG_MAX floor is 128 KiB; the ceiling is three quarters of
        // the 8 MiB default stack. Clamp before converting the u64 rlimit to
        // usize so RLIM_INFINITY is safe on every supported pointer width.
        // Reference: https://github.com/torvalds/linux/blob/master/fs/exec.c
        // (`bprm_stack_limits`).
        const MIN_ARG_BYTES: u64 = 128 * 1024;
        const MAX_ARG_BYTES: u64 = (INIT_STACK_SIZE / 4 * 3) as u64;
        let limit_bytes = (stack_limit_bytes / 4).clamp(MIN_ARG_BYTES, MAX_ARG_BYTES);
        Self {
            remaining_bytes: limit_bytes as usize,
        }
    }

    pub(in crate::process) fn for_args(
        stack_limit_bytes: u64,
        argv: &[CString],
        envp: &[CString],
    ) -> Result<Self> {
        let mut budget = Self::new(stack_limit_bytes);
        budget.charge_strings(argv.iter().chain(envp))?;
        Ok(budget)
    }

    /// Reserves the pointer slot before allocating or copying a string.
    ///
    /// The returned limit includes its nul byte. Passing it to the reader
    /// also bounds a string that another user thread changes while it is read.
    pub(in crate::process) fn begin_string(&mut self) -> Result<usize> {
        self.consume_bytes(size_of::<Vaddr>())?;
        if self.remaining_bytes == 0 {
            return_errno_with_message!(
                Errno::E2BIG,
                "the argument and environment budget is exhausted"
            );
        }
        Ok(self.remaining_bytes.min(MAX_LEN_STRING_ARG))
    }

    pub(in crate::process) fn consume_bytes(&mut self, bytes: usize) -> Result<()> {
        self.remaining_bytes = self.remaining_bytes.checked_sub(bytes).ok_or_else(|| {
            Error::with_message(
                Errno::E2BIG,
                "the argument and environment budget is exhausted",
            )
        })?;
        Ok(())
    }

    /// Admits owned kernel strings before an initial load or shebang splice.
    pub(in crate::process) fn charge_strings<'a>(
        &mut self,
        strings: impl IntoIterator<Item = &'a CString>,
    ) -> Result<()> {
        for string in strings {
            let max_len = self.begin_string()?;
            let len = string.as_bytes_with_nul().len();
            if len > max_len {
                return_errno_with_message!(
                    Errno::E2BIG,
                    "there are too many bytes in the argument"
                );
            }
            self.consume_bytes(len)?;
        }
        Ok(())
    }
}
