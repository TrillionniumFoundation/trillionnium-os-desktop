# A01: final main sync, native source bridge and updated A02 gate

## Outcome and source identities

Ordinary merge `d9ccc523141ec46baef2a0dfe0afe49e4f97f523` incorporates main
`4339acedd2d433f838c7b5fd445709c539043a77`. The changed A02 host gate was
executed and passed at that merge. The complete native kernel, actual
external ABI and build programs are unchanged from the successful native
producer below, so this final sync records their equivalence without
claiming another build or guest execution.

| Identity | Commit | Scope |
| --- | --- | --- |
| Latest integrated main | `4339acedd2d433f838c7b5fd445709c539043a77` | Incoming A02 oracle and A03 receipt lifetime changes, preserved unchanged |
| Source bridge and updated A02 gate | `d9ccc523141ec46baef2a0dfe0afe49e4f97f523` | Project tree `315b2b84319a88442fb054f434ccc2fdc436e47e` |
| Latest actual Rust build and QEMU boot | `40c901c6e189058bdd6f42bb43bf46b3bbcf8ffa` | Incremental `make kernel` then `make run_kernel`, both exit 0, raw QEMU 33 |
| Initial absent-target build, boot and native regressions | `c22891b593f77c98ff4ea94d7aecb54f32222651` | Earlier complete pipeline and OSTD/core ktests; retained at that producer |

The commit that publishes this directory only adds evidence and updates
build README/lock reporting fields. It is a separate identity from these
executions. `kernel.latest_native_boot` and `kernel.latest_native_validation`
keep the actual 40c901c6 producer; new source-bridge and ABI pointers are
recorded separately.

The fixed full upstream base remains Asterinas v0.19.0, commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, with Rust
`nightly-2026-07-21`. The single source directory is `kernel/asterinas/`;
its derived tree is `6c2904e53e79cedbbaf013a73a6173f4afa57010`.
Upstream source, attribution and documentation remain preserved, and the
project root README is 0 bytes.

## Independent source bridge

The [source receipt](source-bridge.json) compares the original native
capture to immutable Git blobs and the bridge worktree. The selected
path set has 3,010 entries in both revisions. Exactly 3,008 retain the
same bytes, mode, blob and SHA256; the two differences are
`support/build/README.md` and reporting/history fields in
`support/upstream-lock.json`.

All 2,941 files under the complete kernel root, the actual external ABI
file, and 65 of the 66 selected support/build files are unchanged. The
66th build file is its README. No build program is excluded as metadata.
All 118 fixed-input checks pass, and the static check's stdout is
byte-identical to the actual native build receipt. A05/A06 core, OSTD and
external ABI paths also match main4339 exactly.

The reviewer scanned all 112 kernel Cargo manifests, relevant Cargo locks,
and 1,687 Rust/manifest/lock/ABI reference files. There is no current
`os-control` dependency or source reference. The core still directly
imports `libs/os-abi/src/lib.rs`. This supports the native input boundary;
the newly merged A03 implementation and its tests are not covered by this
native execution or by the source bridge.

The raw merge-tree publication input is [main-merge-tree.json](main-merge-tree.json).
It preserves the ordinary parents and all 21 incoming blobs. The source
receipt binds the resulting published commit and tree. No other agent
branch was modified, and no force push was used.

## Actual A02 gate at d9ccc523

The unchanged owner entry point was executed with the recorded native
environment and fixed nightly:

```bash
source /workspace/scratch/d7da9e7650f0/a01-runtime/env.sh
export CARGO_BUILD_JOBS=2
python3 -B tests/abi/run_acceptance.py \
  --repo-root /workspace/scratch/d7da9e7650f0/trillionnium-os-desktop \
  --toolchain nightly-2026-07-21 \
  --output-dir /workspace/scratch/d7da9e7650f0/a01-runtime/review/a02-after-main-4339 \
  --timeout 60 --mutation-timeout 900
```

Use a fresh output directory for another run. The actual execution lasted
18.475088 seconds, from 03:52:14 to 03:52:32 UTC on 2026-10-18, and exited 0.

| Check | Actual result |
| --- | --- |
| Unified owner gate | 13/13 checks passed |
| Python ordinary mode | 62/62 passed |
| Python separate optimized mode | 62/62 passed |
| Python mutation subset | 9/9 passed, already included in the ordinary 62 |
| Rust | 78/78 passed, including one doctest; no failed, ignored or filtered tests |
| Compiled source mutants | 20/20 compiled and triggered the expected test failures |
| Golden vectors | 12 + 24 + 1 passed |
| rustfmt, strict Clippy, bare-target no_std | Passed |

All 28 recorded source inputs match d9ccc523 Git blobs. HEAD, tree and
their input hashes remained unchanged before and after execution. These
gate receipts record tracked-clean status only. The independent source
bridge separately observed a clean complete worktree at its own time.

[abi-summary.json](abi-summary.json) provides counts, toolchain and command.
[abi-owner-gate.tar.gz](abi-owner-gate.tar.gz) retains the original report
and mutation JSON with complete raw stdout/stderr and commands, outer
execution receipts, source bindings and recording scripts. Its 14 members
were read back and verified against [abi-archive-manifest.json](abi-archive-manifest.json).
The archive is 47,142 bytes, SHA256
`d1788cfd8f34030d79d9591d30cdf101cb32a62aed5aa80fcda2692184b3791c`.
[Original paths](abi-original-paths.json) preserve provenance without
duplicating source snapshots, target or the already archived runtime.

The [input comparison](abi-input-comparison.json) uses actual earlier
producer 40c901c6 as its baseline. It crosses the intervening evidence
commits, so its two changed full-file hashes (the golden oracle and
upstream-lock reporting data) do not mean that the main4339 merge itself
changed the lock file.

## Native evidence and repeatable entry points

The [latest actual native report](../2026-10-18-main355-followup/REPORT.md)
retains the successful Rust build, exact QEMU invocation and complete
serial log. The kernel ELF loaded by QEMU is 8,303,048 bytes, SHA256
`1eb66b33baef6b338c232598d25f743dc83526a2715811b430e5a7208e249ecd`.
The first ELF produced by that build and the loaded private copy have
identical bytes. The configuration is x86_64, q35, TCG, CPU max, 1 vCPU,
512 MiB, SeaBIOS, serial output and isa-debug-exit, using a 1,107,990-byte
BusyBox initramfs. No NixOS ISO is a prerequisite.

From the repository root with that documented native environment prepared:

```bash
source /workspace/scratch/d7da9e7650f0/a01-runtime/env.sh
export CARGO_BUILD_JOBS=2
export A01_SMP=1
export A01_QEMU_TIMEOUT=300
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
```

The wrapper enters the preserved upstream developer targets `make kernel`
and `make run_kernel`; use distinct fresh `A01_RUN_DIR` paths when retaining
another run. These are repeatable entry instructions, not additional
commands executed by this sync. The exact executed argv and per-stage
output paths remain in the linked native report.

The [initial pipeline report](../2026-10-18-current-main/REPORT.md) retains
source acquisition, 57 privately extracted signed-snapshot Ubuntu packages,
Rust dependency installation, the absent-target full Rust build, actual
boot and native kernel regressions. OSTD reported 221 passes with 3
VMX/EPT capability soft skips; aster-core passed 153 with no skips. Their
374 reported passes / 371 exercised lower bound and zero failures remain
scoped to c22891b. They were not rerun at d9ccc523 or 40c901c6.

## Handoff and remaining limits

The [A00/A05/A06 handoff](../2026-10-18-main355-followup/HANDOFF.md) lists
the exact Process/exec/init, ioctl/device, scheduler, CPU-cgroup and lease
interfaces and ownership. Those implementation files are unchanged here.
Current `QueryAbi` compilation is not a dedicated ioctl effect acceptance.
Trusted capability activation and the four effect/history operations,
final-debit lifecycle/SMP validation, A07 durable recovery and project
G1/G2 remain owner work.

An untracked OSDK manifest appeared after the prior boot's completed source
capture. Its different inode, bytes, stat and nonempty Git status were
preserved and the exact entry was reversibly quarantined under the native
workspace lock. See the [observation](../2026-10-18-main355-followup/late-manifest/observation.json).
There is no entry at this bridge audit, but the writer and root cause
remain unidentified. This report does not claim every earlier worktree
observation was clean.

No new kernel build, QEMU guest, ktest or A03 matrix was run in this sync.
VMX/EPT, the complete upstream userspace/device matrix, bare metal,
cross-host byte reproduction and a complete immutable host dependency
lock remain unverified. The machine-readable scope is in [report.json](report.json);
[SHA256SUMS](SHA256SUMS) covers every other file in this directory.
