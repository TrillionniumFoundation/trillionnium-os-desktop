#!/usr/bin/env bash
# Reclaim the exact Servo build workspace after the qualified runtime binary is
# copied. The D1 image pipeline needs the same runner, but never reads the Servo
# checkout or its target directory.
set -euo pipefail

root=/tmp/trillionnium-d2i
evidence="$root/evidence"
runtime="$root/hepta-workspace-runtime"
runtime_digest="$root/headed-runtime.sha256"
mkdir -p "$evidence"

[[ -x "$runtime" && ! -L "$runtime" ]] || {
  echo "D2I headed runtime is missing or unsafe before reclamation" >&2
  exit 1
}
[[ -s "$runtime_digest" && ! -L "$runtime_digest" ]] || {
  echo "D2I headed-runtime digest is missing or unsafe before reclamation" >&2
  exit 1
}
expected=$(awk 'NR == 1 { print $1 }' "$runtime_digest")
actual=$(sha256sum "$runtime" | awk '{ print $1 }')
[[ $expected =~ ^[0-9a-f]{64}$ && $actual == "$expected" ]] || {
  echo "copied D2I headed-runtime digest changed before reclamation" >&2
  exit 1
}
[[ -d servo-source && ! -L servo-source ]] || {
  echo "exact Servo checkout is absent before reclamation" >&2
  exit 1
}
[[ -d servo-source/target && ! -L servo-source/target ]] || {
  echo "exact Servo target directory is absent before reclamation" >&2
  exit 1
}

before_available=$(df -P -B1 "$RUNNER_TEMP" | awk 'NR == 2 { print $4 }')
source_bytes=$(du -s -B1 servo-source | awk '{ print $1 }')
target_bytes=$(du -s -B1 servo-source/target | awk '{ print $1 }')
{
  printf 'runtime_sha256=%s\n' "$actual"
  printf 'available_bytes=%s\n' "$before_available"
  printf 'servo_source_bytes=%s\n' "$source_bytes"
  printf 'servo_target_bytes=%s\n' "$target_bytes"
  df -P -B1 "$RUNNER_TEMP"
} > "$evidence/resource-before-servo-reclamation.txt"

# The runtime executable and its digest are already outside the checkout. No
# later D2I stage reads Servo source or target outputs; removing the whole tree
# avoids retaining a second, multi-gigabyte build graph while D1 creates two
# rootfs/tar/ext4 candidates on the same hosted runner.
rm -rf --one-file-system servo-source
sync
[[ ! -e servo-source ]]
[[ -x "$runtime" ]]
[[ $(sha256sum "$runtime" | awk '{ print $1 }') == "$expected" ]]

after_available=$(df -P -B1 "$RUNNER_TEMP" | awk 'NR == 2 { print $4 }')
(( after_available >= before_available )) || {
  echo "available runner storage decreased after Servo reclamation" >&2
  exit 1
}
reclaimed=$((after_available - before_available))
python3 - "$evidence/resource-reclamation.json" \
  "$expected" "$before_available" "$after_available" \
  "$source_bytes" "$target_bytes" "$reclaimed" <<'PY'
import json
import pathlib
import sys

pathlib.Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema": "trillionnium.desktop.d2i-resource-reclamation.v1",
            "status": "PASS_SERVO_BUILD_TREE_RECLAIMED",
            "headed_runtime_sha256": sys.argv[2],
            "available_bytes_before": int(sys.argv[3]),
            "available_bytes_after": int(sys.argv[4]),
            "servo_source_bytes_removed": int(sys.argv[5]),
            "servo_target_bytes_removed": int(sys.argv[6]),
            "available_bytes_delta": int(sys.argv[7]),
            "servo_source_absent_after": True,
            "runtime_preserved": True,
            "claim_ceiling": "runner_resource_reclamation_only",
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

df -P -B1 "$RUNNER_TEMP" > "$evidence/resource-after-servo-reclamation.txt"
