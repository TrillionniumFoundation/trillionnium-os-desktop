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

selection=$(readlink -f "$selection")
artifacts=$(readlink -f "$artifacts")
image=$(readlink -f "$image")
preparation=$(readlink -f "$preparation")
mkdir -p "$output_dir"
output_dir=$(readlink -f "$output_dir")
shared_evidence="$(dirname "$output_dir")/evidence/qemu"

capture_d2i_diagnostics() {
  local code=$?
  trap - EXIT
  set +e
  mkdir -p "$shared_evidence"
  if [[ -d "$output_dir" ]]; then
    while IFS= read -r -d '' file; do
      local name size
      name=$(basename "$file")
      [[ "$name" == "trillionnium-d2i-qemu.ext4" ]] && continue
      size=$(stat -c %s "$file" 2>/dev/null || echo 0)
      case "$name" in
        *.json|*.txt|*.log)
          if (( size > 4194304 )); then
            tail -c 4194304 "$file" > "$shared_evidence/$name"
          else
            cp "$file" "$shared_evidence/$name"
          fi
          ;;
        *.png)
          if (( size <= 8388608 )); then
            cp "$file" "$shared_evidence/$name"
          fi
          ;;
      esac
    done < <(find "$output_dir" -maxdepth 1 -type f -print0)
  fi
  cp "$preparation" "$shared_evidence/preparation.json" 2>/dev/null || true
  cp "$selection" "$shared_evidence/selection.json" 2>/dev/null || true
  printf 'script_exit_status=%s\n' "$code" > "$shared_evidence/script-exit-status.txt"
  exit "$code"
}
trap capture_d2i_diagnostics EXIT

for path in "$selection" "$image" "$preparation" \
  "$artifacts/vmlinuz" "$artifacts/initrd.img" "$artifacts/package-lock.tsv"; do
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
cp --sparse=always "$image" "$run_image"
: > "$serial_log"
: > "$qemu_log"

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
printf '%q ' "${qemu_command[@]}" > "$command_file"
printf '\n' >> "$command_file"
grep -q -- '-nic none' "$command_file"
if grep -Eq '(-net|-nic)[[:space:]]+(user|tap|bridge|socket)' "$command_file"; then
  echo "D2I QEMU command enables networking" >&2
  exit 1
fi

set +e
timeout --signal=TERM --kill-after=20s "${timeout_seconds}s" \
  "${qemu_command[@]}" > "$qemu_log" 2>&1
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

dump_guest_file() {
  local guest_path=$1
  local host_path=$2
  local log_path=$3
  debugfs -R "dump -p $guest_path $host_path" "$run_image" > "$log_path" 2>&1
  [[ -s $host_path ]]
}
dump_guest_file /var/lib/trillionnium-d2i/guest-acceptance.json \
  "$acceptance" "$output_dir/debugfs-acceptance.log"
dump_guest_file /var/lib/trillionnium-d2i/runtime-ready.json \
  "$runtime_ready" "$output_dir/debugfs-runtime-ready.log"
dump_guest_file /var/lib/trillionnium-d2i/servo-content-recovered.png \
  "$screenshot" "$output_dir/debugfs-screenshot.log"
dump_guest_file /var/lib/trillionnium-d2i/runtime-journal.txt \
  "$runtime_journal" "$output_dir/debugfs-runtime-journal.log"

python3 - "$acceptance" "$runtime_ready" <<'PY'
import json
import pathlib
import sys
acceptance = json.loads(pathlib.Path(sys.argv[1]).read_text())
runtime = json.loads(pathlib.Path(sys.argv[2]).read_text())
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
assert acceptance["actual_content_process_crash_proven"] is True, acceptance
assert acceptance["actual_crash_callbacks"] >= 1, acceptance
assert runtime["actual_content_process_crash_proven"] is True, runtime
assert runtime["actual_crash_callbacks"] >= 1, runtime
assert runtime["content_process_termination_observed"] is True, runtime
assert acceptance["release_ready"] is False, acceptance
assert runtime["status"] == "PASS_HEADED_SERVO_NATIVE_CHROME_SINGLE_CONTENT_RECOVERY", runtime
assert runtime["content_surface_limit"] == 1, runtime
assert runtime["content_generation"] == 2, runtime
assert runtime["frame_count"] >= 2, runtime
assert runtime["page_input_verified"] is True, runtime
assert runtime["ime_path_exercised"] is True, runtime
assert runtime["ime_composition_events_sent"] == 3, runtime
assert runtime["external_network_used"] is False, runtime
PY

post_image_sha=$(sha256sum "$run_image" | awk '{print $1}')
serial_sha=$(sha256sum "$serial_log" | awk '{print $1}')
acceptance_sha=$(sha256sum "$acceptance" | awk '{print $1}')
runtime_sha=$(sha256sum "$runtime_ready" | awk '{print $1}')
screenshot_sha=$(sha256sum "$screenshot" | awk '{print $1}')
package_lock_sha=$(sha256sum "$artifacts/package-lock.tsv" | awk '{print $1}')
python3 - "$output_dir/boot-result.json" <<PY
import json
import pathlib
result = {
  "schema": "trillionnium.desktop.d2i-qemu-boot-result.v1",
  "status": "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE",
  "machine": "$machine",
  "acceleration": "$acceleration",
  "memory_mib": $memory_mib,
  "vcpus": $vcpus,
  "network": "none",
  "direct_kernel_boot": True,
  "qemu_exit_status": $qemu_status,
  "serial_pass_marker": True,
  "prepared_image_sha256": "$expected_image_sha",
  "post_boot_image_sha256": "$post_image_sha",
  "serial_log_sha256": "$serial_sha",
  "guest_acceptance_sha256": "$acceptance_sha",
  "runtime_ready_sha256": "$runtime_sha",
  "recovery_screenshot_sha256": "$screenshot_sha",
  "package_lock_sha256": "$package_lock_sha",
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
    "product_agent_port_default_disabled": True,
    "network_enabled": False,
    "actual_content_process_crash_proven": True,
    "secure_boot_qualified": False,
    "release_ready": False
  }
}
pathlib.Path("$output_dir/boot-result.json").write_text(
  json.dumps(result, indent=2, sort_keys=True) + "\n"
)
PY
