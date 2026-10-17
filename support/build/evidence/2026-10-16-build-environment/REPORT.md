# A01: actual kernel builds despite inherited make controls

The full Asterinas-derived kernel was rebuilt from an **absent target** at
published source `ff040c6d5afbc4e26a249022093b8090181f6176`, then booted in
real QEMU. Inherited dry-run/touch/ignore-error flags and an extra makefile
were deliberately present. The fixed wrapper recorded and removed those
controls; the kernel build recorded 279 compilation lines and returned 0.
The subsequent cached `make run_kernel` boot returned raw QEMU 33. Complete
OSTD and aster-core test kernels then passed in two more real guests.

## Source and fixes

The phase started at A01 `79d7f0530f08237ab2581d70d44fe59130eced8b` and
incorporated actual main `3b2d15bc987e7ca78e64fa54edffb2177b8abde0` through
published merge `74ee9b3d62dc85f272681c5caed3a9c328e38539` (tree
`73b34b91910852917d4c6bea020c8b4dc1e62e10`). This inherited 15 A02 ABI files;
no kernel or OSDK source changed. The authored environment fix is published
as `ff040c6d5afbc4e26a249022093b8090181f6176`, tree
`eb16c5ef5fe8adf3a9249e19a7674cec7b2e359f`, with six files under
`support/build/` changed. Publication receipts bind equivalent local Git
commits to their exact remote trees, modes and ordered parents.

Two defects were reproduced before editing:

- The old public kernel-build entry returned success with `MAKEFLAGS=n` or
  `t` even though its Cargo build recipe never ran. The reproducer uses real
  GNU Make 4.3 and the original upstream Makefile plus A01 overlay, with
  fixture external tools. A normal-flags control actually invoked the recipe.
  This was a host reproducer, not a passing kernel build. The old run_kernel
  checker already rejected a missing actual QEMU run.
- Real fixed-nightly Cargo experiments showed that a present
  `CARGO_ENCODED_RUSTFLAGS`, even an empty value, suppresses ordinary
  `RUSTFLAGS`. The fixed OSDK source supplies required linker/CPU flags through
  the latter variable. Merely recording inherited encoded flags did not make
  that configuration safe for this fixed profile.

`kernel.sh` now records shell-quoted inherited `MAKEFLAGS`, `MFLAGS`,
`GNUMAKEFLAGS`, `MAKEFILES`, `MAKEOVERRIDES` and `MAKELEVEL`, then unsets them
before its make calls. GNU Make establishes its ordinary recursion state for
children. Its real fixture verifies that dry-run/touch/question modes do not
skip recipes, ignore-errors does not mask a failure, extra makefiles are not
read, and child/grandchild MAKELEVEL values are 1/2. This is an environment
contract for a fixed build profile, not an untrusted-tool sandbox.

The normal kernel and kernel-test public entries reject the presence of
`CARGO_ENCODED_RUSTFLAGS` before output, locks or tool invocation. Both empty
and nonempty cases are tested; unsetting it permits the same command and
output path to succeed. Debug's kernel worker also reaches the shell guard.
The separate OSDK integration harness was not changed or rerun this phase;
this is not a claim that every possible direct Cargo/OSDK invocation is guarded.

## Actual source build, boot and regression

| Entry | Cache/build scope | Actual result |
| --- | --- | --- |
| `kernel.sh kernel` | Target absent; 279 compilation lines including Rust core/alloc, OSDK, aster-core and asterinas | Public/worker exit 0, owned manifest cleanup 0 |
| `kernel.sh run_kernel` | Reused the preceding build; zero new compilation lines | Public/worker exit 0, live checker pass, raw QEMU 33 |
| Full OSTD | Reused normal-build target, actual test-kernel build | 221 reported passes, 3 explicit VMX/EPT soft skips, 0 failed/filtered, raw QEMU 33 |
| Full aster-core | Same explicit reuse | 141 passes, 0 failed/filtered, raw QEMU 33 |

The actual native-build controller tool session was **47989/exit 0**, and the
kernel-test controller was **74160/exit 0**. There were **three real QEMU
guests**, all raw 33. OSTD/core report 362 successes, with an **exercised pass
lower bound of 359** after the three hardware soft skips. These are full
crate runs without a test-name filter. No cancellation, GDB, SMP, userspace
compatibility or complete upstream device matrix result is added here.

The kernel build and boot snapshots are both **8,266,576 bytes**, SHA256
`d90ebc3210e74271252a6d1f75ca22a16a569a8b48a99805d30d3d99124b9306`.
They were captured separately through stable file descriptors and both are
retained. Their equality connects these two stages of **one** clean build;
it is not a second independent clean build. The common 1,107,990-byte initramfs
has SHA256 `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`.
The boot serial SHA256 is
`18f820dba25feb4186b881cd68fb3d44c53b4d129653152bcfccefbce330c357`.
Test ELF, serial and generated-lock hashes are separately indexed in the
kernel-tests package. The normal generated Cargo.lock was independently
captured after boot and matches the committed 41,843-byte minimal lock
`b42d8fff136d80a5f8159356882096996991e05975d8da9c81ad9db9bdb06e10`.

Both native calls deliberately received `MAKEFLAGS=nt`, `MFLAGS=-n`,
`GNUMAKEFLAGS=--ignore-errors`, `MAKEOVERRIDES=TARGET_ARCH=riscv64`,
`MAKELEVEL=73`, and `MAKEFILES` naming a retained file containing a make
`$(error ...)` directive. The original values and effective unsets remain in
both environment logs. Actual architecture and QEMU arguments stayed x86_64,
q35/TCG, CPU max, 1 vCPU, 512 MiB, explicit SeaBIOS, serial and debug-exit,
without data disks or networking. Before building, two actual shell calls
with empty/nonempty encoded flags returned 2 without creating output, lock
or target; the unset retry built successfully.

Commands from a prepared disposable Ubuntu 24.04 x86_64 host are:

```sh
support/build/prepare-host.sh --apt
unset CARGO_ENCODED_RUSTFLAGS
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -I support/build/ktest/run.py
```

These use the upstream developer make targets and small BusyBox initramfs.
No NixOS ISO, Docker daemon or Nix was needed. Existing kernel toolchain,
registry and host packages were reused; the exact fixed-nightly Clippy
component was actually installed for the separate ABI check below. The
normal kernel target was new, not every tool/registry cache. Actual rustc is
1.99.0-nightly (`87e5904f5`), Cargo 1.99.0-nightly (`3efb1f477`), QEMU 8.2.2.
Both saved controllers retain their exact argv, paths, environment and exits.
Their scratch absolute paths are run records and require adapting before reuse.

## Host results and retained failures

The authored entrance regressions comprise 30 kernel-runner, 9 supervisor and
17 kernel-test-runner tests: **56 distinct tests**, passed in `-I` and `-I -O`.
The original agent runs therefore account for 112 executions. A second
integrated pass at the published source repeated those same 112 executions
to retain six explicit invocation/exit/log-hash receipts (actual tool session
56957/exit 0). It does not add 112 distinct cases. The earlier make package
keeps its four successful raw suite logs but lacks four separate original
invocation receipts; its replay commands and observer summary are identified
as such rather than reconstructed into original receipts.

Main's new ABI snapshot passed **39 Rust + 28 Python** tests, rustfmt, and
**13 golden checks** (12 HOS2 frames and one transport vector). That gives
67 passing host test executions plus 224 entrance executions = **291 passing
host test executions**, with 13 golden checks and three tiny Cargo flag experiments
listed separately. The tiny experiment's source/argv/results are retained;
its compiled binaries and original aggregate controller were not retained.
Original make/encoded red tests are preserved and are not counted as passes.

**The overall host validation is partial.** Strict fixed-nightly Clippy
initially failed because the component was missing. Installing it exited 0;
the identical `--all-targets -- -D warnings` retry exited **101**, reporting
`chunks_exact_to_as_chunks` at `libs/os-abi/tests/mutation_kill.rs:21` and
`libs/os-abi/tests/transport_vectors.rs:14`. No A02 source or lint suppression
was applied. Initial failure, dependency installation, retry and exact source
are preserved. The source-mutation matrix was not rerun. These host codec
results do not establish a kernel HOS2 driver or permission boundary.

## Evidence and handoff

| Package | Contents |
| --- | --- |
| [kernel-public](kernel-public/README.md) | Actual clean build and cached boot, two ELF captures, shared initramfs, commands, full logs/serial/QEMU, generated normal lock |
| [kernel-tests](kernel-tests/README.md) | Actual two test guests and ELF captures, full serial, generated locks, source/env and ten command receipts |
| [make-controls](make-controls/README.md) | Original false-success reproducer, red tests, exact before/after patch and real GNU Make regressions |
| [encoded-flags](encoded-flags/README.md) | Old-runner red tests, 17-test suites, real Cargo priority experiments and precise archive limitations |
| [host-recheck](host-recheck/README.md) | Six additional exact invocations at published ff040c6d, logs, exits and unchanged source hashes |
| [merged-host](merged-host/README.md) | Original immutable ABI snapshot, successful tests and retained Clippy failures |

Every package has its own checksum list; the root master list additionally
covers all packages and their lists. `archive-manifests.json` records the
frozen inventory. Runtime upstream-lock snapshots are build inputs; the final
lock update records these results after testing. Git identifies the final
evidence commit without a recursive self-SHA field.

Fixed upstream remains full Asterinas v0.19.0 commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, nightly-2026-07-21. All 118 fixed
input checks pass. The single vendored root is `kernel/asterinas/`; upstream
documentation/license remain intact, and root README stays zero bytes.
No tracked file below that kernel root changed in this phase.

A05 owns `kernel/core/src/process/process/mod.rs::Process`,
`kernel/core/src/syscall/ioctl.rs::sys_ioctl` and
`kernel/core/src/fs/file/file_handle.rs::FileLike::ioctl`. A06 owns the common
`kernel/core/src/sched/sched_class/mod.rs::ClassScheduler`/`LocalRunQueue` and
class/accounting implementations. Those paths are relative to the kernel
root. A01 retains build tooling and does not overwrite their source. The
core subtree is `fa1684a84388ce4ff6f93a5519b1a5b13e2bec3c`; OSTD is
`5037563c4b9cbfc4826568e5c5c4d56d2891a904`, both unchanged.

Remaining limits include the two A02 Clippy diagnostics, crosspath/crosshost
bit reproduction, VMX/EPT and SMP coverage for this profile, native HOS2 and
resource-budget acceptance, full hardware/userspace/Hepta validation, the
prior A04 fd-limit/SCM_RIGHTS failures and the historical unidentified
generated-manifest writer. No new result resolves those owner issues. The
main workspace's pre-existing untracked manifest was preserved; actual
builds used the disposable exact-source worktree and ended with clean Git
status and owned-manifest cleanup. No Linux-host or installer boot is counted
as a project-kernel pass.

The previous same-host/same-path two-clean-build equality proof remains
bound to its earlier source and path. This phase does not upgrade that proof
to crosspath reproduction. Compiler path remapping also risks separating
`file!()` component registration keys from macro-generated absolute Cargo
metadata literals; that is source analysis, not a newly executed panic.
No component macro, core, OSTD or OSDK change was made for such an experiment.
Remote CI and PR state are read independently after publication; local
successes do not imply GitHub green or a main merge.
