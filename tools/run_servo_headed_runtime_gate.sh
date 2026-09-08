#!/usr/bin/env bash
# Generated once from the reviewed permanent gate; do not self-modify.
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || {
  echo "cannot locate D0A-02 gate script directory" >&2
  exit 1
}
# ShellCheck resolves source directives from the repository working directory.
# Keep this root-relative so the same annotation works in CI and locally.
# shellcheck source=tools/reject_symlink_path.sh
source "$script_dir/reject_symlink_path.sh"

step_identities() {
set -euo pipefail
tested_sha=$(git rev-parse HEAD)
tested_tree_sha=$(git rev-parse 'HEAD^{tree}')
mapfile -t parents < <(
  git show -s --format='%P' HEAD | tr ' ' '\n' | sed '/^$/d'
)
merged_candidate_sha=
case "$EVENT_NAME" in
  pull_request)
    [[ ${#parents[@]} -eq 2 ]] || {
      echo "pull-request qualification requires an exact two-parent merge" >&2
      exit 1
    }
    # The merge event's base can be stale by the time a hosted runner starts.
    # Bind the tested first parent to the current main ref before accepting
    # any headed-runtime evidence for this candidate.
    git fetch --no-tags origin main
    current_main=$(git rev-parse origin/main)
    base_sha=${parents[0]}
    candidate_head_sha=${parents[1]}
    [[ "$base_sha" == "$current_main" ]] || {
      echo "merge first parent is not the current origin/main object" >&2
      exit 1
    }
    [[ -n "$EVENT_HEAD_SHA" && "$candidate_head_sha" == "$EVENT_HEAD_SHA" ]] || {
      echo "checked-out merge second parent is not the live PR head" >&2
      exit 1
    }
    evidence_mode=pr_synthetic_merge
    merged_candidate_sha=$candidate_head_sha
    ;;
  push)
    candidate_head_sha=$tested_sha
    if [[ "$GITHUB_REF_NAME" == main ]]; then
      [[ "$GITHUB_REF" == refs/heads/main ]] || {
        echo "exact-main headed qualification requires refs/heads/main" >&2
        exit 1
      }
      git fetch --no-tags origin main
      current_main=$(git rev-parse origin/main)
      [[ "$tested_sha" == "$current_main" ]] || {
        echo "tested push object is not the current origin/main object" >&2
        exit 1
      }
      [[ ${#parents[@]} -ge 1 ]] || {
        echo "exact-main qualification requires at least one parent" >&2
        exit 1
      }
      base_sha=${parents[0]}
      evidence_mode=exact_main_push
      if [[ ${#parents[@]} -ge 2 ]]; then
        merged_candidate_sha=${parents[1]}
      fi
      if [[ -n "${EVENT_BEFORE:-}" \
        && "${EVENT_BEFORE}" != "0000000000000000000000000000000000000000" ]]; then
        git cat-file -e "${EVENT_BEFORE}^{commit}" || {
          echo "main push event.before is not present in the checkout" >&2
          exit 1
        }
        git merge-base --is-ancestor "${EVENT_BEFORE}" "${parents[0]}" || {
          echo "main push first-parent history does not contain event.before" >&2
          exit 1
        }
      fi
    else
      git fetch --no-tags origin main
      base_sha=$(git merge-base HEAD origin/main)
      evidence_mode=candidate_branch_push
    fi
    ;;
  workflow_dispatch)
    candidate_head_sha=$tested_sha
    git fetch --no-tags origin main
    base_sha=$(git merge-base HEAD origin/main)
    evidence_mode=manual_exact_object
    ;;
  *)
    echo "unsupported event for D0A-02 evidence: $EVENT_NAME" >&2
    exit 1
    ;;
esac
git cat-file -e "$base_sha^{commit}"
git cat-file -e "$candidate_head_sha^{commit}"
[[ -z "$(git status --porcelain=v1)" ]]
{
  printf 'TESTED_SHA=%s\n' "$tested_sha"
  printf 'TESTED_TREE_SHA=%s\n' "$tested_tree_sha"
  printf 'BASE_SHA=%s\n' "$base_sha"
  printf 'CANDIDATE_HEAD_SHA=%s\n' "$candidate_head_sha"
  printf 'MERGED_CANDIDATE_SHA=%s\n' "$merged_candidate_sha"
  printf 'TESTED_PARENT_COUNT=%s\n' "${#parents[@]}"
  printf 'EVIDENCE_MODE=%s\n' "$evidence_mode"
} >> "$GITHUB_ENV"
printf 'mode=%s\nbase=%s\ncandidate=%s\ntested=%s\ntree=%s\nparents=%s\n' \
  "$evidence_mode" "$base_sha" "$candidate_head_sha" \
  "$tested_sha" "$tested_tree_sha" "${parents[*]:-none}"
}

step_verify_servo() {
set -euo pipefail
test "$(git -C servo-source rev-parse HEAD)" = "$SERVO_COMMIT"
test -z "$(git -C servo-source status --porcelain=v1)"
python3 - <<'PY'
from pathlib import Path
import sys

sys.path.insert(0, str(Path('tools').resolve()))
from gate_evidence_envelope import load_json_strict

def read_json(path):
    with path.open('r', encoding='utf-8') as stream:
        return load_json_strict(stream)

expected = '670ae8a70801b162e186f81cbb5bdd2d59c39108'
lock = read_json(Path('manifests/servo.lock.json'))
ledger = read_json(Path('manifests/servo-patch-ledger.v1.json'))
assert lock['commit'] == expected
assert ledger['servo_commit'] == expected
assert ledger['patch_count'] == 0 and ledger['patches'] == []
PY
}

step_install_deps() {
set -euo pipefail
sed -e '/^[[:space:]]*#/d' -e '/^[[:space:]]*$/d' \
  servo-source/python/servo/platform/linux_packages/apt/apt_common.txt \
  servo-source/python/servo/platform/linux_packages/apt/apt_ubuntu_only.txt \
  | sort -u > /tmp/servo-packages.txt
sudo apt-get update
xargs -r sudo apt-get install -y --no-install-recommends < /tmp/servo-packages.txt
sudo apt-get install -y --no-install-recommends \
  iproute2 mesa-utils x11-utils xdotool xvfb
sudo apt-get purge -y fonts-droid-fallback || true
sudo rm -rf /var/lib/apt/lists/*
}

step_install_rust() {
set -euo pipefail
SERVO_RUST_CHANNEL="$(python3 - <<'PY'
from pathlib import Path
import tomllib
print(tomllib.loads(Path('servo-source/rust-toolchain.toml').read_text())['toolchain']['channel'])
PY
)"
printf 'SERVO_RUST_CHANNEL=%s\n' "$SERVO_RUST_CHANNEL" >> "$GITHUB_ENV"
rustup toolchain install "$SERVO_RUST_CHANNEL" --profile minimal
rustup component add rustfmt --toolchain "$SERVO_RUST_CHANNEL"
RUSTUP_TOOLCHAIN="$SERVO_RUST_CHANNEL" rustc --version --verbose
RUSTUP_TOOLCHAIN="$SERVO_RUST_CHANNEL" cargo --version --verbose
}

step_install_overlay() {
set -euo pipefail
export RUSTUP_TOOLCHAIN="$SERVO_RUST_CHANNEL"
overlay="$RUNNER_TEMP/trillionnium_headed_runtime.rs"
reject_symlink_path "$RUNNER_TEMP" "D0A-02 runner temporary directory" || exit 1
reject_symlink_path "$overlay" "D0A-02 formatted overlay" || exit 1
require_regular_path "$PWD/experiments/servo-headed-runtime/src/main.rs" \
  "D0A-02 committed runtime source" || exit 1
require_regular_path "$PWD/experiments/servo-headed-runtime/fixture/index.html" \
  "D0A-02 committed fixture source" || exit 1
examples_dir="$PWD/servo-source/ports/servoshell/examples"
examples_parent=$(dirname -- "$examples_dir")
# Some exact Servo pins intentionally omit an examples directory.  Validate
# the tracked parent, create only the missing final component, and revalidate
# before writing the ephemeral product overlay.  This preserves the zero-patch
# checkout proof while avoiding a broad mkdir that could cross a symlink.
reject_symlink_path "$examples_parent" "D0A-02 Servo examples parent" || exit 1
if [[ ! -d "$examples_parent" || -L "$examples_parent" ]]; then
  echo "D0A-02 Servo examples parent is missing or unsafe" >&2
  exit 1
fi
reject_symlink_path "$examples_dir" "D0A-02 Servo examples directory" || exit 1
if [[ -L "$examples_dir" || ( -e "$examples_dir" && ! -d "$examples_dir" ) ]]; then
  echo "D0A-02 Servo examples directory is not a directory" >&2
  exit 1
fi
if [[ ! -e "$examples_dir" ]]; then
  mkdir -- "$examples_dir"
fi
reject_symlink_path "$examples_dir" "D0A-02 Servo examples directory" || exit 1
if [[ ! -d "$examples_dir" || -L "$examples_dir" ]]; then
  echo "D0A-02 Servo examples directory is missing or unsafe" >&2
  exit 1
fi
cp experiments/servo-headed-runtime/src/main.rs "$overlay"
rustfmt --edition 2024 "$overlay"
rustfmt --edition 2024 --check "$overlay"
runtime_example="$examples_dir/trillionnium_headed_runtime.rs"
fixture_example="$examples_dir/trillionnium_headed_fixture.html"
require_regular_path "$runtime_example" "D0A-02 Servo runtime example" || exit 1
require_regular_path "$fixture_example" "D0A-02 Servo fixture example" || exit 1
install -D -m 0644 "$overlay" \
    "$runtime_example"
install -D -m 0644 experiments/servo-headed-runtime/fixture/index.html \
    "$fixture_example"
require_regular_path "$runtime_example" "D0A-02 Servo runtime example" || exit 1
require_regular_path "$fixture_example" "D0A-02 Servo fixture example" || exit 1
{
  printf 'FORMATTED_OVERLAY_SHA256=%s\n' "$(sha256sum "$overlay" | cut -d' ' -f1)"
  printf 'COMMITTED_SOURCE_SHA256=%s\n' \
    "$(sha256sum experiments/servo-headed-runtime/src/main.rs | cut -d' ' -f1)"
} >> "$GITHUB_ENV"
}

step_compile() {
set -euo pipefail
export RUSTUP_TOOLCHAIN="$SERVO_RUST_CHANNEL"
reject_symlink_path "$PWD/artifacts/servo-headed-runtime" \
  "D0A-02 compile artifact directory" || exit 1
mkdir -p artifacts/servo-headed-runtime
cargo check --locked --manifest-path servo-source/Cargo.toml \
  -p servoshell --example trillionnium_headed_runtime \
  --no-default-features --features bundled,gamepad,js_jit,max_log_level \
  2>&1 | tee artifacts/servo-headed-runtime/cargo-check.log
cargo build --locked --manifest-path servo-source/Cargo.toml \
  -p servoshell --example trillionnium_headed_runtime \
  --no-default-features --features bundled,gamepad,js_jit,max_log_level \
  2>&1 | tee artifacts/servo-headed-runtime/cargo-build.log
}

step_run_runtime() {
set -euo pipefail
output="$PWD/artifacts/servo-headed-runtime/runtime"
reject_symlink_path "$output" "D0A-02 runtime evidence directory" || exit 1
mkdir -p "$output"
reject_symlink_path "$output" "D0A-02 runtime evidence directory" || exit 1
export HEPTA_D0A02_OUTPUT="$output"
export RUST_BACKTRACE=1

Xvfb :99 -screen 0 1280x900x24 -nolisten tcp >"$output/xvfb.log" 2>&1 &
xvfb_pid=$!
app_pid=
injector_pid=
cleanup() {
  if [[ -n "${app_pid:-}" ]]; then
    kill "$app_pid" 2>/dev/null || true
    wait "$app_pid" 2>/dev/null || true
  fi
  if [[ -n "${injector_pid:-}" ]]; then
    kill "$injector_pid" 2>/dev/null || true
    wait "$injector_pid" 2>/dev/null || true
  fi
  kill "$xvfb_pid" 2>/dev/null || true
  wait "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT
export DISPLAY=:99
for _ in $(seq 1 100); do
  xdpyinfo >/dev/null 2>&1 && break
  sleep 0.1
done
xdpyinfo >"$output/xdpyinfo.txt"

python3 "$PWD/tools/inject_servo_content_process.py" \
  --state-dir "$output" --timeout-seconds 120 \
  >"$output/external-injector.log" 2>&1 &
injector_pid=$!
servo-source/target/debug/examples/trillionnium_headed_runtime \
  >"$output/runtime.log" 2>&1 &
app_pid=$!
for _ in $(seq 1 600); do
  [[ -f "$output/input-ready" ]] && break
  kill -0 "$injector_pid" 2>/dev/null || {
    cat "$output/external-injector.log" >&2 || true
    exit 1
  }
  kill -0 "$app_pid" 2>/dev/null || {
    cat "$output/runtime.log" >&2
    exit 1
  }
  sleep 0.1
done
test -f "$output/input-ready"

window_id="$(xdotool search --name 'TrillionniumOS Desktop.*D0A-02' | head -n1)"
test -n "$window_id"
xwininfo -id "$window_id" >"$output/xwininfo.txt"
xdotool windowfocus --sync "$window_id"
test "$(xdotool getwindowfocus)" = "$window_id"

xdotool mousemove --sync --window "$window_id" 200 132
xdotool mousedown 1
xdotool mouseup 1
xdotool key k
xdotool mousemove --sync --window "$window_id" 400 164
xdotool mousedown 1
xdotool mouseup 1
xdotool click 5
xdotool mousemove --sync --window "$window_id" 200 132
xdotool mousedown 1
xdotool mouseup 1

ps -eo pid,ppid,stat,args >"$output/process-table-during-input.txt"
timeout 180 tail --pid="$app_pid" -f /dev/null
wait "$app_pid"
app_pid=
wait "$injector_pid"
injector_pid=
ps -eo pid,ppid,stat,args >"$output/process-table-after-result.txt"
}

step_enforce_evidence() {
set -euo pipefail
reject_symlink_path "$PWD/artifacts/servo-headed-runtime/runtime" \
  "D0A-02 runtime evidence directory" || exit 1
python3 - <<'PY'
from pathlib import Path
import hashlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, str(Path('tools').resolve()))
from gate_evidence_envelope import (
    _has_symlink_component,
    _open_artifact,
    load_json_strict,
)

root = Path('artifacts/servo-headed-runtime/runtime')

def read_artifact_bytes(path):
    relative = path.relative_to(root).as_posix()
    with _open_artifact(root, relative) as stream:
        return stream.read()

def read_repo_bytes(relative):
    with _open_artifact(Path('.'), relative) as stream:
        return stream.read()

def read_artifact_text(path):
    try:
        return read_artifact_bytes(path).decode('utf-8')
    except UnicodeDecodeError as error:
        raise AssertionError(f'non-UTF-8 artifact: {path}') from error

def read_json(path):
    try:
        payload = read_artifact_bytes(path).decode('utf-8')
    except UnicodeDecodeError as error:
        raise AssertionError(f'non-UTF-8 JSON artifact: {path}') from error
    return load_json_strict(io.StringIO(payload))

def write_json_artifact(path, value):
    """Atomically write a generated JSON artifact without following links."""
    relative = path.relative_to(root).as_posix()
    if _has_symlink_component(path.parent):
        raise AssertionError(f'artifact parent contains a symlink: {relative}')
    path.parent.mkdir(parents=True, exist_ok=True)
    if _has_symlink_component(path.parent):
        raise AssertionError(f'artifact parent contains a symlink: {relative}')
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', closefd=True) as stream:
            descriptor = -1
            stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                pass
        if _has_symlink_component(path):
            raise AssertionError(f'artifact destination contains a symlink: {relative}')
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

path = root / 'runtime-result.json'
report = read_json(path)
receipt = read_json(root / 'content-sigkill-sent.json')
assert report['schema'] == 'trillionnium.desktop.d0a02-headed-runtime.v2'
assert report['status'] == 'PASS_HEADED_LOCAL_FIXTURE_ONLY'
assert report['servo_commit'] == '670ae8a70801b162e186f81cbb5bdd2d59c39108'
assert report['window_created'] is True
assert report['trusted_chrome_separate_from_content'] is True
assert report['callback_identity_enforced'] is True
assert isinstance(report['stale_callbacks_ignored'], int)
assert report['stale_callbacks_ignored'] >= 0
assert report['logical_content_webview_peak'] == 1
assert report['logical_webviews_created'] == 2
assert report['logical_webviews_invalidated'] == 1
assert report['logical_webviews_live_at_result'] == 1
assert report['initial_generation'] == 1
assert report['recovery_generation'] == 2
assert all(report[key] is True for key in [
    'chrome_initial_pixels_verified',
    'chrome_crash_pixels_verified',
    'chrome_recovery_pixels_verified',
    'trusted_window_survived_content_crash',
])
assert report['native_pointer_events'] > 0
assert report['native_button_events'] >= 4
assert report['native_wheel_events'] > 0
assert report['native_keyboard_events'] >= 2
assert report['native_ime_events'] > 0
assert report['synthetic_ime_composition_events'] == 3
assert report['input_handled_callbacks'] >= 6
assert report['input_method_controls'] > 0
assert report['popup_requests_denied'] > 0
assert report['external_navigation_requests_denied'] > 0

initial = report['initial_page_evidence']
assert initial['generation'] == 1 and initial['loaded'] is True
assert initial['pointerMoves'] > 0 and initial['pointerDowns'] > 0
assert initial['clicks'] > 0 and initial['wheels'] > 0
assert 'k' in [str(item).lower() for item in initial['keyDowns']]
assert initial['popupAttempted'] is True
assert initial['externalNavigationAttempted'] is True
recovery = report['recovery_page_evidence']
assert recovery['generation'] == 2 and recovery['loaded'] is True

fault = report['fault_injection']
assert fault['generation'] == 1
assert fault['mechanism'] == 'external_SIGKILL'
assert isinstance(fault['selected_pid'], int) and fault['selected_pid'] > 1
assert isinstance(fault['selected_start_time'], int)
assert fault['selected_start_time'] > 0
for key in [
    'signal_sent',
    'exact_termination_observed',
    'old_process_absent',
]:
    assert fault[key] is True, (key, fault)
assert fault['servo_pipeline_panic_callback_required'] is False
assert isinstance(fault['servo_pipeline_panic_callback_observed'], bool)
assert isinstance(fault['servo_pipeline_panic_callback_reason'], str)

replacement = report['replacement_process']
assert replacement['generation'] == 2
assert replacement['distinct_from_fault_target'] is True
assert isinstance(replacement['pid'], int) and replacement['pid'] > 1
assert isinstance(replacement['start_time'], int)
assert replacement['start_time'] > 0
assert replacement['pid'] != fault['selected_pid']

pre = read_json(root / 'process-topology-pre-fault.json')
terminated = read_json(root / 'process-topology-post-termination.json')
recovered = read_json(root / 'process-topology-post-recovery.json')
assert pre['active_process_count'] == 1 and len(pre['processes']) == 1
assert terminated['active_process_count'] == 0
assert terminated['processes'] == []
assert recovered['active_process_count'] == 1
assert len(recovered['processes']) == 1
old = pre['processes'][0]
new = recovered['processes'][0]
assert (old['pid'], old['start_time']) == (
    fault['selected_pid'],
    fault['selected_start_time'],
)
assert (new['pid'], new['start_time']) == (
    replacement['pid'],
    replacement['start_time'],
)
assert old['pid'] != new['pid']
assert old['parent_pid'] == pre['embedder_pid']
assert new['parent_pid'] == recovered['embedder_pid']

selected_receipt = read_json(root / 'content-process-identity.json')
signal_receipt = read_json(root / 'content-sigkill-sent.json')
assert selected_receipt == {
    'generation': 1,
    'pid': fault['selected_pid'],
    'start_time': fault['selected_start_time'],
}
assert signal_receipt == {
    'generation': 1,
    'pid': fault['selected_pid'],
    'signal': 'SIGKILL',
    'start_time': fault['selected_start_time'],
}
assert receipt == signal_receipt
injector_log = read_artifact_text(root / 'external-injector.log')
assert injector_log.count('D2I host external SIGKILL delivered:') == 1

authority = report['authority']
assert authority['fixture_listener_loopback_only'] is True
for key in [
    'external_navigation_performed',
    'webdriver_listener_started',
    'browser_actor_started',
    'agent_port_enabled',
    'persistent_credentials_used',
    'clipboard_path_claimed',
    'clean_runtime_teardown_claimed',
    'product_ready',
]:
    assert authority[key] is False, (key, authority)

report['ime_evidence'] = {
    'native_winit_events_observed': report['native_ime_events'],
    'servo_input_method_controls_observed': report['input_method_controls'],
    'composition_events_submitted': report['synthetic_ime_composition_events'],
    'dom_composition_events_observed': len(initial['composition']),
    'claim_ceiling': (
        'basic embedder IME control and submission path only; '
        'DOM composition dispatch is not claimed by this gate'
    ),
}

artifacts = {}
for file in sorted(root.glob('*.png')):
    data = read_artifact_bytes(file)
    assert data.startswith(b'\x89PNG\r\n\x1a\n')
    artifacts[file.name] = {
        'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
    }
required = {
    'content-generation-1.png',
    'content-generation-2.png',
    'workspace-generation-1.png',
    'workspace-crash-placeholder.png',
    'workspace-generation-2.png',
}
assert required.issubset(artifacts)
report['artifacts'] = artifacts

evidence_files = [
    'content-process-identity.json',
    'content-sigkill-sent.json',
    'process-topology-pre-fault.json',
    'process-topology-post-termination.json',
    'process-topology-post-recovery.json',
]
evidence_file_digests = {
    name: hashlib.sha256(read_artifact_bytes(root / name)).hexdigest()
    for name in evidence_files
}
report['evidence_identity'] = {
    'repository': os.environ['GITHUB_REPOSITORY'],
    'event_name': os.environ['GITHUB_EVENT_NAME'],
    'ref': os.environ['GITHUB_REF'],
    'ref_name': os.environ['GITHUB_REF_NAME'],
    'promotion_authoritative': os.environ['EVIDENCE_MODE'] == 'exact_main_push',
    'mode': os.environ['EVIDENCE_MODE'],
    'base_sha': os.environ['BASE_SHA'],
    'candidate_head_sha': os.environ['CANDIDATE_HEAD_SHA'],
    'merged_candidate_sha': os.environ['MERGED_CANDIDATE_SHA'] or None,
    'tested_sha': os.environ['TESTED_SHA'],
    'tree_sha': os.environ['TESTED_TREE_SHA'],
    'parent_count': int(os.environ['TESTED_PARENT_COUNT']),
    'workflow_sha256': hashlib.sha256(
        read_repo_bytes('.github/workflows/servo-headed-runtime.yml')
    ).hexdigest(),
    'source_sha256': os.environ['COMMITTED_SOURCE_SHA256'],
    'formatted_overlay_sha256': os.environ['FORMATTED_OVERLAY_SHA256'],
    'fixture_sha256': hashlib.sha256(
        read_repo_bytes('experiments/servo-headed-runtime/fixture/index.html')
    ).hexdigest(),
    'servo_lock_sha256': hashlib.sha256(
        read_repo_bytes('manifests/servo.lock.json')
    ).hexdigest(),
    'evidence_file_sha256': evidence_file_digests,
}
write_json_artifact(path, report)

runtime_sha256 = hashlib.sha256(read_artifact_bytes(path)).hexdigest()
receipt = {
    'schema': 'trillionnium.desktop.d0a02-gate-evidence.v2',
    'status': 'PASS_CAUSAL_HEADED_HOST_ONLY',
    'runtime_result_sha256': runtime_sha256,
    'runtime_evidence_identity': report['evidence_identity'],
    'fault_identity': {
        'generation': 1,
        'pid': fault['selected_pid'],
        'start_time': fault['selected_start_time'],
        'signal': 'SIGKILL',
        'exact_termination_observed': True,
        'servo_pipeline_panic_callback_observed': fault['servo_pipeline_panic_callback_observed'],
    },
    'replacement_identity': {
        'generation': 2,
        'pid': replacement['pid'],
        'start_time': replacement['start_time'],
    },
    'claim_ceiling': {
        'headed_local_fixture_only': True,
        'clipboard_path': False,
        'clean_runtime_teardown': False,
        'debian_qemu_integration': False,
        'browser_actor': False,
        'agent_port': False,
        'external_effects': False,
        'release': False,
    },
}
write_json_artifact(root / 'gate-evidence.json', receipt)
PY
}

step_restore_servo() {
reject_symlink_path "$PWD/servo-source/ports/servoshell/examples/trillionnium_headed_runtime.rs" \
  "D0A-02 runtime overlay" || exit 1
reject_symlink_path "$PWD/servo-source/ports/servoshell/examples/trillionnium_headed_fixture.html" \
  "D0A-02 fixture overlay" || exit 1
rm -f \
  servo-source/ports/servoshell/examples/trillionnium_headed_runtime.rs \
  servo-source/ports/servoshell/examples/trillionnium_headed_fixture.html
test -z "$(git -C servo-source status --porcelain=v1)"
}

step_validate_repository() {
set -euo pipefail
validation_root="$RUNNER_TEMP/trillionnium-d0a02-validation"
rm -rf "$validation_root"
mkdir -p "$validation_root"
git archive --format=tar HEAD | tar -xf - -C "$validation_root"
python3 "$validation_root/tools/validate_repository.py"
python3 "$validation_root/tools/validate_project_truth.py"
}

case "${1:-}" in
  identities)
    step_identities
    ;;
  verify-servo)
    step_verify_servo
    ;;
  install-deps)
    step_install_deps
    ;;
  install-rust)
    step_install_rust
    ;;
  install-overlay)
    step_install_overlay
    ;;
  compile)
    step_compile
    ;;
  run-runtime)
    step_run_runtime
    ;;
  enforce-evidence)
    step_enforce_evidence
    ;;
  restore-servo)
    step_restore_servo
    ;;
  validate-repository)
    step_validate_repository
    ;;
  *)
    printf 'unknown Servo headed gate command: %s\n' "${1:-}" >&2
    exit 64
    ;;
esac
