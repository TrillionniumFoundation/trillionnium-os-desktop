# A06 N0 CPU bandwidth — reproducible implementation evidence

Date: 2026-10-16. **Kernel effect observed; not production-ready, not HOS2-authorized.** Changes belong to [Draft PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18). Root README remains zero bytes.

## Implementation

The existing Asterinas cgroup CPU controller now tracks absolute TSC-aligned periods and actual per-thread runtime, while the common `ClassScheduler` charges and checks both Fair and real-time tasks. Exhausted tasks are parked in a runqueue-local set and reconsidered on periodic idle ticks, without synchronous Hepta calls. Parent bandwidth limits are checked alongside child controls; quota writes retain already-consumed runtime rather than refunding it. The existing Linux cgroup and future native HOS2 entry points must converge on this *same* accounting state.

This N0 profile runs **one vCPU only**. It uses OSTD's 1000Hz periodic tick, so 1ms quotas may overshoot by roughly a tick per 100ms period; the current result is not an exact hardware deadline or strict 1% promise.

During multi-cap testing, the 10% guest timed out immediately after a `cpu.stat` read. Review identified that `CpuController::read_cpu_stat` held the bandwidth spinlock while writing into `VmPrinter`, a user-memory operation that may fault or schedule. Commit `512e45d02b4ff544189b104cb36994f2edc588f4` copies all throttle counters to scalars and **releases the lock before writing**; the new kernel was compiled from source and tested separately. This is an evidence-backed remediation, not a proof that all possible SMP/IRQ lock orders are correct.

An unrelated A01 build-script issue (`make --version | head -1` under `set -o pipefail` caused SIGPIPE 141) was corrected without changing the build inputs.

## Real guest results

The original unchanged kernel accepted 1% CPU configuration but consumed approximately 998ms per 1000ms. The first patched kernel compiled and booted; QEMU on a disposable initramfs observed 970ms/1000ms without a cap and 21ms/1000ms after 1% configuration.

| Workload | Configured | Observed CPU per wall time | Guest result | Scope |
| --- | ---: | ---: | --- | --- |
| First patched N0 guest | 1% | ≈2.1% | QEMU 33, no panic | Periodic tick overshoot remains |
| First patched N0 guest | 5% | 6.0% | QEMU 33, no panic | Not yet post-lockfix re-run |
| First patched N0 guest | 10% | Unknown | QEMU timeout at cpu.stat | Preserved failure |
| First patched N0 guest | 50% | 50.18% | QEMU 33, no panic | Not yet post-lockfix re-run |
| After lock release, repeated | 10% | 11.03%, 10.55%, 10.91% | 3 × QEMU 33, no panic | Same candidate kernel |
| Committed reproducible runner | 10% | 10.997% | QEMU 33 | Ordinary leaf task |
| Committed reproducible runner | 10% | 11.189% | QEMU 33 | Actual SCHED_FIFO |
| Committed reproducible runner | Parent 10%, leaf unlimited | 11.098% | QEMU 33 | Inherited parent limit |

The post-lockfix candidate kernel ELF SHA256 is `a2f72e2bc75d0490b658898697ced0532fe36395067939e3959f88dab051676e`. [Machine-readable results](../results/organ-backend/2026-10-16/a06-cpu-bandwidth-n0.json) retain the actual samples, boot status and SHA values. Large QEMU serial logs and test binaries remain in the isolated execution environment rather than increasing the Git repository by megabytes of binaries.

## Reproduce without changing a host cgroup

```bash
python3 tests/organ_backend/run_candidate_matrix.py \
  --a01-tree /absolute/path/to/repo-with-original-a01-evidence \
  --kernel /absolute/path/to/newly-built/asterinas-osdk-bin.elf \
  --expected-sha256 a2f72e2bc75d0490b658898697ced0532fe36395067939e3959f88dab051676e \
  --out /absolute/new/disposable/output/leaf-10 \
  --mode leaf --quota-us 10000 --repeat 3
```

For a parent limit, use `--mode parent`; for SCHED_FIFO, use `--mode rt`. For one-percent resolution use `--mode leaf --quota-us 1000`. Each command verifies the pinned kernel ELF and original A01 initramfs, checks the fixed SeaBIOS, compiles a static Linux ELF probe, builds an in-memory cpio archive and invokes QEMU with **no disk or host network**. The guest checks the cgroup quota readback and actual membership, and records CPU time from `getrusage`. The runner's success exit means the guest completed safely, *not that the CPU ratio is within a production limit*.

## Remaining blockers

- **Accuracy:** fix or explicitly bound tick-scale overrun. Present 1% observation ≈2.1%; cannot claim exact CPU cap.
- **SMP:** global quota accounting, per-CPU parking and wake ordering, CPU hotplug, cross-CPU migration, memory ordering and IPI behavior have not been verified.
- **CPU controller lifecycle:** sub-controller activation/disable, quota-period reconfiguration, cpu.weight, OOM/memory ownership and shutdown tests remain.
- **Hepta:** no tested HOS2 ioctl, CapSpace authorization or durable K↔D effect/retire flow yet. `TrustedReadOnlyOrganV1` must not be used for effectful device writes.
- **Kernel conformance:** selected A01 boot and isolated tests do not prove the full OSTD/upstream regression suite on this changed kernel.

Keep this PR **Draft** until A00/A06 have reviewed lock ordering, supplied a quantified cap error contract, and run relevant kernel regressions. No need for a second control database, HOS3 protocol or full from-scratch kernel rewrite.
