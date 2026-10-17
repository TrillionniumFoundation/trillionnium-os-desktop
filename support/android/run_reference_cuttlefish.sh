#!/usr/bin/env bash
# Start a disposable, source-built Android/Linux Cuttlefish reference only.
# A successful launcher exit is NOT a verified guest boot and NOT Asterinas.
set -Eeuo pipefail
: "${AOSP_ROOT:?Set AOSP_ROOT to exact checked out AOSP source}"
: "${A08_EVIDENCE:?Set A08_EVIDENCE to its audited build evidence directory}"
: "${A08_CVD_HOME:?Set A08_CVD_HOME to a NEW, empty isolated instance HOME}"
: "${A08_CVD_INSTANCE_ID:?Set A08_CVD_INSTANCE_ID to an UNUSED numeric Cuttlefish instance slot}"
[[ "$A08_CVD_INSTANCE_ID" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid numeric instance ID" >&2; exit 2; }
root="$(realpath "$AOSP_ROOT")"
out="$(realpath "$A08_EVIDENCE")"
home="$(realpath -m "$A08_CVD_HOME")"
[[ "$root" != / && "$out" != / && "$home" != / ]] || { echo 'Refusing root directory paths' >&2; exit 2; }
[[ "$home" != "$root" && "$home" != "$out" && "$home/" != "$root/"* && "$home/" != "$out/"* ]] || {
  echo 'CVD HOME must not be the checkout or evidence path or nested within either' >&2; exit 2;
}
[[ ! -e "$home" || ( -d "$home" && -z "$(ls -A "$home")" ) ]] || {
  echo 'CVD HOME already contains data; refusing to change a running/old instance' >&2; exit 3;
}
[[ -c /dev/kvm && -r /dev/kvm && -w /dev/kvm ]] || {
  echo 'KVM device absent or inaccessible; refusing to launch Cuttlefish' >&2; exit 4;
}
[[ -f "$out/product-out.txt" ]] || { echo 'Build product-out record missing' >&2; exit 5; }
raw_product_out="$(head -n 1 "$out/product-out.txt")"
if [[ "$raw_product_out" = /* ]]; then
  product_out="$(realpath -m "$raw_product_out")"
else
  product_out="$(realpath -m "$root/$raw_product_out")"
fi
[[ "$product_out/" == "$root/out/"* ]] || { echo 'PRODUCT_OUT must lie under AOSP build out/' >&2; exit 5; }
host_out="$root/out/host/linux-x86"
launcher="$host_out/bin/launch_cvd"
[[ -x "$launcher" ]] || { echo "Missing same-source built CVD launcher $launcher" >&2; exit 6; }
# Re-check mutable source HEADs and product files immediately before launch;
# evidence from an earlier AOSP build is not enough by itself.
python3 "$(dirname "${BASH_SOURCE[0]}")/verify_product_source.py" \
  --aosp-root "$root" \
  --resolved-manifest "$out/manifest-resolved.xml" \
  --out "$out/product-source-launch-audit.json"
python3 "$(dirname "${BASH_SOURCE[0]}")/verify_launch_preflight.py" \
  --aosp-root "$root" --evidence "$out" --product-out "$product_out" \
  --launcher "$launcher" --out "$out/cuttlefish-launch-preflight.json"
mkdir -p "$home"
# Launch is confined to this new HOME; do not stop, reuse or touch other CVDs.
export HOME="$home"
export ANDROID_PRODUCT_OUT="$product_out"
export ANDROID_HOST_OUT="$host_out"
export CUTTLEFISH_INSTANCE="$A08_CVD_INSTANCE_ID"
set -o pipefail
"$launcher" --daemon --gpu_mode=guest_swiftshader 2>&1 | tee "$out/cuttlefish-launch.log"
printf 'Launcher returned 0; guest boot remains UNVERIFIED. Run boot_gates.py with explicit disposable ADB serial.\n' | tee "$out/cuttlefish-launch-status.txt"
