# G1-a native ktest host preparation — 2026-10-19 UTC

The host tools are ready for the product-owned `aster-core` ktest after the new G1 source and derived lock are frozen. This task performed **0 kernel builds and 0 Asterinas guest runs**. It built the local OSDK tool and instantiated QEMU once with its CPUs stopped, then quit.

The complete machine-readable result is [ready.json](ready.json). It records commands, times, hashes, package versions, source binding and remaining preconditions. Tool installation and inspection found no host blocker.

## Tools actually prepared

| Item | Actual installation / result |
| --- | --- |
| Rust | `nightly-2026-07-21`; rustc `1.99.0-nightly (87e5904f5 2026-07-20)`; LLVM `22.1.8` |
| Cargo | `1.99.0-nightly (3efb1f477 2026-07-17)` |
| Components | rust-src, rustc-dev, llvm-tools-preview, rustfmt, host std/Cargo/compiler |
| Bare-metal targets | x86_64-unknown-none; aarch64-unknown-none-softfloat; riscv64imac-unknown-none-elf; loongarch64-unknown-none-softfloat |
| OSDK | Repository `cargo-osdk 0.19.0`, installed with its own unchanged Cargo.lock and `--locked` |
| QEMU | `8.2.2`, Ubuntu package `1:8.2.2+ds-0ubuntu1.18` |
| SeaBIOS | `1.16.3-2`; exact firmware `/usr/share/seabios/bios-256k.bin` |
| Host compilation | build-essential, clang/lld 18.1.3, pkg-config/OpenSSL development headers |
| Other profile helpers | Python 3.12, Git, curl, CA certificates, BusyBox static, cpio |
| vDSO | Original `asterinas/linux_vdso` commit `8af571775a3d3a1df3e84fc9709b9d6b160c771a` |

APT installation completed at **01:09:30.182464 UTC**, exit 0. `dpkg --audit` returned empty output and exit 0. The prior host's package-configuration problem did not occur in this fresh container.

The Rust official dated manifest was verified against its official SHA file. The pinned toolchain installed **01:08:06.551937–01:08:40.903843 UTC**, exit 0. The OSDK tool installed **01:10:20.521109–01:12:00.025676 UTC**, exit 0. Read [fixed-nightly.json](fixed-nightly.json), [apt-install.json](apt-install.json) and [osdk-install.json](osdk-install.json) for complete commands and log bindings.

## Exact handoff command

Run from the existing G1 worktree after its product source and new `aster-core` derived lock are frozen:

```bash
cd /workspace/scratch/499c7902de8e/r10-g1-owner
source /workspace/scratch/499c7902de8e/implementation-tools/g1-env.sh
python3 -I support/build/ktest/run.py \
  --crate aster-core \
  --skip-osdk-install \
  --output /workspace/scratch/499c7902de8e/r10-evidence/g1-a-ktest-01
```

The output directory must be fresh. This command is a handoff instruction and was **not executed by this environment task**. The wrapper owns source verification, the selected derived lock, the kernel target directory, guest receipts and ktest summary checking.

The new local `os-control` dependency requires the product agent's updated derived-lock policy. The old `prepare-locks.py` allowance for only a new OSDK base package must not be applied to that changed graph. No kernel dependency fetch or metadata resolution was performed by this environment task; the first product build may still download packages.

The environment script uses task-specific `RUSTUP_HOME` and `CARGO_HOME`, two Cargo jobs and disabled incremental compilation. It leaves `HOME` and shell profiles unchanged. It intentionally does not export `CARGO_TARGET_DIR`: the product ktest runner sets `kernel/asterinas/target`, while the OSDK tool build used the separate `implementation-tools/osdk-target`.

## QEMU check and profile boundary

This container has no Docker executable and no `/dev/kvm`. QEMU advertises TCG and KVM backends, but KVM is unavailable without its device. The existing downstream profile uses:

- x86_64 q35, TCG, CPU `max`, 1 vCPU, 512 MiB.
- SeaBIOS, direct ELF boot, multiboot protocol.
- Serial logging and `isa-debug-exit`.
- No network, data disks or graphical display.

The host probe created this machine with **`-S`**, without a kernel, and used only QMP capability negotiation, status inspection, KVM inspection and quit. QMP returned **`status=prelaunch`, `running=false`, `enabled=false` for KVM**. QEMU exited 0. The complete argv, replies and timestamps are in [qemu-paused.json](qemu-paused.json) and [qemu-paused-qmp.log](qemu-paused-qmp.log). These observations establish host instantiation only.

This profile does not require GRUB, OVMF, xorriso, GDB or an initramfs. It also leaves `strip_elf=false`; `rust-strip` and the aarch64-only `rust-objcopy` path are not called. Thus cargo-binutils was not installed. These choices are derived from `support/build/ktest/run.py`, `record-qemu.py`, the OSDK build configuration and the x86 default scheme, not assumptions about all supported boot profiles.

The downstream QEMU 8.2.2 path follows the repository's recorded native build. It is not a claim that the upstream Docker QEMU version, KVM, VMX/EPT, SMP, physical desktop hardware or mobile devices have been exercised.

## Tool and source identity

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Installed cargo-osdk | 8,504,760 | `9bf344bb405c6eb96d1bdd1488eaf33d5465ddc8361fea1135ead7130ad65008` |
| QEMU executable | 26,415,624 | `8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854` |
| SeaBIOS firmware | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| Pinned x86_64 vDSO | 28,760 | `27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3` |

The OSDK Cargo.lock SHA is `99a21f72f6a9f1582553b34f06e80f86e539f38e62eab7a0847afd0906e75be3`. All **104 tracked files under the OSDK directory** matched the pre-build snapshot after installation. The six actual local packages named in the tool build log were compared with the recorded Git baseline: cargo-osdk, linux-bzimage-builder, align_ext, ostd-pod, ostd-pod-macros and padding-struct. Those source comparisons also matched. Full maps and the actual package list are in [tool-inspection.json](tool-inspection.json).

The product agent was concurrently implementing G1 in the shared worktree. At post-build inspection, its root workspace manifest contained the separate `os-control` declaration; the exact edit time relative to Cargo's manifest read was not recorded. The manifest diff is preserved in [osdk-root-manifest-concurrent-product-diff.patch](osdk-root-manifest-concurrent-product-diff.patch). This receipt does not claim the whole product checkout remained unchanged.

`OSDK_LOCAL_DEV=1` makes the installed tool refer to this exact local worktree path. Rebuild the tool if that path or the tool source graph changes. Product changes confined to the intended G1 crate are validated and bound by the product runner.

## Resource budget and remaining acceptance

The completed tool inspection observed **25,608,192,000 free bytes** (about 23.85 GiB), an **8 GiB memory cgroup limit**, and an **8-core CPU quota**. Cargo is configured for two build jobs. No kernel Cargo target was populated by this task.

The remaining acceptance is the main agent's actual source-bound `aster-core` build and guest execution with the newly derived lock. A ktest pass must come from that later run's raw QEMU result, serial summary and source/lock receipts. There is no new kernel test result in this environment report.
