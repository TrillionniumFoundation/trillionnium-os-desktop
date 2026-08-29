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

selection=$(readlink -f "$selection")
artifacts=$(readlink -f "$artifacts")
mkdir -p "$output_dir"
output_dir=$(readlink -f "$output_dir")
for name in build-result.json package-lock.tsv trillionnium-d1.ext4 vmlinuz initrd.img; do
  [[ -f "$artifacts/$name" ]] || {
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
debugfs -R 'stat /etc/hepta/enable-agent-port' \
  "$artifacts/trillionnium-d1.ext4" > "$marker_audit" 2>&1 || true
if grep -q 'Inode:' "$marker_audit"; then
  echo "release candidate contains the AgentPort enable marker" >&2
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
cp --sparse=always "$artifacts/trillionnium-d1.ext4" "$run_image"
: > "$serial_log"
: > "$qemu_log"

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
printf '%q ' "${qemu_command[@]}" > "$command_file"
printf '\n' >> "$command_file"
if grep -Eq '(-net|-nic)[[:space:]]+(user|tap|bridge|socket)' "$command_file"; then
  echo "QEMU command unexpectedly enables networking" >&2
  exit 1
fi
grep -q -- '-nic none' "$command_file"

set +e
timeout --signal=TERM --kill-after=20s "${timeout_seconds}s" \
  "${qemu_command[@]}" > "$qemu_log" 2>&1
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
  debugfs -R "dump -p $guest_path $host_path" "$run_image" > "$log_path" 2>&1
  [[ -s "$host_path" ]]
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

python3 - "$acceptance_json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text())
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

python3 - "$output_dir/boot-result.json" <<PY
import json, pathlib
result = {
  "schema": "trillionnium.desktop.d1-qemu-boot-result.v2",
  "status": "PASS_QEMU_PID1_WAYLAND_AND_AGENT_PORT",
  "machine": "$machine",
  "acceleration": "$acceleration",
  "memory_mib": $memory_mib,
  "vcpus": $vcpus,
  "network": "none",
  "direct_kernel_boot": True,
  "qemu_exit_status": $qemu_status,
  "serial_pass_marker": True,
  "guest_acceptance_sha256": "$acceptance_sha256",
  "serial_log_sha256": "$serial_sha256",
  "wayland_info_sha256": "$wayland_info_sha256",
  "package_lock_sha256": "$package_lock_sha256",
  "agent_port_journal_sha256": "$agent_journal_sha256",
  "pre_boot_image_sha256": "$pre_image_sha256",
  "post_boot_image_sha256": "$post_image_sha256",
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
pathlib.Path("$output_dir/boot-result.json").write_text(
  json.dumps(result, indent=2, sort_keys=True) + "\n"
)
PY
