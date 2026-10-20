# A01 → A00 / A05 / A06: native blocker closure, 2026-10-20

## Exact source and current acceptance

Branch: `agents/A01-asterinas-boot`; [PR #22 → main](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22).
The observed main is `0c1de23a3754bc3a6976fed53c7dfa0ec3778e57`.
The full-kernel cold-build producer is `684c4c82bbe770d712da75a199b7f5757ee61191`
(tree `8dde0a4beb98f6749a529624aeb1d0b7c0f13a98`). The successful default UNIX
OSDK matrix producer is `8769a3e224fb97ce6d06fbcb1512281a7427156e`
(tree `d18105364f75d4ffacb42c6cf6de793f0e846ccc`).
A later evidence/documentation commit is not a newly rebuilt native producer.

The upstream remains full Asterinas v0.19.0, commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, with `nightly-2026-07-21`.
There is one kernel implementation at `kernel/asterinas/`. Root `README.md`
remains zero bytes; upstream licenses and required documentation remain.

Two different clean, detached source checkouts at producer 684 each started
with absent kernel and OSDK targets. Both compiled the complete Rust kernel
through upstream Make and reached the small-initramfs boot marker in real
QEMU. C took 439.446273 seconds; D took 473.829691 seconds. Each launcher/make
returned 0, each QEMU returned raw 33, with no timeout and unchanged source.

The final independent audit passed **855 checks**. It read and compared the
complete artifact bytes, not only hashes:

| Actual loaded artifact | Bytes | SHA256, identical in C and D |
| --- | ---: | --- |
| Full kernel ELF | 8,410,560 | `00f3bfb76164fac3890c68115f5347e758820aeeffd42bb9021261900acca508` |
| Small initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| SeaBIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

Each run recorded six actual `cargo metadata --locked --format-version 1`
projections, each preserving all 19 configured components. Each compiler
ledger bound 340 successful Cargo units and 500 dependency references to
completed producers. This establishes this same-host fixed-profile cold
comparison; it does not establish arbitrary-host reproducibility.

At producer 876 the complete default UNIX matrix passed **22/22** with zero
failed or blocked cases. Eleven actual guest processes exited raw 33. The
independent audit checked 389 files and 114 locked Cargo requests. One VMX
unavailable fallback is reported separately and is not exercised VMX support.
The coverage-specific AF_UNIX listener, GDB breakpoint/PC, original symbol ELF,
loaded ELF, raw profile, LLVM result and guest serial are bound to the same run.
The original VSCode test retains its upstream TCP semantics.

Producer 684 → 876 changes only two OSDK integration-harness files. The entire
kernel tree, core, OSTD, os-control, kernel entry, minimal overlay, recorder,
reproduction code and upstream lock retain the same Git objects. These are
source-identity checks, not a claim to have rebuilt the full kernel at 876.

## Actual entries

From a prepared clean project checkout, with the fixed native runtime loaded:

```sh
bash support/build/kernel.sh kernel
bash support/build/kernel.sh run_kernel
```

The entry invokes upstream `make kernel` / `make run_kernel` with
`support/build/minimal.mk`. The guest is x86_64, q35, TCG, CPU max, one vCPU,
512 MiB, SeaBIOS, fixed devices and serial output. The minimal boot route does
not require a NixOS installation ISO. The recorded QEMU argv includes the
actual private prelaunch ELF/initrd/BIOS snapshots and the runtime data path.

For a fresh default OSDK matrix output:

```sh
python3 -B -I support/build/osdk-integration/run.py \
  --output /absolute/new-osdk-matrix-output
```

For the qualified opt-in schema-5 cold comparison, use two distinct clean
checkouts at producer 684, absent targets, the same new owned profile root and
separate new outputs. The launcher selects one Cargo job, disables incremental
compilation and enforces the recorded profile. Use this command for each
checkout, replacing the example absolute paths:

```sh
python3 -B -I support/build/repro/run.py \
  --checkout /absolute/clean-checkout-c \
  --profile-root /absolute/owned-repro-profile \
  --output /absolute/new-cold-output-c \
  --action run_kernel
```

The [complete evidence report](../evidence/2026-10-20-blocker-closure/REPORT.md)
contains both successful full serials with declared private-prefix redaction,
original/delivered hashes, normalized actual commands, exact producers, all
complete matrix results and preserved failure identities. Original commands,
environment, build logs, compiler ledgers, metadata, frozen artifacts and full
unmodified serials are retained separately for the user.

## A05 interfaces: process identity and ioctl

| Interface | Project-relative source | Ownership / use |
| --- | --- | --- |
| `Process` | `kernel/asterinas/kernel/core/src/process/process/mod.rs` | A05 process object |
| `ProcessImageKey` | `kernel/asterinas/kernel/core/src/process/process/image.rs` | A05 image identity and generation |
| Exec replacement | `kernel/asterinas/kernel/core/src/process/execve.rs` | A05 image lifecycle |
| Initial process | `kernel/asterinas/kernel/core/src/process/process/init_proc.rs` | A05 initial process construction |
| ioctl syscall | `kernel/asterinas/kernel/core/src/syscall/ioctl.rs` | A05 dispatch through `FileLike::ioctl` |
| HOS2 device | `kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs` | A05 control dispatch; experimental ioctl `0xC020_4802` |

## A06 interfaces: scheduler and CPU owner

| Interface | Project-relative source | Ownership / use |
| --- | --- | --- |
| `ClassScheduler` and run queues | `kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs` | A06 scheduling; `with_current_cpu_bandwidth_settled` / `owner_update` |
| CPU controller | `kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs` | A06 single resource-budget owner |
| Native CPU observation | `kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native.rs` | A06 native state / observation |
| Shared scheduler abstraction | `kernel/asterinas/ostd/src/task/scheduler/mod.rs` | Shared OSTD; A00 coordination required |

A02 retains `libs/os-abi/**`; A03 retains `libs/os-control/**`. A01 retains
`support/build/**` and `support/upstream-lock.json` and does not take over A05/A06
core files. Ordinary product boots remain QueryAbi-only; dedicated G1-c opt-in
acceptance is separately reported by its owner workflow.

## Passed upstream regressions and exact limits

- Earlier producer `a927146241a8622affd6172a1584c9555ba3cc6b` completed OSTD 221
  reported passes, including three VMX/EPT soft skips, and aster-core 247 passes:
  468 reported, at least 465 exercised. These remain earlier-producer results.
- Producer e37 passed the complete 22-case explicit TCP coverage matrix.
- Producer 876 passed the complete 22-case default UNIX matrix.
- Producer 684 passed the two full-kernel cold builds/boots and complete artifact
  byte comparison described above.
- The 203 different host cases at producer 684 and 17 marker cases at 876 are
  host regression evidence; they are not extra native guest or kernel counts.

The initial tmpfs ENOSPC attempt, original UNIX post-exit coverage failure,
cc8 component-initialization panic (raw 65), and 684 pre-spawn marker rejection
remain failed evidence with their exact commands, logs and producer identities.

## Remaining integration coordination

A01's measured default UNIX capture and schema-5 cold-boot blockers are closed.
Current GitHub workflow state is read independently; queued jobs are not passes.

Two concrete source changes remain outside A01 ownership under
`docs/agents/PLAN.md` (A00 uniquely coordinates cross-owner changes):

1. A04's Linux reference fixture supplies `NULL` to `pivot_root` while asserting
   capability-denial EPERM. The same ELF passed 32/32 on one actual CI host and
   31/32 on another, returning EFAULT in the failing case. A minimal two-hunk
   owner patch exists in PR #215; its 52-file PR is not an authorized wholesale
   A01 import. Keep EPERM, all 32 cases and the independent Python oracle.
2. The inherited CodeQL regex finding in
   `results/integration/2026-10-19-g1b-usage/source-publication/validate-publication.py`
   has a bounded reproducer and a minimal candidate. New CodeQL workflow success
   does not itself prove that unchanged inherited source has been repaired.

[CodeQL coordination](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#issuecomment-6294838522)
and [A04 coordination](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#issuecomment-6295094269)
carry the concrete findings. These owner items and exact-head CI are not silently
marked closed. No other Agent branch, main, active disk, firmware, GPU driver or
production service was modified.
