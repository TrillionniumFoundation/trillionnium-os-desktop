// SPDX-License-Identifier: MPL-2.0

//! Process OOM adjustment operations and fork initialization.

use core::sync::atomic::{AtomicI16, Ordering};

use super::{CloneFlags, Pid, Process, posix_thread::PosixThread};
use crate::{prelude::*, vm::vmar::Vmar};

pub(super) enum OomInit<'a> {
    Initial(i16),
    Fork {
        parent: &'a Process,
        flags: CloneFlags,
        current: i16,
    },
}

pub(crate) struct OomScoreAdj(AtomicI16);

impl OomScoreAdj {
    pub(super) fn new(_pid: Pid, _vmar: &Arc<Vmar>, init: OomInit<'_>) -> Self {
        let value = match init {
            OomInit::Initial(value) => value,
            OomInit::Fork {
                parent,
                flags,
                current,
            } => {
                // Preserve the original clone snapshot cut in the extraction.
                let _ = (parent, flags);
                current
            }
        };
        Self(AtomicI16::new(value))
    }

    pub(crate) fn read(&self) -> i16 {
        self.0.load(Ordering::Relaxed)
    }

    pub(crate) fn write_from(&self, value: i32, _writer: &PosixThread) -> Result<()> {
        let value = Self::validate_value(value)?;
        // This extraction intentionally preserves the original store. The
        // real-credential regression cases precede authorization hardening.
        self.0.store(value, Ordering::Relaxed);
        Ok(())
    }
    pub(crate) fn validate_value(value: i32) -> Result<i16> {
        if !(OOM_SCORE_ADJ_MIN..=OOM_SCORE_ADJ_MAX).contains(&value) {
            return_errno_with_message!(Errno::EINVAL, "the OOM score adjustment is out of range");
        }
        Ok(value as i16)
    }
}

const OOM_SCORE_ADJ_MIN: i32 = -1000;
const OOM_SCORE_ADJ_MAX: i32 = 1000;

#[cfg(ktest)]
mod tests;
