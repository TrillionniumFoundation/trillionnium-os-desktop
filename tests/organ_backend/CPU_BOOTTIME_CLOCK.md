# G1-b: paired BOOTTIME clock samples

This slice preserves the original calibrated clock domain and its fractional
conversion phase. It prepares a reliable nanosecond endpoint for the original
CPU bandwidth owner. It does **not** yet convert `CpuMax` to BOOTTIME windows,
assemble the HOS2 `ReadUsage` fields, enable native effects, or qualify SMP
migration. Those remain separate G1-b/G1-c/G1-d work.

## Production ownership and changes

The production input is the existing
[aster-time ClockSource](../../kernel/asterinas/kernel/core/comps/time/src/clocksource.rs).
[BootTimeClock](../../kernel/asterinas/kernel/core/src/time/clocks/system_wide.rs)
reads this same TSC source through `read_monotonic_time`; suspend is currently
unsupported, so BOOTTIME and MONOTONIC share that origin. The original
[TSC bootstrap](../../kernel/asterinas/kernel/core/comps/time/src/tsc.rs)
still establishes the RTC/TSC calibration. This slice does not introduce a
second clock, resource ledger, budget or revision owner.

`ClockSourceSample` contains the paired `Instant`, counter value, retained
fraction and reliability state. A valid sample reads the hardware counter
exactly once. A refresh captures and updates the record while holding the
original IRQ-safe write lock; it cannot overwrite another refresh with a
previously calculated base. A read releases its read lock before reporting
faults. If it observed a fault, it takes the write lock only to invalidate the
current record, without overwriting newer timestamp/counter values.

The original `Coeff` conversion is `cycles * mult / 2^shift`. At each refresh,
the new implementation computes the integer elapsed nanoseconds and retains
the remainder modulo `2^shift`. The intermediate product and sum use checked
`u128` arithmetic; the integer result and absolute endpoint must fit their
destination types. This retains the same coefficient and origin across any
partition of the same elapsed interval. In particular, 3,001 one-cycle
refreshes at the fixture's 3 GHz produce the same 1,000 ns and remaining phase
as a single 3,001-cycle observation. Rounding each interval individually would
instead lose all 1,000 ns.

The constructor now records its actual initial counter, and uses the normalized
minimum refresh interval consistently when constructing `Coeff`. The system
clock still performs its existing private bootstrap calibration afterward.
Zero frequency, multiplication overflow and an unrepresentable coefficient
cannot silently create a supposedly reliable clock.

[`try_read_monotonic_sample`](../../kernel/asterinas/kernel/core/comps/time/src/lib.rs)
returns `None` before initialization, for an invalid clock observation or
retained unreliable clock, and when absolute nanoseconds do not fit `u64`.
Future resource-accounting code must use this original source and subtract
absolute validated endpoints. It must not substitute raw TSC, Jiffies, zero or
separately rounded intervals when this function returns `None`.

## Invalid input contract

| Observation | General clock result | Reliable accounting result |
| --- | --- | --- |
| Valid counter within the maximum delay | Original calibrated time, retaining fractional phase | A checked absolute `u64` nanosecond endpoint |
| Counter before the retained base | Keep the previous base, without rewinding its counter | Invalid; later retries remain invalid |
| Interval exceeds the configured maximum delay | Preserve the original lossy clamp for ordinary time readers | Invalid; the missing elapsed time cannot become authorized |
| Arithmetic, coefficient or representation failure | Retain the previous base where conversion failed | Invalid |

A bad read or refresh permanently invalidates reliability in the existing
clock record. Only the private bootstrap calibration can establish a new
origin. A normal later read/refresh never restores reliability. Fault logs are
emitted after releasing the clock lock. This is a failure signal for future
accounting; it is not a fabricated successful zero-time sample.

An unreliable `ClockSourceSample` is not a fresh `(time, observed-counter)`
pair: a backwards/overflowed conversion deliberately retains the last usable
base. Consumers must honor validity before interpreting the fields.

## vDSO data and width

The [existing vDSO publisher](../../kernel/asterinas/kernel/core/src/vdso.rs)
receives the complete sample returned by that refresh. It does not reread a
possibly newer clock record to pair with an older timestamp.

The pinned Linux vDSO already expects high-resolution `nanos_info` to be
left-shifted. The publisher now stores:

```text
nanos_info = (instant.nanos << shift) + fractional_numerator
```

It validates `shift <= 32`, normalized nanoseconds and
`fractional_numerator < 2^shift`. The largest possible normalized base is
`(1_000_000_000 << 32) - 1`, less than `2^62`, so it fits the existing `u64`
field. No Linux vDSO field, offset, library byte, dependency pin or OSTD
primitive changes. Realtime seconds addition is separately checked before
publishing any new high-resolution base.

An invalid sample disables the existing TSC fast mode. The new `clock_mode`
value is written to the actual shared frame inside the original sequence
update, together with the retained counter and time base. Later callbacks do
not re-enable the mode. A delayed reliable callback cannot move the published
counter backwards.

The fixed x86 vDSO library is SHA-256
`27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3`.
Independent disassembly confirms that mode zero returns an invalid hardware
counter and takes the existing `SYS_clock_gettime` fallback. Its high-resolution
REALTIME, MONOTONIC and BOOTTIME paths use the first data area. MONOTONIC_RAW
uses a second data area at offset `0xf0`, which the existing kernel leaves
disabled, so RAW retains its syscall fallback. The tests do not claim to enable
a RAW fast path or repair the original sequence implementation for additional
architectures.

## Eight core regressions

All tests live in
[clocksource_regressions.rs](../../kernel/asterinas/kernel/core/src/vdso/clocksource_regressions.rs)
under `aster_core::vdso::clocksource_regressions::`:

| Test suffix | Assertion |
| --- | --- |
| `nonzero_origin_and_each_sample_use_one_counter_observation` | Actual nonzero origin; one counter read for each returned pair and refresh |
| `fragmented_refreshes_preserve_fractional_time_and_endpoint_differences` | 3,001 refreshes retain exactly the same integer time and phase as one observation; adjacent endpoint differences telescope |
| `vdso_and_kernel_share_the_fractional_phase_at_the_next_nanosecond` | Original kernel sample and published first-area high-resolution clocks cross the same 1 ns boundary |
| `backwards_refresh_keeps_the_counter_base_and_revokes_reliable_samples` | A bad read, a retry, a bad refresh and recovery cannot rewind or reauthorize the clock |
| `excessive_delay_is_clamped_but_never_a_reliable_accounting_endpoint` | The inclusive maximum remains valid; exceeding it clamps ordinary time but invalidates accounting permanently |
| `full_width_vdso_fraction_survives_second_rollover_and_checks_realtime_overflow` | Production `shift = 32`, maximum-width fraction, exact second rollover and realtime addition overflow |
| `vdso_rejects_invalid_phase_width_and_does_not_rewind_on_a_stale_callback` | Invalid shifts/fraction widths disable fast mode; old callbacks do not rewind the base |
| `mapped_vdso_publishes_the_phase_and_fault_mode_under_the_existing_sequence` | Production VMO allocation, real data-frame publication, phase and `seq = 2, 4, 6`, including permanent mode disable |

Counter fixtures drive the production `ClockSource`, not a replacement clock
algorithm. The mapped test calls the original VMO construction and publication
paths, including the pinned library text. Tests do not initialize or replace
the global TSC, RTC, vDSO or time singletons. Data-field arithmetic checks are
not evidence of executing the userspace library itself.

## Frozen negative controls

Apply each control separately to its own checkout of the final candidate.
All expected failures use the prefix above. Tests outside the stated set must
pass; a compilation error, panic before the test summary, timeout or a
different failure set is not the intended RED result.

| Patch | Deliberate defect | Exact expected failed suffixes |
| --- | --- | --- |
| [clocksource_drop_fraction_negative.patch](clocksource_drop_fraction_negative.patch) | Clear the fraction only when retaining a refresh record | `fragmented_refreshes_preserve_fractional_time_and_endpoint_differences`; `vdso_and_kernel_share_the_fractional_phase_at_the_next_nanosecond`; `full_width_vdso_fraction_survives_second_rollover_and_checks_realtime_overflow` |
| [vdso_drop_fraction_negative.patch](vdso_drop_fraction_negative.patch) | Drop the fraction from the existing vDSO shifted base | `vdso_and_kernel_share_the_fractional_phase_at_the_next_nanosecond`; `full_width_vdso_fraction_survives_second_rollover_and_checks_realtime_overflow`; `mapped_vdso_publishes_the_phase_and_fault_mode_under_the_existing_sequence` |
| [vdso_skip_fault_mode_negative.patch](vdso_skip_fault_mode_negative.patch) | Update the internal mode but omit its actual data-frame write | `mapped_vdso_publishes_the_phase_and_fault_mode_under_the_existing_sequence` |

The controls preserve warnings, test selection, source checks, library bytes
and normal kernel entry points. Each RED run must retain its real modified
source snapshot and ELF identity. Expected guest completion is the normal
ktest failure exit (`QEMU 65`), with respectively three, three or one failures.
The original gate command is:

```sh
python3 -I -B support/build/ktest/run.py \
  --crate aster-core --skip-osdk-install --output /absolute/new/output
```

Use a fresh absolute output path outside the source tree. Do not filter test
names. Record the fixed toolchain, exact QEMU ELF and firmware, source snapshot,
actual process exit, serial output, test summary and input hashes. Negative
checkouts are intentionally modified and must be labeled as such. Do not
change the gate to describe them as clean production artifacts.

The final unmodified candidate needs the full original core and OSTD gate,
followed by the ordinary-kernel regression probes on the same published ELF.
It must have no failures and normal success exits. Counts include the other
changes integrated into that final source tree; the eight added names are the
stable expected increment.

## Validation status at source handoff

The fixed `nightly-2026-07-21` parser accepts the changed Rust sources. The new
test file is formatted with that toolchain, `git diff --check` passes, and each
negative patch applies to the frozen source. The fixed x86 vDSO fallback and
arithmetic instructions were independently inspected.

At this handoff the new slice has **not** been type-checked or executed in a
kernel. Local heavy builds were deferred because the shared host has limited
free disk; CI must supply the exact-source RED/GREEN evidence. Neither this
document nor a parser-only check closes the G1-b blocker. The source is kept
separate from the already frozen CPU owner-retention change, and must be
integrated and tested against the current main before any closure claim.
