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
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || {
  echo "cannot locate D1 QEMU script directory" >&2
  exit 1
}
# Check the raw spellings before canonicalization.  ``readlink -f`` would
# otherwise erase a symlinked workspace/output parent and let subsequent
# writes escape the caller's intended tree.
# ShellCheck resolves source directives from the repository working directory.
# Keep this root-relative so the same annotation works in CI and locally.
# shellcheck source=tools/reject_symlink_path.sh
source "$script_dir/../../tools/reject_symlink_path.sh"
if ! reject_symlink_path "$workspace" "D1 workspace"; then
  exit 1
fi
if ! reject_symlink_path "$output_dir" "D1 output directory"; then
  exit 1
fi
if ! workspace=$(readlink -f -- "$workspace"); then
  echo "cannot canonicalize D1 workspace" >&2
  exit 1
fi
[[ -d "$workspace" ]] || {
  echo "D1 workspace is not a directory: $workspace" >&2
  exit 1
}
mkdir -p -- "$output_dir"
if ! reject_symlink_path "$output_dir" "D1 output directory"; then
  exit 1
fi
if ! output_dir=$(readlink -f -- "$output_dir"); then
  echo "cannot canonicalize D1 output directory" >&2
  exit 1
fi
[[ -d "$output_dir" && ! -L "$output_dir" ]] || {
  echo "D1 output path is not a regular directory: $output_dir" >&2
  exit 1
}
safe_io="$workspace/tools/qemu_safe_io.py"
require_regular_path "$safe_io" "D1 safe I/O helper" || exit 1
[[ -f "$safe_io" ]] || {
  echo "D1 safe I/O helper is absent: $safe_io" >&2
  exit 1
}
logs="$output_dir/logs"
evidence="$output_dir/evidence"
ensure_directory() {
  local directory=$1
  local label=$2
  reject_symlink_path "$directory" "$label" || return 1
  mkdir -p -- "$directory" || return 1
  reject_symlink_path "$directory" "$label" || return 1
  [[ -d "$directory" && ! -L "$directory" ]] || {
    printf '%s is not a real directory: %s\n' "$label" "$directory" >&2
    return 1
  }
}

ensure_directory "$logs" "D1 pipeline logs" || exit 1
ensure_directory "$evidence" "D1 pipeline evidence" || exit 1
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
import os
import pathlib
import sys
import tempfile


def has_symlink_component(path: pathlib.Path) -> bool:
    """Return whether an existing component of *path* is a symlink."""

    lexical = path if path.is_absolute() else pathlib.Path.cwd() / path
    current = pathlib.Path(lexical.anchor)
    for component in lexical.parts:
        if component in {lexical.anchor, "", "."}:
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            if current.is_symlink():
                return True
        except OSError as error:
            raise OSError(f"cannot inspect result path component: {current}") from error
    return False


def atomic_write_text(path: pathlib.Path, text: str) -> None:
    """Write a generated result without following a preseeded path/link."""

    path = path if path.is_absolute() else pathlib.Path.cwd() / path
    if has_symlink_component(path.parent):
        raise OSError(f"result parent contains a symlink: {path.parent}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if has_symlink_component(path.parent):
        raise OSError(f"result parent contains a symlink: {path.parent}")

    descriptor = None
    temporary_path = None
    try:
        # mkstemp uses O_EXCL, so a pre-existing temporary symlink cannot be
        # opened.  The same-directory rename makes publication atomic.
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = pathlib.Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as stream:
            descriptor = None
            stream.write(text)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                # Some CI filesystems do not expose fsync; the rename remains
                # atomic even when durability cannot be requested.
                pass

        # os.replace swaps the directory entry and never follows a final
        # symlink.  Check before and after publication for fail-closed output.
        if has_symlink_component(path):
            raise OSError(f"refusing to overwrite symlink result: {path}")
        os.replace(temporary_path, path)
        temporary_path = None
        if has_symlink_component(path):
            raise OSError(f"result became a symlink: {path}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


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
atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")
PY
}

copy_if_file() {
  local source=$1
  local destination=$2
  local destination_parent

  # Empty optional inputs are expected during early-stage failures.  For any
  # non-empty path, inspect the raw spelling before any file test or helper
  # open can follow a link.  This also rejects FIFOs, sockets, devices, and
  # directories that a compromised builder could leave in an evidence location.
  [[ -n "$source" ]] || return 0
  reject_symlink_path "$source" "D1 evidence source" || return 1
  if [[ ! -e "$source" ]]; then
    return 0
  fi
  require_regular_path "$source" "D1 evidence source" || return 1
  [[ -f "$source" ]] || return 1

  destination_parent=$(dirname -- "$destination")
  ensure_directory "$destination_parent" "D1 evidence destination parent" || return 1
  require_regular_path "$destination" "D1 evidence destination" || return 1
  python3 "$safe_io" copy \
    --source "$source" --destination "$destination" || return 1
}

copy_regular_tree() {
  local source_root=$1
  local destination_root=$2
  local label=$3
  local source
  local relative

  reject_symlink_path "$source_root" "$label source" || return 1
  [[ -d "$source_root" && ! -L "$source_root" ]] || return 0
  ensure_directory "$destination_root" "$label destination" || return 1

  # Do not silently preserve links or special files in uploaded evidence.
  # ``find -P`` keeps traversal link-free; the explicit type check fails
  # closed if a nested symlink/FIFO/socket/device is present.
  if find -P "$source_root" -mindepth 1 \
      ! -type f ! -type d -print -quit | grep -q .; then
    printf '%s contains a non-regular entry\n' "$label source" >&2
    return 1
  fi

  while IFS= read -r -d '' source; do
    relative=${source#"$source_root"/}
    copy_if_file "$source" "$destination_root/$relative" || return 1
  done < <(find -P "$source_root" -mindepth 1 -type f -print0)
}

gather_evidence() {
  write_result || return 1
  copy_if_file "$result" "$evidence/pipeline-result.json" || return 1
  copy_if_file "$d1_lock" "$evidence/debian-d1.lock.v1.json" || return 1
  copy_if_file "$prepared_dir/prepared-inputs.json" \
    "$evidence/prepared-inputs.json" || return 1
  copy_if_file "$prepared_dir/exact-packages.txt" \
    "$evidence/exact-packages.txt" || return 1
  copy_if_file "$prepared_dir/expected-package-lock.tsv" \
    "$evidence/expected-package-lock.tsv" || return 1
  copy_if_file "$build_a/build-result.json" \
    "$evidence/build-a/build-result.json" || return 1
  copy_if_file "$build_a/package-lock.tsv" \
    "$evidence/build-a/package-lock.tsv" || return 1
  copy_if_file "$build_b/build-result.json" \
    "$evidence/build-b/build-result.json" || return 1
  copy_if_file "$build_b/package-lock.tsv" \
    "$evidence/build-b/package-lock.tsv" || return 1
  copy_if_file "$repro_result" "$evidence/reproducibility-result.json" || return 1
  if [[ -d "$qemu_result" ]]; then
    reject_symlink_path "$qemu_result" "D1 QEMU evidence" || return 1
    while IFS= read -r -d '' source; do
      copy_if_file "$source" "$evidence/$(basename -- "$source")" || return 1
    done < <(
      find -P "$qemu_result" -maxdepth 1 -type f \
        ! -name 'trillionnium-d1-qemu.ext4' -print0
    )
  fi
  if [[ -d "$logs" ]]; then
    copy_regular_tree "$logs" "$evidence/logs" "D1 pipeline logs" || true
  fi
  for build_root_base in "$build_a_root" "$build_b_root"; do
    [[ -n "$build_root_base" ]] || continue
    build_root="$build_root_base/candidate/logs"
    if [[ -d "$build_root" ]]; then
      local name
      # The candidate directory is shared by both builds; derive the evidence
      # bucket from its parent so build-a and build-b never overwrite logs.
      name=$(basename -- "$build_root_base")
      copy_regular_tree "$build_root" "$evidence/logs/$name" \
        "D1 $name build logs" || true
    fi
  done
  if [[ -d "$resolution_logs" ]]; then
    copy_regular_tree "$resolution_logs" "$evidence/logs/resolution" \
      "D1 resolution logs" || true
  fi
  while IFS= read -r -d '' file; do
    require_regular_path "$file" "D1 evidence file" || continue
    case "$file" in
      *.json|*.tsv|*.txt|*.log)
        # Keep only a bounded diagnostic tail through descriptor-backed,
        # atomic helper I/O; shell redirection and mv would reopen mutable
        # pathnames and can race a pre-seeded symlink.
        python3 "$safe_io" tail \
          --path "$file" --max-bytes 4194304 || continue
        ;;
    esac
  done < <(find -P "$evidence" -type f -size +4M -print0)
}

on_exit() {
  local code=$?
  local gather_code
  if [[ "$final_status" != PASS && -z "$failed_stage" ]]; then
    failed_stage=$current_stage
  fi
  # Evidence publication is part of a successful gate, not best-effort
  # diagnostics.  Preserve an existing stage failure, but turn a clean run
  # into a failure when required evidence could not be gathered.
  gather_evidence
  gather_code=$?
  if [[ "$gather_code" -ne 0 ]]; then
    echo "D1 evidence gathering failed (status=$gather_code)" >&2
    if [[ "$code" -eq 0 ]]; then
      code=1
    fi
  fi
  exit "$code"
}
trap on_exit EXIT

run_stage() {
  local name=$1
  shift
  current_stage=$name
  local log_path="$logs/$name.log"
  ensure_directory "$(dirname -- "$log_path")" "D1 stage log parent" || return 1
  require_regular_path "$log_path" "D1 stage log" || return 1

  # Run the stage with a descriptor opened O_NOFOLLOW/O_NONBLOCK.  This keeps
  # a preseeded symlink/FIFO from redirecting or blocking the qualification
  # gate, while preserving the exact argv (there is intentionally no shell
  # re-parsing of the child command).
  python3 - "$log_path" "$@" <<'PY'
import os
import stat
import subprocess
import sys

if len(sys.argv) < 3:
    raise SystemExit("stage command is missing")
log_path = sys.argv[1]
command = sys.argv[2:]
flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
flags |= getattr(os, "O_CLOEXEC", 0)
flags |= getattr(os, "O_NOFOLLOW", 0)
flags |= getattr(os, "O_NONBLOCK", 0)
try:
    descriptor = os.open(log_path, flags, 0o644)
except OSError as error:
    print(f"cannot open stage log safely: {log_path}: {error}", file=sys.stderr)
    raise SystemExit(1)
try:
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        print(f"stage log is not a regular file: {log_path}", file=sys.stderr)
        raise SystemExit(1)
    completed = subprocess.run(command, stdout=descriptor, stderr=subprocess.STDOUT)
    status = completed.returncode
finally:
    os.close(descriptor)

# subprocess uses a negative status for signal termination; shell commands
# conventionally expose the corresponding 128+signal status.
if status < 0:
    status = 128 + (-status)
raise SystemExit(status)
PY
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
# D1 is a qualification image: inject only the explicit feature-gated handler.
agent_portd="$workspace/target/release/hepta-agent-port-qualificationd"
agent_fixture="$workspace/target/release/hepta-agent-d1-fixture"
mke2fs_binary=$(readlink -f "$(command -v mke2fs)")
e2fsck_binary=$(readlink -f "$(command -v e2fsck)")
dumpe2fs_binary=$(readlink -f "$(command -v dumpe2fs)")
e2fsprogs_dir=$(dirname "$mke2fs_binary")
if [[ $(dirname "$e2fsck_binary") != "$e2fsprogs_dir" \
   || $(dirname "$dumpe2fs_binary") != "$e2fsprogs_dir" ]]; then
  echo "D1 filesystem tools do not share one exact reviewed prefix" >&2
  exit 1
fi
d1_root_path="$e2fsprogs_dir:/usr/sbin:/usr/bin:/sbin:/bin"

selection_status=$(D1_TOOLS_DIR="$workspace/tools" python3 - "$selection" <<'PY'
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(os.environ["D1_TOOLS_DIR"]).resolve()))
from gate_evidence_envelope import _has_symlink_component, load_json_strict

path = Path(sys.argv[1])
if _has_symlink_component(path):
    raise SystemExit(f"D1 selection path contains a symlink: {path}")
flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
try:
    descriptor = os.open(path, flags)
except OSError as error:
    raise SystemExit(f"D1 selection is absent or unsafe: {path}: {error}") from error
try:
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        raise SystemExit(f"D1 selection is not a regular file: {path}")
    with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
        descriptor = -1
        selection_document = load_json_strict(stream)
finally:
    if descriptor >= 0:
        os.close(descriptor)
if not isinstance(selection_document, dict):
    raise SystemExit("D1 selection must be a JSON object")
status = selection_document.get("status")
if not isinstance(status, str) or not status:
    raise SystemExit("D1 selection status is missing or malformed")
print(status)
PY
) || {
  echo "D1 selection status could not be read safely" >&2
  exit 1
}
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
  sudo env \
    PATH="$d1_root_path" \
    D1_MKE2FS_BINARY="$mke2fs_binary" \
    D1_E2FSCK_BINARY="$e2fsck_binary" \
    D1_DUMPE2FS_BINARY="$dumpe2fs_binary" \
    "$workspace/packaging/debian/image/build-d1-image.sh" \
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
  sudo env \
    PATH="$d1_root_path" \
    D1_MKE2FS_BINARY="$mke2fs_binary" \
    D1_E2FSCK_BINARY="$e2fsck_binary" \
    D1_DUMPE2FS_BINARY="$dumpe2fs_binary" \
    "$workspace/packaging/debian/image/build-d1-image.sh" \
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
