// SPDX-License-Identifier: MPL-2.0

//! Paired BOOTTIME samples and the original Linux-compatible vDSO data.
//!
//! These fixtures supply a controlled hardware counter to the production
//! ClockSource. They do not install or replace the system clock. VdsoData is
//! the production publication format; no duplicate clock or usage ledger is
//! involved. Executing the prebuilt userspace vDSO is a separate guest gate.

use alloc::sync::Arc;
use core::sync::atomic::{AtomicU64, Ordering};

use aster_time::{ClockSource, ClockSourceSample};
use ostd::{mm::VmIo, prelude::ktest};

use super::{DEFAULT_CLOCK_MODE, VDSO_VMO_LAYOUT, Vdso, VdsoClockMode, VdsoData};
use crate::syscall::ClockId;

struct Counter {
    cycles: Arc<AtomicU64>,
    clock: ClockSource,
}

impl Counter {
    fn new(freq: u64, max_delay_secs: u64, origin: u64) -> Self {
        let cycles = Arc::new(AtomicU64::new(origin));
        let reader = cycles.clone();
        let clock = ClockSource::new(
            freq,
            max_delay_secs,
            Arc::new(move || reader.load(Ordering::SeqCst)),
        );
        Self { cycles, clock }
    }

    fn set(&self, cycles: u64) {
        self.cycles.store(cycles, Ordering::SeqCst);
    }

    fn vdso_data(&self, sample: ClockSourceSample, realtime_base_secs: u64) -> VdsoData {
        let mut data = VdsoData::empty();
        data.set_clock_mode(DEFAULT_CLOCK_MODE);
        data.set_coeff(self.clock.coeff());
        data.update_high_res_instant(sample, realtime_base_secs);
        data
    }
}

// The pinned Linux vDSO evaluates the already-published fields this way.
// Checked arithmetic also verifies that this fixture stays within its u64
// extrapolation range instead of hiding overflow in a wider host model.
fn vdso_nanos_at(data: &VdsoData, id: ClockId, cycles: u64) -> u64 {
    assert_eq!(data.clock_mode, VdsoClockMode::Tsc as i32);
    let base = data.basetime[id as usize];
    let delta = cycles.checked_sub(data.last_cycles).unwrap() & data.mask;
    let shifted = delta
        .checked_mul(u64::from(data.mult))
        .unwrap()
        .checked_add(base.nanos_info)
        .unwrap();
    base.secs
        .checked_mul(1_000_000_000)
        .unwrap()
        .checked_add(shifted >> data.shift)
        .unwrap()
}

#[ktest]
fn nonzero_origin_and_each_sample_use_one_counter_observation() {
    const ORIGIN: u64 = 10_000_003;
    let cycles = Arc::new(AtomicU64::new(ORIGIN));
    let reads = Arc::new(AtomicU64::new(0));
    let cycles_reader = cycles.clone();
    let reads_reader = reads.clone();
    let clock = ClockSource::new(
        1_000_000_000,
        100,
        Arc::new(move || {
            reads_reader.fetch_add(1, Ordering::SeqCst);
            cycles_reader.fetch_add(13, Ordering::SeqCst)
        }),
    );
    assert_eq!(reads.load(Ordering::SeqCst), 1);
    assert_eq!(clock.last_sample().cycles(), ORIGIN);
    assert_eq!(clock.last_sample().checked_nanos(), Some(0));

    let first = clock.read_sample();
    assert_eq!(reads.load(Ordering::SeqCst), 2);
    assert_eq!(first.cycles(), ORIGIN + 13);
    assert_eq!(first.checked_nanos(), Some(13));
    assert_eq!(clock.last_sample().cycles(), ORIGIN);

    let refreshed = clock.update();
    assert_eq!(reads.load(Ordering::SeqCst), 3);
    assert_eq!(refreshed.cycles(), ORIGIN + 26);
    assert_eq!(refreshed.checked_nanos(), Some(26));
    let (instant, recorded_cycles) = clock.last_record();
    assert_eq!(instant.secs(), 0);
    assert_eq!(instant.nanos(), 26);
    assert_eq!(recorded_cycles, refreshed.cycles());

    let next = clock.read_sample();
    assert_eq!(reads.load(Ordering::SeqCst), 4);
    assert_eq!(next.cycles(), ORIGIN + 39);
    assert_eq!(next.checked_nanos(), Some(39));
}

#[ktest]
fn fragmented_refreshes_preserve_fractional_time_and_endpoint_differences() {
    const ORIGIN: u64 = 12_345;
    const CYCLES: u64 = 3_001;
    let fragmented = Counter::new(3_000_000_000, 100, ORIGIN);
    let whole = Counter::new(3_000_000_000, 100, ORIGIN);
    let mut previous = 0;
    let mut elapsed = 0;
    for cycles in 1..=CYCLES {
        fragmented.set(ORIGIN + cycles);
        let sample = fragmented.clock.update();
        let nanos = sample.checked_nanos().unwrap();
        elapsed += nanos.checked_sub(previous).unwrap();
        previous = nanos;
    }
    whole.set(ORIGIN + CYCLES);
    let expected = whole.clock.read_sample();
    let actual = fragmented.clock.last_sample();
    assert_eq!(expected.checked_nanos(), Some(1_000));
    assert_eq!(actual.checked_nanos(), expected.checked_nanos());
    assert_eq!(
        actual.fractional_numerator(),
        expected.fractional_numerator()
    );
    assert_eq!(actual.cycles(), expected.cycles());
    assert_eq!(elapsed, 1_000);
    assert_eq!(*fragmented.clock.coeff() * 1_u64, 0);
}

#[ktest]
fn vdso_and_kernel_share_the_fractional_phase_at_the_next_nanosecond() {
    const ORIGIN: u64 = 10_000;
    const REALTIME_BASE: u64 = 1_234_567_890;
    let counter = Counter::new(3_000_000_000, 100, ORIGIN);
    counter.set(ORIGIN + 1);
    let published = counter.clock.update();
    assert_eq!(published.checked_nanos(), Some(0));
    assert!(published.fractional_numerator() > 0);
    let data = counter.vdso_data(published, REALTIME_BASE);

    counter.set(ORIGIN + 4);
    let observed = counter.clock.read_sample();
    assert_eq!(observed.checked_nanos(), Some(1));
    // The fixed x86 Linux ELF uses this first data area for these clocks.
    // MONOTONIC_RAW uses its separate, currently disabled second data area
    // and retains the existing syscall fallback.
    for id in [
        ClockId::CLOCK_REALTIME,
        ClockId::CLOCK_MONOTONIC,
        ClockId::CLOCK_BOOTTIME,
    ] {
        let offset = if id == ClockId::CLOCK_REALTIME {
            REALTIME_BASE * 1_000_000_000
        } else {
            0
        };
        assert_eq!(vdso_nanos_at(&data, id, observed.cycles()), offset + 1);
    }

    // The discarded phase is decisive: the original integer-only base is
    // still at zero at exactly the same observed counter value.
    let without_phase =
        ((observed.cycles() - data.last_cycles) * u64::from(data.mult)) >> data.shift;
    assert_eq!(without_phase, 0);
}

#[ktest]
fn backwards_refresh_keeps_the_counter_base_and_revokes_reliable_samples() {
    let counter = Counter::new(1_000_000_000, 100, 1_000);
    counter.set(1_200);
    let trusted = counter.clock.update();
    let mut data = counter.vdso_data(trusted, 0);

    counter.set(1_100);
    let bad_read = counter.clock.read_sample();
    assert!(!bad_read.is_reliable());
    assert_eq!(bad_read.checked_nanos(), None);
    assert_eq!(bad_read.cycles(), 1_200);
    assert_eq!(bad_read.instant().nanos(), 200);
    assert!(!counter.clock.last_sample().is_reliable());
    counter.set(1_300);
    assert_eq!(counter.clock.read_sample().checked_nanos(), None);
    counter.set(1_100);

    let bad_refresh = counter.clock.update();
    assert_eq!(counter.clock.last_sample().cycles(), 1_200);
    assert!(!counter.clock.last_sample().is_reliable());
    data.update_high_res_instant(bad_refresh, 0);
    assert_eq!(data.clock_mode, VdsoClockMode::None as i32);
    assert_eq!(data.last_cycles, trusted.cycles());

    counter.set(1_300);
    let after = counter.clock.update();
    assert_eq!(after.instant().nanos(), 300);
    assert_eq!(after.checked_nanos(), None);
    data.update_high_res_instant(after, 0);
    data.update_high_res_instant(trusted, 0);
    assert_eq!(data.clock_mode, VdsoClockMode::None as i32);
}

#[ktest]
fn excessive_delay_is_clamped_but_never_a_reliable_accounting_endpoint() {
    const LIMIT: u64 = 2_000_000_000;
    let counter = Counter::new(1_000_000_000, 2, 0);
    counter.set(LIMIT);
    let boundary = counter.clock.update();
    assert_eq!(boundary.checked_nanos(), Some(LIMIT));
    let mut data = counter.vdso_data(boundary, 0);

    counter.set(2 * LIMIT + 1);
    let invalid = counter.clock.update();
    assert_eq!(invalid.checked_nanos(), None);
    assert_eq!(invalid.instant().secs(), 4);
    assert_eq!(invalid.instant().nanos(), 0);
    assert_eq!(invalid.cycles(), 2 * LIMIT + 1);
    data.update_high_res_instant(invalid, 0);
    assert_eq!(data.clock_mode, VdsoClockMode::None as i32);

    counter.set(2 * LIMIT + 2);
    let later = counter.clock.update();
    assert_eq!(later.instant().secs(), 4);
    assert_eq!(later.instant().nanos(), 1);
    assert_eq!(later.checked_nanos(), None);
    data.update_high_res_instant(later, 0);
    assert_eq!(data.clock_mode, VdsoClockMode::None as i32);
}

#[ktest]
fn full_width_vdso_fraction_survives_second_rollover_and_checks_realtime_overflow() {
    // Four GHz and the normalized minimum refresh interval exercise the
    // largest shift the production Coeff can emit: 32 bits.
    let counter = Counter::new(4_000_000_000, 0, 0);
    assert_eq!(counter.clock.max_delay_secs(), 2);
    assert_eq!(counter.clock.coeff().shift(), 32);
    counter.set(3_999_999_999);
    let edge = counter.clock.update();
    assert_eq!(edge.checked_nanos(), Some(999_999_999));
    assert_eq!(edge.fractional_numerator(), 3 * (1_u64 << 30));
    let mut data = counter.vdso_data(edge, 11);
    let packed = data.basetime[ClockId::CLOCK_BOOTTIME as usize].nanos_info;
    assert_eq!(packed, (999_999_999_u64 << 32) + 3 * (1_u64 << 30));
    assert!(packed < (1_u64 << 62));

    counter.set(4_000_000_000);
    let next = counter.clock.update();
    assert_eq!(next.checked_nanos(), Some(1_000_000_000));
    assert_eq!(next.instant().secs(), 1);
    assert_eq!(next.instant().nanos(), 0);
    assert_eq!(next.fractional_numerator(), 0);
    assert_eq!(
        vdso_nanos_at(&data, ClockId::CLOCK_BOOTTIME, next.cycles()),
        1_000_000_000
    );
    data.update_high_res_instant(next, 11);
    assert_eq!(data.basetime[ClockId::CLOCK_BOOTTIME as usize].secs, 1);
    assert_eq!(
        data.basetime[ClockId::CLOCK_BOOTTIME as usize].nanos_info,
        0
    );
    assert_eq!(data.basetime[ClockId::CLOCK_REALTIME as usize].secs, 12);

    let before = data;
    data.update_high_res_instant(next, u64::MAX);
    assert_eq!(data.clock_mode, VdsoClockMode::None as i32);
    assert_eq!(data.last_cycles, before.last_cycles);
    assert_eq!(data.basetime[ClockId::CLOCK_REALTIME as usize].secs, 12);
}

#[ktest]
fn vdso_rejects_invalid_phase_width_and_does_not_rewind_on_a_stale_callback() {
    let counter = Counter::new(3_000_000_000, 100, 1_000);
    counter.set(1_001);
    let first = counter.clock.read_sample();
    let mut data = counter.vdso_data(first, 0);
    counter.set(1_004);
    let later = counter.clock.read_sample();
    data.update_high_res_instant(later, 0);
    data.update_high_res_instant(first, 0);
    assert_eq!(data.last_cycles, later.cycles());
    assert_eq!(
        vdso_nanos_at(&data, ClockId::CLOCK_BOOTTIME, later.cycles()),
        1
    );

    let mut wrong_shift = counter.vdso_data(first, 0);
    wrong_shift.shift = 64;
    wrong_shift.update_high_res_instant(later, 0);
    assert_eq!(wrong_shift.clock_mode, VdsoClockMode::None as i32);
    assert_eq!(wrong_shift.last_cycles, first.cycles());

    let mut wrong_fraction = counter.vdso_data(first, 0);
    wrong_fraction.shift = 0;
    wrong_fraction.update_high_res_instant(later, 0);
    assert_eq!(wrong_fraction.clock_mode, VdsoClockMode::None as i32);
    assert_eq!(wrong_fraction.last_cycles, first.cycles());
}

#[ktest]
fn mapped_vdso_publishes_the_phase_and_fault_mode_under_the_existing_sequence() {
    let counter = Counter::new(3_000_000_000, 100, 1_000);
    let data = counter.vdso_data(counter.clock.last_sample(), 0);
    // This is the production VMO constructor, including the pinned Linux
    // vDSO text and actual shared data frame. No global singleton is changed.
    let vdso = Vdso::from_data(data);
    counter.set(1_001);
    let trusted = counter.clock.update();
    vdso.update_high_res_instant(trusted, 0);
    let published: VdsoData = vdso
        .data_frame
        .read_val(VDSO_VMO_LAYOUT.data_offset)
        .unwrap();
    assert_eq!(published.seq, 2);
    assert_eq!(published.clock_mode, VdsoClockMode::Tsc as i32);
    assert_eq!(published.last_cycles, trusted.cycles());
    assert_eq!(
        published.basetime[ClockId::CLOCK_BOOTTIME as usize].nanos_info,
        trusted.fractional_numerator()
    );

    counter.set(1_000);
    vdso.update_high_res_instant(counter.clock.update(), 0);
    let invalid: VdsoData = vdso
        .data_frame
        .read_val(VDSO_VMO_LAYOUT.data_offset)
        .unwrap();
    assert_eq!(invalid.seq, 4);
    assert_eq!(invalid.clock_mode, VdsoClockMode::None as i32);
    assert_eq!(invalid.last_cycles, published.last_cycles);
    assert_eq!(
        invalid.basetime[ClockId::CLOCK_BOOTTIME as usize].nanos_info,
        published.basetime[ClockId::CLOCK_BOOTTIME as usize].nanos_info
    );

    vdso.update_high_res_instant(trusted, 0);
    let final_data: VdsoData = vdso
        .data_frame
        .read_val(VDSO_VMO_LAYOUT.data_offset)
        .unwrap();
    assert_eq!(final_data.seq, 6);
    assert_eq!(final_data.clock_mode, VdsoClockMode::None as i32);
}
