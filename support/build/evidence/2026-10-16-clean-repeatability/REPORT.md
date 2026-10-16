# A01: two clean kernel builds and current-main integration

Two independent empty-target builds of the full Asterinas-derived kernel at
`5bcec614c1a075782b6ffaa5a5212fdee29be37d` produced **byte-identical ELF files**,
and both completed the real initramfs boot. The result is scoped to the same
host, absolute source directory and absolute target directory. Shared registry
and toolchain caches were retained. Cross-directory and cross-host bit
reproducibility remain open.

## Source and authored change

The fixed upstream remains Asterinas v0.19.0, commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, Rust
`nightly-2026-07-21`. The only vendored implementation is `kernel/asterinas/`.
Its upstream documentation, MPL license and attribution remain in place;
the project-root README is zero bytes. All 118 fixed-input checks pass.

The phase began at published A01 commit
`0a533b92d4a4df8e8e4643c1b7de00e83ba0fd9d` and incorporated the actual fetched
main `a1c61d50fe281361ca04ad4bc3c6b3aba2c2260f` through published merge
`81bd3f21804221dcc5de73f3e59b2f953282506a` (tree
`48d1c43cb77706870cd431a7cc4cecb0f73f3254`). Main added ABI boundary tests and
evidence-CI guards, plus status documentation. It did **not** add kernel, OSTD
or OSDK source changes; an A06 status entry is not an integrated runtime fix.

The authored fix, published as
`5bcec614c1a075782b6ffaa5a5212fdee29be37d` (tree
`00e70e58dfa0dbf4718db55240136683f0a23310`), obtains the stable workspace lock
before creating either explicit or default evidence output. Previously a
busy-lock rejection consumed that new directory, so retrying the same command
failed even after the lock owner exited. Both public-shell routes now retain
a reusable output pathname. Two regressions cover rejection and successful
same-command retry. Build metadata also records Rust flags, target directory
and the explicit build timestamp. Only `kernel.sh`, its host regression file
and build documentation were authored; no tracked file beneath
`kernel/asterinas/` changed in this phase.

## Actual results

| Run | Build/cache scope | Actual result |
| --- | --- | --- |
| Public A | Kernel target absent before launch; standard-library and kernel compilation observed | Outer 0, raw QEMU 33, live boot checker pass |
| Public B | A cache captured, moved under verified custody and deleted; same target absent before launch | Outer 0, raw QEMU 33, live boot checker pass |
| OSTD | Reused B target; real test-kernel build and guest | 221 reported passes, 3 VMX/EPT soft skips, 0 failed/filtered; raw QEMU 33 |
| aster-core | Same explicit cache reuse | 141 passes, 0 failed/filtered; raw QEMU 33 |

There were **four actual QEMU guests**, all raw exit 33. The public pair's
actual controller tool session was 86915/exit 0; the kernel-test controller
was 88957/exit 0. Kernel tests report 362 successes but only **359 exercised
passes as a lower bound** after three explicit hardware soft skips. All ten
test command leaders were reaped with actual/effective exit 0. These are full
crate runs, without a test-name filter; they are not the full upstream
userspace, hardware or device matrix.

The merged-main host snapshot passed 105 test executions: ABI Python 19,
ABI Rust 25, os-control Rust 21, and archive validation 20 in each of `-I`
and `-I -O`. The golden generator independently verified 12 vectors. The
build-entry suite passed 33 tests in each mode, bringing this phase's host
test executions to 171, with the 12 golden vectors counted separately.
The original failing busy-lock reproducer is retained. Host ABI/control
tests do not establish a kernel HOS2/ioctl implementation. CI's new absent
source bootstrap branch was inspected, not executed as a new local test.

## Artifacts and commands

Both public ELF files are **8,288,088 bytes**, SHA256
`6c0c382ec88d2e59b58d50abb0ef3671635f30ce08c3b442d2bdc2204821d040`.
They are each retained as gzip and were independently decompressed and
compared byte for byte. Their shared 1,107,990-byte initramfs has SHA256
`86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`.
Serial bytes differ as expected and have separate recorded digests.
The OSTD/core ELF sizes are 2,005,200/6,519,544 bytes, with hashes
`862cfd3e3a34464733668f350494e69d52f5b788a9fd921bd6183384d5647151` and
`706e77b9e2e4d322b69742db42a142480961b83131a917f4241bc20a8a9531e3`.

The profile is x86_64, q35/TCG, CPU `max`, 1 vCPU, 512 MiB, explicit SeaBIOS,
serial and isa-debug-exit, without data disks or networking. Native QEMU is
8.2.2; rustc is 1.99.0-nightly (`87e5904f5`), Cargo 1.99.0-nightly
(`3efb1f477`). The normal native dependency installation and build entries are:

```sh
support/build/prepare-host.sh --apt
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -I support/build/ktest/run.py
```

The wrapper uses upstream `make kernel` and `make run_kernel`, with the
small initramfs prerequisite. No NixOS ISO, Nix or Docker was required.
Earlier phase evidence retains dependency installation; the current phase
reused its installed fixed toolchain, host packages and populated offline
registry. Current runs are new source builds, not a new dependency download.

For this pair, the absolute worktree was
`/workspace/scratch/ae1a8cf05419/a01-next8-repeat`, with target
`kernel/asterinas/target` inside it. `CARGO_NET_OFFLINE=true`,
`CARGO_BUILD_JOBS=2`, `SOURCE_DATE_EPOCH=0`, `TZ=UTC`, `LC_ALL=C`, and
`ASTER_BUILD_TIMESTAMP='Thu Jan  1 00:00:00 UTC 1970'` were explicit.
`RUSTFLAGS` and `CARGO_ENCODED_RUSTFLAGS` were unset. Exact argv, PATH,
tool locations, versions, firmware and all QEMU arguments remain in the
retained invocation/environment/command records. The saved controller is the
actual run record with its original absolute paths; adapt paths before reuse.
Its guarded cache deletion removed only this controller's freshly generated
A target (apparent 1,100,719,091 bytes), after saving and verifying all A
outputs. The OSDK host tool was built for A and reused for B; not every tool
cache was cold.

Both public inputs record the fixed minimal lock, and the production source
copies it into the generated workspace before Cargo `--locked`. B's generated
lock was separately captured after the pair and matches the 41,843-byte
minimal lock SHA256 `b42d8fff136d80a5f8159356882096996991e05975d8da9c81ad9db9bdb06e10`.
A's post-build generated-lock snapshot was **not retained before cache
deletion** and has not been reconstructed. Both test-generated locks were
retained and match their respective committed locks.

## Archive map

| Directory | Retained evidence |
| --- | --- |
| [clean-pair](clean-pair/README.md) | Both actual ELF gzip files, initramfs, full build/serial/QEMU records, source/env bindings, empty-target and cache-custody receipts |
| [kernel-tests](kernel-tests/README.md) | Actual full crate runs, both ELF gzip files, commands, generated locks, serial logs, exit/reaping receipts |
| [busy-output](busy-output/README.md) | Original failure, exact patch/source reconstruction, 33 tests in both Python modes |
| [merged-host](merged-host/README.md) | Immutable merged-source snapshot, 105 host test executions and 12 golden vectors |
| [path-analysis](path-analysis/README.md) | Read-only analysis of historical ELF differences, with repository-relative retained artifact references |

Subdirectory checksum lists and indexed tar members bind original bytes.
The root `SHA256SUMS` covers the full package, including those inner lists;
`archive-manifests.json` records their frozen inventories. Runtime records
retain the earlier upstream-lock snapshot; the final lock update records
results and was not an input change to these builds. Source publication
receipts bind local Git trees to the equivalent remote commits. The final
evidence commit is identified by Git, without a recursive self-SHA field.

The previous ELF comparison found 931 checkout-root occurrences in each
loaded `.rodata`, plus Rustup/Cargo roots. Neither normal ELF contained
DWARF `.debug_*`; five of six PT_LOAD segments differed. The fixed component
macro also embeds absolute Cargo metadata strings as ordinary Rust literals.
Compiler source remapping alone cannot remove arbitrary literals. This
establishes path-dependent loaded bytes, without assigning every historical
byte difference to one cause. No core or metadata macro was changed to force
a crosspath result. The broad reproducible-build readiness flag remains false.

## A00 / A05 / A06 handoff and remaining limits

All source paths below are relative to `kernel/asterinas/`:

| Owner | Actual interface |
| --- | --- |
| A05 process | `kernel/core/src/process/process/mod.rs::Process` |
| A05 launch/exec | `kernel/core/src/process/process/init_proc.rs`; `kernel/core/src/process/execve.rs` |
| A05 ioctl entry | `kernel/core/src/syscall/ioctl.rs::sys_ioctl` |
| A05 file dispatch | `kernel/core/src/fs/file/file_handle.rs::FileLike::ioctl` |
| A06 common scheduler | `kernel/core/src/sched/sched_class/mod.rs::ClassScheduler`, `LocalRunQueue` |
| A06 classes/accounting | `kernel/core/src/sched/sched_class/{stop,real_time,fair,idle,time}.rs` |

The kernel subtree is `51f02c3b0c85fc150737a17d3c1a3681377c78e8`, its
`kernel/core` subtree is `fa1684a84388ce4ff6f93a5519b1a5b13e2bec3c`, and
OSTD is `5037563c4b9cbfc4826568e5c5c4d56d2891a904`, unchanged from the
original imported implementation. A05/A06 own their core changes; A01 owns
build/configuration and does not overwrite those interfaces. The new full
crate results are a baseline for their changes, not native resource-control
acceptance. Main inclusion of any owner runtime-budget work still needs A00
coordination; this phase did not test such a change.

Unresolved scope: cross-host/crosspath reproduction, TCG's VMX/EPT and SMP
coverage, HOS2/native budget enforcement, complete hardware/userspace/Hepta
acceptance, and the prior same-ELF diagnostic's two fd-limit failures and two
SCM_RIGHTS timeouts. That diagnostic, prior TCP/GDB OSDK 22/22 and prior live
Rust-entry debug/cancellation results were not rerun here. The previous
AF_UNIX `socket()` EPERM limitation was not reprobed here. The historical
external generated-manifest writer remains unidentified. Current A/B cleanup
receipts are `owned_removed` with exit 0 and clean tracked source; they do not
identify that writer. A pre-existing untracked manifest in the main workspace
was preserved; all builds used the disposable exact-source worktree.

No new Linux-host/installer boot is counted as a project-kernel pass. No main
merge or remote-CI green result is implied by local tests. PR #22 targets main;
only `agents/A01-asterinas-boot` is published, with normal fast-forward updates.
