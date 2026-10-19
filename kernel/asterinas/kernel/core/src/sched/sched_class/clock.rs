// SPDX-License-Identifier: MPL-2.0

//! Paired scheduler cycles and the original calibrated BOOTTIME endpoint.

use aster_time::ClockSourceSample;

/// One observation with separate units for scheduling and bandwidth accounting.
#[derive(Clone, Copy)]
pub(super) struct CpuClockSample {
    pub(super) cycles: u64,
    pub(super) boottime_ns: Option<u64>,
}

impl CpuClockSample {
    pub(super) fn read() -> Self {
        if let Some(sample) = aster_time::try_read_monotonic_sample() {
            return Self::from_sample(sample);
        }

        // CFS/RT retain their original cycle domain when the accounting clock
        // is unavailable. This counter is never used as a bandwidth endpoint.
        Self {
            cycles: super::sched_clock(),
            boottime_ns: None,
        }
    }

    pub(super) fn from_sample(sample: ClockSourceSample) -> Self {
        Self {
            cycles: sample.cycles(),
            boottime_ns: sample.checked_nanos(),
        }
    }

    /// Deterministic one-cycle/one-nanosecond fixtures, never a live fallback.
    #[cfg(ktest)]
    pub(super) fn fixture(now: u64) -> Self {
        Self {
            cycles: now,
            boottime_ns: Some(now),
        }
    }
}
