#!/bin/sh
set -eu

usage() {
  echo "usage: $0 --image IMAGE --output-dir DIR" >&2
  exit 64
}

image=
output_dir=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --image) [ "$#" -ge 2 ] || usage; image=$2; shift 2 ;;
    --output-dir) [ "$#" -ge 2 ] || usage; output_dir=$2; shift 2 ;;
    *) usage ;;
  esac
done

[ -n "$image" ] && [ -f "$image" ] || usage
[ -n "$output_dir" ] || usage
command -v debugfs >/dev/null 2>&1 || { echo "debugfs is required" >&2; exit 1; }
mkdir -p "$output_dir"
proof="$output_dir/content-process-crash-proof.json"
rm -f "$proof"
debugfs -R "dump -p /var/lib/trillionnium-d2i/content-process-crash-proof.json $proof" "$image" >/dev/null 2>&1
[ -s "$proof" ] || { echo "content-process crash proof was not persisted in the integrated image" >&2; exit 1; }
jq -e '.status == "PASS_ACTUAL_CONTENT_PROCESS_CRASH_AND_RECOVERY"' "$proof" >/dev/null
chmod 0644 "$proof"
sha256sum "$proof" > "$output_dir/content-process-crash-proof.sha256"
