# A01 next phase: real kernel regression baseline

The pushed code commit **94139171cdf84f2b920a8cad94801540055c3040** passed two
real upstream kernel crate test sets and another complete-kernel initramfs boot.
The original full OSDK host unit suite still has **one preserved failure**.
No full upstream matrix or HOS2 implementation is claimed.

## Source and environment

- Branch: `agents/A01-asterinas-boot`; PR: <https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5>.
- Integrated actual main: `47afb8229bd3a3ff05077c7b01aac6fa8ef6f956` through merge `a93113e0d1c24d9cb823b9d35ad450efcef609a9`.
- Sole kernel root: `kernel/asterinas/`, complete Asterinas v0.19.0, upstream commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`.
- Tested derivative kernel tree: `9752b3abdc895d435d33cedc3062bf952c78beeb`.
- Fixed `nightly-2026-07-21`; rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48`, Cargo 1.99.0-nightly.
- Native Ubuntu 24.04 x86_64, QEMU 8.2.2, packaged SeaBIOS, explicit TCG CPU `max`, q35, 1 vCPU, 512 MiB, serial, debug-exit. No network or writable data disks.
- Root README: 0 bytes. Upstream licenses, attribution and documentation remain.

Only upstream `osdk/src/commands/build/mod.rs` differs from the imported source.
The original Cargo manifests/locks, OSTD and kernel core process/ioctl/scheduler
sources are unchanged. Input verification checked 118 fixed files successfully.

## Actual guest results

| Committed replay | Reported pass | Fail | Filter | Explicit soft skip | Exercised pass lower bound | Raw QEMU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| OSTD | 221 | 0 | 0 | 3 | 218 | 33 |
| aster-core | 141 | 0 | 0 | 0 | 141 | 33 |
| Total, two crate sets | 362 | 0 | 0 | 3 | 359 | Both 33 |

The three upstream soft skips report VMX unavailable twice and VMX/EPT
invalidation unavailable once. They returned success without exercising those
hardware paths. Counts are for the committed replay, not summed across repeats.
Each selected crate also passed an initial run; initial compilation/installation
logs are retained separately in `initial-kernel-tests/`. Those initial runs
record the precommit HEAD and later-published worktree changes; use
`acceptance/kernel-tests/` for final committed-code provenance and input hashes.

OSTD covers discovered tests in its arch/boot/cpu/io/irq/log/mm/smp/sync/task/
test/util/vm modules. aster-core includes discovered filesystem, VM, process,
thread, syscall, event, net and utility tests. Module names do not establish
SMP enforcement, device-matrix coverage or a HOS2 implementation.

The complete-kernel smoke also passed at the pushed commit: OSTD initialization,
initramfs, guest x86_64/CPU-count checks, unmodified upstream `boot_hello.sh`,
project completion marker and normal poweroff. Raw QEMU=33, make=0, log=0,
wrapper=0. The caller deliberately set `INITRAMFS=off`; the wrapper's explicit
`INITRAMFS=on` preserved its required prerequisite.

## Reproduce

Use a disposable development host and the fixed input setup in
[`../../README.md`](../../README.md):

```sh
support/build/prepare-host.sh --apt
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -I support/build/ktest/run.py
```

These use upstream `make kernel`, `make run_kernel`, and `cargo osdk test`.
The small BusyBox initramfs needs no full NixOS ISO, Docker, Nix, GRUB or OVMF.
The test runner invokes each selected crate without a positional filter,
installs the patched OSDK from source with `--locked`, and applies the separate
fixed test-base locks. Every external dependency identity remains in the
original upstream root lock. OSTD's test lock contains 97 packages; aster-core's
contains 199. The ordinary kernel run lock remains separate at 203 packages.

The final replay used `--skip-osdk-install` to reuse the source-built OSDK
identified by SHA256 in `acceptance/kernel-tests/environment.json`. Its initial
locked installation log remains in `initial-kernel-tests/ostd-initial/`.
`commands.json` records wrapper validation commands and exits. The acceptance
subdirectories retain exact generated Cargo/Make/QEMU commands and environments.
Output destinations must be new directories; existing evidence is rejected.

## Artifacts and logs

| Kernel | Uncompressed ELF SHA256 | Retained artifact |
| --- | --- | --- |
| Full Asterinas | `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63` | `../2026-10-16/artifacts/kernel.elf.gz` |
| OSTD test kernel | `0c0c31c04e20132be755db97d975c4a87fe95fb7c450818c9aed1b05c50af3ea` | `artifacts/ostd.elf.gz` |
| aster-core test kernel | `439e21711aeddec2e412537cc40da55b9207108b940ef78423093bb2de5ef213` | `artifacts/aster-core.elf.gz` |

The full-kernel initramfs SHA256 remains
`86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`;
the identical retained initramfs is in the previous evidence directory.
`artifacts/manifest.json` checks each retained ELF against the actual QEMU
record. Decompress `.elf.gz` before using the recorded `-kernel` argument.
Recorded absolute paths identify this host; reproduce through the wrappers or
substitute the extracted ELF and log destination in the saved QEMU argv.

Complete unmodified serial bytes and exact invocations are in:

- `acceptance/kernel-tests/ostd/guests/guest-001/{serial.log,qemu.json}`
- `acceptance/kernel-tests/aster-core/guests/guest-001/{serial.log,qemu.json}`
- `acceptance/boot/{serial.log,qemu.json,command.sh}`

Nonserial command logs are gzip-compressed with fixed gzip timestamp zero.
From this directory, run `sha256sum -c evidence.sha256` to check all saved files.
Earlier first-boot errors and the script compatibility workaround remain in
`../2026-10-16/`; this phase does not overwrite them.

## Build fixes and host tests

- OSDK lock installation now reads before atomic replacement. Same-path,
  hard-link and missing-input regressions: 3 passed, 14 unrelated units filtered.
- Build runner refuses reused evidence, preserves its shared lock inode,
  installs its temporary manifest without replacement, cleans only its own
  inode, forces initramfs on, and propagates log write failures: 9 tests passed.
- Kernel evidence rejects empty/all-filtered runs, non-33 exits, timeout,
  missing/mismatched raw serial SHA256 and inconsistent target results:
  12 mutation tests passed. Existing real guest records also passed this check.
- Rust formatting, shell syntax and fixed source checks passed.
- Current main contracts: 6 ABI structural tests, 14 sequential specification
  tests and 12 independently generated golden vectors passed. These are host
  contracts, not an implemented kernel wire interface.

GDB 15.1 was acquired with eight verified Ubuntu packages into an isolated
scratch dependency root without executing package postinst scripts. Version
execution and the upstream availability unit passed; ptrace/remote debugging
were not tested. The original complete 14-unit OSDK suite ran without filtering:
**13 passed, 1 failed**, exit 101. The 13 selected non-VM integration cases
passed; 9 other integration cases were not selected. See
[`host-tools/REPORT.md`](host-tools/REPORT.md) and its full command/error logs.

The failed unit is
`daemon::supervisor::tests::stop_all_terminates_daemon_descendants`.
This host exposes ancestor-namespace `/proc` entries while child APIs return
namespace-local PIDs. The test's `/proc/<pid>` predicate can inspect an unrelated
process or miss a live one. The original failed child's host PID was not
observed, so attributing that particular failure solely to the mismatch is an
inference. Three focused diagnostic passes do not replace the full-suite
failure. A single isolated proc-alignment attempt failed before the harness
with `uid_map: Operation not permitted`; it was not retried or bypassed.

A separate production risk remains: waiting for the direct daemon leader and
skipping kill after it is reaped may leave a TERM-ignoring descendant. It was
not fixed or validated here. This guest profile configures no host daemons.

## A00 / A05 / A06 handoff and remaining blockers

The shared source root is ready for A00 integration. After integration, A05
owns process identity/exec/ioctl work and A06 owns scheduler/resource work.
Use the concrete interface map in [`../../README.md`](../../README.md):

- Process: `kernel/core/src/process/process/{mod.rs,init_proc.rs}`, `Process`,
  `spawn_init_process`; exec: `kernel/core/src/process/execve.rs`.
- ioctl: `kernel/core/src/syscall/ioctl.rs::sys_ioctl`,
  `kernel/core/src/fs/file/file_handle.rs::FileLike::ioctl`, actual `Context`.
- Scheduler: `kernel/core/src/sched/sched_class/{mod.rs,time.rs,stop.rs,real_time.rs,fair.rs,idle.rs}`,
  `ClassScheduler`, `PerCpuClassRqSet`, `LocalRunQueue` and runtime accounting.

Those paths are relative to `kernel/asterinas/` and were not modified by A01.
A01 retains build-tool ownership and will not overwrite their core sources.
The two saved crate runs provide an upstream baseline they can compare after
their own changes; they do not establish their future functionality.

Open blockers/limits: the complete OSDK host unit result is not green; its PID
namespace assumptions and daemon lifecycle need follow-up on an appropriate
host. The prior BusyBox script `/proc/self/exe` workaround and native
libibverbs1 configuration restriction remain. Full upstream userspace/device
matrix, VMX/EPT/KVM, controlled SMP, physical hardware and bit-for-bit cross-host
reproducibility remain unverified. HOS2, CapSpace, exec_epoch, ResourceDomain,
Hepta, Android and GPU functionality are not supplied by this A01 change.
