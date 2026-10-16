#!/usr/bin/env bash
# Build/run the complete pinned kernel through the upstream developer targets.
set -euo pipefail
build_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd "$build_dir/../.." && pwd)
kernel_dir="$project_dir/kernel/asterinas"
target=${1:-kernel}
case "$target" in kernel|run_kernel) ;; *) echo "usage: $0 [kernel|run_kernel]" >&2; exit 2 ;; esac
export PATH="${CARGO_HOME:-$HOME/.cargo}/bin:$PATH"
export RUSTUP_TOOLCHAIN=nightly-2026-07-21
export CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS:-2}
export CARGO_NET_GIT_FETCH_WITH_CLI=true
export RUST_LOG=info
export OSDK_CARGO_LOCK="$build_dir/minimal/Cargo.lock"
export VDSO_LIBRARY_DIR=${VDSO_LIBRARY_DIR:-$build_dir/out/linux-vdso}
run_dir=${A01_RUN_DIR:-$build_dir/out/$(date -u +%Y%m%dT%H%M%SZ)-$target}
mkdir -p "$run_dir"
run_dir=$(cd "$run_dir" && pwd)
exec 9>"$build_dir/out-kernel.lock"
flock -n 9 || { echo "another A01 build is using the kernel workspace" >&2; exit 1; }
trap 'rm -f "$kernel_dir/kernel/OSDK.toml" "$build_dir/out-kernel.lock"' EXIT
if [[ -e "$kernel_dir/kernel/OSDK.toml" || -L "$kernel_dir/kernel/OSDK.toml" ]]; then
    trap - EXIT
    echo "kernel/OSDK.toml already exists; refusing to replace it" >&2
    exit 1
fi
python3 "$build_dir/verify-source.py" > "$run_dir/source-inputs.json"
{
    date -u --iso-8601=seconds
    uname -a
    cat /etc/os-release
    rustc -Vv
    cargo -Vv
    rustup component list --installed
    rustup target list --installed
    make --version | head -1
    gcc --version | head -1
    qemu-system-x86_64 --version || true
    git -C "$project_dir" rev-parse HEAD
    git -C "$project_dir" status --short
    printf 'CARGO_BUILD_JOBS=%s\nVDSO_LIBRARY_DIR=%s\n' "$CARGO_BUILD_JOBS" "$VDSO_LIBRARY_DIR"
    sha256sum "$VDSO_LIBRARY_DIR/vdso_x86_64.so"
    sha256sum "$OSDK_CARGO_LOCK"
    for tool in docker nix-build; do command -v "$tool" || true; done
    if [[ -e /dev/kvm ]]; then ls -l /dev/kvm; else echo '/dev/kvm absent; explicit TCG selected'; fi
} > "$run_dir/environment.log" 2>&1
python3 "$build_dir/minimal/prepare-initramfs.py" \
    --upstream "$kernel_dir" --busybox "${A01_BUSYBOX:-/usr/bin/busybox}" \
    --output "$run_dir/initramfs.cpio.gz" --manifest "$run_dir/initramfs-manifest.json"
cp "$build_dir/minimal/OSDK.toml" "$kernel_dir/kernel/OSDK.toml"
export A01_QEMU_EVIDENCE="$run_dir/qemu.json"
if [[ "$target" == run_kernel ]]; then rm -f "$kernel_dir/kernel/qemu.log"; fi
command=(make -C "$kernel_dir" -f Makefile -f "$build_dir/minimal.mk" "$target"
    "CARGO_OSDK=${CARGO_HOME:-$HOME/.cargo}/bin/cargo-osdk"
    "A01_INITRAMFS=$run_dir/initramfs.cpio.gz"
    "A01_QEMU_WRAPPER=$build_dir/record-qemu.py" TARGET_ARCH=x86_64 SMP=1 MEM=512M
    ENABLE_KVM=0 BOOT_PROTOCOL=multiboot AUTO_TEST=none)
printf '%q ' "${command[@]}" > "$run_dir/command.sh"
printf '\n' >> "$run_dir/command.sh"
set +e
"${command[@]}" 2>&1 | tee "$run_dir/$target.log"
result=${PIPESTATUS[0]}
set -e
printf '%s\n' "$result" > "$run_dir/make-exit-code.txt"
if [[ "$target" == run_kernel && -f "$kernel_dir/kernel/qemu.log" ]]; then
    cp "$kernel_dir/kernel/qemu.log" "$run_dir/serial.log"
fi
if [[ "$target" == run_kernel && "$result" == 0 ]]; then
    python3 -I "$build_dir/check-boot.py" "$run_dir"
fi
echo "evidence: $run_dir"
exit "$result"
