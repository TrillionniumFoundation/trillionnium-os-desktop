// SPDX-License-Identifier: MPL-2.0

//! Exercises CPU controls through the actual attribute read/write boundary.

use aster_systree::Error;
use ostd::{
    mm::{VmReader, VmWriter},
    prelude::ktest,
};

use super::{super::SubControl, CpuController, CpuMax};
use crate::error::{Errno, Error as KernelError};

fn assert_neutral_weight_readback(controller: &CpuController) {
    for offset in 0..=4 {
        let mut bytes = [0xa5; 8];
        let mut writer = VmWriter::from(&mut bytes[..]).to_fallible();
        let size = controller
            .read_attr_at("cpu.weight", offset, &mut writer)
            .unwrap();
        assert_eq!(&bytes[..size], &b"100\n"[offset..]);
    }
}

#[ktest]
fn valid_cpu_weight_write_reports_unsupported_without_claiming_policy() {
    // Audit closure: a successful dummy write falsely claimed scheduling policy.
    let controller = CpuController::new(true);
    let before = controller.control().unwrap().max.lock().max;
    assert_neutral_weight_readback(&controller);
    for input in ["1", "100\n", "250", "10000", " +250 "] {
        let mut reader = VmReader::from(input.as_bytes()).to_fallible();
        let error = controller
            .write_attr("cpu.weight", &mut reader)
            .unwrap_err();
        assert!(matches!(&error, Error::OperationNotSupported));
        assert_eq!(KernelError::from(error).error(), Errno::EOPNOTSUPP);
        assert_neutral_weight_readback(&controller);
        assert_eq!(controller.control().unwrap().max.lock().max, before);
    }
}

#[ktest]
fn invalid_or_inactive_cpu_weight_write_keeps_original_error_and_readback() {
    let controller = CpuController::new(true);
    let before = controller.control().unwrap().max.lock().max;
    for input in ["", "0", "10001", "-1", "4294967296", "not-a-weight", "1 2"] {
        let mut reader = VmReader::from(input.as_bytes()).to_fallible();
        let error = controller
            .write_attr("cpu.weight", &mut reader)
            .unwrap_err();
        assert!(matches!(&error, Error::InvalidOperation));
        assert_eq!(KernelError::from(error).error(), Errno::EINVAL);
        assert_neutral_weight_readback(&controller);
        assert_eq!(controller.control().unwrap().max.lock().max, before);
    }
    let inactive = CpuController::new(false);
    let mut reader = VmReader::from(&b"250"[..]).to_fallible();
    assert!(matches!(
        inactive.write_attr("cpu.weight", &mut reader),
        Err(Error::AttributeError)
    ));
    assert!(inactive.is_attr_absent("cpu.weight"));
    let mut bytes = [0; 4];
    let mut writer = VmWriter::from(&mut bytes[..]).to_fallible();
    assert!(matches!(
        inactive.read_attr_at("cpu.weight", 0, &mut writer),
        Err(Error::AttributeError)
    ));
}

fn assert_budget_unchanged(before: &CpuMax, after: &CpuMax) {
    assert_eq!(after.quota_usec, before.quota_usec);
    assert_eq!(after.period_usec, before.period_usec);
    assert_eq!(after.window_start_ns, before.window_start_ns);
    assert_eq!(after.used_ns, before.used_ns);
    assert_eq!(after.carry_debt_ns, before.carry_debt_ns);
    assert_eq!(after.nr_periods, before.nr_periods);
    assert_eq!(after.nr_throttled, before.nr_throttled);
    assert_eq!(after.throttled_since_ns, before.throttled_since_ns);
    assert_eq!(after.throttled_ns, before.throttled_ns);
}

#[ktest]
fn invalid_cpu_max_write_does_not_change_budget_or_accounting() {
    let controller = CpuController::new(true);
    let control = controller.control().unwrap();
    let before = {
        let mut state = control.max.lock();
        let budget = &mut state.max;
        budget.quota_usec = 10_000;
        budget.period_usec = 100_000;
        budget.window_start_ns = 123;
        budget.used_ns = 17;
        budget.carry_debt_ns = 19;
        budget.nr_periods = 3;
        budget.nr_throttled = 5;
        budget.throttled_since_ns = Some(23);
        budget.throttled_ns = 29;
        *budget
    };

    for input in [
        "1000 nope",
        "1000 18446744073709551616",
        "max nope",
        "1000 100000 junk",
        "max 100000 1",
    ] {
        let mut reader = VmReader::from(input.as_bytes()).to_fallible();
        assert!(
            matches!(
                controller.write_attr("cpu.max", &mut reader),
                Err(Error::InvalidOperation)
            ),
            "accepted {input:?}"
        );
        assert_budget_unchanged(&before, &control.max.lock().max);
    }
}

#[ktest]
fn single_quota_write_keeps_the_current_owner_period() {
    aster_time::init_for_ktest();
    let controller = CpuController::new(true);
    let control = controller.control().unwrap();
    control.max.lock().max.period_usec = 250_000;

    let input = b"2000\n";
    let mut reader = VmReader::from(&input[..]).to_fallible();
    assert_eq!(
        controller.write_attr("cpu.max", &mut reader).unwrap(),
        input.len()
    );

    let state = control.max.lock();
    let budget = &state.max;
    assert_eq!(budget.quota_usec, 2_000);
    assert_eq!(budget.period_usec, 250_000);
}
