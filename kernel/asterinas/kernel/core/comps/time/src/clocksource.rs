// SPDX-License-Identifier: MPL-2.0

//! This module provides abstractions for hardware-assisted timing mechanisms, encapsulated
//! by the `ClockSource` struct.
//!
//! A `ClockSource` can be constructed from any counter with a stable frequency, enabling precise
//! time measurements to be taken by retrieving instances of `Instant`.
//!
//! The `ClockSource` module is a fundamental building block for timing in systems that require
//! high precision and accuracy. It can be integrated into larger systems to provide timing capabilities,
//! or used standalone for time tracking and elapsed time measurements.

use alloc::sync::Arc;
use core::{cmp::max, ops::Add, time::Duration};

use aster_util::coeff::Coeff;
use ostd::sync::{LocalIrqDisabled, RwLock};

const NANOS_PER_SECOND: u32 = 1_000_000_000;

/// `ClockSource` is an abstraction for hardware-assisted timing mechanisms.
///
/// A `ClockSource` can be created based on any counter that operates at a stable frequency.
/// Users are able to measure time by retrieving `Instant` from this source.
///
/// # Implementation
/// The `ClockSource` relies on obtaining the frequency of the counter and the method for
/// reading the cycles in order to measure time.
///
/// The **cycles** here refer the counts of the base time counter.
///
/// Additionally, the `ClockSource` also holds a last record for an `Instant` and the
/// corresponding cycles, which acts as a reference point for subsequent time retrieval.
/// To prevent numerical overflow during  the calculation of `Instant`, this last recorded instant
/// **must be periodically refreshed**. The maximum interval for these updates must be determined
/// at the time of the `ClockSource` initialization.
///
/// # Examples
/// Suppose we have a counter called `counter` which have the frequency `counter.freq`, and the method
/// to read its cycles called `read_counter()`. We can create a corresponding `ClockSource` and
/// use it as follows:
///
/// ```rust
/// // here we set the max_delay_secs = 10
/// let max_delay_secs = 10;
/// // create a clocksource named counter_clock
/// let counter_clock = ClockSource::new(counter.freq, max_delay_secs, Arc::new(read_counter));
/// // read an instant.
/// let instant = counter_clock.read_instant();
/// ```
///
/// If using this `ClockSource`, you must ensure its internal instant will be updated
/// at least once within a time interval of not more than `max_delay_secs.
pub struct ClockSource {
    read_cycles: Arc<dyn Fn() -> u64 + Sync + Send>,
    base: ClockSourceBase,
    coeff: Coeff,
    /// A paired time/cycle record, including the unrounded sub-nanosecond phase.
    last_record: RwLock<ClockSourceSample, LocalIrqDisabled>,
}

/// A single hardware-counter observation in its calibrated clock domain.
///
/// The fractional numerator is in units of `1 / 2^Coeff::shift()` nanoseconds.
/// Keep it when publishing a new conversion base, including vDSO data. Rounding
/// every refresh separately would permanently discard elapsed fractions.
///
/// Only a reliable sample pairs its instant with the observed counter. A
/// backwards/overflowed observation retains the last usable base, flagged as
/// unreliable; it is not a new accounting endpoint.
#[derive(Clone, Copy, Debug)]
pub struct ClockSourceSample {
    instant: Instant,
    cycles: u64,
    fractional_numerator: u64,
    reliable: bool,
}

impl ClockSourceSample {
    fn origin(cycles: u64) -> Self {
        Self {
            instant: Instant::zero(),
            cycles,
            fractional_numerator: 0,
            reliable: true,
        }
    }

    pub fn instant(&self) -> Instant {
        self.instant
    }

    pub fn cycles(&self) -> u64 {
        self.cycles
    }

    pub fn fractional_numerator(&self) -> u64 {
        self.fractional_numerator
    }

    /// Whether this clock has observed only valid counter samples.
    pub fn is_reliable(&self) -> bool {
        self.reliable
    }

    /// Returns an absolute nanosecond endpoint only for a reliable sample.
    ///
    /// Consumers with a u64 time ABI must also reject an unrepresentable time.
    /// Taking differences of these absolute endpoints preserves rounding
    /// across adjacent intervals; do not separately round every cycle delta.
    pub fn checked_nanos(&self) -> Option<u64> {
        if !self.reliable {
            return None;
        }
        Duration::new(self.instant.secs(), self.instant.nanos())
            .as_nanos()
            .try_into()
            .ok()
    }
}

#[derive(Clone, Copy, Debug)]
enum SampleFault {
    Backwards,
    ExcessiveDelay,
    InvalidCoefficient,
    Overflow,
}

impl ClockSource {
    /// Creates a new `ClockSource` instance.
    ///
    /// This method requires basic information of the time counter, including the function for
    /// reading cycles, the frequency, and the maximum delay seconds to update this `ClockSource`.
    /// The `ClockSource` also calculates a reliable `Coeff` based on the counter's frequency and
    /// the maximum delay seconds. This `Coeff` is used to convert the number of cycles into
    /// the duration of time that has passed for those cycles.
    /// Time starts at zero at the constructor's single counter observation.
    /// System bootstrap subsequently applies the existing private RTC/TSC
    /// calibration; maintenance never changes that origin.
    pub fn new(
        freq: u64,
        max_delay_secs: u64,
        read_cycles: Arc<dyn Fn() -> u64 + Sync + Send>,
    ) -> Self {
        assert!(freq > 0, "clock source frequency must be nonzero");
        let base = ClockSourceBase::new(freq, max_delay_secs);
        // Too big `max_delay_secs` will lead to a low resolution `Coeff`.
        debug_assert!(base.max_delay_secs < 600);
        let max_cycles = base
            .max_delay_secs
            .checked_mul(freq)
            .expect("clock source maximum interval must fit in u64");
        let coeff = Coeff::new(NANOS_PER_SECOND as u64, freq, max_cycles);
        assert!(
            coeff.mult() > 0 && coeff.shift() <= 32,
            "clock source coefficient must be representable"
        );
        let origin = ClockSourceSample::origin(read_cycles());
        Self {
            read_cycles,
            base,
            coeff,
            last_record: RwLock::new(origin),
        }
    }

    /// Uses the instant cycles to calculate the instant.
    ///
    /// It first calculates the difference between the instant cycles and the last
    /// recorded cycles stored in the clocksource. Then `ClockSource` will convert
    /// the passed cycles into passed time and calculate the current instant.
    ///
    /// A reliable result contains the calculated instant and the exact same
    /// counter observation. Invalid results must not be used for accounting.
    pub fn read_sample(&self) -> ClockSourceSample {
        let (sample, fault, last_cycles, cycles) = self.read_sample_with_fault();
        Self::report_fault(fault, last_cycles, cycles);
        sample
    }

    /// Reads the same source without logging inside a caller's runqueue lock.
    pub(crate) fn read_accounting_sample(&self) -> ClockSourceSample {
        self.read_sample_with_fault().0
    }

    fn read_sample_with_fault(&self) -> (ClockSourceSample, Option<SampleFault>, u64, u64) {
        let (cycles, last) = {
            let last_record = self.last_record.read();
            (self.read_cycles(), *last_record)
        };
        let (sample, fault) = self.calculate_sample(last, cycles);
        if fault.is_some() {
            // A failed read cannot become an authorizable sample merely by
            // retrying. Do not overwrite a newer base with this read's stale
            // values; only invalidate the current clock's reliability.
            self.last_record.write().reliable = false;
        }
        (sample, fault, last.cycles, cycles)
    }

    /// Computes from one locked record; the caller reports faults after unlock.
    fn calculate_sample(
        &self,
        last: ClockSourceSample,
        cycles: u64,
    ) -> (ClockSourceSample, Option<SampleFault>) {
        let invalid = || ClockSourceSample {
            reliable: false,
            ..last
        };
        let Some(delta) = cycles.checked_sub(last.cycles) else {
            // Keep the last known counter base. Rewinding it would count the
            // same cycles again when the hardware counter catches back up.
            return (invalid(), Some(SampleFault::Backwards));
        };
        let Some(max_cycles) = self.base.max_delay_secs.checked_mul(self.base.freq) else {
            return (invalid(), Some(SampleFault::Overflow));
        };
        let shift = self.coeff.shift();
        if shift > 32 || self.coeff.mult() == 0 {
            return (invalid(), Some(SampleFault::InvalidCoefficient));
        }
        let denominator = 1_u64 << shift;
        if last.fractional_numerator >= denominator {
            return (invalid(), Some(SampleFault::Overflow));
        }
        // Preserve the existing lossy/clamped general-clock behavior, but
        // mark that value unusable for an exact resource-accounting sample.
        let fault = (delta > max_cycles).then_some(SampleFault::ExcessiveDelay);
        let scaled = u128::from(delta.min(max_cycles))
            .checked_mul(u128::from(self.coeff.mult()))
            .and_then(|value| value.checked_add(u128::from(last.fractional_numerator)));
        let Some(scaled) = scaled else {
            return (invalid(), Some(SampleFault::Overflow));
        };
        let Ok(delta_nanos) = u64::try_from(scaled >> shift) else {
            return (invalid(), Some(SampleFault::Overflow));
        };
        let Some(duration) = Duration::new(last.instant.secs(), last.instant.nanos())
            .checked_add(Duration::from_nanos(delta_nanos))
        else {
            return (invalid(), Some(SampleFault::Overflow));
        };
        (
            ClockSourceSample {
                instant: Instant::from(duration),
                cycles,
                fractional_numerator: (scaled & u128::from(denominator - 1)) as u64,
                reliable: last.reliable && fault.is_none(),
            },
            fault,
        )
    }

    fn report_fault(fault: Option<SampleFault>, last_cycles: u64, cycles: u64) {
        if let Some(fault) = fault {
            ostd::warn!(
                "Unreliable clock source sample: {:?}, previous cycles {}, observed cycles {}",
                fault,
                last_cycles,
                cycles
            );
        }
    }

    /// Reads current cycles of the `ClockSource`.
    pub fn read_cycles(&self) -> u64 {
        (self.read_cycles)()
    }

    /// Returns the last instant and last cycles recorded in the `ClockSource`.
    pub fn last_record(&self) -> (Instant, u64) {
        let record = self.last_record.read();
        (record.instant, record.cycles)
    }

    /// Returns the whole conversion base, including the fractional phase.
    pub fn last_sample(&self) -> ClockSourceSample {
        *self.last_record.read()
    }

    /// Returns the maximum delay seconds for updating of the `ClockSource`.
    pub fn max_delay_secs(&self) -> u64 {
        self.base.max_delay_secs
    }

    /// Returns the reference to the generated cycles coeff of the `ClockSource`.
    pub fn coeff(&self) -> &Coeff {
        &self.coeff
    }

    /// Returns the frequency of the counter used in the `ClockSource`.
    pub fn freq(&self) -> u64 {
        self.base.freq
    }

    /// Calibrates the recorded `Instant` to zero, and record the instant cycles.
    pub(crate) fn calibrate(&self, instant_cycles: u64) {
        *self.last_record.write() = ClockSourceSample::origin(instant_cycles);
    }

    /// Refreshes the conversion base, preserving fractional elapsed time.
    ///
    /// This maintenance operation does not change the clock's origin. Once a
    /// bad read or refresh is observed, later samples remain unreliable. Only
    /// the private bootstrap calibration can establish a new origin.
    pub fn update(&self) -> ClockSourceSample {
        let (sample, fault, last_cycles, cycles) = {
            let mut last = self.last_record.write();
            let cycles = self.read_cycles();
            let last_cycles = last.cycles;
            let (sample, fault) = self.calculate_sample(*last, cycles);
            *last = sample;
            (sample, fault, last_cycles, cycles)
        };
        Self::report_fault(fault, last_cycles, cycles);
        sample
    }

    /// Reads the instant corresponding to the current time.
    pub(crate) fn read_instant(&self) -> Instant {
        self.read_sample().instant
    }
}

/// A specific moment.
///
/// [`Instant`] captures a specific moment, storing the duration of time
/// elapsed since a reference point (typically the system boot time).
/// The [`Instant`] is expressed in seconds and the fractional part is
/// expressed in nanoseconds.
#[derive(Clone, Copy, Debug, Default)]
pub struct Instant {
    secs: u64,
    nanos: u32,
}

impl Instant {
    /// Creates a zeroed `Instant`.
    pub const fn zero() -> Self {
        Self { secs: 0, nanos: 0 }
    }

    /// Creates an new `Instant` based on the inputting `secs` and `nanos`.
    pub fn new(secs: u64, nanos: u32) -> Self {
        Self { secs, nanos }
    }

    /// Returns the seconds recorded in the Instant.
    pub fn secs(&self) -> u64 {
        self.secs
    }

    /// Returns the nanoseconds recorded in the Instant.
    pub fn nanos(&self) -> u32 {
        self.nanos
    }
}

impl From<Duration> for Instant {
    fn from(value: Duration) -> Self {
        Self {
            secs: value.as_secs(),
            nanos: value.subsec_nanos(),
        }
    }
}

impl Add<Duration> for Instant {
    type Output = Instant;

    fn add(self, other: Duration) -> Self::Output {
        let mut secs = self.secs + other.as_secs();
        let mut nanos = self.nanos + other.subsec_nanos();
        if nanos >= NANOS_PER_SECOND {
            secs += 1;
            nanos -= NANOS_PER_SECOND;
        }
        Instant::new(secs, nanos)
    }
}

/// The basic properties of `ClockSource`.
#[derive(Clone, Copy, Debug)]
struct ClockSourceBase {
    freq: u64,
    max_delay_secs: u64,
}

impl ClockSourceBase {
    fn new(freq: u64, max_delay_secs: u64) -> Self {
        let max_delay_secs = max(2, max_delay_secs);
        ClockSourceBase {
            freq,
            max_delay_secs,
        }
    }
}
