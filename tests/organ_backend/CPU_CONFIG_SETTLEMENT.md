# CPU configuration settlement regression

This G1-b slice settles the local running interval before a validated ordinary
`cpu.max` update. `CpuControl.max` remains the sole bandwidth state. The existing
`CpuBandwidthState::reconfigure` continues to enforce the shared native revision
and detached-instance fence.

## Implementation

`with_current_cpu_bandwidth_settled` obtains the actual class scheduler's local
runqueue with local interrupts disabled, captures one scheduler TSC value, and
uses the existing `charge_task_cpu` hierarchy before calling the owner update.
The order is local runqueue → individual original bandwidth locks. Input parsing
and user copying finish before entering this section. The callback must neither
block nor enter another runqueue.

`CurrentRuntime.bandwidth_accounted_through` partitions the debited intervals.
It contains a timestamp, no budget or accumulated usage. Configuration advances
that cursor while preserving `start`, `delta`, and `period_delta` for the next
CFS/RT update. Tick, switch, and final scheduler accounting charge only the suffix
after the cursor. The original `CpuMax` performs all period/debt arithmetic.

The class scheduler is absent during early initialization and in standalone
OSTD FIFO owner tests; no class-scheduled POSIX interval exists to settle there.

## Kernel regression

The four `bandwidth_settlement_regressions` ktests exercise real CPU owners and
real, unstarted Process/Task objects with deterministic timestamps through the
production runtime helper. They verify:

- Same-value configuration settles old-window positive debt before advancing.
- Repeated configuration partitions bandwidth exactly while preserving the
  whole CFS runtime delta, including repeated timestamps.
- A lower quota sees the complete running prefix at its application point.
- Final accounting after configuration charges only the remaining suffix to
  the retained cgroup.

Run the original pinned entry points from the repository root:

```sh
bash support/build/prepare-host.sh
python3 -I support/build/ktest/prepare-locks.py --output-dir /tmp/g1b-locks
cmp /tmp/g1b-locks/aster-core.Cargo.lock support/build/ktest/locks/aster-core.Cargo.lock
python3 -I support/build/ktest/run.py --crate aster-core --output /tmp/g1b-core
```

During development, reversing only the helper's order to configuration → debit
is a negative control. It must fail the new accounting assertions. This control
is distinct from an unmodified ordinary product kernel and must be identified
as such in evidence.

## Ordinary one-vCPU regression

`run_cpu_config_settlement.py` accepts an explicitly hashed ordinary ELF and the
existing pinned initramfs/BIOS. It records source, compiled probe, ELF, initramfs,
firmware, QEMU arguments, and numerical criteria before starting a fresh guest.
The fixed q35/TCG/CPU-max/512-MiB/one-vCPU guest has no network or data disks.
The v2 receipt records the actual QEMU ELF bytes and version; a shell wrapper
is rejected. It rechecks all recorded files after the guest, including the
original and injected initramfs, firmware, source, probe, compiler, and QEMU.
The init script records the actual probe exit status and allows the original
boot completion only after exit zero. Exact parameter, sample, statistics,
completion, exit, and boot lines must occur once in the declared order.

```sh
python3 -B tests/organ_backend/run_cpu_config_settlement.py \
  --kernel /absolute/path/product-kernel.elf \
  --expected-sha256 FULL_ELF_SHA256 \
  --initramfs /absolute/path/original-initramfs.cpio.gz \
  --bios /usr/share/seabios/bios-256k.bin \
  --qemu /usr/bin/qemu-system-x86_64 \
  --out /tmp/g1b-config-100ms-same-value \
  --period-us 100000 --mode same-value
```

Run both `read-only` and `same-value` modes for periods `100000` and `2000` µs.
The quota remains 1000 µs. Over four seconds, the predeclared CPU bounds are
1.2% for the N0 100-ms case and 52% for the separate ordinary 2-ms case. An
unlimited sample below 70%, incomplete markers, a timeout, a panic, or a raw
QEMU exit other than 33 cannot pass. `getrusage` is a separate low-resolution
cross-check; it is not the native usage snapshot.

Host verifier rejection tests cover misleading markers and order, incorrect
case parameters, missing/nonzero probe exits, invalid timing samples, QEMU
failures, and mutations or disappearance of every recorded input. They are
verifier tests, not additional kernel execution evidence:

```sh
python3 -B tests/organ_backend/test_cpu_config_settlement.py
```

Earlier v1 observations retain their original receipt identity; the stronger
v2 verdict requires a new guest execution with the explicit process-exit line.

Continuous work commonly exhausts quota near the beginning of each period and
may not exercise an unsettled late-window prefix. Therefore an ordinary timing
pass is a regression observation, not a claim that the missing settlement was
reproduced in that product binary. The deterministic kernel control identifies
the ordering defect separately.

## Remaining G1-b work

This is local-CPU configuration settlement, not an SMP rendezvous. Remote
running tasks, controller-generation retention across replacement, membership
transition settlement, calibrated BOOTTIME alignment, conversion remainder,
and a single-version native usage snapshot still need their own implementation
and guest evidence. This slice does not enable native grants, additional HOS2
operations, or durable Hepta effects.
