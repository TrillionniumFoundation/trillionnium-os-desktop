#!/usr/bin/env bash
# Builds the separate DEX-only and x86_64 JNI APK fixtures, never a phone image.
# Requires a dedicated checked-out, fully synced Android 15 r36 AOSP tree.
set -Eeuo pipefail
: "${AOSP_ROOT:?AOSP_ROOT required}"
: "${A08_EVIDENCE:?A08_EVIDENCE required}"
root="$(realpath "$AOSP_ROOT")"
out="$(realpath -m "$A08_EVIDENCE")"
[[ "$root" != / && "$out" != / ]] || { echo 'Refusing root paths' >&2; exit 2; }
[[ "$out/" != "$root/"* && "$root/" != "$out/"* ]] || {
  echo 'Checkout and log dirs may not nest' >&2; exit 2;
}
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/../../tests/workloads/android/apk-smoke"
dst="$root/external/a08smoke"
[[ -d "$root/.repo" && -f "$root/build/envsetup.sh" ]] || {
  echo 'Not a full AOSP checkout' >&2; exit 3;
}
[[ ! -e "$dst" ]] || {
  echo 'Refusing to overwrite pre-existing external/a08smoke' >&2; exit 3;
}
mkdir -p "$out" "$root/external"
AOSP_ROOT="$root" A08_EVIDENCE="$out" "$here/prepare_aosp.sh" audit
cp -a "$src" "$dst"
# Only remove the directory this script created; retain all evidence logs.
cleanup() { rm -rf -- "$dst"; }
trap cleanup EXIT
cd "$root"
set +u
source build/envsetup.sh
lunch aosp_cf_x86_64_phone-trunk_staging-userdebug 2>&1 | tee "$out/smoke-lunch.log"
[[ "$(get_build_var TARGET_PRODUCT)" == aosp_cf_x86_64_phone ]] || exit 5
[[ "$(get_build_var TARGET_ARCH)" == x86_64 ]] || exit 5
[[ "$(get_build_var TARGET_BUILD_VARIANT)" == userdebug ]] || exit 5
m -j "${A08_BUILD_JOBS:-4}" A08Smoke A08NativeSmoke 2>&1 | tee "$out/smoke-build.log"
product_out="$(get_build_var PRODUCT_OUT)"
aapt2="$(get_build_var HOST_OUT_EXECUTABLES)/aapt2"
[[ -x "$aapt2" ]] || { echo "Missing AAPT2: $aapt2" >&2; exit 7; }

# Prefer uniquely built, installed packages. If this build only produced Soong
# intermediates, accept a single exact module APK. An ambiguous selection is
# an error rather than silently recording a wrong/unsigned APK hash.
select_apk() {
  local module="$1" candidate_dir="$root/out/soong/.intermediates/external/a08smoke/$1"
  local -a found=()
  mapfile -t found < <(find "$product_out" -name "$module.apk" -type f -print | LC_ALL=C sort)
  if [[ ${#found[@]} -eq 0 && -d "$candidate_dir" ]]; then
    mapfile -t found < <(find "$candidate_dir" -name "$module.apk" -type f -print | LC_ALL=C sort)
  fi
  if [[ ${#found[@]} -ne 1 ]]; then
    printf '%s APK candidates: %s (must be exactly 1)\n' "$module" "${#found[@]}" >&2
    printf '%s\n' "${found[@]}" >&2
    return 6
  fi
  printf '%s\n' "${found[0]}"
}

dex_apk="$(select_apk A08Smoke)"
native_apk="$(select_apk A08NativeSmoke)"
"$aapt2" dump badging "$dex_apk" > "$out/smoke-dex-aapt2-badging.log"
"$aapt2" dump badging "$native_apk" > "$out/smoke-native-aapt2-badging.log"
grep -Eq "^package: name='org\.trillionnium\.a08smoke' versionCode='1' versionName='1\.0'" \
  "$out/smoke-dex-aapt2-badging.log" || { echo 'DEX APK identity mismatch' >&2; exit 8; }
grep -Eq "^package: name='org\.trillionnium\.a08native' versionCode='1' versionName='1\.0'" \
  "$out/smoke-native-aapt2-badging.log" || { echo 'Native APK identity mismatch' >&2; exit 8; }
# Verify actual ZIP/DEX and exact native architecture using the workload probes.
python3 - "$here/../../tests/workloads/android" "$dex_apk" "$native_apk" "$out" <<'PY'
import json
from pathlib import Path
import sys
sys.path.insert(0,sys.argv[1])
from run_apk import apk_metadata
from run_native_apk import inspect_native_apk
p1,p2,out=map(Path,sys.argv[2:])
dex=apk_metadata(p1)
if not dex['classes_dex'] or dex['native_libraries']:
    raise SystemExit('DEX-only artifact contains unexpected native libraries or lacks DEX')
native=inspect_native_apk(p2)
(out/'smoke-apk-artifacts.json').write_text(json.dumps({
    'status':'artifacts_verified_NOT_installed_or_executed',
    'target_kernel':'Linux Cuttlefish reference, NOT Asterinas',
    'dex_only':dex,'x86_64_jni':native}, indent=2, sort_keys=True)+'\n')
(out/'smoke-dex-apk.sha256').write_text(dex['sha256']+'  '+str(p1)+'\n')
(out/'smoke-native-apk.sha256').write_text(native['sha256']+'  '+str(p2)+'\n')
PY
printf '%s\n' "$dex_apk" > "$out/smoke-dex-apk-path.txt"
printf '%s\n' "$native_apk" > "$out/smoke-native-apk-path.txt"
