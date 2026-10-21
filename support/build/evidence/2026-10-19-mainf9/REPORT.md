# A01: current main-f9 Rust build, QEMU boot and kernel regressions

The full derived Asterinas kernel at **`7758ffe294bb0e1eab46e20cba60e8af9d8bcd61`**
was built from an absent target and successfully booted on **2026-10-19 UTC**.
Both complete kernel-mode suites then ran in real QEMU guests: **OSTD 221**
reported passes and **aster-core 169** passes, with zero failed or filtered tests.
Three OSTD VMX/EPT capability soft skips leave **387 exercised passes as a lower
bound**, out of 390 reported passes. All nine CPU-configuration regressions newly
incorporated from main completed in the aster-core guest.

The first boot invocation failed before make or QEMU because an unexpected public
`OSDK.toml` existed. Its original bytes and error are retained. A separate retry,
after a reversible move under the native lock, is the successful boot. The public
manifest subsequently reappeared, including after a second recorded move. Its
writer remains unidentified and the final observed worktree has that untracked
file. The 3,014 selected tracked source/build inputs still match the producer.
**No whole-worktree-clean or continuously clean workspace claim is made.**

The [machine-readable report](report.json), [source summary](source-summary.json),
[artifact bindings](artifact-bindings.json), [archive index](archive-index.json)
and [A00/A05/A06 handoff](HANDOFF.md) provide the corresponding receipts. This
evidence publication follows the native producer; it is not a separate rebuild
of the following reporting commit.

## 1. Published source and complete upstream retention

| Identity | Value |
|---|---|
| Repository | `TrillionniumFoundation/trillionnium-os-desktop` |
| Authorized branch / PR | `agents/A01-asterinas-boot` / [#22 to main](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22) |
| Native source producer | `7758ffe294bb0e1eab46e20cba60e8af9d8bcd61` |
| Project tree | `98c7b099ff280f0804041dca13d691d431a8caf6` |
| Derived kernel tree | `9b400ccf16c275935736e6e2b0b08aecbe20c40e` |
| Actual main, first parent | `f9e306f76154590e096a42f70ce9de0a7c859e60` |
| Prior A01, second parent | `71524be19383e2ff98f6abc90668c48988e7c8e2` |
| Fixed Asterinas tag / commit | `v0.19.0` / `c4b7ed575b7b32773475b194d2ad41fb6d03765b` |
| Fixed upstream Git tree | `96605cf64aeae2d34f29b97e85eff9315fe10a8e` |
| Canonical source directory | `kernel/asterinas/` |
| Rust toolchain | `nightly-2026-07-21` |

The actual main and A01 refs were fetched before creating an independent worktree.
The source commit uses main as its first parent and preserves A01 history through
an ordinary two-parent merge and a verified, non-forced ref update. Main was read
again after the session resumed on October 19 and still resolved to f9. The PR's
base branch is main; its separately returned base-SHA snapshot may lag the branch
endpoint and is not used to identify the fetched main.

The main update contains six files: the owner CPU parser/controller changes and
tests, the upstream cgroup shell regression, and its host-parser entry/runbook.
The complete kernel core, OSTD, upstream tests and actual external ABI are exactly
main f9. A01 build support, approved OSDK derivations and lock metadata at the
producer are exactly prior A01 71524. No A05/A06 core source was edited by A01 in
this round.

The producer contains **2,945 tracked kernel paths**, including all **2,938 original
upstream paths**. Relative to the fixed upstream, 2,906 original paths are
unchanged, 32 retain existing project derivations and seven are added. No original
upstream path or file mode was removed. All 84 audited upstream documentation,
license and attribution protection items are unchanged. `LICENSE-MPL`, upstream
README/AGENTS files and the full implementation are retained. The project root
`README.md` remains **0 bytes**.

The independent owner audit passed 25 static identity checks. Its 2,875 on-disk
checks deliberately excluded live TOML/manifest reads and checked 139 such files
as immutable Git objects. Separately, the native source-capture receipts checked
**all 3,014 selected actual worktree inputs**, including the tracked manifests,
before and after execution. These complementary scopes are recorded explicitly.
The fixed-input verifier passed all 118 checks; the root Cargo.lock SHA256 is
`6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316`.
The approved host OSDK lock is a documented existing derivation, not a new kernel
version. Full receipts are in [source-records.tar.xz](source-records.tar.xz).

The independent worktree uses Git sparse checkout to omit historical nonbuild
evidence/handoff directories. **The entire kernel subtree is physically present**;
none of its index entries is sparse-skipped. This does not change the committed
tree or introduce another kernel implementation.

## 2. Actual dependency installation and current availability

This run reuses the private environment actually installed on October 18 at
08:34–08:36 UTC. Its [original installation archive](dependencies/installation-2026-10-18.tar.gz)
contains the executed bootstrap scripts, logs, signed package-index checks and
input hashes. It is not relabeled as a new October 19 installation.

The environment contains 57 privately extracted Ubuntu packages from the recorded
`20260828T000000Z` snapshot, the exact Rust nightly, and cargo-binutils 0.4.0
installed with its lock. Revalidation immediately before this build passed
**13/13 commands**, **70/70 actual binary/library hashes**, **48/48 QEMU dynamic
dependencies**, and **4/4 BIOS/BusyBox/vDSO/initramfs inputs**. See the
[current summary](dependencies/current-summary.json) and
[raw current revalidation archive](dependencies/revalidation-2026-10-19.tar.gz).

| Tool/input | Actual selection |
|---|---|
| rustc | 1.99.0-nightly, commit `87e5904f5eb6398af6b22eac2802c78934260c48` |
| Cargo | 1.99.0-nightly, commit `3efb1f477e99b42974b982d939fd100303cdf7db` |
| Rust target | `x86_64-unknown-none` |
| QEMU | 8.2.2, Ubuntu `1:8.2.2+ds-0ubuntu1.18` |
| Clang / LLD | 18.1.3 |
| Rust binutils LLVM | 22.1.8 |
| SeaBIOS | `bios-256k.bin`, 262,144 bytes, package 1.16.3-2 |
| BusyBox | Static 1.36.1, package `1:1.36.1-6ubuntu3.1` |
| vDSO | Commit `8af571775a3d3a1df3e84fc9709b9d6b160c771a` |
| Initramfs | 1,107,990 bytes; SHA256 `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| Docker / Nix / KVM | Unavailable; the real run uses native QEMU TCG |

Some actual tools and libraries are supplied by the host and recorded as such.
This is not a complete immutable host lock or a cross-host reproducibility proof.
No NixOS installation ISO was needed or downloaded for this pipeline. No live
system disk, host BIOS, GPU driver or production service was modified.

## 3. Actual build and boot entry points

The build wrapper invokes the upstream developer targets with the existing small
initramfs overlay:

```sh
# From the project root, with the fixed native development dependencies ready:
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -B -I support/build/ktest/run.py
```

The actual run used this environment and independent checkout:

```sh
cd /workspace/scratch/d7da9e7650f0/a01-mainf9
source /workspace/scratch/d7da9e7650f0/a01-current-runtime/env.sh
export CARGO_BUILD_JOBS=2
export A01_SMP=1
```

`A01_RUN_DIR` selected separate new directories under
`support/build/out/2026-10-19-mainf9/`: `kernel`, the failed `boot`, and successful
`boot-retry`. Ktests used `--output` with a new `ktest` directory. Existing output
paths are intentionally rejected. The retained outer argv, environment selector,
UTC time and exit status are in [executions/](executions/). The complete underlying
make invocations are [kernel/command.sh](kernel/command.sh) and
[boot/command.sh](boot/command.sh). Each invocation builds and installs OSDK from
this exact checkout into its own private prefix with `--locked`.

`minimal.mk` supplies the small initramfs prerequisite while retaining the
upstream `make kernel` / `make run_kernel` route. The temporary public manifest is
guarded against replacement; this guard was not weakened to obtain a pass.
Preparation for a disposable native development host is documented in the
[main build runbook](../../README.md). The dependency installation scripts and
actual private-prefix settings used here are preserved in the archive above.

| Actual stage, UTC | Duration | Result |
|---|---:|---|
| `make kernel`, 00:52:08–00:55:17 | 189.633 s | make/driver 0; both target directories absent before launch; 284 compilation lines |
| First boot preflight, 00:55:59 | 0.084 s | driver 1; no make or QEMU launched |
| `make run_kernel` retry, 00:57:08–00:57:12 | 3.406 s | make/driver 0; raw guest 33, no timeout |
| Complete OSTD/core ktests, 00:57:39–01:00:00 | 140.866 s | runner 0; both raw guests 33 |

The successful boot reuses the kernel target just built in this run; it is not
claimed as a second cold build. Existing compilation warnings remain in the
[complete build log](kernel/kernel.log) and did not make the build fail.

## 4. Loaded ELF, fixed QEMU and complete serial evidence

The first produced ELF was frozen immediately after the successful cold build.
It is byte-identical to the private read-only ELF actually loaded by QEMU:

```text
Size:   8,382,376 bytes
SHA256: 4625a5ddf9e82aee2ce01bdfb23127f88a5200565ce2a0645a09e181073ab6d4
```

The guest configuration is x86_64, q35, TCG, CPU max, **1 vCPU and 512 MiB**,
SeaBIOS, serial and the ISA debug-exit device. There is no configured network,
writable data disk, ISO, display or monitor. Full actual argv, selected firmware,
input hashes, timestamps and status are in [boot/qemu.json](boot/qemu.json).
The raw command is also preserved in [boot/qemu.command.sh](boot/qemu.command.sh).
The recorder creates exclusive kernel/initramfs/BIOS snapshots and validates them
before and after QEMU. These exact bytes are in
[guest-artifacts.tar.xz](guest-artifacts.tar.xz).

The full raw [boot/serial.log](boot/serial.log) is **72,279 bytes**, SHA256
`b585103e6b898bbd1c804b554cb66876ab7d2463872247f98d0def6bd3cc057f`.
The following five markers each occur once and in this order:

```text
OSTD initialized. Preparing components.
TRILLIONNIUM_A01_INIT_BEGIN
TRILLIONNIUM_A01_CPU_COUNT=1
Successfully booted.
TRILLIONNIUM_A01_BOOT_OK
```

The evidence includes execution of the project kernel's initramfs and shutdown
path. Raw QEMU status 33 is the expected successful debug-exit status checked by
the runner. A host Linux boot or an installer boot is not used as acceptance.

## 5. Actual kernel regressions and limits

| Suite | Reported passes | Soft skips | Exercised lower bound | Failed | Filtered |
|---|---:|---:|---:|---:|---:|
| OSTD | 221 | 3 | 218 | 0 | 0 |
| aster-core | 169 | 0 | 169 | 0 | 0 |
| Total | 390 | 3 | 387 | 0 | 0 |

See [ktest/result.json](ktest/result.json), the
[OSTD serial](ktest/ostd/guests/guest-001/serial.log) and
[aster-core serial](ktest/aster-core/guests/guest-001/serial.log).
The existing per-crate test locks were used unchanged; generated locks matched
them. No test-name filter was supplied. The nine new CPU configuration tests
comprise seven direct production-parser cases and two actual controller writes
using `CpuController::write_attr` and `VmReader`. The independent review matches
each full path to one successful completion in the raw guest serial.

The complete current suite also retains the prior final-charge and scheduling
regressions. No new full OSDK host/debug/coverage matrix, host ABI gate or dedicated
guest syscall/cgroup-shell acceptance was run here. Earlier results retain their
own source identities and are not added to this run's count. TCG does not qualify
the three VMX/EPT soft-skipped paths, general SMP or real hardware.

Ktest QEMU loads its generated live target path after a stable-FD hash. The archived
test ELFs were frozen after execution and matched to those recorded hashes. They
are not described as prelaunch private snapshots; the main boot has that stronger
snapshot mechanism. The complete independent review is
[review/native-review.json](review/native-review.json): **53 passed checks, zero
failures**, with no guest execution performed by the reviewer.

## 6. Retained failures and actual remaining blockers

The [first boot error](failures/boot-preflight/driver.log) is a real preflight
failure. The unexpected 1,019-byte manifest has SHA256
`1ff39174c39411f8b9a7fd328f762268e62d88521b43ebbde384d03d7d9a9f9f`.
The same preserved content appears with multiple different inode identities:

1. The build cleanup and immediate source capture observed no public manifest.
   The first boot then saw inode 19670 and was refused before make/QEMU. Under
   an exclusive nonblocking workspace lock, a stable FD and hash check preceded
   an `os.rename` into a new evidence directory. No original file was overwritten
   or unlinked. The [first custody receipt](failures/boot-preflight/quarantine.json)
   and original file remain available.
2. The successful retry cleanup and immediate source capture again observed the
   path absent. Inode 19777 with the older build-time mtime appeared before ktests
   and remained present after those tests passed. The
   [second custody receipt](failures/post-boot-manifest/quarantine.json) records a
   second reversible move after ktests.
3. A subsequent source capture and independent review again found the public
   file, now inode 26590. Its [read-only observation and preserved bytes](failures/manifest-reappearance/)
   are retained. The public path was left in place after this observation rather
   than hiding it from Git status. Both rename receipts describe their observed
   instant, not persistent absence.

The writer is not identified. No full writer trace was captured, so neither an
OSDK defect nor an external restorer is asserted as the cause. The build guard
continues to reject this affected checkout while an unowned public manifest
exists. This remains an environment blocker for unattended repeat invocation;
it does not change the recorded passing guests or the matching tracked inputs.

Acquisition also encountered low disk space. Old ignored target ELFs were checked
against their already-published artifact archive before deleting only that
regenerable cache under the native lock; a later observation found the target
directory reappeared. These receipts, the sparse empty-index merge failure and
its `read-tree` recovery, and the source auditor's two retained selection/type
diagnostics are in the source archive. They are not counted as native guest
failures or assigned an unobserved cause. Available space had recovered before
the successful independent build.

Other open acceptance boundaries remain: a complete immutable host lock and
cross-host reproduction; real KVM/VMX/EPT and broader SMP; A05/A06 native HOS2
effects, durable K-D and G1/G2; and real device integration. The current control
endpoint's QueryAbi path and unsupported-effect behavior are described in the
[owner handoff](HANDOFF.md); the minimal boot is not proof of those future effects.

## 7. Archive and publication verification

The archive index records every archive's size, SHA256 and scope. Each new tar.xz
has an internal member manifest and was decoded immediately to compare every
member's bytes and mode with its source. Native records retain full logs,
commands, environment, generated locks, failure observations and stage receipts;
large build caches and private SDK executables are excluded. SDK build logs and
their selected executable hashes are retained.

The source archive retains source captures and the complete fixed-object audit.
The installation archive and both current revalidation archives preserve their
original bytes and date identities. `SHA256SUMS` covers the final payload set;
the checksum receipt and publication bridge state their own scope explicitly.
The publication bridge checks that only reporting metadata in the selected input
set changes after the native producer, while all kernel, ABI and build programs
remain equal to it. Commits are pushed to the authorized A01 branch without
force; main and other Agent branches are not changed.
