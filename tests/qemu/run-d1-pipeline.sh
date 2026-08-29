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
evidence="$output_dir/evidence"
mkdir -p "$logs" "$evidence"
result="$output_dir/pipeline-result.json"
started_epoch=$(date +%s)
current_stage=initialization
failed_stage=
final_status=FAIL
stages_json='{}'
d1_lock=
prepared_dir=
build_a_root=
build_b_root=
build_a=
build_b=
repro_result=
qemu_result=
resolution_logs=

record_stage() {
  local name=$1
  local state=$2
  local code=$3
  stages_json=$(python3 - "$stages_json" "$name" "$state" "$code" <<'PY'
import json
import sys
value = json.loads(sys.argv[1])
value[sys.argv[2]] = {"status": sys.argv[3], "exit_code": int(sys.argv[4])}
print(json.dumps(value, sort_keys=True))
PY
  )
}

write_result() {
  local finished_epoch
  finished_epoch=$(date +%s)
  python3 - "$result" "$final_status" "$failed_stage" \
    "$started_epoch" "$finished_epoch" "$stages_json" <<'PY'
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
data = {
    "schema": "trillionnium.desktop.d1-pipeline-result.v2",
    "status": sys.argv[2],
    "failed_stage": sys.argv[3] or None,
    "started_unix": int(sys.argv[4]),
    "finished_unix": int(sys.argv[5]),
    "stages": json.loads(sys.argv[6]),
    "authority": {
        "qemu_network_enabled": False,
        "servo_started": False,
        "visible_window_created": False,
        "secure_boot_qualified": False,
        "release_qualified": False,
    },
}
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
PY
}

copy_if_file() {
  local source=$1
  local destination=$2
  if [[ -f "$source" ]]; then
    mkdir -p "$(dirname "$destination")"
    cp "$source" "$destination"
  fi
}

gather_evidence() {
  write_result
  copy_if_file "$result" "$evidence/pipeline-result.json"
  copy_if_file "$d1_lock" "$evidence/debian-d1.lock.v1.json"
  copy_if_file "$prepared_dir/prepared-inputs.json" \
    "$evidence/prepared-inputs.json"
  copy_if_file "$prepared_dir/exact-packages.txt" \
    "$evidence/exact-packages.txt"
  copy_if_file "$prepared_dir/expected-package-lock.tsv" \
    "$evidence/expected-package-lock.tsv"
  copy_if_file "$build_a/build-result.json" \
    "$evidence/build-a/build-result.json"
  copy_if_file "$build_a/package-lock.tsv" \
    "$evidence/build-a/package-lock.tsv"
  copy_if_file "$build_b/build-result.json" \
    "$evidence/build-b/build-result.json"
  copy_if_file "$build_b/package-lock.tsv" \
    "$evidence/build-b/package-lock.tsv"
  copy_if_file "$repro_result" "$evidence/reproducibility-result.json"
  if [[ -d "$qemu_result" ]]; then
    find "$qemu_result" -maxdepth 1 -type f \
      ! -name 'trillionnium-d1-qemu.ext4' \
      -exec cp {} "$evidence/" \;
  fi
  if [[ -d "$logs" ]]; then
    mkdir -p "$evidence/logs"
    cp -a "$logs/." "$evidence/logs/" 2>/dev/null || true
  fi
  for build_root in "$build_a_root/candidate/logs" "$build_b_root/candidate/logs"; do
    if [[ -d "$build_root" ]]; then
      local name
      name=$(basename "$(dirname "$build_root")")
      mkdir -p "$evidence/logs/$name"
      cp -a "$build_root/." "$evidence/logs/$name/" 2>/dev/null || true
    fi
  done
  if [[ -d "$resolution_logs" ]]; then
    mkdir -p "$evidence/logs/resolution"
    cp -a "$resolution_logs/." "$evidence/logs/resolution/" 2>/dev/null || true
  fi
  find "$evidence" -type f -size +4M -exec sh -c '
    for file do
      case "$file" in
        *.json|*.tsv|*.txt|*.log)
          tail -c 4194304 "$file" > "$file.tail"
          mv "$file.tail" "$file"
          ;;
      esac
    done
  ' sh {} +
}

on_exit() {
  local code=$?
  if [[ "$final_status" != PASS && -z "$failed_stage" ]]; then
    failed_stage=$current_stage
  fi
  gather_evidence || true
  exit "$code"
}
trap on_exit EXIT

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
  failed_stage=$name
  echo "D1 pipeline failed at stage $name; inspect $logs/$name.log" >&2
  return "$code"
}

selection="$workspace/manifests/debian-d1.selection.json"
requirements="$workspace/manifests/debian-d1.requirements.v1.json"
baseline_lock="$workspace/manifests/debian-snapshot.lock.v1.json"
resolution_root="$output_dir/resolution"
resolution_work="$resolution_root/work"
resolution_logs="$resolution_root/logs"
generated_lock="$resolution_root/debian-d1.lock.v1.json"
prepared_dir="$output_dir/prepared"
build_a_root="$output_dir/build-a"
build_b_root="$output_dir/build-b"
build_a="$build_a_root/candidate/artifacts"
build_b="$build_b_root/candidate/artifacts"
repro_result="$output_dir/reproducibility-result.json"
qemu_result="$output_dir/qemu"
agent_portd="$workspace/target/release/hepta-agent-portd"
agent_fixture="$workspace/target/release/hepta-agent-d1-fixture"

selection_status=$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["status"])' \
  "$selection")
if [[ "$selection_status" == COMMITTED_SIGNED_D1_PACKAGE_LOCK ]]; then
  d1_lock="$workspace/manifests/debian-d1.lock.v1.json"
  run_stage validate_committed_lock \
    test -f "$d1_lock" || exit $?
else
  d1_lock="$generated_lock"
  mkdir -p "$resolution_work" "$resolution_logs"
  run_stage resolve_signed_d1_closure \
    python3 "$workspace/tools/resolve_debian_snapshot_with_pinned_keys.py" \
      --requirements "$requirements" \
      --output "$d1_lock" \
      --work-dir "$resolution_work" \
      --logs "$resolution_logs" \
    || exit $?
fi

run_stage prepare_exact_inputs \
  python3 "$workspace/tools/prepare_d1_inputs.py" \
    --selection "$selection" \
    --baseline-lock "$baseline_lock" \
    --d1-lock "$d1_lock" \
    --requirements "$requirements" \
    --output-dir "$prepared_dir" \
  || exit $?

# Package downloads used to prove the signed closure are no longer required
# after the exact lock and input manifests have been materialized.
rm -rf "$resolution_work/apt-cache" "$resolution_work/apt-state" 2>/dev/null || true

run_stage build_first \
  sudo "$workspace/packaging/debian/image/build-d1-image.sh" \
    --selection "$selection" \
    --prepared-manifest "$prepared_dir/prepared-inputs.json" \
    --sources-list "$prepared_dir/sources.list" \
    --exact-packages "$prepared_dir/exact-packages.txt" \
    --expected-package-lock "$prepared_dir/expected-package-lock.tsv" \
    --agent-portd-binary "$agent_portd" \
    --agent-fixture-binary "$agent_fixture" \
    --overlay "$workspace/packaging/debian/image/rootfs-overlay" \
    --output-dir "$build_a_root" \
    --build-name candidate \
  || exit $?
sudo chown -R "$(id -u):$(id -g)" "$build_a_root"

run_stage build_second \
  sudo "$workspace/packaging/debian/image/build-d1-image.sh" \
    --selection "$selection" \
    --prepared-manifest "$prepared_dir/prepared-inputs.json" \
    --sources-list "$prepared_dir/sources.list" \
    --exact-packages "$prepared_dir/exact-packages.txt" \
    --expected-package-lock "$prepared_dir/expected-package-lock.tsv" \
    --agent-portd-binary "$agent_portd" \
    --agent-fixture-binary "$agent_fixture" \
    --overlay "$workspace/packaging/debian/image/rootfs-overlay" \
    --output-dir "$build_b_root" \
    --build-name candidate \
  || exit $?
sudo chown -R "$(id -u):$(id -g)" "$build_b_root"

run_stage compare_builds \
  python3 "$workspace/tools/compare_d1_builds.py" \
    --first "$build_a" \
    --second "$build_b" \
    --prepared-inputs "$prepared_dir/prepared-inputs.json" \
    --result "$repro_result" \
  || exit $?

# Preserve only small machine records from build B and the first rootfs archive
# after byte-for-byte comparison. QEMU needs build A's image, kernel, and initrd.
rm -f \
  "$build_b/rootfs.tar" \
  "$build_b/trillionnium-d1.ext4" \
  "$build_b/vmlinuz" \
  "$build_b/initrd.img" \
  "$build_a/rootfs.tar"

run_stage qemu_acceptance \
  "$workspace/tests/qemu/run-d1-boot-test.sh" \
    --selection "$selection" \
    --artifacts "$build_a" \
    --output-dir "$qemu_result" \
  || exit $?

record_stage pipeline PASS 0
final_status=PASS
failed_stage=
