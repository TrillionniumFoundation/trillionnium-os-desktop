#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-d1-boot-test.sh \
  --selection manifests/debian-d1.selection.json \
  --artifacts /path/build-a/artifacts \
  --output-dir /path/qemu-result
EOF
}

selection=
artifacts=
output_dir=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --selection) selection=$2; shift 2 ;;
    --artifacts) artifacts=$2; shift 2 ;;
    --output-dir) output_dir=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
if [[ -z "$selection" || -z "$artifacts" || -z "$output_dir" ]]; then
  usage >&2
  exit 2
fi

for command in qemu-system-x86_64 timeout debugfs python3 sha256sum jq; do
  command -v "$command" >/dev/null || {
    echo "required command is missing: $command" >&2
    exit 1
  }
done

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || {
  echo "cannot locate D1 QEMU script directory" >&2
  exit 1
}
# ShellCheck resolves source directives from the repository working directory.
# Keep this root-relative so the same annotation works in CI and locally.
# shellcheck source=tools/reject_symlink_path.sh
source "$script_dir/../../tools/reject_symlink_path.sh"
safe_io="$script_dir/../../tools/qemu_safe_io.py"
require_regular_path "$safe_io" "D1 safe I/O helper" || exit 1
reject_symlink_path "$selection" "D1 selection" || exit 1
reject_symlink_path "$artifacts" "D1 artifacts" || exit 1
reject_symlink_path "$output_dir" "D1 output directory" || exit 1
selection=$(readlink -f -- "$selection")
artifacts=$(readlink -f -- "$artifacts")
mkdir -p -- "$output_dir"
reject_symlink_path "$output_dir" "D1 output directory" || exit 1
output_dir=$(readlink -f -- "$output_dir")
[[ -d "$artifacts" ]] || {
  echo "D1 artifacts path is not a directory: $artifacts" >&2
  exit 1
}
[[ -d "$output_dir" ]] || {
  echo "D1 output path is not a directory: $output_dir" >&2
  exit 1
}
for name in build-result.json package-lock.tsv trillionnium-d1.ext4 vmlinuz initrd.img; do
  artifact_path="$artifacts/$name"
  require_regular_path "$artifact_path" "D1 artifact $name" || exit 1
  [[ -f "$artifact_path" ]] || {
    echo "D1 build artifact is missing: $name" >&2
    exit 1
  }
done

build_status=$(jq -er '.status' "$artifacts/build-result.json")
if [[ "$build_status" != PASS_BUILD_ONLY ]]; then
  echo "build result is not eligible for QEMU acceptance: $build_status" >&2
  exit 1
fi
machine=$(jq -er '.qemu.machine' "$selection")
acceleration=$(jq -er '.qemu.acceleration' "$selection")
memory_mib=$(jq -er '.qemu.memory_mib' "$selection")
vcpus=$(jq -er '.qemu.vcpus' "$selection")
network=$(jq -er '.qemu.network' "$selection")
timeout_seconds=$(jq -er '.qemu.timeout_seconds' "$selection")
if [[ "$machine" != q35 || "$acceleration" != tcg || "$network" != none ]]; then
  echo "D1 QEMU authority changed from q35/TCG/no-network" >&2
  exit 1
fi
if ! [[ "$timeout_seconds" =~ ^[0-9]+$ ]] \
  || (( timeout_seconds < 60 || timeout_seconds > 600 )); then
  echo "D1 QEMU timeout is outside the accepted range" >&2
  exit 1
fi

# The immutable candidate must not contain the activation marker. The writable
# QEMU copy may create it only during the acceptance transaction.
marker_audit="$output_dir/release-marker-audit.txt"
require_regular_path "$marker_audit" "D1 release-marker audit" || exit 1
set +e
python3 "$safe_io" run --log "$marker_audit" -- \
  debugfs -R 'stat /etc/hepta/enable-agent-port' \
  "$artifacts/trillionnium-d1.ext4"
marker_audit_status=$?
set -e
if [[ "$marker_audit_status" -ne 0 ]]; then
  echo "debugfs marker audit failed; refusing to treat the marker as absent" >&2
  cat "$marker_audit" >&2
  exit 1
fi
if grep -q 'Inode:' "$marker_audit"; then
  echo "release candidate contains the AgentPort enable marker" >&2
  exit 1
fi
if ! grep -q 'File not found by ext2_lookup' "$marker_audit"; then
  echo "debugfs marker audit did not prove an absent marker" >&2
  cat "$marker_audit" >&2
  exit 1
fi

run_image="$output_dir/trillionnium-d1-qemu.ext4"
serial_log="$output_dir/serial.log"
qemu_log="$output_dir/qemu.log"
command_file="$output_dir/qemu-command.txt"
acceptance_json="$output_dir/acceptance.json"
wayland_info="$output_dir/wayland-info.txt"
unauthorized_agent="$output_dir/unauthorized-agent.json"
authorized_initial="$output_dir/authorized-health-initial.json"
authorized_recovery="$output_dir/authorized-health-recovery.json"
agent_journal="$output_dir/agent-port-journal.txt"
boot_result="$output_dir/boot-result.json"
require_regular_path "$run_image" "D1 QEMU image" || exit 1
require_regular_path "$serial_log" "D1 serial log" || exit 1
require_regular_path "$qemu_log" "D1 QEMU log" || exit 1
require_regular_path "$command_file" "D1 QEMU command" || exit 1
require_regular_path "$acceptance_json" "D1 acceptance result" || exit 1
require_regular_path "$wayland_info" "D1 Wayland info" || exit 1
require_regular_path "$unauthorized_agent" "D1 unauthorized-agent result" || exit 1
require_regular_path "$authorized_initial" "D1 initial health result" || exit 1
require_regular_path "$authorized_recovery" "D1 recovery health result" || exit 1
require_regular_path "$agent_journal" "D1 AgentPort journal" || exit 1
require_regular_path "$boot_result" "D1 boot result" || exit 1
for log_path in \
  "$output_dir/debugfs-acceptance.log" \
  "$output_dir/debugfs-wayland-info.log" \
  "$output_dir/debugfs-unauthorized-agent.log" \
  "$output_dir/debugfs-authorized-initial.log" \
  "$output_dir/debugfs-authorized-recovery.log" \
  "$output_dir/debugfs-agent-journal.log"; do
  require_regular_path "$log_path" "D1 debugfs log" || exit 1
done
python3 "$safe_io" copy \
  --sparse \
  --source "$artifacts/trillionnium-d1.ext4" \
  --destination "$run_image"
python3 "$safe_io" truncate --path "$serial_log"
python3 "$safe_io" truncate --path "$qemu_log"

kernel_command_line=(
  root=/dev/vda
  rootfstype=ext4
  rw
  console=ttyS0,115200n8
  systemd.unit=trillionnium-d1-acceptance.target
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
  -chardev "file,id=d1serial,path=$serial_log"
  -serial chardev:d1serial
)
{
  printf '%q ' "${qemu_command[@]}"
  printf '\n'
} | python3 "$safe_io" write --path "$command_file"
if grep -Eq '(-net|-nic)[[:space:]]+(user|tap|bridge|socket)' "$command_file"; then
  echo "QEMU command unexpectedly enables networking" >&2
  exit 1
fi
grep -q -- '-nic none' "$command_file"

set +e
python3 "$safe_io" run --log "$qemu_log" -- \
  timeout --signal=TERM --kill-after=20s "${timeout_seconds}s" \
  "${qemu_command[@]}"
qemu_status=$?
set -e
if [[ "$qemu_status" -ne 0 ]]; then
  echo "QEMU D1 acceptance exited with status $qemu_status" >&2
  tail -n 240 "$serial_log" >&2 || true
  tail -n 120 "$qemu_log" >&2 || true
  exit 1
fi
if grep -q 'TRILLIONNIUM_D1_ACCEPTANCE_FAIL:' "$serial_log"; then
  echo "guest reported a D1 acceptance failure" >&2
  grep 'TRILLIONNIUM_D1_ACCEPTANCE_FAIL:' "$serial_log" >&2
  exit 1
fi
grep -q 'TRILLIONNIUM_D1_ACCEPTANCE_PASS' "$serial_log"

dump_guest_file() {
  local guest_path=$1
  local host_path=$2
  local log_path=$3
  local temporary
  local status=1
  # The image is consumed by debugfs by pathname.  Revalidate it immediately
  # before each read so a late replacement cannot turn diagnostics into an
  # arbitrary-host file read (or block on a FIFO).
  require_regular_path "$run_image" "D1 QEMU image" || return 1
  temporary=$(mktemp "$output_dir/.d1-guest-dump.XXXXXX") || return 1
  require_regular_path "$temporary" "D1 temporary guest dump" || {
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
dump_guest_file /var/lib/trillionnium-d1/acceptance.json \
  "$acceptance_json" "$output_dir/debugfs-acceptance.log"
dump_guest_file /var/lib/trillionnium-d1/wayland-info.txt \
  "$wayland_info" "$output_dir/debugfs-wayland-info.log"
dump_guest_file /var/lib/trillionnium-d1/unauthorized-agent.json \
  "$unauthorized_agent" "$output_dir/debugfs-unauthorized-agent.log"
dump_guest_file /var/lib/trillionnium-d1/authorized-health-initial.json \
  "$authorized_initial" "$output_dir/debugfs-authorized-initial.log"
dump_guest_file /var/lib/trillionnium-d1/authorized-health-recovery.json \
  "$authorized_recovery" "$output_dir/debugfs-authorized-recovery.log"
dump_guest_file /var/lib/trillionnium-d1/agent-port-journal.txt \
  "$agent_journal" "$output_dir/debugfs-agent-journal.log"

D1_TOOLS_DIR="$script_dir/../../tools" python3 - "$acceptance_json" <<'PY'
import json
import os
import pathlib
import stat
import sys

sys.path.insert(0, str(pathlib.Path(os.environ["D1_TOOLS_DIR"]).resolve()))
from gate_evidence_envelope import _has_symlink_component, load_json_strict

path = pathlib.Path(sys.argv[1])
if _has_symlink_component(path):
    raise AssertionError(f"acceptance result path contains a symlink: {path}")
flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
flags |= getattr(os, "O_NONBLOCK", 0)
try:
    descriptor = os.open(path, flags)
except OSError as error:
    raise AssertionError(f"acceptance result is absent or unsafe: {path}") from error
try:
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        raise AssertionError(f"acceptance result is not a regular file: {path}")
    with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
        descriptor = -1
        data = load_json_strict(stream)
finally:
    if descriptor >= 0:
        os.close(descriptor)
if not isinstance(data, dict):
    raise AssertionError("acceptance result must be a JSON object")
assert data["schema"] == "trillionnium.desktop.d1-acceptance.v2", data
assert data["status"] == "PASS", data
assert data["pid1"] == "systemd", data
for key in ["systemd", "udev", "dbus", "logind", "wayland_compositor"]:
    assert data[key] == "active", (key, data[key])
assert data["wayland_socket"] == "/run/hepta-desktop/wayland-0", data
assert data["network_enabled"] is False, data
agent = data["agent_port"]
for key in [
    "default_disabled",
    "marker_created_at_runtime_only",
    "unauthorized_peer_denied",
    "authorized_request_completed",
    "per_connection_teardown",
    "connection_kill_recovered",
    "marker_removed_before_poweroff",
    "socket_removed_before_poweroff",
]:
    assert agent[key] is True, (key, agent[key])
assert agent["socket_identity"] == "hepta-browserd:hepta-agent:660", agent
assert agent["per_connection_service_observed"].startswith(
    "hepta-browserd-agent@"
), agent
for key in [
    "package_lock_sha256",
    "package_set_sha256",
    "wayland_info_sha256",
    "weston_log_sha256",
]:
    value = data[key]
    assert isinstance(value, str) and len(value) == 64
    int(value, 16)
for key in [
    "initial_response_sha256",
    "recovery_response_sha256",
    "journal_sha256",
]:
    value = agent[key]
    assert isinstance(value, str) and len(value) == 64
    int(value, 16)
PY

grep -q 'interface:' "$wayland_info"
grep -q '"connection_admitted":false' "$unauthorized_agent"
grep -q '"status":"PASS"' "$authorized_initial"
grep -q '"status":"PASS"' "$authorized_recovery"
pre_image_sha256=$(jq -er '.image.sha256' "$artifacts/build-result.json")
post_image_sha256=$(sha256sum "$run_image" | awk '{print $1}')
serial_sha256=$(sha256sum "$serial_log" | awk '{print $1}')
acceptance_sha256=$(sha256sum "$acceptance_json" | awk '{print $1}')
wayland_info_sha256=$(sha256sum "$wayland_info" | awk '{print $1}')
package_lock_sha256=$(sha256sum "$artifacts/package-lock.tsv" | awk '{print $1}')
agent_journal_sha256=$(sha256sum "$agent_journal" | awk '{print $1}')

D1_TOOLS_DIR="$script_dir/../../tools" \
RESULT_PATH="$boot_result" \
MACHINE="$machine" \
ACCELERATION="$acceleration" \
MEMORY_MIB="$memory_mib" \
VCPUS="$vcpus" \
QEMU_STATUS="$qemu_status" \
ACCEPTANCE_SHA256="$acceptance_sha256" \
SERIAL_SHA256="$serial_sha256" \
WAYLAND_INFO_SHA256="$wayland_info_sha256" \
PACKAGE_LOCK_SHA256="$package_lock_sha256" \
AGENT_JOURNAL_SHA256="$agent_journal_sha256" \
PRE_IMAGE_SHA256="$pre_image_sha256" \
POST_IMAGE_SHA256="$post_image_sha256" \
python3 - <<'PY'
import json, pathlib
import os
import sys

sys.path.insert(0, os.environ["D1_TOOLS_DIR"])
from qemu_safe_io import write_text

result = {
  "schema": "trillionnium.desktop.d1-qemu-boot-result.v2",
  "status": "PASS_QEMU_PID1_WAYLAND_AND_AGENT_PORT",
  "machine": os.environ["MACHINE"],
  "acceleration": os.environ["ACCELERATION"],
  "memory_mib": int(os.environ["MEMORY_MIB"]),
  "vcpus": int(os.environ["VCPUS"]),
  "network": "none",
  "direct_kernel_boot": True,
  "qemu_exit_status": int(os.environ["QEMU_STATUS"]),
  "serial_pass_marker": True,
  "guest_acceptance_sha256": os.environ["ACCEPTANCE_SHA256"],
  "serial_log_sha256": os.environ["SERIAL_SHA256"],
  "wayland_info_sha256": os.environ["WAYLAND_INFO_SHA256"],
  "package_lock_sha256": os.environ["PACKAGE_LOCK_SHA256"],
  "agent_port_journal_sha256": os.environ["AGENT_JOURNAL_SHA256"],
  "pre_boot_image_sha256": os.environ["PRE_IMAGE_SHA256"],
  "post_boot_image_sha256": os.environ["POST_IMAGE_SHA256"],
  "release_marker_absent": True,
  "clean_poweroff": True,
  "claims": {
    "systemd_booted": True,
    "udev_active": True,
    "dbus_active": True,
    "logind_active": True,
    "headless_wayland_active": True,
    "agent_port_default_disabled": True,
    "agent_port_pid1_activation_validated": True,
    "unauthorized_peer_denied": True,
    "authorized_fixture_request": True,
    "per_connection_teardown": True,
    "connection_kill_recovered": True,
    "servo_started": False,
    "visible_window_created": False,
    "network_enabled": False,
    "secure_boot_qualified": False
  }
}
write_text(
  pathlib.Path(os.environ["RESULT_PATH"]),
  json.dumps(result, indent=2, sort_keys=True) + "\n",
  "D1 boot result",
)
PY
