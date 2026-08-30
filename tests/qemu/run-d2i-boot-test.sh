#!/bin/bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: run-d2i-boot-test.sh \
  --selection PATH \
  --artifacts PATH \
  --image PATH \
  --preparation PATH \
  --output-dir PATH
EOF
}

selection=
artifacts=
image=
preparation=
output_dir=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --selection) selection=$2; shift 2 ;;
    --artifacts) artifacts=$2; shift 2 ;;
    --image) image=$2; shift 2 ;;
    --preparation) preparation=$2; shift 2 ;;
    --output-dir) output_dir=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done
for value in selection artifacts image preparation output_dir; do
  [[ -n ${!value} ]] || { usage; exit 2; }
done
for command in qemu-system-x86_64 timeout debugfs python3 sha256sum jq grep; do
  command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 1; }
done

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || {
  echo "cannot locate D2I QEMU script directory" >&2
  exit 1
}
# ShellCheck resolves source directives from the repository working directory.
# Keep this root-relative so the same annotation works in CI and locally.
# shellcheck source=tools/reject_symlink_path.sh
source "$script_dir/../../tools/reject_symlink_path.sh"
safe_io="$script_dir/../../tools/qemu_safe_io.py"
require_regular_path "$safe_io" "D2I safe I/O helper" || exit 1
reject_symlink_path "$selection" "D2I selection" || exit 1
reject_symlink_path "$artifacts" "D2I artifacts" || exit 1
reject_symlink_path "$image" "D2I image" || exit 1
reject_symlink_path "$preparation" "D2I preparation" || exit 1
reject_symlink_path "$output_dir" "D2I output directory" || exit 1
selection=$(readlink -f -- "$selection")
artifacts=$(readlink -f -- "$artifacts")
image=$(readlink -f -- "$image")
preparation=$(readlink -f -- "$preparation")
mkdir -p -- "$output_dir"
reject_symlink_path "$output_dir" "D2I output directory" || exit 1
output_dir=$(readlink -f -- "$output_dir")
[[ -d "$artifacts" ]] || {
  echo "D2I artifacts path is not a directory: $artifacts" >&2
  exit 1
}
[[ -d "$output_dir" ]] || {
  echo "D2I output path is not a directory: $output_dir" >&2
  exit 1
}
for path in "$selection" "$image" "$preparation" \
  "$artifacts/vmlinuz" "$artifacts/initrd.img" "$artifacts/package-lock.tsv"; do
  require_regular_path "$path" "D2I input $path" || exit 1
  [[ -f $path && ! -L $path ]] || { echo "missing or unsafe D2I input: $path" >&2; exit 1; }
done
jq -e '.status == "PASS_DETERMINISTIC_INPUT_INJECTION"' "$preparation" >/dev/null
expected_image_sha=$(jq -er '.integrated_image_sha256' "$preparation")
actual_image_sha=$(sha256sum "$image" | awk '{print $1}')
[[ $actual_image_sha == "$expected_image_sha" ]] || { echo "D2I image digest drift" >&2; exit 1; }

machine=$(jq -er '.qemu.machine' "$selection")
acceleration=$(jq -er '.qemu.acceleration' "$selection")
memory_mib=$(jq -er '.qemu.memory_mib' "$selection")
vcpus=$(jq -er '.qemu.vcpus' "$selection")
network=$(jq -er '.qemu.network' "$selection")
timeout_seconds=$(jq -er '.qemu.timeout_seconds' "$selection")
[[ $machine == q35 && $acceleration == tcg && $network == none ]] || {
  echo "D2I QEMU authority changed from q35/TCG/no-network" >&2
  exit 1
}
if ! [[ $timeout_seconds =~ ^[0-9]+$ ]] || (( timeout_seconds < 60 || timeout_seconds > 600 )); then
  echo "D2I timeout outside accepted range" >&2
  exit 1
fi

run_image="$output_dir/trillionnium-d2i-qemu.ext4"
serial_log="$output_dir/serial.log"
qemu_log="$output_dir/qemu.log"
command_file="$output_dir/qemu-command.txt"
acceptance="$output_dir/guest-acceptance.json"
runtime_ready="$output_dir/runtime-ready.json"
screenshot="$output_dir/servo-content-recovered.png"
runtime_journal="$output_dir/runtime-journal.txt"
runtime_result="$output_dir/runtime-result.json"
runtime_state="$output_dir/runtime-state.json"
crash_proof="$output_dir/content-process-crash-proof.json"
crash_diagnostics="$output_dir/content-crash-proof-diagnostics.txt"
acceptance_diagnostics="$output_dir/guest-failure-diagnostics.txt"
boot_result="$output_dir/boot-result.json"
require_regular_path "$run_image" "D2I QEMU image" || exit 1
require_regular_path "$serial_log" "D2I serial log" || exit 1
require_regular_path "$qemu_log" "D2I QEMU log" || exit 1
require_regular_path "$command_file" "D2I QEMU command" || exit 1
require_regular_path "$acceptance" "D2I acceptance result" || exit 1
require_regular_path "$runtime_ready" "D2I runtime-ready result" || exit 1
require_regular_path "$screenshot" "D2I recovery screenshot" || exit 1
require_regular_path "$runtime_journal" "D2I runtime journal" || exit 1
require_regular_path "$runtime_result" "D2I runtime result" || exit 1
require_regular_path "$runtime_state" "D2I runtime state" || exit 1
require_regular_path "$crash_proof" "D2I crash proof" || exit 1
require_regular_path "$crash_diagnostics" "D2I crash diagnostics" || exit 1
require_regular_path "$acceptance_diagnostics" "D2I acceptance diagnostics" || exit 1
require_regular_path "$output_dir/content-process-identity.json" "D2I content identity" || exit 1
require_regular_path "$output_dir/content-sigkill-sent.json" "D2I SIGKILL receipt" || exit 1
require_regular_path "$output_dir/process-topology-pre-fault.json" "D2I pre-fault topology" || exit 1
require_regular_path "$output_dir/process-topology-post-termination.json" "D2I termination topology" || exit 1
require_regular_path "$output_dir/process-topology-post-recovery.json" "D2I recovery topology" || exit 1
require_regular_path "$boot_result" "D2I boot result" || exit 1
for log_path in \
  "$output_dir/debugfs-acceptance.log" \
  "$output_dir/debugfs-acceptance-diagnostics.log" \
  "$output_dir/debugfs-runtime-ready.log" \
  "$output_dir/debugfs-runtime-result.log" \
  "$output_dir/debugfs-runtime-state.log" \
  "$output_dir/debugfs-runtime-journal.log" \
  "$output_dir/debugfs-crash-proof.log" \
  "$output_dir/debugfs-crash-diagnostics.log" \
  "$output_dir/debugfs-identity.log" \
  "$output_dir/debugfs-sigkill.log" \
  "$output_dir/debugfs-topology-pre.log" \
  "$output_dir/debugfs-topology-term.log" \
  "$output_dir/debugfs-topology-recovery.log" \
  "$output_dir/debugfs-screenshot.log"; do
  require_regular_path "$log_path" "D2I debugfs log" || exit 1
done
python3 "$safe_io" copy --sparse --source "$image" --destination "$run_image"
python3 "$safe_io" truncate --path "$serial_log"
python3 "$safe_io" truncate --path "$qemu_log"

dump_guest_file() {
  local guest_path=$1
  local host_path=$2
  local log_path=$3
  local temporary
  local status=1
  # The image is consumed by debugfs by pathname.  Revalidate it immediately
  # before each read so a late replacement cannot turn diagnostics into an
  # arbitrary-host file read (or block on a FIFO).
  require_regular_path "$run_image" "D2I QEMU image" || return 1
  temporary=$(mktemp "$output_dir/.d2i-guest-dump.XXXXXX") || return 1
  require_regular_path "$temporary" "D2I temporary guest dump" || {
    rm -f -- "$temporary"
    return 1
  }
  if python3 "$safe_io" run --log "$log_path" -- \
      debugfs -R "dump -p $guest_path $temporary" "$run_image" \
      && [[ -s "$temporary" ]]; then
    if python3 "$safe_io" copy \
        --source "$temporary" --destination "$host_path"; then
      status=0
    fi
  fi
  rm -f -- "$temporary"
  return "$status"
}

# Always export the bounded guest records, including when QEMU or acceptance
# fails before the pass marker.  The previous gate only dumped these files on
# success, which hid the systemd ordering and injector diagnostics needed to
# repair a failed candidate.
collect_guest_diagnostics() {
  require_regular_path "$run_image" "D2I QEMU image" || return 0
  dump_guest_file /var/lib/trillionnium-d2i/guest-acceptance.json \
    "$acceptance" "$output_dir/debugfs-acceptance.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/guest-failure-diagnostics.txt \
    "$acceptance_diagnostics" "$output_dir/debugfs-acceptance-diagnostics.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/runtime-ready.json \
    "$runtime_ready" "$output_dir/debugfs-runtime-ready.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/runtime-result.json \
    "$runtime_result" "$output_dir/debugfs-runtime-result.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/runtime-state.json \
    "$runtime_state" "$output_dir/debugfs-runtime-state.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/runtime-journal.txt \
    "$runtime_journal" "$output_dir/debugfs-runtime-journal.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/content-process-crash-proof.json \
    "$crash_proof" "$output_dir/debugfs-crash-proof.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/content-crash-proof-diagnostics.txt \
    "$crash_diagnostics" "$output_dir/debugfs-crash-diagnostics.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/content-process-identity.json \
    "$output_dir/content-process-identity.json" "$output_dir/debugfs-identity.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/content-sigkill-sent.json \
    "$output_dir/content-sigkill-sent.json" "$output_dir/debugfs-sigkill.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/process-topology-pre-fault.json \
    "$output_dir/process-topology-pre-fault.json" "$output_dir/debugfs-topology-pre.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/process-topology-post-termination.json \
    "$output_dir/process-topology-post-termination.json" "$output_dir/debugfs-topology-term.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/process-topology-post-recovery.json \
    "$output_dir/process-topology-post-recovery.json" "$output_dir/debugfs-topology-recovery.log" || true
  dump_guest_file /var/lib/trillionnium-d2i/servo-content-recovered.png \
    "$screenshot" "$output_dir/debugfs-screenshot.log" || true
}

on_exit() {
  local status=$?
  collect_guest_diagnostics
  if [[ $status -ne 0 ]]; then
    printf '%s\n' 'D2I bounded guest diagnostics:' >&2
    for file in "$acceptance_diagnostics" "$crash_diagnostics" \
      "$runtime_state" "$runtime_journal"; do
      if [[ -s "$file" ]]; then
        printf '%s\n' "--- $file (tail) ---" >&2
        tail -n 160 "$file" >&2 || true
      fi
    done
  fi
  exit "$status"
}
trap on_exit EXIT

kernel_command_line=(
  root=/dev/vda
  rootfstype=ext4
  rw
  console=ttyS0,115200n8
  systemd.unit=trillionnium-d2i-acceptance.target
  systemd.show_status=yes
  systemd.log_target=console
  systemd.log_level=info
  panic=-1
)
qemu_command=(
  qemu-system-x86_64
  -machine "$machine,accel=$acceleration"
  -cpu max
  -smp "$vcpus"
  -m "$memory_mib"
  -nodefaults
  -no-reboot
  -display none
  -monitor none
  -nic none
  -device virtio-rng-pci
  -drive "file=$run_image,format=raw,if=virtio,cache=unsafe,discard=unmap"
  -kernel "$artifacts/vmlinuz"
  -initrd "$artifacts/initrd.img"
  -append "${kernel_command_line[*]}"
  -chardev "file,id=d2iserial,path=$serial_log"
  -serial chardev:d2iserial
)
{
  printf '%q ' "${qemu_command[@]}"
  printf '\n'
} | python3 "$safe_io" write --path "$command_file"
grep -q -- '-nic none' "$command_file"
if grep -Eq '(-net|-nic)[[:space:]]+(user|tap|bridge|socket)' "$command_file"; then
  echo "D2I QEMU command enables networking" >&2
  exit 1
fi

set +e
python3 "$safe_io" run --log "$qemu_log" -- \
  timeout --signal=TERM --kill-after=20s "${timeout_seconds}s" \
  "${qemu_command[@]}"
qemu_status=$?
set -e
if [[ $qemu_status -ne 0 ]]; then
  echo "QEMU D2I acceptance exited with status $qemu_status" >&2
  tail -n 300 "$serial_log" >&2 || true
  tail -n 160 "$qemu_log" >&2 || true
  exit 1
fi
if grep -q 'TRILLIONNIUM_D2I_ACCEPTANCE_FAIL:' "$serial_log"; then
  grep 'TRILLIONNIUM_D2I_ACCEPTANCE_FAIL:' "$serial_log" >&2
  exit 1
fi
grep -q 'TRILLIONNIUM_D2I_ACCEPTANCE_PASS' "$serial_log"

collect_guest_diagnostics

python3 - "$acceptance" "$runtime_ready" "$crash_proof" \
  "$script_dir/../../tools" <<'PY'
import io
import os
import pathlib
import sys
sys.path.insert(0, sys.argv[4])
from gate_evidence_envelope import load_json_strict
from qemu_safe_io import read_bytes

def read_json(path):
    try:
        payload = read_bytes(path, "D2I boot result")
        return load_json_strict(io.StringIO(payload.decode("utf-8")))
    except UnicodeDecodeError as error:
        raise AssertionError(f"D2I JSON is not UTF-8: {path}") from error

acceptance = read_json(pathlib.Path(sys.argv[1]))
runtime = read_json(pathlib.Path(sys.argv[2]))
proof = read_json(pathlib.Path(sys.argv[3]))
assert acceptance["schema"] == "trillionnium.desktop.d2i-guest-acceptance.v1", acceptance
assert acceptance["status"] == "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE", acceptance
for key in [
    "udev_active", "dbus_active", "logind_active", "headless_wayland_active",
    "headed_servo_runtime_completed", "trusted_chrome_survived_recovery",
    "page_input_verified", "ime_path_exercised",
    "product_agent_port_default_disabled", "product_agent_port_socket_absent",
]:
    assert acceptance[key] is True, (key, acceptance.get(key))
assert acceptance["network_enabled"] is False, acceptance
assert acceptance["actual_content_process_crash_proven"] is False, acceptance
assert acceptance["release_ready"] is False, acceptance
assert acceptance["external_crash_proof_status"] == \
    "PASS_EXTERNAL_CONTENT_PROCESS_TERMINATION_AND_RECOVERY", acceptance
assert acceptance["external_crash_injector_count"] == 1, acceptance
assert acceptance["runtime_internal_injector"] is False, acceptance
assert runtime["status"] == "PASS_HEADED_LOCAL_FIXTURE_ONLY", runtime
assert runtime["logical_content_webview_peak"] == 1, runtime
assert runtime["recovery_generation"] == 2, runtime
assert runtime["logical_webviews_created"] == 2, runtime
assert runtime["page_input_verified"] is True, runtime
assert runtime["ime_path_exercised"] is True, runtime
assert runtime["synthetic_ime_composition_events"] == 3, runtime
assert runtime["external_network_used"] is False, runtime
assert proof["status"] == "PASS_EXTERNAL_CONTENT_PROCESS_TERMINATION_AND_RECOVERY", proof
assert proof["injector_count"] == 1, proof
assert proof["runtime_internal_injector"] is False, proof
assert proof["killed_pid_disappeared"] is True, proof
assert proof["replacement_pid_distinct"] is True, proof
PY

post_image_sha=$(sha256sum "$run_image" | awk '{print $1}')
serial_sha=$(sha256sum "$serial_log" | awk '{print $1}')
acceptance_sha=$(sha256sum "$acceptance" | awk '{print $1}')
runtime_sha=$(sha256sum "$runtime_ready" | awk '{print $1}')
screenshot_sha=$(sha256sum "$screenshot" | awk '{print $1}')
crash_proof_sha=$(sha256sum "$crash_proof" | awk '{print $1}')
package_lock_sha=$(sha256sum "$artifacts/package-lock.tsv" | awk '{print $1}')
D2I_TOOLS_DIR="$script_dir/../../tools" \
RESULT_PATH="$boot_result" \
MACHINE="$machine" \
ACCELERATION="$acceleration" \
MEMORY_MIB="$memory_mib" \
VCPUS="$vcpus" \
QEMU_STATUS="$qemu_status" \
EXPECTED_IMAGE_SHA="$expected_image_sha" \
POST_IMAGE_SHA="$post_image_sha" \
SERIAL_SHA="$serial_sha" \
ACCEPTANCE_SHA="$acceptance_sha" \
RUNTIME_SHA="$runtime_sha" \
SCREENSHOT_SHA="$screenshot_sha" \
CRASH_PROOF_SHA="$crash_proof_sha" \
PACKAGE_LOCK_SHA="$package_lock_sha" \
python3 - <<'PY'
import json
import os
import pathlib
import sys
sys.path.insert(0, os.environ["D2I_TOOLS_DIR"])
from qemu_safe_io import write_text
result = {
  "schema": "trillionnium.desktop.d2i-qemu-boot-result.v1",
  "status": "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE",
  "machine": os.environ["MACHINE"],
  "acceleration": os.environ["ACCELERATION"],
  "memory_mib": int(os.environ["MEMORY_MIB"]),
  "vcpus": int(os.environ["VCPUS"]),
  "network": "none",
  "direct_kernel_boot": True,
  "qemu_exit_status": int(os.environ["QEMU_STATUS"]),
  "serial_pass_marker": True,
  "prepared_image_sha256": os.environ["EXPECTED_IMAGE_SHA"],
  "post_boot_image_sha256": os.environ["POST_IMAGE_SHA"],
  "serial_log_sha256": os.environ["SERIAL_SHA"],
  "guest_acceptance_sha256": os.environ["ACCEPTANCE_SHA"],
  "runtime_ready_sha256": os.environ["RUNTIME_SHA"],
  "recovery_screenshot_sha256": os.environ["SCREENSHOT_SHA"],
  "content_crash_proof_sha256": os.environ["CRASH_PROOF_SHA"],
  "package_lock_sha256": os.environ["PACKAGE_LOCK_SHA"],
  "clean_poweroff": True,
  "claims": {
    "systemd_booted": True,
    "udev_active": True,
    "dbus_active": True,
    "logind_active": True,
    "headless_wayland_active": True,
    "headed_servo_started": True,
    "native_window_created_under_headless_wayland": True,
    "trusted_chrome_survived_recovery": True,
    "single_content_surface": True,
    "page_input_verified": True,
    "ime_path_exercised": True,
    "external_content_process_termination_observed": True,
    "external_crash_injector_count": 1,
    "runtime_internal_injector": False,
    "product_agent_port_default_disabled": True,
    "network_enabled": False,
    "actual_content_process_crash_proven": False,
    "secure_boot_qualified": False,
    "release_ready": False
  }
}
write_text(
  pathlib.Path(os.environ["RESULT_PATH"]),
  json.dumps(result, indent=2, sort_keys=True) + "\n",
  "D2I boot result",
)
PY
