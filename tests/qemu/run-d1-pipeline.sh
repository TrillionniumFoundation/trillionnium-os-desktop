#!/bin/bash
set -uo pipefail

usage() {
  echo "Usage: run-d1-pipeline.sh --workspace PATH --output-dir PATH" >&2
}
workspace=
output_dir=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace) workspace=$2; shift 2 ;;
    --output-dir) output_dir=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done
if [[ -z "$workspace" || -z "$output_dir" ]]; then
  usage
  exit 2
fi
workspace=$(readlink -f "$workspace")
mkdir -p "$output_dir"
output_dir=$(readlink -f "$output_dir")
logs="$output_dir/logs"
mkdir -p "$logs"
result="$output_dir/pipeline-result.json"
started_epoch=$(date +%s)
current_stage=initialization
stages_json='{}'

record_stage() {
  local name=$1
  local state=$2
  local code=$3
  stages_json=$(python3 - "$stages_json" "$name" "$state" "$code" <<'PY'
import json, sys
value = json.loads(sys.argv[1])
value[sys.argv[2]] = {"status": sys.argv[3], "exit_code": int(sys.argv[4])}
print(json.dumps(value, sort_keys=True))
PY
  )
}

write_result() {
  local final_status=$1
  local failed_stage=${2:-}
  local finished_epoch
  finished_epoch=$(date +%s)
  python3 - "$result" "$final_status" "$failed_stage" "$started_epoch" "$finished_epoch" "$stages_json" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = {
  "schema": "trillionnium.desktop.d1-pipeline-result.v1",
  "status": sys.argv[2],
  "failed_stage": sys.argv[3] or None,
  "started_unix": int(sys.argv[4]),
  "finished_unix": int(sys.argv[5]),
  "stages": json.loads(sys.argv[6]),
  "authority": {
    "qemu_network_enabled": False,
    "servo_started": False,
    "visible_window_created": False,
    "secure_boot_qualified": False
  }
}
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
PY
}

run_stage() {
  local name=$1
  shift
  current_stage=$name
  "$@" >"$logs/$name.log" 2>&1
  local code=$?
  if [[ "$code" -eq 0 ]]; then
    record_stage "$name" PASS 0
    return 0
  fi
  record_stage "$name" FAIL "$code"
  write_result FAIL "$name"
  echo "D1 pipeline failed at stage $name; inspect $logs/$name.log" >&2
  return "$code"
}

selection="$workspace/manifests/debian-d1.selection.json"
packages="$workspace/packaging/debian/image/d1-packages.txt"
overlay="$workspace/packaging/debian/image/rootfs-overlay"
resolved_dir="$output_dir/resolved"
resolved_input="$resolved_dir/debian-d1.resolved.input.json"
sources_list="$resolved_dir/sources.list"
build_a_root="$output_dir/build-a"
build_b_root="$output_dir/build-b"
build_a="$build_a_root/candidate/artifacts"
build_b="$build_b_root/candidate/artifacts"
repro_result="$output_dir/reproducibility-result.json"
resolved_output="$output_dir/debian-d1.resolved.json"
qemu_result="$output_dir/qemu"

run_stage resolve_snapshot \
  python3 "$workspace/tools/resolve_debian_d1_lock.py" \
    --selection "$selection" \
    --output-dir "$resolved_dir" \
    --resolved-manifest "$resolved_input" \
    --sources-list "$sources_list" \
  || exit $?

run_stage build_first \
  sudo "$workspace/packaging/debian/image/build-d1-image.sh" \
    --selection "$selection" \
    --resolved-manifest "$resolved_input" \
    --sources-list "$sources_list" \
    --packages "$packages" \
    --overlay "$overlay" \
    --output-dir "$build_a_root" \
    --build-name candidate \
  || exit $?
sudo chown -R "$(id -u):$(id -g)" "$build_a_root"

run_stage build_second \
  sudo "$workspace/packaging/debian/image/build-d1-image.sh" \
    --selection "$selection" \
    --resolved-manifest "$resolved_input" \
    --sources-list "$sources_list" \
    --packages "$packages" \
    --overlay "$overlay" \
    --output-dir "$build_b_root" \
    --build-name candidate \
  || exit $?
sudo chown -R "$(id -u):$(id -g)" "$build_b_root"

run_stage compare_builds \
  python3 "$workspace/tools/compare_d1_builds.py" \
    --first "$build_a" \
    --second "$build_b" \
    --resolved-input "$resolved_input" \
    --resolved-output "$resolved_output" \
    --result "$repro_result" \
  || exit $?

run_stage qemu_acceptance \
  "$workspace/tests/qemu/run-d1-boot-test.sh" \
    --artifacts "$build_a" \
    --output-dir "$qemu_result" \
  || exit $?

record_stage pipeline PASS 0
write_result PASS ""
