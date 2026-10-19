# A06 N0 CPU bandwidth — reproducible implementation evidence

Updated: 2026-10-18; final-debit change based on main `3551e1e0e017e2973da7e2b8ab811ece25c258c0`. **Kernel effect observed; not production-ready, not HOS2-authorized.** The cgroup CPU implementation is already in main through [PR #121](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/121). [Draft PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) retains the original development history; it is not the current integration state. Root README remains zero bytes.

## Current integrated evidence and next implementation boundary

The [G1-a owner development manual](ASTERINAS_CPU_OWNER_G1A.md) describes the
next source slice: shared `cpu.max` revision and irreversible real-controller
detachment, its actual-owner ktests, dependency pins and remaining qualification
limits. Added test source is not a new runtime receipt; the historical results
below keep their original source bindings.

The [2026-10-17 integrated receipt](../results/organ-backend/2026-10-17/a05-a06-integrated-acceptance.json) binds tested source `b913202b2e487126319e60813a54163666b9a2ad` to equivalent remote merge commit `eaf5242233b799356b7daa73898a14d240832abb`, tree `b852e0037af8f84c22a8fc7347fa55d8183e07e6`. It records ten real quota probes across the selected one/two-vCPU profiles, three read-only QueryAbi probes, and kernel regression with 374 reported passes, three VMX/EPT soft skips, and an actual executed lower bound of 371. These historical receipts do not automatically qualify a later HEAD.

| Integrated sample | Configured CPU | Observed CPU percent |
| --- | ---: | --- |
| One-vCPU leaf, three runs | 1% | 1.100, 1.000, 0.999 |
| One-vCPU leaf / real-time / parent | 10% | 10.352 / 9.824 / 10.226 |
| Two-vCPU leaf | 1% | 0.957 |
| Two-vCPU leaf / parent / real-time | 10% | 10.112 / 10.396 / 10.187 |

The actual owner is the existing [cgroup CPU controller](../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs), consumed by the common [ClassScheduler](../kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs). A native HOS2 budget entry must mutate this same state. Main's HOS2 device still exposes only QueryAbi. Process/exec-epoch/nonce identity fencing is now merged with a [separate single-vCPU receipt](../results/kernel/control/a05-main-combined-acceptance-20261017.json); trusted capability grants and the four other operations remain unimplemented there.

[PR #178](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/178) retained a thread-owned cgroup lease for deferred charging after the Process Arc is dropped. Its remaining gap was an **unreaped zombie**: `exit_process` marks the process zombie and clears `process.cgroup` before the scheduler's final charge, but a parent's strong reference still makes `weak_process().upgrade()` succeed. The old dispatch therefore charged root and missed the former leaf and its ancestors.

The final-debit change here uses the retained lease for detached zombie and already-reaped owners. A live process still uses its authoritative cgroup binding, including migration to root; it does not use a possibly stale backup. A zombie whose cgroup binding is still present also preserves the existing dispatch: an admitted concurrent migration can publish that binding before updating the thread snapshot. The scheduler reads the RCU binding before the acquire load of the zombie flag, so a binding published by exit cannot be classified using an earlier live-state read. It adds no membership mutex to the scheduler path and retains the existing IRQ-disabled bandwidth locks. This settles **TSC quota bandwidth/debt**; `cpu.stat` usage remains on its independent jiffies path.

The [six new kernel regressions](../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/final_charge_regressions.rs) construct real Process/Task objects through a [test-only fixture](../kernel/asterinas/kernel/core/src/process/test_util.rs), perform real CgroupMembership transitions and call the production `charge_task_cpu` entry. They assert leaf/ancestor/root debits for an unreaped zombie, a failed Weak upgrade, live leaf-to-leaf-to-root migration, intentionally stale snapshots before and after the zombie flag is published but before detachment, and a final interval crossing a quota window. The objects are not scheduled and the fixture explicitly publishes the exit state; these tests do not reproduce the complete `exit_current` sequence or certify SMP timing. Reverting only the zombie-aware dispatch must break the unreaped and cross-window expectations. The point at which an exiting non-main thread's final-debit owner becomes fixed during concurrent process migration remains a separate lifecycle design and validation question.

Run the new regressions as part of the real `aster-core` guest suite with `python3 -I support/build/ktest/run.py --crate aster-core`; preparation and raw guest validation are documented in the [ktest runbook](../support/build/ktest/README.md). The existing A06 workflow also builds the exact SMP=2 candidate and executes bounded one/two-vCPU quota/exit probes. Added test source is not a pass receipt: qualification requires the corresponding candidate's build logs and raw QEMU evidence. Controller disable/re-enable, full exit/reap scheduling races and general SMP/lock lifetime remain separate validation work.

The original 2026-10-16 experiments below are retained with their failures and original hashes. Their approximately 2.1% first-patch result is historical; use the table above for the later integrated samples. Neither establishes a strict per-100ms hard maximum, a general SMP guarantee or a product SLO.

## Implementation and original experiment history

The existing Asterinas cgroup CPU controller now tracks absolute TSC-aligned periods and actual per-thread runtime, while the common `ClassScheduler` charges and checks both Fair and real-time tasks. Exhausted tasks are parked in a runqueue-local set and reconsidered on periodic idle ticks, without synchronous Hepta calls. Parent bandwidth limits are checked alongside child controls; quota writes retain already-consumed runtime rather than refunding it. The existing Linux cgroup and future native HOS2 entry points must converge on this *same* accounting state.

The original N0 experiment below used **one vCPU only**. It used OSTD's 1000Hz periodic tick, so 1ms quotas could overshoot by roughly a tick per 100ms period. The later limited two-vCPU samples above expand measured scenarios without proving general SMP correctness or a strict 1% guarantee.

During multi-cap testing, the 10% guest timed out immediately after a `cpu.stat` read. Review identified that `CpuController::read_cpu_stat` held the bandwidth spinlock while writing into `VmPrinter`, a user-memory operation that may fault or schedule. Commit `512e45d02b4ff544189b104cb36994f2edc588f4` copies all throttle counters to scalars and **releases the lock before writing**; the new kernel was compiled from source and tested separately. This is an evidence-backed remediation, not a proof that all possible SMP/IRQ lock orders are correct.

An unrelated A01 build-script issue (`make --version | head -1` under `set -o pipefail` caused SIGPIPE 141) was corrected without changing the build inputs.

## Historical 2026-10-16 guest results

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

## Replay the historical candidate without changing a host cgroup

The following hash is the original post-lockfix candidate, not the current main kernel. To test a new candidate, first build and bind its source/ELF/input identities using the [A01 build workflow](../support/build/README.md); retain a new result instead of replacing the historical receipt.

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

- **Accuracy:** quantify the current implementation's per-window overrun; neither the historical ≈2.1% first patch nor the later integrated samples prove an exact CPU cap.
- **SMP:** global quota accounting, per-CPU parking and wake ordering, CPU hotplug, cross-CPU migration, memory ordering and IPI behavior have not been verified.
- **CPU controller lifecycle:** final exit/reap debit and original-domain lifetime, sub-controller activation/disable, quota-period reconfiguration, cpu.weight, OOM/memory ownership and shutdown tests remain.
- **Hepta:** read-only QueryAbi has real guest evidence; trusted CapSpace authorization, HOS2 budget/usage/history operations and durable K↔D effect/retire flow are not integrated. `TrustedReadOnlyOrganV1` must not be used for effectful device writes.
- **Kernel conformance:** the integrated OSTD/aster-core receipt has its exact source, counts and soft skips; changed kernel code needs relevant new regressions rather than inheriting that receipt.

Keep unaccepted follow-up candidates **Draft** until A00/A06 have reviewed their actual lock/lifetime changes and run the relevant kernel scenarios. The existing main quota implementation is already merged; its remaining gates must not be confused with the status of old PR #18. No second control database or new wire version is required for this documentation correction.

## Independent kernel-mode regression and explicit pass/fail guard

The modified kernel also passed the real `aster-core` OSDK kernel test suite: **141/141 tests executed and passed**, 0 failed, 0 filtered, 0 soft-skipped, QEMU raw exit 33. This is a pinned x86_64/TCG single-vCPU run, not SMP, OSTD's full matrix or physical-hardware qualification. The [original machine result](../results/organ-backend/2026-10-16/a06-aster-core-ktest.json) records the exact counts.

The candidate runner now optionally supports `--max-cpu-percent` so a gross non-enforcement regression cannot be misreported as a green *quota* check merely because QEMU exited normally. In the real guest with 10% quota, `--max-cpu-percent 12` passed (exit 0, observed 11.245%), while `--max-cpu-percent 5` correctly failed (exit 2, guest still exited 33, observed 11.402%). The [guard results](../results/organ-backend/2026-10-16/a06-guard-checks.json) preserve both cases. This 12% bound is only an N0 1000Hz diagnostic tolerance; it is **not** a guaranteed precise hardware resource cap or a product SLO.
