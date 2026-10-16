# A01 native build environment investigation

The exact fixed Rust nightly is installed and verified. Native QEMU can instantiate a paused q35 TCG VM. This report does not claim an Asterinas boot. No kernel or build implementation files were modified by this environment sub-agent; only this evidence subdirectory was added during packaging.

## Rust

- Official manifest: `https://static.rust-lang.org/dist/2026-07-21/channel-rust-nightly.toml` returned HTTP 200.
- Saved manifest matches its official SHA256 file (`rust-manifest-verification.log`). It is retained as deterministic `channel-rust-nightly.toml.gz` (mtime=0, no embedded filename). Verify with `gzip -dc channel-rust-nightly.toml.gz | sha256sum` and compare `channel-rust-nightly.toml.sha256`.
- `rustc 1.99.0-nightly (87e5904f5 2026-07-20)`; full commit `87e5904f5eb6398af6b22eac2802c78934260c48`; LLVM 22.1.8.
- `cargo 1.99.0-nightly (3efb1f477 2026-07-17)`.
- Installed components: rust-src, rustc-dev, llvm-tools, native rust-std and cargo/rustc. Installed all four targets declared in upstream rust-toolchain.toml, including the required x86_64-unknown-none.

```sh
export CARGO_HOME=/workspace/scratch/ae1a8cf05419/toolchains/cargo
export RUSTUP_HOME=/workspace/scratch/ae1a8cf05419/toolchains/rustup
export PATH="$CARGO_HOME/bin:$PATH"
rustup toolchain install nightly-2026-07-21 --profile minimal --component rust-src --component rustc-dev --component llvm-tools-preview --target x86_64-unknown-none
rustup target add --toolchain nightly-2026-07-21 riscv64imac-unknown-none-elf loongarch64-unknown-none-softfloat aarch64-unknown-none-softfloat
```

## Native dependencies

```sh
apt-get -o APT::Sandbox::User=root update
mkdir -p /workspace/scratch/ae1a8cf05419/apt-cache/archives/partial
DEBIAN_FRONTEND=noninteractive apt-get -o APT::Sandbox::User=root -o Dir::Cache::Archives=/workspace/scratch/ae1a8cf05419/apt-cache/archives install -y --no-install-recommends qemu-system-x86 qemu-system-common qemu-system-data qemu-utils ovmf busybox-static cpio clang lld pkg-config libssl-dev grub-pc-bin grub-efi-amd64-bin grub-common xorriso exfatprogs e2fsprogs
```

The update completed with exit 0. The install unpacked all required binaries but returned exit 100 because libibverbs1's post-install script cannot open the container's audit interface while adding the rdma group (script exit 82). libibverbs1 remains half configured; librdmacm1t64 and qemu-system-x86 remain unpacked/unconfigured. No account, audit, permissions, or post-install script change was attempted to suppress this failure. Package status is preserved in packages.log/dpkg-audit.log. Package scripts attempted service registration during normal dependency installation; policy-rc.d denied actual service startup.

Before this, plain apt update failed on setgroups/seteuid (exit 100). The first install using root sandbox failed to access the default cache partial directory (owned by unmapped nobody, mode 0700) and was interrupted (130). Its errors are preserved; the subsequent install used a scratch cache without changing default directory permissions.

## Executability checks

- qemu-system-x86_64 8.2.2 loads all dynamic libraries (qemu-dynamic-libraries.log).
- clang 18.1.3, LLD 18.1.3, BusyBox 1.36.1, cpio 2.15 execute.
- `/dev/kvm` is absent. Use TCG, not KVM. Host has 9 vCPU and about 10 GB memory.
- `timeout 3 qemu-system-x86_64 -accel tcg -machine q35 -cpu max -m 256M -smp 1 -S -display none -monitor none -serial none -nic none` instantiated successfully and ended at the expected timeout (124). No guest kernel was run for this check.
- Firmware binaries from seabios 1.16.3 and ovmf 2024.02 are installed; hashes are in firmware.sha256.
- Ubuntu QEMU 8.2.2 differs from upstream development environment QEMU 10.2.1; Ubuntu GRUB 2.12 differs from upstream fork. Native versions must be recorded as actual inputs. Docker and Nix were not installed or started.

## Evidence

Complete installation logs, manifests, package states, tool versions, firmware hashes, and environment smoke are in this directory. A pre-install snapshot and machine-readable report are host-before-package-install.json and environment-investigation.json. The static BusyBox used for early initramfs preparation has SHA256 dbac288c29ba568459550a2da9e7ae0ded6b1fc728ee9fad3044c44e62d6ac14.

## Native host versus upstream development environment

This experiment used disposable Ubuntu 24.04 native host tools and the fixed upstream Rust toolchain. The upstream documented developer entry points remain `make kernel` and `make run_kernel`; host preparation used neither a Docker daemon nor Nix. The native versions and package-configuration failure above are preserved rather than described as equivalent to upstream's pinned Docker/Nix environment. No NixOS installation ISO was downloaded or used by this host preparation; the initial userspace was a small initramfs containing the installed static BusyBox. Refer to the parent build/boot evidence for the actual kernel result.

`apt-sources-snapshot.list` is the standard, authentication-free source configuration used for package installation. Its snapshot is Ubuntu `20260828T000000Z`; `apt-keyring.sha256` identifies the standard Ubuntu archive keyring used by its `signed-by` setting. `commands.json` records the installation commands, environments, exit codes, and related evidence. No .deb archive or executable/toolchain binary is included in this directory; only their SHA256 records are retained.
