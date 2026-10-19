# A01: fixed Asterinas source build and QEMU smoke

The single kernel source root is `kernel/asterinas/`. Its initial import is the
complete Asterinas **v0.19.0**, commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`. Upstream documentation, attribution,
and `LICENSE-MPL` are preserved. The project root README stays empty.

## Current main-f9 build and native regressions — 2026-10-19

Published source `7758ffe294bb0e1eab46e20cba60e8af9d8bcd61` incorporates actual
main `f9e306f76154590e096a42f70ce9de0a7c859e60` as first parent while preserving
A01 history. The complete fixed Rust kernel passed an absent-target **make kernel**
in 189.633 seconds, then a real **make run_kernel** retry with raw QEMU **33**.
Its 8,382,376-byte ELF has SHA256
`4625a5ddf9e82aee2ce01bdfb23127f88a5200565ce2a0645a09e181073ab6d4`;
the frozen first build and actual private loaded copy are identical.

Current real kernel-mode suites passed **OSTD 221** (three VMX/EPT soft skips)
and **aster-core 169**, with zero failures or filters: **390 reported passes,
387 exercised lower bound**. All nine new CPU configuration regressions completed
in the guest. Dependencies reuse the actual October 18 private installation and
were revalidated immediately before this build; no new installation is claimed.

The first boot invocation was refused before make/QEMU because a public manifest
unexpectedly reappeared. Its error and original bytes are retained. A locked,
reversible move preceded the successful retry. The manifest reappeared again,
including after a second move, and remains present in the final observed local
checkout. Its writer is unknown. All 3,014 selected tracked inputs match the
producer; that does **not** establish a clean whole worktree. Existing build
refusal and cleanup guards remain unchanged.

The [current report](evidence/2026-10-19-mainf9/REPORT.md) contains actual artifacts,
full serial logs, dependency/source receipts and failures, with the
[A00/A05/A06 handoff](evidence/2026-10-19-mainf9/HANDOFF.md). Independent source
and native evidence reviews passed 25 and 53 checks respectively. The reporting
commit is evidence-only, not a separately rebuilt native producer. Earlier
results below retain their own source identities and acceptance boundaries.

## Current main cold build, boot and kernel tests — 2026-10-18

Actual main `01225ab0a20a9f25dd8313a7fad7652dd9154e30` is the first parent of
published source producer `b39e154ae5a1e9853f57e23f9bee84712ee8ef7e`; the ordinary
merge preserves the existing A01 branch history. This run freshly installed the
fixed native dependencies, completed an absent-target **make kernel** in 197.265
seconds, and booted the resulting full Rust kernel with **make run_kernel**.
QEMU q35/TCG used 1 vCPU, 512 MiB and a 1,107,990-byte initramfs; raw exit was 33.
The complete ELF is 8,283,136 bytes, SHA256
`6518b6472efbc599498b71550ef9761f6f20e74814db0c9a81bff101ab036e55`.
The frozen first-produced ELF and actual loaded private copy are byte-identical.

Both complete current kernel-mode suites ran: **OSTD 221** reported passes with
three VMX/EPT capability soft skips, and **aster-core 160** passes with no skips,
failures or filtering. Combined: 381 reported, **378 exercised lower bound**.
Main's zombie final-charge and parity regressions are included. The current
host build gate passed 81/81; all recorded native source inputs remain equal to
the producer. A05/A06 core, OSTD and the actual external ABI equal main012.

The first boot attempt was refused **before QEMU** after an unexpected untracked
OSDK manifest appeared. Its original error/bytes/stat were preserved, and the
file was reversibly quarantined under the native lock before the successful
retry. Another appearance after ktests was also preserved and quarantined.
The writer remains unidentified; the existing refusal/cleanup guards were not
changed. The after-native source audit observed a clean worktree and no public
manifest, without claiming that it stayed clean throughout execution.

The [current report](evidence/2026-10-18-main012-current/REPORT.md) includes all
commands, complete serial logs, actual artifacts, fixed dependency installation,
source closure, failure evidence and [A00/A05/A06 handoff](evidence/2026-10-18-main012-current/HANDOFF.md).
Its publication commit is evidence-only and is not a separately rebuilt native
producer. Older results below keep their own source identities and scope.

## Earlier main sync and source bridge — 2026-10-18

Main `4339acedd2d433f838c7b5fd445709c539043a77` is incorporated by ordinary
merge `d9ccc523141ec46baef2a0dfe0afe49e4f97f523`. Its updated A02 gate
passed 13/13 checks: 78 Rust tests, 62 Python tests in each separate mode,
and all 20 compiled mutation checks. The [sync report](evidence/2026-10-18-main4339-sync/REPORT.md)
preserves the raw gate output and an independent source bridge.

All 2,941 kernel files, the actual external ABI and build programs are
identical to the successful native producer `40c901c6` below. Of the same
3,010 selected inputs, only this README and upstream-lock reporting/history
fields differ; all 118 fixed-input checks produce the identical receipt.
No new native execution is claimed for d9ccc523 or the following evidence
commit. At that source-bridge snapshot, the latest actual build/boot was 40c901c6
and the kernel regression was c22891b. The [A00/A05/A06 handoff](evidence/2026-10-18-main355-followup/HANDOFF.md)
still matches the integrated owner sources. The late manifest entry is
absent after quarantine, but its writer remains unidentified.

## Rebuild after main ABI update — 2026-10-18

Main advanced during the first pipeline to
`3551e1e0e017e2973da7e2b8ab811ece25c258c0`, changing the external ABI
compiled by the kernel. Published producer
`40c901c6e189058bdd6f42bb43bf46b3bbcf8ffa` merges that main unchanged and
passed a new incremental **make kernel → make run_kernel** (raw QEMU33).
Its complete ELF is 8,303,048 bytes, SHA256
`1eb66b33baef6b338c232598d25f743dc83526a2715811b430e5a7208e249ecd`.
The existing A02 ABI gate passed 13/13 checks, 78 Rust tests and 20 compiled
mutation checks, including strict Clippy and bare-target no_std.

The [main integration report](evidence/2026-10-18-main355-followup/REPORT.md)
and [current handoff](evidence/2026-10-18-main355-followup/HANDOFF.md) retain
the new source/ABI fingerprints and actual loaded artifacts. The earlier
cold build and 374 reported kernel tests below keep their original c22891b
scope; those kernel tests were not rerun on the ABI update. A post-boot
untracked OSDK manifest with a different inode was preserved and manually
quarantined under the native workspace lock. Its unknown writer remains
an environment issue; raw nonempty Git status and the quarantine receipt
are retained, without changing the successful boot evidence.

## Initial main validation — 2026-10-18

The current run starts from remote main `b7a8388726b67394398431e74d2e5d2079ff375f`
and preserves the existing A01 history through an ordinary merge. Published
producer `c22891b593f77c98ff4ea94d7aecb54f32222651` completed an absent-target
**make kernel → make run_kernel** with the fixed nightly, a small initramfs,
1 vCPU and 512 MiB under QEMU TCG. Both make commands returned 0 and the
actual full-kernel guest returned raw **33**. Its complete boot ELF is
8,310,560 bytes, SHA256
`208caf5126c94f660292aacd36040ec62c9d317b116b9a861634f08cb02cd8f3`.
The source-built first ELF and the actual loaded private copy are identical.

OSTD/core ktests at that producer reported **374 passes**, zero failures or
filtered tests; three VMX/EPT capability skips leave a **371 exercised lower
bound**. Current core passed all 153 tests. The host build gate passed 86
checks on the pre-commit merge worktree with its 13 recorded inputs equal to
the producer; OSDK host units at the producer passed 45 with one existing
ignored transport probe. A05/A06 core, OSTD and the external ABI retain the
exact bytes of the fetched main. No dedicated A05 ioctl or A06 final-debit
lifecycle/SMP acceptance is claimed by this minimal boot.

[The current report](evidence/2026-10-18-current-main/REPORT.md) links the full
serial logs, exact QEMU command, dependency installation evidence, compressed
loaded artifacts and before/after source receipts. The [owner handoff](evidence/2026-10-18-current-main/HANDOFF.md)
lists concrete Process, ioctl and scheduler interfaces. The report/lock/evidence
publication follows the tested producer; it is not claimed as a separately
rebuilt final HEAD. All earlier results below retain their own producer and
acceptance scope.

## Earlier validation snapshots

The 2026-10-17 project-cloud validation completed the ordinary developer
pipeline at published code `d879a9d2ffae8d0eb0df441370da54f9e3a38431`:
an absent target, `make kernel`, then `make run_kernel`, a full initramfs boot
and raw QEMU exit **33**. The complete boot ELF is 8,258,112 bytes, SHA256
`c49ad7da1c76c1f559d065ac3f8cbcbad407242dda54f1ed00028f02d5c2413d`.
The first build's frozen ELF has the same bytes. The boot stage reused that
newly built target; it is one cold-build/boot pipeline, not two cold builds.

Separately, opt-in schema4 at `4e8c7083575cec69efabe8d2250dfdd040c8dee8`
completed two absent-target builds in different actual source roots. Both
full kernels booted with raw33; their complete ELF, initramfs and BIOS bytes
are identical. The ELF SHA256 is
`8c540288c6af2a1a97121031643c1af4c4db395d7e8b4082d6edc4604449849a`.
This establishes same-host cross-path reproduction for that explicit profile.
Cross-host reproduction and a complete immutable host/container lock remain
open. Earlier component-path panics, unequal A2/B2 ELFs and A3's producer
ordering failure remain archived, with their actual commands and errors.

The final TCP/GDB OSDK matrix at `d879a9d2...` passed **22/22**, zero failures
or blocked cases, eleven actual guests at raw33 and one VMX soft skip.
Coverage exported 5,692 functions with execution counts. Each case owns its
generated OSDK directory, and QEMU loads private kernel/BIOS copies; coverage
also uses a private symbol ELF. All 23 input mappings were preserved.
The correct-source-root OSTD/core run at `d895dd73...` reported **362**
passes, with three VMX/EPT soft skips and a **359** exercised lower bound.
Host-only snapshot tests passed 152 checks in each Python mode; they are
separate from the real VM results.

Native tools were restored from 57 signed Ubuntu packages into a private
prefix, together with the exact fixed Rust nightly. The failed system APT
attempt is retained; no sandbox or capability restrictions were weakened.
The minimal profile needs no Docker/Nix daemon or full NixOS installer ISO.
Private BIOS and QEMU data-directory selectors fix the cloud's packaged-ROM
paths without changing host firmware. Exact environment, dependency checks,
commands, full serial logs, artifacts, failures and remaining work are indexed
in [the cloud closure report](evidence/2026-10-17-cloud-closure/REPORT.md).

Actual main `40ca002fac0726b366726d3353916637b29adeae` was merged through
`5fffe3394dd562ad88fda7c37edc258cf9b56387`. Its control model passed 129 tests
in each backend; the earlier exact `8f3bb49...` ABI validation passed all 13
runner checks, including strict fixed-nightly Clippy. The previously pending
A02 helper fix is now adopted in main. The final source bridge checks the
exact Git inputs of these historical host runs; it does not claim to rerun
them or establish native HOS2 enforcement. Kernel core files remain owned by
A05/A06, and G1/G2, KVM/VMX, default host AF_UNIX, cross-host/immutable
reproduction and the unidentified workspace writer remain open.

Earlier accepted complete-kernel Rust-entry debugging, same-path repeatability
and build-environment results remain in the
[previous cloud report](evidence/2026-10-16-blocker-closure/REPORT.md),
[clean-repeatability report](evidence/2026-10-16-clean-repeatability/REPORT.md)
and [build-environment report](evidence/2026-10-16-build-environment/REPORT.md).
They retain their own precise producer commits and acceptance scope.

## Build and boot

On a disposable native **Ubuntu 24.04 x86_64** development host:

```sh
# --apt installs host build tools and QEMU; it requires root.
support/build/prepare-host.sh --apt
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
```

Without `--apt`, preparation installs the exact Rust toolchain and fetches the
fixed vDSO dependency and cargo-binutils 0.4.0 with its published lock, assuming
host packages already exist. `rust-strip` is needed for the separate stripped
debug boot ELF. If Rust is already
installed in a nonstandard location, export `CARGO_HOME`, `RUSTUP_HOME`, and its
`bin` directory in `PATH`. `VDSO_LIBRARY_DIR` and `A01_BUSYBOX` may point to
existing verified inputs; the defaults are `support/build/out/linux-vdso` and
`/usr/bin/busybox`. For private-prefix installations, set `A01_QEMU_BIOS` to
the verified SeaBIOS file and `A01_QEMU_DATA_DIR` to the packaged QEMU data
directory. The latter supplies `-L` for ROM lookup. Also put the native tools
and Cargo in `PATH` and configure their library paths as recorded in the
cloud report; these selectors do not install packages or change host firmware.

The wrapper invokes the **upstream `make kernel` and `make run_kernel` targets**,
with `minimal.mk` replacing their initramfs prerequisite. It temporarily publishes
the minimal OSDK manifest at `kernel/asterinas/kernel/OSDK.toml` and refuses to
replace an existing entry. Its exit cleanup is described below. No full NixOS ISO,
Nix installation, Docker daemon, GRUB image, writable data disk, network,
display, or KVM is needed for this profile.

Every normal kernel, run, and GDB invocation installs the locked OSDK from
this checkout into its new evidence directory's private `osdk/` prefix.
Upstream `cargo osdk` selects that binary through `PATH`; the shared Cargo
home's `bin` entry is explicitly retained after the private bin directory to
prevent Cargo's default home-bin precedence from selecting a different SDK.
`CARGO_HOME`, when set, must be an absolute path; otherwise `HOME` must be
absolute for the default `.cargo/` location. The selected Cargo home path
must have no `..` components, so its explicit bin
entry matches Cargo's lookup path. The dependency cache and
Rustup toolchain stay shared. The environment log records the installation and lookup paths,
and `osdk/cargo-osdk.sha256` records the installed binary's bytes. The profile
does not update or consume the global installed `cargo-osdk`; a newer global
binary or another checkout's installation cannot change the selected SDK.

The profile fixes x86_64, QEMU q35/TCG, CPU model `max`, **1 vCPU**, **512 MiB**,
explicit packaged SeaBIOS, a serial console, and `isa-debug-exit`. It packages
static BusyBox, a small init script, and the unmodified upstream
`test/initramfs/src/boot_hello.sh` into a deterministic newc/gzip initramfs.

The wrapper records and clears inherited `MAKEFLAGS`, `MFLAGS`,
`GNUMAKEFLAGS`, `MAKEFILES`, `MAKEOVERRIDES` and `MAKELEVEL` before invoking
GNU make. Dry-run, touch, ignore-error modes and caller-supplied makefiles
must not turn a skipped or failed kernel recipe into a successful build.
GNU make establishes normal recursion state for its own children. This is
the fixed profile's environment contract, not a sandbox for untrusted tools.

Unset `CARGO_ENCODED_RUSTFLAGS` before invoking the normal kernel, ktest,
debug or integration entry, including when its current value is empty. Cargo gives its presence
priority over the `RUSTFLAGS` that OSDK supplies for kernel linking and CPU
configuration. These entries reject it before creating output or taking a
workspace lock, so the same command and output path can be retried after
unsetting it. Ordinary `RUSTFLAGS` continue to follow upstream OSDK behavior.

Evidence is written to a new directory under `support/build/out/` by default.
`A01_RUN_DIR` selects a destination that must not already exist;
`A01_QEMU_TIMEOUT` sets the timeout in seconds (default 300).
Each run records environment, exact make command, make exit status, initramfs
manifest, full build output, exact QEMU argv, artifact SHA256 values, raw QEMU
exit status, and complete serial output. The smoke passes only with all guest
markers, no panic, and **raw QEMU exit 33**. QEMU exit 65 is guest failure;
OSDK normalizes successful 33 to make exit 0.
The QEMU recorder binds the complete raw serial bytes by SHA256 and size.
It exclusively creates three read-only input snapshots in a fresh private
`artifacts-*` directory and passes those actual paths to QEMU. `qemu.json`
retains the original arguments and each input's source path/stat/hash alongside
the loaded snapshot path/stat/hash. Stable-FD source checks and pre/post-run
snapshot verification fail on detected changes; they do not attribute an
external writer or provide a sandbox against the same user.
Fresh runs also verify the recorded kernel, initramfs and BIOS bytes against
their live paths. For offline archive checks, use `check-boot.py DIR` without
`--live-artifacts`; historical records without a serial digest require the
checker from their recorded acceptance commit, not a retroactively added hash.
The wrapper rejects incomplete log capture, forces its initramfs prerequisite
on, and shares a persistent workspace lock with the kernel-test runner.
A busy lock is rejected before creating explicit or default evidence directories,
so the same command can be retried after the current owner exits. Its temporary
manifest is installed without replacing an existing file, and
FD 8 pins its owned regular-file inode before publication, including when a
signal arrives immediately after the atomic link operation. Cleanup atomically
moves the public entry into a fresh private directory before inspecting it.
It deletes only the captured owned inode. A foreign regular file, symlink or
directory is restored with `renameat2(RENAME_NOREPLACE)`. If restoration is
unavailable or another writer has filled the public name, the captured entry
is retained under `.a01-manifest-custody-*` with its recovery path reported.
Cleanup failure makes an otherwise successful invocation fail; an earlier
nonzero build status is preserved. `manifest-cleanup.json` records the outcome
and helper source hash. The workspace lock stays held throughout cleanup.

Standalone calls supervise one worker process group through interruption and
completion. SIGINT/SIGTERM stop that group before reaping its waitable leader;
the first cancellation returns 130/143. The Rust-entry debug helper owns its
worker group directly, so it explicitly selects the internal worker route
instead of starting a second supervisor session. This route selects cleanup
ownership and does not provide authorization.

For concurrent development or a workspace that restores generated files, use
a disposable Git worktree at the exact source commit and a target directory
inside that worktree. This isolates generated Cargo/OSDK state while retaining
the same single vendored kernel source and upstream pin:

```sh
git worktree add --detach /absolute/new/build-worktree "$(git rev-parse HEAD)"
cd /absolute/new/build-worktree
export CARGO_TARGET_DIR="$PWD/kernel/asterinas/target"
support/build/kernel.sh run_kernel
```

Each worktree retains the existing refusal to overwrite a pre-existing
`kernel/OSDK.toml`. Preserve and inspect such a file before another attempt;
the wrapper does not guess that an existing manifest is safe to remove.
An external writer can still replace files inside a worktree. Custody protects
the captured entry; it does not keep the public pathname continuously occupied
or prevent a new entry from appearing there while cleanup runs.

## Kernel-mode regression tests

```sh
# Runs both full crate test sets inside separate QEMU guests.
python3 -I support/build/ktest/run.py

# Or run a single crate.
python3 -I support/build/ktest/run.py --crate ostd
python3 -I support/build/ktest/run.py --crate aster-core
```

These use the same fixed CPU, memory and firmware profile. They build real
upstream test kernels with separate locks derived from the original root
lock, retain complete serial logs, and reject empty or filtered full runs.
See `ktest/README.md` for lock preparation, focused filters, output selection
and reuse of the source-built OSDK.

For the separate OSDK tooling and example-kernel integration profile:

```sh
python3 -I support/build/osdk-integration/run.py --output NEW_INTEGRATION_DIR
```

See `osdk-integration/README.md` for its isolated harness adaptations, pinned
generated locks and raw guest checks. The historical default-UNIX results are 20/22
passed, with the original UNIX GDB and coverage cases failing because this
execution environment rejects UNIX socket creation. One passing hypervisor
case explicitly takes its VMX-unavailable fallback. The full-run failure and
exact retries are retained in `evidence/2026-10-16-native-integration/`; they
are distinct from complete Asterinas kernel acceptance. That phase also
reran OSTD/aster-core with the fixed OSDK and retained 221/141 reported passes
and the same 3 soft skips (359 exercised lower bound).

For the explicit loopback TCP profile with GDB-assisted coverage capture:

```sh
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb --output NEW_TCP_CAPTURE_DIR
```

The earlier `osdk-native-local-tcp-gdb-capture-v2` full matrix passed **22/22**, with
one explicit VMX soft skip and eleven actual QEMU guests returning raw 33.
Coverage capture stops before the architecture poweroff path, exports the
announced initialized data, detaches and requires the original guest exit.
The fixed LLVM tools parsed 5,696 functions with nonzero execution counts.
A later fatal-panic rejection guard passed its focused checks and a fresh
coverage guest. These are separate results from the retained default UNIX
failures and the initial TCP-only coverage failures. Their exact source
snapshots and logs are in `evidence/2026-10-16-debug-coverage/osdk/`.
The subsequent review fixes were tested again as a complete **22/22** run at
`f473a2ccc8dfeaed1223e8478a19c79c90b323e4`, including the fatal-panic guard,
finite Cargo argument parser, owned-session cleanup, and private connected
monitor FD. The host suite passed 38 tests with one ignored QEMU transport
test; that transport test was separately run successfully and is not a kernel
boot. Full kernel Rust-entry debugging also passed again with raw QEMU 33.
See `evidence/2026-10-16-review/REPORT.md` for this phase and retained failures.

The final cloud matrix after the per-case target and private-input fixes
passed all 22 cases in one execution at `d879a9d2...`, with eleven raw33
guests and one VMX soft skip. All actual private boot inputs and the coverage
symbol ELF are retained in
[`native-cloud-final`](evidence/2026-10-17-native-cloud-final/README.md).
The earlier 20/22 cloud run, missing offline dependencies, wrong-source-root
OSDK retry and coverage recovery remain in
[`native-cloud-before`](evidence/2026-10-17-native-cloud-before/README.md).
That initial run lost one original example ELF to reuse; its original serial
and hash are retained, and it is not retroactively treated as a fully
preserved-input pass. The final runner captures inputs before QEMU's version
probe and verifies private copies before and after execution.

The independent A04 same-ELF diagnostic is documented in
`linux-guest/README.md`. Its 28 fixed workloads are separate from OSDK tests;
read their actual pass/failure/timeout counts before making compatibility
claims. A Linux-host reference pass does not establish a new-kernel pass.

## Full kernel Rust-entry debugging

```sh
python3 -I support/build/debug/run.py --output NEW_KERNEL_DEBUG_DIR
```

This source-builds the full kernel through the upstream developer target,
retains its DWARF symbol ELF, passes an owned loopback listener into QEMU,
breaks at `__ostd_main`, checks the actual PC, and detaches. The complete
initramfs boot must then pass the ordinary live checker with raw QEMU 33.
The real run displayed a Rust source line and boot call stack before passing
that boot check. See `debug/README.md` for dependencies and deadlines, and
`evidence/2026-10-16-debug-coverage/kernel-debug/` for the complete successful
run and both preceding failures.

The recorded next-phase runs report OSTD **221 passed**, aster-core **141
passed**, and zero failures. Three OSTD tests returned success after explicitly
soft-skipping VMX/EPT paths unavailable under TCG; the exercised pass lower
bound is **359**, not 362. These results cover those two kernel crates on
one vCPU; they do not establish the full upstream userspace/device matrix.

## Dependency and source integrity

```sh
python3 support/build/verify-source.py
```

This checks the fixed commit/tree/toolchain contract, upstream Cargo manifests
and locks, license, root Makefile/OSDK manifest, and the empty project README.
`--pristine` checks every upstream file and Git mode against the original tree;
it passes at import commit `7081fb9b34030af47b7a65d4e62a00fcf147de05`.
Later intentional derivative edits are expected to fail that strict comparison.

Derivative changes are confined to OSDK's host build tooling. Its
`osdk/src/commands/build/mod.rs` accepts `OSDK_CARGO_LOCK` and passes `--locked`
to the generated-crate build. The daemon supervisor also cleans its original
process group before reaping the leader; its regression fixtures use a TCP
lease rather than interpreting namespace-local PIDs through `/proc`.
The boot ELF is published through an independent temporary file, so QEMU's
x86 ELF-header conversion cannot modify the original Cargo symbol ELF through
a hard link. VSC launch configuration points to that actual symbol ELF and
quotes target paths. Debugger integration waits are bounded.
Lock installation uses a temporary file and atomic replacement, including
when the supplied lock is the destination itself or a hard link to it.
The generated OSDK base crate is a separate Cargo workspace; upstream's root
lock alone does not freeze it. `minimal/Cargo.lock` is normalized from that
fixed root lock: 203 packages, with no external version/source/checksum drift.
OSDK installation uses its approved derived host `osdk/Cargo.lock` with
`--locked`. The exact host manifest and lock add `command-fds = "=0.3.2"`
and four locked transitive packages to preserve child descriptors without
local unsafe Rust. All 154 original package identities/checksums remain;
the complete kernel's original `Cargo.lock` and Rust toolchain are unchanged.
`verify-source.py` reports the two exact approved host derivations separately
from the fixed upstream Git identities and refuses other manifest/lock bytes.

The native smoke uses QEMU 8.2.2; upstream's full development image uses QEMU
10.2.1 and additional firmware/GRUB tooling. This is a recorded native-host
profile, not equivalence to the full upstream container matrix. Build inputs
and successful output hashes are retained; bit-for-bit cross-host
reproducibility is not claimed.

BusyBox comes from Ubuntu's `busybox-static` package (GPL-2.0); preserve its
package/source attribution when distributing the generated initramfs. The
vDSO comes from `asterinas/linux_vdso` commit
`8af571775a3d3a1df3e84fc9709b9d6b160c771a`, as fixed by upstream. Its README
attributes the x86_64 image to Linux 6.2.10. These userland/build inputs do not
replace or boot a Linux host kernel as the project kernel.

Focused host regressions for the workspace lease, cancellation and approved
host-tool inputs (repeat with `-O` after `-I` for optimized Python):

```sh
python3 -I support/build/debug/test_workspace_lock.py
python3 -I support/build/debug/test_worker_cleanup.py
python3 -I support/build/repro/test_lifecycle.py
python3 -I support/build/osdk-integration/test_fixed_root_cleanup.py
python3 -I support/build/tests/test_source_inputs.py
```

These exercise host tooling and refusal paths; real kernel/guest results are
reported separately. Integration scratch cleanup removes contents through its
owned directory descriptor on success, failure and cancellation, preserving
the empty outer directory and any foreign pathname replacement.
Kernel session owners allow up to two seconds for worker EXIT cleanup before
the final group kill and leader reap. Cleanup beyond that bound may leave an
owned manifest; a later invocation refuses to overwrite it and preserves the
failure for inspection. This is bounded process cleanup, not unconditional
recovery from an arbitrary host delay.

## Opt-in cross-path reproduction

```sh
python3 -I support/build/repro/run.py --checkout /absolute/source-worktree \
    --profile-root /absolute/stable-profile --output /absolute/new-evidence
```

Use the same profile root and two distinct clean worktrees with absent kernel
targets. Schema4 projects compiler/component paths and binds local Cargo
metadata to recorded source/compiler/producer descriptors. It deliberately
uses one Cargo job because this fixed Cargo can pipeline consumer metadata
before its producer completion receipt exists. The strict producer check stays
enabled. Ordinary builds retain their normal upstream flags and job count.
See [the profile documentation](repro/README.md) and
[the actual complete-kernel comparison](evidence/2026-10-17-repro-cross-path/README.md).
This is the one vendored implementation built from separate Git worktrees;
no alternate OSTD-only kernel or duplicated implementation is maintained.

## A00 / A05 / A06 handoff

All paths below are relative to `kernel/asterinas/`:

| Owner / purpose | Actual source interface |
| --- | --- |
| A05 process identity | `kernel/core/src/process/process/mod.rs`: `Process`, `new`, `pid`, `start_time`, `tasks`, `run` |
| A05 trusted launch | `kernel/core/src/process/process/init_proc.rs`: `create_init_process`, `create_init_task`, `spawn_init_process`; final `process.run()` |
| A05 exec transition | `kernel/core/src/process/execve.rs`: `do_execve`, `do_execve_no_return`, VMAR/credentials transition and CLOEXEC handling |
| A05 ioctl entry | `kernel/core/src/syscall/ioctl.rs`: `sys_ioctl(raw_fd, cmd, arg, &Context)` |
| A05 file transport | `kernel/core/src/fs/file/file_handle.rs`: `FileLike::ioctl`; `fs/file/file_table.rs` |
| A06 common scheduler | `kernel/core/src/sched/sched_class/mod.rs`: `ClassScheduler`, `PerCpuClassRqSet`, `LocalRunQueue` |
| A06 scheduler classes | `kernel/core/src/sched/sched_class/{stop,real_time,fair,idle}.rs` |
| A06 runtime accounting | `kernel/core/src/sched/sched_class/time.rs`: runtime/TSC conversion; audit IRQ-disabled lock order |
| Shared OSTD boundary | `ostd/src/task/scheduler/mod.rs`; changes require A00 coordination |

`sys_ioctl` obtains an owned file reference and drops the file-table borrow
before dispatch. `Context` provides the actual process/thread/task and user
copy interfaces. These are integration points; HOS2, CapSpace, exec_epoch,
stable resource identity, and ResourceDomain are **not implemented by A01**.
`Process::start_time` is Jiffies and is not a complete generation identity.
Budget enforcement must cover the common scheduler path and all controlled
classes, rather than modifying only the fair scheduler.

A01 has not changed those core process/ioctl/scheduler files. A05/A06 have
already started their owner branches against this single source root. A01
retains build tooling ownership and will not overwrite their core changes.
The [current handoff](evidence/2026-10-17-cloud-closure/HANDOFF.md) records
exact build/test producers and the remaining owner work for A00 integration.

Real smoke results, failures, and host package limitations are in
`evidence/2026-10-16/`. The BusyBox applet workaround avoids an observed script
`/proc/self/exe` compatibility issue; that core issue remains for A05 to assess.
The next-phase evidence is in `evidence/2026-10-16-next/`. It includes the two
kernel crate runs and the original OSDK host unit result: 13 passed, one
daemon-descendant test failed. GDB availability and 13 selected non-VM
integration tests passed. The host has mismatched PID and `/proc` namespaces;
focused diagnostic passes do not supersede the original failure. Follow-up
daemon fixes and their actual results are recorded separately in
`evidence/2026-10-16-daemon/`. A05/A06 can use the saved kernel crate results
as an upstream baseline.
The subsequent `evidence/2026-10-16-boot-binding/REPORT.md` records the serial
binding and symbol-ELF fixes, complete 28/28 OSDK host units, and a fresh full
Asterinas `make kernel` / `make run_kernel` boot with raw QEMU exit 33. It also
retains the manifest signal reproducer, an unexplained replacement inode from
one real build, and the explicit missing-log limitation from an initial
missing-GDB test attempt.

The host supervisor uses `waitid(WNOWAIT)` to observe a leader without
releasing its PID, kills remaining members of that original group, then reaps
and permanently disarms the entry. `ECHILD` also disarms group signalling.
This assumes OSDK is the sole reaper of its managed children, with SIGCHLD
left waitable rather than auto-reaped. Descendants that actively leave the
group are outside this boundary. The new host unit
fixtures require Bash with `/dev/tcp` and local loopback TCP sockets. Run the
complete derived OSDK unit suite with the fixed toolchain and GDB available:

```sh
cargo +nightly-2026-07-21 test --manifest-path kernel/asterinas/osdk/Cargo.toml \
    --locked --bin cargo-osdk -- --test-threads=1
```

The full upstream matrix, HOS2, SMP control, physical hardware, Android, GPU,
and Hepta end-to-end behavior remain untested. Cross-host reproducibility
remains open.
