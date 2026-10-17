#!/usr/bin/env bash
# A08 self-contained ABI guest package. Only A08 output files are created.
# A01 kernel sources/build configs remain unchanged. No guest is booted here.
set -Eeuo pipefail
: "${A08_ABI_OUTPUT:?Set A08_ABI_OUTPUT to a NEW scratch output directory}"
: "${A08_BUSYBOX_STATIC:?Set A08_BUSYBOX_STATIC to a verified static x86_64 BusyBox}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
out="$(realpath -m "$A08_ABI_OUTPUT")"
[[ "$out" != / && "$out" != "$repo" && "$out" != "$repo/"* ]] || {
  echo 'Refusing to write ABI evidence into checkout or filesystem root' >&2; exit 2;
}
[[ ! -e "$out" ]] || { echo 'Refusing to overwrite previous ABI evidence' >&2; exit 2; }
[[ "$(uname -m)" == x86_64 ]] || { echo 'A08 guest requires x86_64 host' >&2; exit 2; }
command -v "${A08_CC:-cc}" >/dev/null || { echo 'C compiler unavailable' >&2; exit 3; }
[[ -f "$A08_BUSYBOX_STATIC" ]] || { echo 'Static BusyBox input missing' >&2; exit 3; }
mkdir -p "$out"
cc="${A08_CC:-cc}"
"$cc" -std=c11 -O2 -Wall -Wextra -Werror -static -pthread \
  "$repo/tests/workloads/android/kernel_abi_probe.c" -o "$out/kernel-abi"
"$cc" -std=c11 -O2 -Wall -Wextra -Werror -static \
  "$repo/tests/workloads/android/binder_abi_probe.c" -o "$out/binder-abi"
"$cc" -std=c11 -O2 -Wall -Wextra -Werror -static \
  "$repo/tests/workloads/android/seccomp_abi_probe.c" -o "$out/seccomp-abi"
python3 "$here/prepare_asterinas_abi.py" \
  --busybox "$A08_BUSYBOX_STATIC" \
  --kernel-probe "$out/kernel-abi" --binder-probe "$out/binder-abi" \
  --seccomp-probe "$out/seccomp-abi" \
  --dest "$out/a08-initramfs.cpio.gz" --manifest "$out/manifest.json"
{
  "$cc" --version | head -1
  sha256sum "$A08_BUSYBOX_STATIC" "$out/kernel-abi" "$out/binder-abi" \
    "$out/seccomp-abi" \
    "$out/a08-initramfs.cpio.gz"
} > "$out/build-inputs.log"
echo "A08 guest image prepared but NOT booted: $out/a08-initramfs.cpio.gz"
