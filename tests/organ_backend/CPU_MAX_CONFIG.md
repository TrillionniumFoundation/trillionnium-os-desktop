# CPU bandwidth configuration input

The production `cpu.max` writer parses its copied input through
[`cpu/max_config.rs`](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/max_config.rs)
before acquiring the existing bandwidth mutation lock. A quota by itself keeps
the owner's current period. A quota and a valid period set both values. `max`
still denotes unlimited quota; the existing quota and period bounds remain.

This project's input boundary rejects an explicitly invalid or overflowing
period and rejects additional fields. Previously, `1000 nope` silently retained
the old period while changing quota, and `1000 100000 junk` applied a valid
prefix. Rejection must occur before changing quota, period, usage, debt or
throttling statistics. It does not add an HOS2 operation or a native grant.

This is an intentional strictness choice for malformed input, not a claim of
byte-for-byte Linux parser equivalence. The documented cgroup syntax allows an
omitted period; Linux v6.18's `cpu_period_quota_parse` uses `sscanf` and tolerates
some malformed suffixes. The normal documented one-field and two-field forms
remain supported. See the [Linux cgroup-v2 CPU interface documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html#cpu-interface-files)
and [the Linux v6.18 implementation](https://github.com/torvalds/linux/blob/v6.18/kernel/sched/core.c).

## Direct production-parser regression

From the repository root, with a Rust compiler on `PATH`:

```sh
rustc --edition=2024 --test -Dwarnings \
  --check-cfg 'cfg(test)' --check-cfg 'cfg(ktest)' \
  tests/organ_backend/cpu_max_config_host.rs -o /tmp/cpu-max-config-tests
/tmp/cpu-max-config-tests --nocapture
```

The host entry imports the actual production module by path. It contains no
copied parser or replacement budget model. The same seven parser regressions
are kernel tests under `cfg(ktest)`. They cover valid forms and boundaries,
invalid quotas, out-of-range periods, explicit malformed and overflowing
periods, and extra fields.

## Real controller and kernel qualification

[`cpu/config_regressions.rs`](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/config_regressions.rs)
adds two kernel tests through `CpuController::write_attr` with a real `VmReader`.
Malformed updates must leave every existing `CpuMax` field unchanged; a valid
single quota must preserve the period in the actual owner. These tests use the
existing controller and lock, not a second resource authority or a new model.

With the fixed nightly and native build inputs from the
[A01 runbook](../../support/build/ktest/README.md), execute:

```sh
python3 -I support/build/ktest/run.py --crate aster-core
```

An executed host-parser pass is only a parser result. Kernel compilation,
controller ktests, native QueryAbi and CPU quota guest regressions require
their own exact-source receipts. Asterinas G1/G2, real device control and general
SMP are not established by this input fix.
