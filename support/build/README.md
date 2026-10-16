# A01: fixed Asterinas source build and QEMU smoke

The single kernel source root is `kernel/asterinas/`. Its initial import is the
complete Asterinas **v0.19.0**, commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`. Upstream documentation, attribution,
and `LICENSE-MPL` are preserved. The project root README stays empty.

The latest kernel-test lifecycle phase reran both actual crate suites:
OSTD 221 and aster-core 141 reported passes, with 3 explicit VMX/EPT soft
skips and an exercised lower bound of 359. It also verified the public boot
with raw QEMU33 after atomic manifest cleanup, and separately cancelled a
real native QEMU paused with `-S` (not a boot/test pass). Host interruption
and replacement-file regressions, complete commands, source/ELF bindings and
remaining generated-manifest writer observations are in
[`evidence/2026-10-16-ktest-lifecycle/REPORT.md`](evidence/2026-10-16-ktest-lifecycle/REPORT.md).
Target cache reuse is explicit; the public boot is not a new empty-target
compilation or a bit reproducibility result.

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
`/usr/bin/busybox`.

The wrapper invokes the **upstream `make kernel` and `make run_kernel` targets**,
with `minimal.mk` replacing their initramfs prerequisite. It temporarily publishes
the minimal OSDK manifest at `kernel/asterinas/kernel/OSDK.toml` and refuses to
replace an existing entry. Its exit cleanup is described below. No full NixOS ISO,
Nix installation, Docker daemon, GRUB image, writable data disk, network,
display, or KVM is needed for this profile.

The profile fixes x86_64, QEMU q35/TCG, CPU model `max`, **1 vCPU**, **512 MiB**,
explicit packaged SeaBIOS, a serial console, and `isa-debug-exit`. It packages
static BusyBox, a small init script, and the unmodified upstream
`test/initramfs/src/boot_hello.sh` into a deterministic newc/gzip initramfs.

Evidence is written to a new directory under `support/build/out/` by default.
`A01_RUN_DIR` selects a destination that must not already exist;
`A01_QEMU_TIMEOUT` sets the timeout in seconds (default 300).
Each run records environment, exact make command, make exit status, initramfs
manifest, full build output, exact QEMU argv, artifact SHA256 values, raw QEMU
exit status, and complete serial output. The smoke passes only with all guest
markers, no panic, and **raw QEMU exit 33**. QEMU exit 65 is guest failure;
OSDK normalizes successful 33 to make exit 0.
The QEMU recorder binds the complete raw serial bytes by SHA256 and size.
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
generated locks and raw guest checks. The latest per-case results are 20/22
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

The `osdk-native-local-tcp-gdb-capture-v2` full matrix passed **22/22**, with
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
OSDK installation also uses its own original `osdk/Cargo.lock` with `--locked`.

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

A01 has not changed those core process/ioctl/scheduler files. A05/A06 can begin
against this source root after A00 integrates the branch; A01 retains build
tooling ownership and will not overwrite their core changes.

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
