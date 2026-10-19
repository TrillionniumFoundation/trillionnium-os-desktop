#!/usr/bin/env bash
# Native, disposable Ubuntu host setup; no NixOS image or Docker daemon needed.
set -euo pipefail
build_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$build_dir/out/setup"
if [[ ${1:-} == --apt ]]; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl git python3 pkg-config libssl-dev \
        clang lld qemu-system-x86 busybox-static gdb binutils
elif [[ $# != 0 ]]; then
    echo "usage: $0 [--apt] (the apt option requires root on a disposable host)" >&2
    exit 2
fi
export PATH="${CARGO_HOME:-$HOME/.cargo}/bin:$PATH"
if ! command -v rustup >/dev/null; then
    curl --fail --location --retry 3 https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init \
        -o "$build_dir/out/setup/rustup-init"
    sha256sum "$build_dir/out/setup/rustup-init" > "$build_dir/out/setup/rustup-init.sha256"
    chmod +x "$build_dir/out/setup/rustup-init"
    "$build_dir/out/setup/rustup-init" -y --no-modify-path --default-toolchain none
fi
rustup toolchain install nightly-2026-07-21 --profile minimal \
    --component rust-src,rustc-dev,llvm-tools-preview \
    --target x86_64-unknown-none,riscv64imac-unknown-none-elf,loongarch64-unknown-none-softfloat,aarch64-unknown-none-softfloat
# OSDK uses rust-strip when keeping a separate DWARF symbol ELF for debugging.
cargo +nightly-2026-07-21 install --locked --version 0.4.0 cargo-binutils
vdso_dir="$build_dir/out/linux-vdso"
if [[ ! -d "$vdso_dir/.git" ]]; then
    git clone https://github.com/asterinas/linux_vdso.git "$vdso_dir"
fi
git -C "$vdso_dir" checkout --detach 8af571775a3d3a1df3e84fc9709b9d6b160c771a
test "$(git -C "$vdso_dir" rev-parse HEAD^{tree})" = 8e0a300d78c2a020ccc79f1253bc27a8301416e6
printf '%s  %s\n' 27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3 \
    "$vdso_dir/vdso_x86_64.so" | sha256sum --check
rustc +nightly-2026-07-21 -Vv
qemu-system-x86_64 --version
echo "ready: support/build/kernel.sh kernel; support/build/kernel.sh run_kernel"
