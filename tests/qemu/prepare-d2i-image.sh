#!/bin/bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: prepare-d2i-image.sh \
  --base-image PATH \
  --runtime-binary PATH \
  --overlay PATH \
  --source-epoch UNIX_SECONDS \
  --servo-revision SHA \
  --output-image PATH \
  --evidence PATH
EOF
}

base_image=
runtime_binary=
overlay=
source_epoch=
servo_revision=
output_image=
evidence=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-image) base_image=$2; shift 2 ;;
    --runtime-binary) runtime_binary=$2; shift 2 ;;
    --overlay) overlay=$2; shift 2 ;;
    --source-epoch) source_epoch=$2; shift 2 ;;
    --servo-revision) servo_revision=$2; shift 2 ;;
    --output-image) output_image=$2; shift 2 ;;
    --evidence) evidence=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

for value in base_image runtime_binary overlay source_epoch servo_revision output_image evidence; do
  [[ -n ${!value} ]] || { echo "missing --${value//_/-}" >&2; exit 2; }
done
[[ $source_epoch =~ ^[0-9]+$ ]] || { echo "invalid source epoch" >&2; exit 2; }
[[ $servo_revision =~ ^[0-9a-f]{40}$ ]] || { echo "invalid Servo revision" >&2; exit 2; }
for command in cp debugfs e2fsck sha256sum python3 readlink stat; do
  command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 1; }
done

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || {
  echo "cannot locate D2I image script directory" >&2
  exit 1
}
safe_io="$script_dir/../../tools/qemu_safe_io.py"
[[ -f $safe_io && ! -L $safe_io ]] || {
  echo "missing safe QEMU I/O helper" >&2
  exit 1
}
# ShellCheck resolves source directives from the repository working directory.
# Keep this root-relative so the same annotation works in CI and locally.
# shellcheck source=tools/reject_symlink_path.sh
source "$script_dir/../../tools/reject_symlink_path.sh"
reject_symlink_path "$base_image" "D2I base image" || exit 1
reject_symlink_path "$runtime_binary" "D2I runtime binary" || exit 1
reject_symlink_path "$overlay" "D2I overlay" || exit 1
reject_symlink_path "$output_image" "D2I output image" || exit 1
reject_symlink_path "$evidence" "D2I evidence" || exit 1
base_image=$(readlink -f -- "$base_image")
runtime_binary=$(readlink -f -- "$runtime_binary")
overlay=$(readlink -f -- "$overlay")
mkdir -p -- "$(dirname -- "$output_image")" "$(dirname -- "$evidence")"
reject_symlink_path "$output_image" "D2I output image" || exit 1
reject_symlink_path "$evidence" "D2I evidence" || exit 1
output_image=$(readlink -m -- "$output_image")
evidence=$(readlink -m -- "$evidence")
reject_symlink_path "$output_image" "D2I output image" || exit 1
reject_symlink_path "$evidence" "D2I evidence" || exit 1
[[ -d "$(dirname -- "$output_image")" && -d "$(dirname -- "$evidence")" ]] || {
  echo "D2I output/evidence parent is not a directory" >&2
  exit 1
}
[[ -f $base_image && ! -L $base_image ]] || { echo "unsafe base image" >&2; exit 1; }
[[ -f $runtime_binary && -x $runtime_binary && ! -L $runtime_binary ]] || {
  echo "unsafe headed runtime binary" >&2
  exit 1
}
[[ -d $overlay && ! -L $overlay ]] || { echo "unsafe D2I overlay" >&2; exit 1; }

required_overlay=(
  etc/systemd/system/trillionnium-d2i-runtime.service
  etc/systemd/system/trillionnium-d2i-content-crash-proof.service
  etc/systemd/system/trillionnium-d2i-acceptance.service
  etc/systemd/system/trillionnium-d2i-acceptance.target
  usr/local/libexec/trillionnium-d2i-acceptance
  usr/local/libexec/trillionnium-d2i-content-crash-proof
)
for relative in "${required_overlay[@]}"; do
  [[ -f "$overlay/$relative" && ! -L "$overlay/$relative" ]] || {
    echo "missing D2I overlay file: $relative" >&2
    exit 1
  }
done

base_sha=$(sha256sum "$base_image" | awk '{print $1}')
runtime_sha=$(sha256sum "$runtime_binary" | awk '{print $1}')
python3 "$safe_io" copy \
  --source "$base_image" \
  --destination "$output_image" \
  --sparse
python3 - "$output_image" "$safe_io" <<'PY'
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(sys.argv[2]).resolve().parent))
from qemu_safe_io import open_regular  # noqa: E402

descriptor = open_regular(Path(sys.argv[1]), "D2I output image")
try:
    os.fchmod(descriptor, 0o600)
finally:
    os.close(descriptor)
PY

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
manifest="$work/d2i-image-manifest.json"
python3 - "$manifest" "$base_sha" "$runtime_sha" "$source_epoch" "$servo_revision" \
  "$safe_io" <<'PY'
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(sys.argv[6]).resolve().parent))
from qemu_safe_io import write_text  # noqa: E402

write_text(pathlib.Path(sys.argv[1]), json.dumps({
    "schema": "trillionnium.desktop.d2i-image-input.v1",
    "base_d1_image_sha256": sys.argv[2],
    "headed_runtime_sha256": sys.argv[3],
    "source_date_epoch": int(sys.argv[4]),
    "servo_revision": sys.argv[5],
    "product_agent_port_enabled": False,
    "content_crash_injector": "external-systemd-helper",
    "content_crash_injector_count": 1,
    "runtime_internal_injector": False,
    "network_device_expected": False,
    "release_ready": False,
}, indent=2, sort_keys=True) + "\n", "D2I image input manifest")
PY

export E2FSPROGS_FAKE_TIME="$source_epoch"
run_debugfs() {
  debugfs -w -R "$1" "$output_image" >/dev/null
}
write_file() {
  local source=$1
  local destination=$2
  run_debugfs "rm $destination" 2>/dev/null || true
  run_debugfs "write $source $destination"
}

write_file "$runtime_binary" /usr/libexec/hepta-workspace-runtime
write_file "$overlay/etc/systemd/system/trillionnium-d2i-runtime.service" \
  /etc/systemd/system/trillionnium-d2i-runtime.service
write_file "$overlay/etc/systemd/system/trillionnium-d2i-content-crash-proof.service" \
  /etc/systemd/system/trillionnium-d2i-content-crash-proof.service
write_file "$overlay/etc/systemd/system/trillionnium-d2i-acceptance.service" \
  /etc/systemd/system/trillionnium-d2i-acceptance.service
write_file "$overlay/etc/systemd/system/trillionnium-d2i-acceptance.target" \
  /etc/systemd/system/trillionnium-d2i-acceptance.target
write_file "$overlay/usr/local/libexec/trillionnium-d2i-acceptance" \
  /usr/local/libexec/trillionnium-d2i-acceptance
write_file "$overlay/usr/local/libexec/trillionnium-d2i-content-crash-proof" \
  /usr/local/libexec/trillionnium-d2i-content-crash-proof
write_file "$manifest" /usr/lib/trillionnium-d1/d2i-image-manifest.json

run_debugfs "set_inode_field /usr/libexec/hepta-workspace-runtime mode 0100755"
run_debugfs "set_inode_field /usr/local/libexec/trillionnium-d2i-acceptance mode 0100755"
run_debugfs "set_inode_field /usr/local/libexec/trillionnium-d2i-content-crash-proof mode 0100755"
for path in \
  /usr/libexec/hepta-workspace-runtime \
  /etc/systemd/system/trillionnium-d2i-runtime.service \
  /etc/systemd/system/trillionnium-d2i-content-crash-proof.service \
  /etc/systemd/system/trillionnium-d2i-acceptance.service \
  /etc/systemd/system/trillionnium-d2i-acceptance.target \
  /usr/local/libexec/trillionnium-d2i-acceptance \
  /usr/local/libexec/trillionnium-d2i-content-crash-proof \
  /usr/lib/trillionnium-d1/d2i-image-manifest.json; do
  run_debugfs "set_inode_field $path uid 0"
  run_debugfs "set_inode_field $path gid 0"
  run_debugfs "set_inode_field $path atime $source_epoch"
  run_debugfs "set_inode_field $path ctime $source_epoch"
  run_debugfs "set_inode_field $path mtime $source_epoch"
  run_debugfs "set_inode_field $path crtime $source_epoch"
done

set +e
e2fsck -fy "$output_image" >"$work/e2fsck-write.log" 2>&1
e2fsck_status=$?
set -e
if (( e2fsck_status > 1 )); then
  cat "$work/e2fsck-write.log" >&2
  exit "$e2fsck_status"
fi
e2fsck -fn "$output_image" >"$work/e2fsck-read-only.log" 2>&1

image_sha=$(sha256sum "$output_image" | awk '{print $1}')
image_bytes=$(stat -c %s "$output_image")
debugfs -R 'stat /usr/libexec/hepta-workspace-runtime' "$output_image" \
  >"$work/runtime-stat.txt" 2>&1
python3 - "$evidence" "$base_sha" "$runtime_sha" "$image_sha" "$image_bytes" \
  "$source_epoch" "$servo_revision" "$safe_io" <<'PY'
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(sys.argv[8]).resolve().parent))
from qemu_safe_io import write_text  # noqa: E402

write_text(pathlib.Path(sys.argv[1]), json.dumps({
    "schema": "trillionnium.desktop.d2i-image-preparation.v1",
    "status": "PASS_DETERMINISTIC_INPUT_INJECTION",
    "base_d1_image_sha256": sys.argv[2],
    "headed_runtime_sha256": sys.argv[3],
    "integrated_image_sha256": sys.argv[4],
    "integrated_image_bytes": int(sys.argv[5]),
    "source_date_epoch": int(sys.argv[6]),
    "servo_revision": sys.argv[7],
    "injected_paths": [
        "/usr/libexec/hepta-workspace-runtime",
        "/etc/systemd/system/trillionnium-d2i-runtime.service",
        "/etc/systemd/system/trillionnium-d2i-content-crash-proof.service",
        "/etc/systemd/system/trillionnium-d2i-acceptance.service",
        "/etc/systemd/system/trillionnium-d2i-acceptance.target",
        "/usr/local/libexec/trillionnium-d2i-acceptance",
        "/usr/local/libexec/trillionnium-d2i-content-crash-proof",
        "/usr/lib/trillionnium-d1/d2i-image-manifest.json",
    ],
    "product_agent_port_enabled": False,
    "content_crash_injector": "external-systemd-helper",
    "content_crash_injector_count": 1,
    "runtime_internal_injector": False,
    "network_device_expected": False,
    "release_ready": False,
}, indent=2, sort_keys=True) + "\n", "D2I preparation evidence")
PY
