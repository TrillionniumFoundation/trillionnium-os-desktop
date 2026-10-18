// SPDX-License-Identifier: MPL-2.0

//! Exercises `cpu.max` through the actual controller attribute-write boundary.

use aster_systree::Error;
use ostd::{mm::VmReader, prelude::ktest};

use super::{super::SubControl, CpuController, CpuMax};

fn assert_budget_unchanged(before: &CpuMax, after: &CpuMax) {
    assert_eq!(after.quota_usec, before.quota_usec);
    assert_eq!(after.period_usec, before.period_usec);
    assert_eq!(after.window_start, before.window_start);
    assert_eq!(after.used_clocks, before.used_clocks);
    assert_eq!(after.carry_debt_clocks, before.carry_debt_clocks);
    assert_eq!(after.nr_periods, before.nr_periods);
    assert_eq!(after.nr_throttled, before.nr_throttled);
    assert_eq!(after.throttled_since, before.throttled_since);
    assert_eq!(after.throttled_clocks, before.throttled_clocks);
}

#[ktest]
fn invalid_cpu_max_write_does_not_change_budget_or_accounting() {
    let controller = CpuController::new(true);
    let control = controller.control().unwrap();
    let before = {
        let mut budget = control.max.lock();
        budget.quota_usec = 10_000;
        budget.period_usec = 100_000;
        budget.window_start = 123;
        budget.used_clocks = 17;
        budget.carry_debt_clocks = 19;
        budget.nr_periods = 3;
        budget.nr_throttled = 5;
        budget.throttled_since = Some(23);
        budget.throttled_clocks = 29;
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
        assert_budget_unchanged(&before, &control.max.lock());
    }
}

#[ktest]
fn single_quota_write_keeps_the_current_owner_period() {
    let controller = CpuController::new(true);
    let control = controller.control().unwrap();
    control.max.lock().period_usec = 250_000;

    let input = b"2000\n";
    let mut reader = VmReader::from(&input[..]).to_fallible();
    assert_eq!(
        controller.write_attr("cpu.max", &mut reader).unwrap(),
        input.len()
    );

    let budget = control.max.lock();
    assert_eq!(budget.quota_usec, 2_000);
    assert_eq!(budget.period_usec, 250_000);
}
