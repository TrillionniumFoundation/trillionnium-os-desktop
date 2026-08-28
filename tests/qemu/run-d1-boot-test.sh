#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-d1-boot-test.sh \
  --artifacts /path/build-a/artifacts \
  --output-dir /path/qemu-result
EOF
}

artifacts=
output_dir=
timeout_seconds=180
while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifacts) artifacts=$2; shift 2 ;;
    --output-dir) output_dir=$2; shift 2 ;;
    --timeout-seconds) timeout_seconds=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
if [[ -z "$artifacts" || -z "$output_dir" ]]; then
  usage >&2
  exit 2
fi

for command in qemu-system-x86_64 timeout debugfs python3 sha256sum; do
  command -v "$command" >/dev/null || {
    echo "required command is missing: $command" >&2
    exit 1
  }
done
if ! [[ "$timeout_seconds" =~ ^[0-9]+$ ]] || (( timeout_seconds < 30 || timeout_seconds > 600 )); then
  echo "timeout must be between 30 and 600 seconds" >&2
  exit 2
fi

artifacts=$(readlink -f "$artifacts")
mkdir -p "$output_dir"
output_dir=$(readlink -f "$output_dir")
for name in build-result.json package-lock.tsv trillionnium-d1.ext4 vmlinuz initrd.img; do
  [[ -f "$artifacts/$name" ]] || {
    echo "D1 build artifact is missing: $name" >&2
    exit 1
  }
done

build_status=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$artifacts/build-result.json")
if [[ "$build_status" != PASS_BUILD_ONLY ]]; then
  echo "build result is not eligible for QEMU acceptance: $build_status" >&2
  exit 1
fi

run_image="$output_dir/trillionnium-d1-qemu.ext4"
serial_log="$output_dir/serial.log"
qemu_log="$output_dir/qemu.log"
command_file="$output_dir/qemu-command.txt"
acceptance_json="$output_dir/acceptance.json"
wayland_info="$output_dir/wayland-info.txt"
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
  -machine q35,accel=tcg
  -cpu max
  -smp 2
  -m 2048
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
  tail -n 200 "$serial_log" >&2 || true
  tail -n 100 "$qemu_log" >&2 || true
  exit 1
fi
if grep -q 'TRILLIONNIUM_D1_ACCEPTANCE_FAIL:' "$serial_log"; then
  echo "guest reported a D1 acceptance failure" >&2
  grep 'TRILLIONNIUM_D1_ACCEPTANCE_FAIL:' "$serial_log" >&2
  exit 1
fi
grep -q '^TRILLIONNIUM_D1_ACCEPTANCE_PASS$' "$serial_log"

debugfs -R "dump -p /var/lib/trillionnium-d1/acceptance.json $acceptance_json" \
  "$run_image" > "$output_dir/debugfs-acceptance.log" 2>&1
debugfs -R "dump -p /var/lib/trillionnium-d1/wayland-info.txt $wayland_info" \
  "$run_image" > "$output_dir/debugfs-wayland-info.log" 2>&1
[[ -s "$acceptance_json" ]]
[[ -s "$wayland_info" ]]

python3 - "$acceptance_json" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text())
assert data["schema"] == "trillionnium.desktop.d1-acceptance.v1", data
assert data["status"] == "PASS", data
for key in ["systemd", "udev", "dbus", "logind", "wayland_compositor"]:
    assert data[key] == "active", (key, data[key])
assert data["wayland_socket"] == "/run/hepta-desktop/wayland-0", data
assert data["network_enabled"] is False, data
for key in ["package_lock_sha256", "wayland_info_sha256", "weston_log_sha256"]:
    value = data[key]
    assert isinstance(value, str) and len(value) == 64
    int(value, 16)
PY

grep -q 'interface:' "$wayland_info"
pre_image_sha256=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image"]["sha256"])' "$artifacts/build-result.json")
post_image_sha256=$(sha256sum "$run_image" | awk '{print $1}')
serial_sha256=$(sha256sum "$serial_log" | awk '{print $1}')
acceptance_sha256=$(sha256sum "$acceptance_json" | awk '{print $1}')
wayland_info_sha256=$(sha256sum "$wayland_info" | awk '{print $1}')
package_lock_sha256=$(sha256sum "$artifacts/package-lock.tsv" | awk '{print $1}')

python3 - "$output_dir/boot-result.json" <<PY
import json, pathlib
result = {
  "schema": "trillionnium.desktop.d1-qemu-boot-result.v1",
  "status": "PASS_QEMU_BOOT_AND_HEADLESS_WAYLAND",
  "machine": "q35",
  "acceleration": "tcg",
  "memory_mib": 2048,
  "vcpus": 2,
  "network": "none",
  "direct_kernel_boot": True,
  "qemu_exit_status": $qemu_status,
  "serial_pass_marker": True,
  "guest_acceptance_sha256": "$acceptance_sha256",
  "serial_log_sha256": "$serial_sha256",
  "wayland_info_sha256": "$wayland_info_sha256",
  "package_lock_sha256": "$package_lock_sha256",
  "pre_boot_image_sha256": "$pre_image_sha256",
  "post_boot_image_sha256": "$post_image_sha256",
  "clean_poweroff": True,
  "claims": {
    "systemd_booted": True,
    "udev_active": True,
    "dbus_active": True,
    "logind_active": True,
    "headless_wayland_active": True,
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
