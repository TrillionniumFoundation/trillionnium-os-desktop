# A01 actual kernel build and boot acceptance

**Passed:** complete fixed Asterinas source → installed dependencies → Rust
kernel build → QEMU → single-CPU initramfs checks → successful guest poweroff.
This is an Asterinas-derived kernel boot, not a Linux host or ISO installer.

- Branch: `agents/A01-asterinas-boot`; PR: <https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5>.
- Starting main: `4b88b637e520f5a8f10d0e280fb9ee450abee8e4`.
- Exact upstream import commit: `7081fb9b34030af47b7a65d4e62a00fcf147de05`.
- Tested build-code commit: `02febdc7316cf945f7002823ad62f617f6d6eedd`.
- Fixed upstream: `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, v0.19.0;
  original tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`.
- Single source root: `kernel/asterinas/`; initial 2,938 files, symlinks, modes,
  Cargo locks, license, and documentation verified against the original tree.
- Only derivative upstream change: 14 added lines in
  `osdk/src/commands/build/mod.rs`, accepting an explicit generated-crate lock.
  A05/A06 process, ioctl, scheduler and OSTD core files are unchanged.

## Commands and environment

```sh
support/build/prepare-host.sh --apt   # disposable Ubuntu host, requires root
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
```

The actual installation commands, custom toolchain paths, Ubuntu snapshot
sources, package status, and failed attempts are retained in `host/`. The
preparation script is the reusable entry point; it was not substituted for
those actual installation records. The native profile uses Ubuntu 24.04,
`nightly-2026-07-21`, rustc `1.99.0-nightly` commit
`87e5904f5eb6398af6b22eac2802c78934260c48`, Cargo `1.99.0-nightly`, and QEMU
8.2.2. Docker and Nix were absent. No NixOS ISO was downloaded or used.

The wrapper invokes upstream `make kernel` and `make run_kernel` using the
small-initramfs overlay. Exact make commands are in `acceptance/{build,boot}/command.sh`;
the full original locked compile is in `build-locked/kernel.log.gz`.
The generated kernel lock has 203 packages and zero external version/source/
checksum drift from the original 234-package root lock. Both OSDK installation
and generated-kernel compilation use `--locked`; see `kernel-lock.json`.

## Real result

| Check | Actual result |
| --- | --- |
| Full Rust kernel source build | Passed; locked compile finished in 1m35s |
| Clean source-commit build/run recheck | Passed at tested code commit above |
| Guest profile | x86_64, q35, TCG, CPU `max`, 1 vCPU, 512 MiB |
| Guest boot markers | OSTD initialized; initramfs ready; `/init` executed |
| Guest checks | x86_64 and exactly one processor |
| Fixed upstream `boot_hello.sh` | `Successfully booted.` |
| Project marker | `TRILLIONNIUM_A01_BOOT_OK` |
| QEMU raw exit | **33**, no timeout; wrapper/make exit **0** |
| Locked smoke runs | **2 passed / 2 run** |
| Initial diagnostic smoke | Failed, raw 65; retained in `failure/boot-02/` |
| OSDK unit tests | **13 passed**, 0 failed, 1 gdb check filtered |
| Relative/missing build-lock paths | Both rejected, with no unpinned fallback |
| Acceptance guard under Python optimization | 5 checks passed, including rejection of panic, wrong exit and missing markers |
| Initramfs recreation and independent cpio reader | Passed |
| Rust format / shell syntax | Passed |
| Root README | **0 bytes** |

The complete successful serial log is `acceptance/boot/serial.log`.
`acceptance/boot/qemu.json` records exact argv, binary hashes, input artifact
hashes, timing and raw status. The actual invoked ELF and initramfs are
retained in `artifacts/`, with their own reproduction instructions.
The retained artifacts were also independently replayed successfully using
those instructions (raw exit 33, full log in `artifacts/replay-serial.log`).
Final acceptance guards use explicit failures rather than removable Python
assertions and recognize Asterinas's `Uncaught panic:` output.

| Actual boot input | SHA256 |
| --- | --- |
| Kernel ELF, 8,297,624 bytes | `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63` |
| Initramfs, 1,107,990 bytes | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| Explicit SeaBIOS | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| QEMU executable | `8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854` |

Upstream deliberately reports `Linux 5.13.0` through uname/proc for ABI
compatibility. That text is not the identity proof. Source/input hashes,
the OSTD/Asterinas boot trace and guest execution establish what booted.

## Handoff and remaining blockers

[Build instructions and the precise A05/A06 interface map](../../README.md)
identify `Process`, trusted launch/exec transitions, `sys_ioctl`, `FileLike`,
`ClassScheduler`, common runqueue operations, and runtime accounting. A00 can
integrate this single baseline; A05/A06 can then work in their owned core paths.

- The observed script-valued `/proc/self/exe` compatibility issue remains in
  core source. Explicit BusyBox applet invocation avoids it in this initramfs;
  [failure analysis](boot-failure-analysis.md) separates source facts from
  the reexec-path inference. The failed log, original init script and original
  initramfs are retained, not relabeled as passed.
- apt returned 100: `libibverbs1` could not create its rdma group because the
  container audit interface is unavailable. QEMU and its dynamic libraries
  were usable and both real boots passed; the package configuration issue
  remains in this host. No group/permission/postinst bypass was used.
- gdb is absent. The full test invocation exited 12 at its gdb availability
  check. A subsequent broad integration invocation was interrupted at its
  separate kernel matrix. Those logs are retained; only the final focused
  13-test unit invocation is reported as passed.
- Native QEMU 8.2.2 differs from the full upstream Docker/Nix environment's
  QEMU 10.2.1. Full kernel regression, conformance and ktest matrices, KVM,
  physical hardware and SMP control are not validated by this smoke.
- HOS2, CapSpace, exec_epoch, ResourceDomain, real budget enforcement,
  Hepta end-to-end behavior, Android and GPU remain outside this A01 result.
  Cross-host bit reproducibility is not claimed; the lock retains that false
  readiness field while recording this native profile as build/boot verified.

`report.json` is the machine-readable result. `evidence.sha256` covers all
retained evidence files except itself.
