#!/usr/bin/env bash
# Pinned Android 15 Cuttlefish *LINUX-guest reference*; never an Asterinas pass.
set -Eeuo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mode="${1:-}"
: "${AOSP_ROOT:?Point AOSP_ROOT at a dedicated AOSP checkout}"
: "${A08_EVIDENCE:?Point A08_EVIDENCE outside the checkout}"
AOSP_ROOT="$(realpath -m "$AOSP_ROOT")"
A08_EVIDENCE="$(realpath -m "$A08_EVIDENCE")"
[[ "$AOSP_ROOT" != / && "$A08_EVIDENCE" != / ]] || { echo 'Refusing filesystem root paths' >&2; exit 2; }
[[ "$A08_EVIDENCE/" != "$AOSP_ROOT/"* && "$AOSP_ROOT/" != "$A08_EVIDENCE/"* ]] || {
  echo 'Checkout/evidence paths must not contain one another' >&2; exit 2;
}
mkdir -p "$A08_EVIDENCE"
log="$A08_EVIDENCE/attempts.log"
current_stage='preflight'
on_exit() { rc=$?; printf 'utc=%s stage=%s mode=%s status=%s exit=%d\n' \
  "$(date -u +%FT%TZ)" "$current_stage" "$mode" "$([[ $rc == 0 ]] && echo pass || echo fail)" "$rc" >> "$log"; }
trap on_exit EXIT
PINNED_COMMIT='a0601d2912a6cedcaf97e1372173f8704a2715b0'
PINNED_BLOB='a7c482a2345706883f9cde145be289a7c14c1c10'
manifest_preflight() {
  [[ -d "$AOSP_ROOT/.repo/manifests" ]] || { echo 'AOSP checkout not initialized' >&2; exit 3; }
  local got blob
  got="$(git -C "$AOSP_ROOT/.repo/manifests" rev-parse HEAD)"
  blob="$(git -C "$AOSP_ROOT/.repo/manifests" hash-object default.xml)"
  [[ "$got" == "$PINNED_COMMIT" && "$blob" == "$PINNED_BLOB" ]] || {
    echo "Manifest lock mismatch: commit=$got blob=$blob" >&2; exit 4;
  }
}
check_resolved() {
  current_stage='manifest-audit'
  repo manifest -r -o "$A08_EVIDENCE/manifest-resolved.xml"
  python3 "$here/audit.py" manifest "$A08_EVIDENCE/manifest-resolved.xml" "$A08_EVIDENCE/manifest-audit.json"
  current_stage='source-audit'
  python3 "$here/audit.py" source "$AOSP_ROOT" "$A08_EVIDENCE/source-audit.json"
  current_stage='cuttlefish-product-source-audit'
  python3 "$here/verify_product_source.py" \
    --aosp-root "$AOSP_ROOT" \
    --resolved-manifest "$A08_EVIDENCE/manifest-resolved.xml" \
    --out "$A08_EVIDENCE/product-source-audit.json"
}
case "$mode" in
  init)
    current_stage='repo-init'
    command -v repo >/dev/null || { echo 'Official repo launcher not found' >&2; exit 3; }
    if [[ -e "$AOSP_ROOT/.repo" || ( -d "$AOSP_ROOT" && -n "$(ls -A "$AOSP_ROOT")" ) ]]; then
      echo 'Refusing to reuse/overwrite non-empty AOSP checkout during init' >&2; exit 3
    fi
    mkdir -p "$AOSP_ROOT"
    cd "$AOSP_ROOT"
    repo init --partial-clone --no-use-superproject \
      -u https://android.googlesource.com/platform/manifest \
      -b refs/tags/android-15.0.0_r36 -m default.xml 2>&1 | tee "$A08_EVIDENCE/repo-init.log"
    manifest_preflight
    current_stage='repo-sync'
    repo sync -c -j "${A08_SYNC_JOBS:-4}" 2>&1 | tee "$A08_EVIDENCE/repo-sync.log"
    check_resolved
    ;;
  audit)
    current_stage='repo-audit'
    cd "$AOSP_ROOT"
    manifest_preflight
    check_resolved
    ;;
  build)
    current_stage='repo-audit'
    cd "$AOSP_ROOT"
    manifest_preflight
    check_resolved
    current_stage='lunch'
    # AOSP envsetup/m functions are not compatible with bash nounset in all tags.
    set +u
    source build/envsetup.sh
    lunch aosp_cf_x86_64_phone-trunk_staging-userdebug 2>&1 | tee "$A08_EVIDENCE/lunch.log"
    [[ "$(get_build_var TARGET_PRODUCT)" == aosp_cf_x86_64_phone ]] || { echo 'Unexpected product' >&2; exit 5; }
    [[ "$(get_build_var TARGET_ARCH)" == x86_64 ]] || { echo 'Unexpected architecture' >&2; exit 5; }
    [[ "$(get_build_var TARGET_BUILD_VARIANT)" == userdebug ]] || { echo 'Unexpected variant' >&2; exit 5; }
    get_build_var PRODUCT_OUT > "$A08_EVIDENCE/product-out.txt"
    { printf 'lunch=%s\n' aosp_cf_x86_64_phone-trunk_staging-userdebug;
      printf 'release=%s\n' "${TARGET_RELEASE:-unknown}";
      printf 'product=%s\n' "$(get_build_var TARGET_PRODUCT)";
      printf 'arch=%s\n' "$(get_build_var TARGET_ARCH)";
      printf 'release_aidl_use_unfrozen=%s\n' "$(get_build_var RELEASE_AIDL_USE_UNFROZEN)";
      printf 'platform_sdk=%s\n' "$(get_build_var PLATFORM_SDK_VERSION)";
      printf 'host=%s\n' "$(uname -a)";
      printf 'java='; java -version 2>&1 | head -1;
      printf 'repo='; repo version 2>&1 | head -1;
    } > "$A08_EVIDENCE/toolchain.txt"
    current_stage='aosp-build'
    m -j "${A08_BUILD_JOBS:-4}" 2>&1 | tee "$A08_EVIDENCE/build.log"
    current_stage='image-audit'
    product_out="$(get_build_var PRODUCT_OUT)"
  python3 "$here/audit.py" image "$product_out" "$A08_EVIDENCE/image-audit.json"
  current_stage='vintf-compatibility'
  # Run the actual same-source AOSP-built checkvintf. Merely parsing VINTF
  # XML does not establish device/framework HAL metadata compatibility.
  vintf_args=(--aosp-root "$AOSP_ROOT" --product-out "$product_out"
    --checkvintf "$(get_build_var HOST_OUT_EXECUTABLES)/checkvintf"
    --out "$A08_EVIDENCE/vintf-compatibility.json"
    --framework-level 202404 --framework-level 202504)
  apex_info="$(get_build_var APEX_INFO_FILE)"
  if [[ -n "$apex_info" ]]; then
    vintf_args+=(--apex-info-file "$apex_info")
  fi
  python3 "$here/verify_vintf.py" "${vintf_args[@]}"
    ;;
  *)
    echo 'Usage: AOSP_ROOT=/scratch/a08-aosp A08_EVIDENCE=/scratch/a08-log prepare_aosp.sh init|audit|build' >&2
    exit 2;;
esac
