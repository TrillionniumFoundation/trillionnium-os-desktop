#!/usr/bin/env bash
# Build/run the complete pinned kernel through the upstream developer targets.
set -euo pipefail
build_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd "$build_dir/../.." && pwd)
kernel_dir="$project_dir/kernel/asterinas"
target=${1:-kernel}
case "$target" in kernel|run_kernel|gdb_server) ;; *) echo "usage: $0 [kernel|run_kernel|gdb_server]" >&2; exit 2 ;; esac
if [[ ${CARGO_ENCODED_RUSTFLAGS+x} ]]; then
    echo 'unset CARGO_ENCODED_RUSTFLAGS: it overrides the RUSTFLAGS required by OSDK for the kernel build' >&2
    exit 2
fi
if [[ -v CARGO_HOME && "$CARGO_HOME" != /* ]]; then
    echo 'CARGO_HOME must be an absolute path when set; unset it to use the default' >&2
    exit 2
fi
if [[ ! -v CARGO_HOME && "${HOME:-}" != /* ]]; then
    echo 'HOME must be an absolute path when CARGO_HOME is unset' >&2
    exit 2
fi
if [[ "/${CARGO_HOME:-$HOME/.cargo}/" == */../* ]]; then
    echo "Cargo home path must not contain '..' components; use an absolute path without parent components" >&2
    exit 2
fi
if [[ "$target" == gdb_server ]]; then
    [[ ${A01_GDB_PORT:-} =~ ^[0-9]+$ && ${A01_GDB_FD:-} =~ ^[0-9]+$ ]] || {
        echo 'gdb_server requires the owned listener from support/build/debug/run.py' >&2; exit 2;
    }
    (( A01_GDB_PORT > 0 && A01_GDB_PORT <= 65535 && A01_GDB_FD >= 64 )) || exit 2
fi
# Public calls own one supervised worker group. The debug runner supplies this
# private lifecycle route because it already owns the complete inherited group.
# This flag selects cleanup ownership; it is not a security boundary.
if [[ ${A01_KERNEL_WORKER:-} != 1 ]]; then
    exec python3 -I "$build_dir/kernel-supervisor.py" "$target"
fi
# This is a fixed build invocation, including when launched from another make.
# Inherited dry-run/touch/ignore-error flags or extra makefiles must not change
# whether its recipes execute. Keep their exact shell-quoted values as evidence;
# GNU make will establish normal recursion state for its own children.
make_control_names=(MAKEFLAGS MFLAGS GNUMAKEFLAGS MAKEFILES MAKEOVERRIDES MAKELEVEL)
make_control_records=()
for make_control_name in "${make_control_names[@]}"; do
    if [[ -v "$make_control_name" ]]; then
        printf -v make_control_record '%s_INHERITED=%q' "$make_control_name" "${!make_control_name}"
    else
        make_control_record="${make_control_name}_INHERITED=<unset>"
    fi
    make_control_records+=("$make_control_record")
    unset "$make_control_name"
done
export PATH="${CARGO_HOME:-$HOME/.cargo}/bin:$PATH"
export RUSTUP_TOOLCHAIN=nightly-2026-07-21
export CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS:-2}
export CARGO_NET_GIT_FETCH_WITH_CLI=true
export RUST_LOG=info
export OSDK_CARGO_LOCK="$build_dir/minimal/Cargo.lock"
export VDSO_LIBRARY_DIR=${VDSO_LIBRARY_DIR:-$build_dir/out/linux-vdso}
export A01_SMP=${A01_SMP:-1}
# Refuse a busy workspace before consuming a new evidence path. The same
# invocation can then be retried after the current owner releases its lock.
if [[ -v A01_KERNEL_LOCK_FD ]]; then
    [[ "$A01_KERNEL_LOCK_FD" =~ ^[0-9]+$ && ${#A01_KERNEL_LOCK_FD} -le 10 ]] || {
        echo 'A01_KERNEL_LOCK_FD must name the inherited workspace descriptor >=64' >&2; exit 2;
    }
    (( A01_KERNEL_LOCK_FD >= 64 && A01_KERNEL_LOCK_FD <= 2147483647 )) || exit 2
    # Wrappers already own this open file description. Validate its stable
    # pathname and acquire/retain its flock before duplicating it onto FD 9.
    # This private handoff chooses lifecycle ownership, not a security boundary.
    python3 -I - "$build_dir/out-kernel.lock" "$A01_KERNEL_LOCK_FD" <<'PY'
import fcntl, os, stat, sys
path, descriptor = sys.argv[1], int(sys.argv[2])
held, named = os.fstat(descriptor), os.lstat(path)
if (not stat.S_ISREG(held.st_mode) or not stat.S_ISREG(named.st_mode)
        or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)):
    raise SystemExit("inherited kernel workspace descriptor does not match its regular lock pathname")
fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
PY
    exec 9>&"$A01_KERNEL_LOCK_FD"
else
    exec 9>"$build_dir/out-kernel.lock"
    flock -n 9 || { echo "another A01 build is using the kernel workspace" >&2; exit 1; }
fi
# Keep the lock inode stable: unlinking a locked file permits a second caller
# to create and lock a different inode before this process releases its fd.
if [[ -n ${A01_RUN_DIR:-} ]]; then
    run_dir=$A01_RUN_DIR
    mkdir -p "$(dirname "$run_dir")"
    mkdir "$run_dir" || { echo "A01_RUN_DIR must be a new directory" >&2; exit 1; }
else
    mkdir -p "$build_dir/out"
    run_dir=$(mktemp -d "$build_dir/out/$(date -u +%Y%m%dT%H%M%SZ)-$target-XXXXXX")
fi
run_dir=$(cd "$run_dir" && pwd)
case "${HEPTA_G1C_TRUSTED_OBSERVE:-0}" in
    0) ;;
    1)
        if [[ "$target" != kernel ]]; then
            echo "G1-c uses the dedicated guest runner; kernel.sh run_kernel retains the ordinary boot gate" >&2
            exit 2
        fi
        : "${HEPTA_TRUSTED_INITIAL_ELF:?G1-c requires the reviewed static initial ELF}"
        python3 "$build_dir/prepare-trusted-image.py" \
            --input "$HEPTA_TRUSTED_INITIAL_ELF" \
            --output "$run_dir/trusted-initial.elf" \
            --manifest "$run_dir/trusted-initial-manifest.json"
        export HEPTA_TRUSTED_INITIAL_ELF="$run_dir/trusted-initial.elf"
        ;;
    *) echo "HEPTA_G1C_TRUSTED_OBSERVE must be 0 or 1" >&2; exit 2 ;;
esac
# OSDK_LOCAL_DEV embeds its source root at compile time. A global installed
# SDK may belong to another checkout, even when its mtime is newer here.
# Cargo honors PATH order only when its own home/bin is explicitly present;
# keep that exact entry after this invocation's exclusive installation prefix.
osdk_install_root="$run_dir/osdk"
mkdir -m 700 "$osdk_install_root"
mkdir -m 700 "$osdk_install_root/bin"
export PATH="$osdk_install_root/bin:$PATH"
manifest_file="$kernel_dir/kernel/OSDK.toml"
manifest_temporary=
manifest_anchor_open=
cleanup() {
    local original_status=$? cleanup_status=0
    trap - EXIT
    if [[ "$manifest_anchor_open" == 1 ]]; then
        # FD 8 pins the actual owned inode. Capture the pathname atomically;
        # checking stat followed by rm could unlink a foreign replacement.
        if python3 -I "$build_dir/cleanup-manifest.py" \
            --manifest "$manifest_file" --owned-fd 8 > "$run_dir/manifest-cleanup.json"; then
            cleanup_status=0
        else
            cleanup_status=$?
        fi
        exec 8<&-
        manifest_anchor_open=
        printf '%s\n' "$cleanup_status" > "$run_dir/manifest-cleanup-exit-code.txt" || cleanup_status=1
    fi
    if [[ -n "$manifest_temporary" ]]; then
        rm -f -- "$manifest_temporary" || cleanup_status=1
    fi
    if [[ "$original_status" == 0 && "$cleanup_status" != 0 ]]; then
        original_status=$cleanup_status
        printf '%s\n' "$original_status" > "$run_dir/run-exit-code.txt" || true
    fi
    # A failing EXIT trap return alone need not change a successful exit.
    # Preserve an earlier build failure, otherwise propagate cleanup failure.
    exit "$original_status"
}
trap cleanup EXIT
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
    make --version
    gcc --version
    qemu-system-x86_64 --version || true
    git -C "$project_dir" rev-parse HEAD
    git -C "$project_dir" status --short
    printf 'CARGO_BUILD_JOBS=%s\nVDSO_LIBRARY_DIR=%s\n' "$CARGO_BUILD_JOBS" "$VDSO_LIBRARY_DIR"
    printf 'A01_OSDK_INSTALL_ROOT=%s\nCARGO_OSDK=%s\nCARGO_HOME=%s\nRUSTUP_HOME=%s\nPATH=%s\n' \
        "$osdk_install_root" "$osdk_install_root/bin/cargo-osdk" \
        "${CARGO_HOME-<unset>}" "${RUSTUP_HOME-<unset>}" "$PATH"
    printf 'RUSTFLAGS=%s\nCARGO_ENCODED_RUSTFLAGS=%s\nCARGO_TARGET_DIR=%s\nASTER_BUILD_TIMESTAMP=%s\n' \
        "${RUSTFLAGS-<unset>}" "${CARGO_ENCODED_RUSTFLAGS-<unset>}" \
        "${CARGO_TARGET_DIR-<unset>}" "${ASTER_BUILD_TIMESTAMP-<unset>}"
    printf '%s\n' "${make_control_records[@]}"
    printf '%s_EFFECTIVE=<unset>\n' "${make_control_names[@]}"
    sha256sum "$VDSO_LIBRARY_DIR/vdso_x86_64.so"
    sha256sum "$OSDK_CARGO_LOCK"
    sha256sum "$build_dir/cleanup-manifest.py"
    for tool in docker nix-build; do command -v "$tool" || true; done
    if [[ -e /dev/kvm ]]; then ls -l /dev/kvm; else echo '/dev/kvm absent; explicit TCG selected'; fi
} > "$run_dir/environment.log" 2>&1
python3 "$build_dir/minimal/prepare-initramfs.py" \
    --upstream "$kernel_dir" --busybox "${A01_BUSYBOX:-/usr/bin/busybox}" \
    --output "$run_dir/initramfs.cpio.gz" --manifest "$run_dir/initramfs-manifest.json"
manifest_temporary=$(mktemp "$kernel_dir/kernel/.a01-osdk-XXXXXX")
cp "$build_dir/minimal/OSDK.toml" "$manifest_temporary"
# Pin ownership before publication, including an interrupt immediately after
# ln. Reserved FD 8 stays open through cleanup; the workspace lock uses FD 9.
exec 8<"$manifest_temporary"
manifest_anchor_open=1
ln -T "$manifest_temporary" "$manifest_file"
rm "$manifest_temporary"
manifest_temporary=
export A01_QEMU_EVIDENCE="$run_dir/qemu.json"
if [[ "$target" != kernel ]]; then rm -f "$kernel_dir/kernel/qemu.log"; fi
command=(make -C "$kernel_dir" -f Makefile -f "$build_dir/minimal.mk" "$target"
    "CARGO_OSDK=$osdk_install_root/bin/cargo-osdk"
    "A01_OSDK_INSTALL_ROOT=$osdk_install_root"
    "A01_INITRAMFS=$run_dir/initramfs.cpio.gz"
    "A01_QEMU_WRAPPER=$build_dir/record-qemu.py" TARGET_ARCH=x86_64 SMP="$A01_SMP" MEM=512M
    ENABLE_KVM=0 BOOT_PROTOCOL=multiboot INITRAMFS=on AUTO_TEST=none)
if [[ ${HEPTA_G1C_TRUSTED_OBSERVE:-0} == 1 ]]; then
    command+=(HEPTA_G1C_TRUSTED_OBSERVE=1 FEATURES=g1c-trusted-observe)
fi
if [[ "$target" == gdb_server ]]; then command+=("A01_GDB_PORT=$A01_GDB_PORT"); fi
printf '%q ' "${command[@]}" > "$run_dir/command.sh"
printf '\n' >> "$run_dir/command.sh"
set +e
"${command[@]}" 2>&1 | tee "$run_dir/$target.log"
pipeline_status=("${PIPESTATUS[@]}")
result=${pipeline_status[0]}
set -e
printf '%s\n' "$result" > "$run_dir/make-exit-code.txt"
printf '%s\n' "${pipeline_status[1]}" > "$run_dir/log-exit-code.txt"
if [[ ${pipeline_status[1]} != 0 ]]; then
    echo "failed to retain the complete command log" >&2
    result=1
fi
if [[ "$target" != kernel && -f "$kernel_dir/kernel/qemu.log" ]]; then
    cp "$kernel_dir/kernel/qemu.log" "$run_dir/serial.log"
fi
if [[ "$target" != kernel && "$result" == 0 ]]; then
    set +e
    python3 -I "$build_dir/check-boot.py" "$run_dir" --live-artifacts
    result=$?
    set -e
fi
printf '%s\n' "$result" > "$run_dir/run-exit-code.txt"
echo "evidence: $run_dir"
exit "$result"
