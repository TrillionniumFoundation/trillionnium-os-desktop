#!/usr/bin/env bash
# Generated once from the reviewed permanent gate; do not self-modify.
set -euo pipefail

step_identities() {
set -euo pipefail
tested_sha=$(git rev-parse HEAD)
tested_tree_sha=$(git rev-parse 'HEAD^{tree}')
[[ "${GITHUB_EVENT_NAME:-}" == "$EVENT_NAME" && "${GITHUB_SHA:-}" == "$tested_sha" ]] || {
  echo "checkout does not bind the builtin GitHub event and commit" >&2
  exit 1
}
[[ "${GITHUB_REPOSITORY,,}" == trillionniumfoundation/trillionnium-os-desktop ]] || {
  echo "qualification event is for an unexpected repository" >&2
  exit 1
}
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
    base_sha=${parents[0]}
    candidate_head_sha=${parents[1]}
    [[ -n "$EVENT_HEAD_SHA" && "$candidate_head_sha" == "$EVENT_HEAD_SHA" ]] || {
      echo "checked-out merge second parent is not the live PR head" >&2
      exit 1
    }
    evidence_mode=pr_synthetic_merge
    merged_candidate_sha=$candidate_head_sha
    expected_base_ref=${EXPECTED_BASE_REF:-main}
    git check-ref-format --branch "$expected_base_ref" >/dev/null
    git fetch --no-tags origin "refs/heads/$expected_base_ref:refs/remotes/origin/$expected_base_ref"
    [[ "$base_sha" == "$(git rev-parse "refs/remotes/origin/$expected_base_ref")" ]] || {
      echo "checked-out merge first parent is not the current target branch" >&2
      exit 1
    }
    ;;
  push)
    [[ "$GITHUB_REF" == "refs/heads/$GITHUB_REF_NAME" ]] || {
      echo "push event ref does not bind its builtin branch name" >&2
      exit 1
    }
    candidate_head_sha=$tested_sha
    if [[ "$GITHUB_REF_NAME" == main ]]; then
      git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
      [[ "$tested_sha" == "$(git rev-parse refs/remotes/origin/main)" ]] || {
        echo "main push checkout is not the current main commit" >&2
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
import json

expected = '670ae8a70801b162e186f81cbb5bdd2d59c39108'
lock = json.loads(Path('manifests/servo.lock.json').read_text())
ledger = json.loads(Path('manifests/servo-patch-ledger.v1.json').read_text())
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
  iproute2 libx11-6 mesa-utils x11-utils xdotool xvfb
command -v xmessage
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
python3 tools/check_servo_resource_gate.py --servo-source servo-source
overlay="$RUNNER_TEMP/trillionnium_headed_runtime.rs"
cp experiments/servo-headed-runtime/src/main.rs "$overlay"
install -D -m 0644 experiments/servo-headed-runtime/src/input_ownership.rs \
  "$RUNNER_TEMP/input_ownership.rs"
install -D -m 0644 experiments/servo-headed-runtime/src/resource_gate.rs \
  "$RUNNER_TEMP/resource_gate.rs"
rustfmt --edition 2024 "$overlay"
rustfmt --edition 2024 --check "$overlay"
install -D -m 0644 "$overlay" \
  servo-source/ports/servoshell/examples/trillionnium_headed_runtime.rs
install -D -m 0644 "$RUNNER_TEMP/input_ownership.rs" \
  servo-source/ports/servoshell/examples/input_ownership.rs
install -D -m 0644 "$RUNNER_TEMP/resource_gate.rs" \
  servo-source/ports/servoshell/examples/resource_gate.rs
rustc --edition 2024 --test experiments/servo-headed-runtime/src/resource_gate.rs \
  -o "$RUNNER_TEMP/http-resource-gate-tests"
"$RUNNER_TEMP/http-resource-gate-tests"
install -D -m 0644 experiments/servo-headed-runtime/fixture/index.html \
  servo-source/ports/servoshell/examples/trillionnium_headed_fixture.html
{
  printf 'FORMATTED_OVERLAY_SHA256=%s\n' "$(sha256sum "$overlay" | cut -d' ' -f1)"
  printf 'COMMITTED_SOURCE_SHA256=%s\n' \
    "$(sha256sum experiments/servo-headed-runtime/src/main.rs | cut -d' ' -f1)"
} >> "$GITHUB_ENV"
}

step_compile() {
set -euo pipefail
export RUSTUP_TOOLCHAIN="$SERVO_RUST_CHANNEL"
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

# The permanent workflow's v1 negative corpus is independent of this file's old
# full v2 positive runner/verifier. Never route v1 results through those modes.
step_run_held_gestures_v1() {
unset PYTHONOPTIMIZE
python3 - <<'PY'
from contextlib import ExitStack
from pathlib import Path
import ctypes
import hashlib
import json
import os
import re
import resource
import signal
import socket
import subprocess
import time
import traceback
import uuid

root = Path.cwd()
output = root / 'artifacts/servo-headed-runtime/held-gestures-v1'
binary = root / 'servo-source/target/debug/examples/trillionnium_headed_runtime'
failure = 'native held gesture withdrawn; fresh Servo owner recovery is required'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(arguments, environment=None, timeout=5):
    return subprocess.run(arguments, env=environment, check=True, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def process_stat(pid):
    values = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'ppid': int(values[1]), 'pgid': int(values[2]),
            'session': int(values[3]), 'start_time': int(values[19]), 'state': values[0]}


def members(group):
    rows = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            row = process_stat(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
        if row['pgid'] == group:
            require(row['session'] == group, 'owned process group changed its session identity')
            rows.append(row)
    return sorted(rows, key=lambda row: row['pid'])


def spawn(arguments, environment, log, pass_fds=()):
    process = subprocess.Popen(arguments, env=environment, stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True, pass_fds=pass_fds)
    try:
        row = process_stat(process.pid)
        require(row['pgid'] == process.pid and row['session'] == process.pid,
                'new child does not own its new session and process group')
        process._hepta_identity = row
        process._hepta_cleanup_complete = False
    except BaseException:
        # The unreaped direct child still anchors its PID. Without the captured
        # session identity, only that child may be signalled, never a numeric group.
        try:
            os.kill(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        raise
    return process, row


def anchored_identity(process):
    expected = process._hepta_identity
    require(process.returncode is None, 'leader was reaped before owned group cleanup')
    current = process_stat(process.pid)
    require(all(current[key] == expected[key] for key in ('pid', 'start_time', 'pgid', 'session')),
            'captured leader PID/start-time/session/group identity no longer matches')
    return current


def observe_exit(process):
    anchored_identity(process)
    result = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
    if result is None:
        return None
    if result.si_code == os.CLD_EXITED:
        return result.si_status
    require(result.si_code in (os.CLD_KILLED, os.CLD_DUMPED), 'unexpected native waitid outcome')
    return -result.si_status


def wait_exit(process, seconds):
    deadline = time.monotonic() + seconds
    while True:
        result = observe_exit(process)
        if result is not None:
            return result
        require(time.monotonic() < deadline, 'bounded native exit observation expired')
        time.sleep(0.05)


def cleanup(process):
    if process is None:
        return []
    if process._hepta_cleanup_complete:
        return []  # No reused numeric PID/group is touched after the original closes.
    group = process.pid
    require(group > 1 and group != os.getpgrp(), 'refusing to clean an unowned group')
    anchored_identity(process)
    before = members(group)
    anchored_identity(process)
    try:
        os.killpg(group, signal.SIGTERM)
    except ProcessLookupError:
        pass
    # The harness is a Linux subreaper, so content children orphaned by the
    # native fixture's explicit exit can be reaped. Keep the unreaped leader as
    # the numeric session/group anchor until all other members have disappeared.
    started = time.monotonic()
    deadline = started + 7
    killed = False
    while True:
        anchored_identity(process)
        for row in members(group):
            if row['pid'] == group:
                continue
            try:
                os.waitpid(row['pid'], os.WNOHANG)
            except ChildProcessError:
                pass  # Still owned by a live leader; adoption happens on its exit.
        remaining = members(group)
        if observe_exit(process) is not None and all(row['pid'] == group for row in remaining):
            # The last member is our captured, exited leader. Only now may its
            # original PID/session be released; no later kill uses this number.
            process.wait(timeout=1)
            process._hepta_cleanup_complete = True
            return before
        if not killed and time.monotonic() >= started + 2:
            anchored_identity(process)
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            killed = True
        require(time.monotonic() < deadline, 'owned process group did not disappear after bounded cleanup')
        time.sleep(0.05)


def wait_for(predicate, seconds, process=None):
    deadline = time.monotonic() + seconds
    while True:
        value = predicate()
        if value:
            return value
        require(process is None or observe_exit(process) is None, 'native/helper process exited before readiness')
        require(time.monotonic() < deadline, 'bounded native readiness wait expired')
        time.sleep(0.05)


def unique_window(environment, title, pid=None):
    arguments = ['xdotool', 'search', '--onlyvisible']
    if pid is not None:
        arguments += ['--pid', str(pid)]
    arguments += ['--name', title]
    try:
        result = command(arguments, environment)
    except subprocess.CalledProcessError:
        return None
    windows = result.splitlines()
    require(len(windows) == 1, 'native stimulus did not bind one visible owned window')
    return int(windows[0])


def pointer(environment):
    x11 = ctypes.CDLL('libX11.so.6')
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XQueryPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)]
    x11.XQueryPointer.restype = ctypes.c_int
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(environment['DISPLAY'].encode())
    require(display, 'could not open the case X11 display for actual button observation')
    try:
        root_window, child = ctypes.c_ulong(), ctypes.c_ulong()
        root_x, root_y, window_x, window_y = (ctypes.c_int() for _ in range(4))
        mask = ctypes.c_uint()
        require(x11.XQueryPointer(display, x11.XDefaultRootWindow(display),
            ctypes.byref(root_window), ctypes.byref(child), ctypes.byref(root_x), ctypes.byref(root_y),
            ctypes.byref(window_x), ctypes.byref(window_y), ctypes.byref(mask)), 'XQueryPointer failed')
        return {'root_x': root_x.value, 'root_y': root_y.value,
                'child_window': child.value, 'button_mask': mask.value & 0x1f00}
    finally:
        x11.XCloseDisplay(display)


def listeners():
    rows = []
    for line in Path('/proc/self/net/tcp').read_text().splitlines()[1:]:
        fields = line.split()
        if fields[3] != '0A':
            continue
        address, port = fields[1].split(':')
        rows.append({'address': socket.inet_ntoa(bytes.fromhex(address)[::-1]),
                     'port': int(port, 16), 'inode': int(fields[9])})
    return rows


def fixture_listener(pid):
    inodes = set()
    for fd in Path(f'/proc/{pid}/fd').iterdir():
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        match = re.fullmatch(r'socket:\[(\d+)\]', target)
        if match:
            inodes.add(int(match[1]))
    owned = [row for row in listeners() if row['inode'] in inodes]
    require(len(owned) == 1 and owned[0]['address'] == '127.0.0.1' and owned[0]['port'] > 0,
            'native fixture did not own exactly one ephemeral IPv4 loopback listener')
    return owned[0]


def read_json(path):
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'duplicate diagnostic JSON key')
            value[key] = item
        return value
    data = path.read_bytes()
    require(0 < len(data) <= 2 * 1024 * 1024, 'diagnostic JSON exceeded its supported bound')
    return json.loads(data.decode('utf-8'), object_pairs_hook=unique_pairs)


def verify_case(directory, case, returncode):
    require(returncode == 1, 'native refusal must exit 1; timeout/signal/success is not negative evidence')
    report = read_json(directory / 'runtime-result.json')
    state = read_json(directory / 'runtime-state.json')
    gesture = read_json(directory / 'gesture-recovery-required.json')
    require(report == {'schema': 'trillionnium.desktop.d0a02-headed-runtime.v1', 'status': 'FAIL',
                      'failure': failure, 'servo_started': True, 'product_ready': False},
            'runtime did not report the exact held-gesture refusal')
    require(report['servo_started'] is True and report['product_ready'] is False,
            'runtime claim flags must be typed JSON booleans')
    expected_reasons = {'chrome': {'content_boundary'},
                        'window-leave': {'content_boundary', 'window_leave'},
                        'focus-loss': {'window_focus_lost'}}
    expected_gesture = {'schema': 'trillionnium.desktop.native-gesture-withdrawal.v1',
        'generation': 1, 'reason': gesture.get('reason'), 'held_button_count': 1,
        'recovery_required': True, 'owned_webview_handle_removed': True,
        'synthetic_mouse_release_sent': False, 'servo_mouse_state_reset_proven': False,
        'automatic_reconstruction_allowed': False, 'product_ready': False}
    require(gesture == expected_gesture and gesture['reason'] in expected_reasons[case]
            and type(gesture['generation']) is int and type(gesture['held_button_count']) is int,
            'typed withdrawal does not bind this native stimulus and generation')
    for key, expected in expected_gesture.items():
        if type(expected) is bool:
            require(gesture[key] is expected, 'withdrawal claim flags must be typed JSON booleans')
    require(state['schema'] == 'trillionnium.desktop.d0a02-runtime-state.v1'
            and state['failure'] == failure and type(state['generation']) is int
            and state['generation'] == 1, 'refusal changed its content generation')
    require(type(state['native_button_events']) is int and state['native_button_events'] == 1
            and type(state['native_pointer_events']) is int and state['native_pointer_events'] > 0,
            'case must admit exactly one native Down and no Up')
    require(type(state['native_wheel_events']) is int and state['native_wheel_events'] == 0
            and type(state['native_keyboard_events']) is int and state['native_keyboard_events'] == 0,
            'negative case admitted unrelated input')
    for key in ('load_complete', 'content_screenshot_saved', 'workspace_screenshot_saved',
                'focus_ready', 'input_marker_written', 'chrome_initial_ok'):
        require(state[key] is True, 'refusal was not exercised after actual initial native readiness')
    for key in ('synthetic_ime_sent', 'page_evidence_requested', 'initial_page_evidence_present',
                'recovery_page_evidence_present', 'crash_triggered', 'crash_observed',
                'crash_workspace_saved', 'recovery_started', 'chrome_recovery_ok'):
        require(state[key] is False, 'negative case must not qualify crash, synthetic IME or recovery')
    for name in ('content-generation-2.png', 'workspace-generation-2.png',
                 'content-process-identity.json', 'content-sigkill-sent.json', 'gate-evidence.json'):
        require(not (directory / name).exists(), 'negative case published a recovery/fault qualification artifact')
    return gesture


def run_case(case):
    directory = output / case
    directory.mkdir(mode=0o700)
    native = helper = xvfb = None
    fixture = None
    facts = {'case': case, 'stimulus': [], 'synthetic_mouse_up_injected': False}
    with ExitStack() as stack:
        try:
            display_path = directory / 'display-number'
            display_fd = stack.enter_context(display_path.open('w'))
            xvfb_log = stack.enter_context((directory / 'xvfb.log').open('w'))
            # Xvfb chooses a fresh display; every case gets a fresh physical button
            # state. No cleanup MouseUp can ever be delivered to an old WebView.
            xvfb, xvfb_identity = spawn(['Xvfb', '-displayfd', str(display_fd.fileno()),
                '-screen', '0', '1280x900x24', '-nolisten', 'tcp'], dict(os.environ), xvfb_log,
                pass_fds=(display_fd.fileno(),))
            number = wait_for(lambda: display_path.read_text().strip(), 10, xvfb)
            require(re.fullmatch(r'[0-9]+', number), 'Xvfb published an invalid display number')
            environment = dict(os.environ, DISPLAY=f':{number}', HEPTA_D0A02_OUTPUT=str(directory),
                               RUST_BACKTRACE='1')
            environment.pop('WAYLAND_DISPLAY', None)
            environment.pop('HEPTA_D0A02_INPUT_NONCE', None)
            (directory / 'xdpyinfo.txt').write_text(command(['xdpyinfo'], environment))
            if case == 'focus-loss':
                title = f'HEPTA held gesture focus withdrawal {uuid.uuid4().hex}'
                helper_log = stack.enter_context((directory / 'focus-helper.log').open('w'))
                helper, helper_identity = spawn(['xmessage', '-title', title, '-geometry',
                    '120x50+1100+10', '-buttons', 'Close:0', 'Native focus withdrawal'], environment, helper_log)
                helper_window = wait_for(lambda: unique_window(environment, f'^{title}$'), 10, helper)
                facts['focus_helper'] = {**helper_identity, 'window_id': helper_window, 'title': title}
            native_log = stack.enter_context((directory / 'runtime.log').open('w'))
            native, identity = spawn([str(binary)], environment, native_log)
            facts['native_process'] = identity
            require(Path(f'/proc/{native.pid}/exe').resolve() == binary.resolve(),
                    'native process executable changed from the compiled pin target')
            wait_for(lambda: (directory / 'input-ready').is_file(), 60, native)
            fixture = fixture_listener(native.pid)
            facts['fixture_listener'] = fixture
            window = wait_for(lambda: unique_window(environment, 'TrillionniumOS Desktop.*D0A-02', native.pid),
                              10, native)
            facts['native_window_id'] = window
            (directory / 'xwininfo.txt').write_text(command(['xwininfo', '-id', str(window)], environment))
            command(['xdotool', 'windowfocus', '--sync', str(window)], environment)
            require(command(['xdotool', 'getwindowfocus'], environment) == str(window),
                    'native window did not receive actual X11 focus')
            command(['xdotool', 'mousemove', '--sync', '--window', str(window), '200', '132'], environment)
            time.sleep(0.2)
            facts['pointer_before_down'] = pointer(environment)
            require(facts['pointer_before_down']['button_mask'] == 0,
                    'fresh case inherited a held mouse button')
            command(['xdotool', 'mousedown', '1'], environment)
            time.sleep(0.2)
            facts['pointer_after_down'] = pointer(environment)
            require(facts['pointer_after_down']['button_mask'] == 0x100,
                    'X11 server did not observe the exact held Button1')
            facts['stimulus'].append({'event': 'native_x11_mousedown', 'button': 1})
            if case == 'chrome':
                command(['xdotool', 'mousemove', '--sync', '--window', str(window), '10', '10'], environment)
                facts['stimulus'].append({'event': 'native_x11_move_to_chrome', 'x': 10, 'y': 10})
            elif case == 'window-leave':
                geometry = dict(line.split('=', 1) for line in
                    command(['xdotool', 'getwindowgeometry', '--shell', str(window)], environment).splitlines())
                x, y, width = (int(geometry[key]) for key in ('X', 'Y', 'WIDTH'))
                outside_x = x + width + 20 if x + width + 20 < 1280 else x - 20
                require(0 <= outside_x < 1280 and 0 <= y + 132 < 900,
                        'native geometry leaves no supported on-screen outside coordinate')
                command(['xdotool', 'mousemove', '--sync', str(outside_x), str(y + 132)], environment)
                facts['stimulus'].append({'event': 'native_x11_move_outside_window',
                                          'root_x': outside_x, 'root_y': y + 132, 'geometry': geometry})
            else:
                command(['xdotool', 'windowfocus', '--sync', str(helper_window)], environment)
                require(command(['xdotool', 'getwindowfocus'], environment) == str(helper_window),
                        'actual helper did not take focus from the native owner')
                facts['stimulus'].append({'event': 'native_x11_focus_withdrawal', 'window_id': helper_window})
            facts['pointer_after_withdrawal'] = pointer(environment)
            require(facts['pointer_after_withdrawal']['button_mask'] == 0x100,
                    'withdrawal stimulus lost the held button before observing refusal')
            write_json(directory / 'stimulus.json', facts)
            returncode = wait_exit(native, 30)
            facts['native_exit_code'] = returncode
            gesture = verify_case(directory, case, returncode)
            facts['observed_withdrawal'] = gesture
        except BaseException:
            (directory / 'harness-failure.txt').write_text(traceback.format_exc())
            raise
        finally:
            errors = []
            facts['cleanup'] = {}
            for name, process in (('native', native), ('focus_helper', helper), ('xvfb', xvfb)):
                try:
                    facts['cleanup'][name] = {'group_members_before_cleanup': cleanup(process),
                                              'owned_group_absent_after_cleanup': True}
                except BaseException as error:
                    errors.append(f'{name}: {error}')
                    facts['cleanup'][name] = {'error': str(error)}
            if fixture is not None:
                gone = all(row['inode'] != fixture['inode'] for row in listeners())
                facts['fixture_listener_absent_after_cleanup'] = gone
                if not gone:
                    errors.append('native fixture listener remained after process-group cleanup')
            write_json(directory / 'stimulus.json', facts)
            require(not errors, 'bounded owned cleanup failed: ' + '; '.join(errors))
    facts['raw_fact_sha256'] = {name: digest(directory / name) for name in
        ('runtime-result.json', 'runtime-state.json', 'gesture-recovery-required.json',
         'stimulus.json', 'runtime.log', 'xwininfo.txt', 'xdpyinfo.txt')}
    return facts


require(binary.is_file() and os.access(binary, os.X_OK), 'compile the exact pinned native target before this mode')
identity = {key.lower(): os.environ[key] for key in ('BASE_SHA', 'CANDIDATE_HEAD_SHA', 'TESTED_SHA',
    'TESTED_TREE_SHA', 'EVIDENCE_MODE', 'GITHUB_REPOSITORY', 'GITHUB_EVENT_NAME')}
require(identity['tested_sha'] == command(['git', 'rev-parse', 'HEAD'])
        and identity['tested_tree_sha'] == command(['git', 'rev-parse', 'HEAD^{tree}']),
        'negative corpus does not bind the recorded exact source object')
libc = ctypes.CDLL(None, use_errno=True)
require(libc.prctl(36, 1, 0, 0, 0) == 0, 'Linux child-subreaper custody is required for bounded native cleanup')
# Fixed 1024x768 screenshots fit this profile. The inherited file-size limit
# bounds each runtime/helper/Xvfb log; exhaustion fails instead of minting PASS.
logfile_limit = 16 * 1024 * 1024
resource.setrlimit(resource.RLIMIT_FSIZE, (logfile_limit, logfile_limit))
output.parent.mkdir(parents=True, exist_ok=True)
output.mkdir(mode=0o700)  # Refuse stale markers/diagnostics from an earlier run.
binary_sha256 = digest(binary)
receipt = {'schema': 'trillionnium.desktop.native-held-gesture-corpus.v1',
    'status': 'PASS_HELD_GESTURE_REFUSAL_LOCAL_X11_ONLY',
    'servo_commit': '670ae8a70801b162e186f81cbb5bdd2d59c39108',
    'evidence_identity': identity, 'compiled_native_binary_sha256': binary_sha256,
    'harness_regular_file_limit_bytes': logfile_limit,
    'source_sha256': {name: digest(root / name) for name in
        ('.github/workflows/servo-headed-runtime.yml', 'tools/run_servo_headed_runtime_gate.sh',
         'experiments/servo-headed-runtime/src/main.rs',
         'experiments/servo-headed-runtime/src/input_ownership.rs',
         'experiments/servo-headed-runtime/src/resource_gate.rs',
         'experiments/servo-headed-runtime/fixture/index.html', 'manifests/servo.lock.json')},
    'claim_ceiling': {'local_native_x11_xtest_only': True, 'physical_hardware_input_qualified': False,
        'mouse_cancellation_proven': False, 'same_servo_recovery_qualified': False,
        'dom_action_success_receipt': False, 'installed_browser_actor': False,
        'os_ime_qualified': False, 'product_ready': False}, 'cases': []}
try:
    for case in ('chrome', 'window-leave', 'focus-loss'):
        receipt['cases'].append(run_case(case))
    require(digest(binary) == binary_sha256, 'compiled native target changed during the negative corpus')
    write_json(output / 'negative-corpus.json', receipt)
except BaseException:
    (output / 'harness-failure.txt').write_text(traceback.format_exc())
    raise
PY
}

step_run_runtime() {
set -euo pipefail
output="$PWD/artifacts/servo-headed-runtime/runtime"
mkdir -p "$(dirname "$output")"
mkdir -m 0700 "$output"
export HEPTA_D0A02_OUTPUT="$output"
HEPTA_D0A02_INPUT_NONCE=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
export HEPTA_D0A02_INPUT_NONCE
export RUST_BACKTRACE=1

Xvfb :99 -screen 0 1280x900x24 -nolisten tcp >"$output/xvfb.log" 2>&1 &
xvfb_pid=$!
app_pid=
cleanup() {
  if [[ -n "${app_pid:-}" ]]; then
    kill "$app_pid" 2>/dev/null || true
    wait "$app_pid" 2>/dev/null || true
  fi
  kill "$xvfb_pid" 2>/dev/null || true
  wait "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT
export DISPLAY=:99
unset WAYLAND_DISPLAY
for _ in $(seq 1 100); do
  xdpyinfo >/dev/null 2>&1 && break
  sleep 0.1
done
xdpyinfo >"$output/xdpyinfo.txt"

servo-source/target/debug/examples/trillionnium_headed_runtime \
  >"$output/runtime.log" 2>&1 &
app_pid=$!
export HEPTA_D0A02_OWNER_PID=$app_pid
if [[ -n "${GITHUB_ENV:-}" ]]; then
  printf 'HEPTA_D0A02_INPUT_NONCE=%s\nHEPTA_D0A02_OWNER_PID=%s\n' \
    "$HEPTA_D0A02_INPUT_NONCE" "$app_pid" >> "$GITHUB_ENV"
fi
for _ in $(seq 1 600); do
  [[ -f "$output/input-ready" ]] && break
  kill -0 "$app_pid" 2>/dev/null || {
    cat "$output/runtime.log" >&2
    exit 1
  }
  sleep 0.1
done
test -f "$output/input-ready"

window_id="$(xdotool search --name 'TrillionniumOS Desktop.*D0A-02' | head -n1)"
test -n "$window_id"
test "$(xdotool getwindowpid "$window_id")" = "$app_pid"
xwininfo -id "$window_id" >"$output/xwininfo.txt"
xdotool windowfocus --sync "$window_id"
test "$(xdotool getwindowfocus)" = "$window_id"

python3 tools/native_input_checkpoints.py drive --output "$output" \
  --pid "$app_pid" --window "$window_id" --nonce "$HEPTA_D0A02_INPUT_NONCE"

ps -eo pid,ppid,stat,args >"$output/process-table-during-input.txt"
timeout 180 tail --pid="$app_pid" -f /dev/null
wait "$app_pid"
app_pid=
ps -eo pid,ppid,stat,args >"$output/process-table-after-result.txt"
}

step_enforce_evidence() {
set -euo pipefail
unset PYTHONOPTIMIZE
python3 tools/native_input_checkpoints.py verify \
  --output "$PWD/artifacts/servo-headed-runtime/runtime" \
  --pid "$HEPTA_D0A02_OWNER_PID" --nonce "$HEPTA_D0A02_INPUT_NONCE"
python3 - <<'PY'
from pathlib import Path
import hashlib
import json
import os

root = Path('artifacts/servo-headed-runtime/runtime')
path = root / 'runtime-result.json'
report = json.loads(path.read_text())
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
assert initial['pointerMoves'] > 0 and initial['pointerDowns'] == 3
assert 'x' not in [str(item).lower() for item in initial['keyDowns']]
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

pre = json.loads((root / 'process-topology-pre-fault.json').read_text())
terminated = json.loads(
    (root / 'process-topology-post-termination.json').read_text()
)
recovered = json.loads(
    (root / 'process-topology-post-recovery.json').read_text()
)
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

selected_receipt = json.loads(
    (root / 'content-process-identity.json').read_text()
)
signal_receipt = json.loads((root / 'content-sigkill-sent.json').read_text())
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
    data = file.read_bytes()
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
    'resource-gate-result.json',
    'content-process-identity.json',
    'content-sigkill-sent.json',
    'process-topology-pre-fault.json',
    'process-topology-post-termination.json',
    'process-topology-post-recovery.json',
]
evidence_file_digests = {
    name: hashlib.sha256((root / name).read_bytes()).hexdigest()
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
        Path('.github/workflows/servo-headed-runtime.yml').read_bytes()
    ).hexdigest(),
    'source_sha256': os.environ['COMMITTED_SOURCE_SHA256'],
    'formatted_overlay_sha256': os.environ['FORMATTED_OVERLAY_SHA256'],
    'fixture_sha256': hashlib.sha256(
        Path('experiments/servo-headed-runtime/fixture/index.html').read_bytes()
    ).hexdigest(),
    'resource_gate_sha256': hashlib.sha256(
        Path('experiments/servo-headed-runtime/src/resource_gate.rs').read_bytes()
    ).hexdigest(),
    'servo_lock_sha256': hashlib.sha256(
        Path('manifests/servo.lock.json').read_bytes()
    ).hexdigest(),
    'evidence_file_sha256': evidence_file_digests,
}
path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

runtime_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
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
(root / 'gate-evidence.json').write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + '\n'
)
PY
python3 tools/check_servo_resource_gate.py \
  --runtime-dir artifacts/servo-headed-runtime/runtime
}

step_restore_servo() {
rm -f \
  servo-source/ports/servoshell/examples/trillionnium_headed_runtime.rs \
  servo-source/ports/servoshell/examples/input_ownership.rs \
  servo-source/ports/servoshell/examples/resource_gate.rs \
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

step_run_native_burst_v1() {
unset PYTHONOPTIMIZE
python3 - <<'PY'
from contextlib import ExitStack
from pathlib import Path
import ctypes
import hashlib
import json
import os
import re
import resource
import signal
import socket
import subprocess
import time
import traceback
import uuid

root = Path.cwd()
output = root / 'artifacts/servo-headed-runtime/native-burst-v1'
binary = root / 'servo-source/target/debug/examples/trillionnium_headed_runtime'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(arguments, environment=None, timeout=5):
    return subprocess.run(arguments, env=environment, check=True, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def process_stat(pid):
    values = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'ppid': int(values[1]), 'pgid': int(values[2]),
            'session': int(values[3]), 'start_time': int(values[19]), 'state': values[0]}


def members(group):
    rows = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            row = process_stat(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
        if row['pgid'] == group:
            require(row['session'] == group, 'owned process group changed its session identity')
            rows.append(row)
    return sorted(rows, key=lambda row: row['pid'])


def spawn(arguments, environment, log, pass_fds=()):
    process = subprocess.Popen(arguments, env=environment, stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True, pass_fds=pass_fds)
    try:
        row = process_stat(process.pid)
        require(row['pgid'] == process.pid and row['session'] == process.pid,
                'new child does not own its new session and process group')
        process._hepta_identity = row
        process._hepta_cleanup_complete = False
    except BaseException:
        # The unreaped direct child still anchors its PID. Without the captured
        # session identity, only that child may be signalled, never a numeric group.
        try:
            os.kill(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        raise
    return process, row


def anchored_identity(process):
    expected = process._hepta_identity
    require(process.returncode is None, 'leader was reaped before owned group cleanup')
    current = process_stat(process.pid)
    require(all(current[key] == expected[key] for key in ('pid', 'start_time', 'pgid', 'session')),
            'captured leader PID/start-time/session/group identity no longer matches')
    return current


def observe_exit(process):
    anchored_identity(process)
    result = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
    if result is None:
        return None
    if result.si_code == os.CLD_EXITED:
        return result.si_status
    require(result.si_code in (os.CLD_KILLED, os.CLD_DUMPED), 'unexpected native waitid outcome')
    return -result.si_status


def wait_exit(process, seconds):
    deadline = time.monotonic() + seconds
    while True:
        result = observe_exit(process)
        if result is not None:
            return result
        require(time.monotonic() < deadline, 'bounded native exit observation expired')
        time.sleep(0.05)


def cleanup(process):
    if process is None:
        return []
    if process._hepta_cleanup_complete:
        return []  # No reused numeric PID/group is touched after the original closes.
    group = process.pid
    require(group > 1 and group != os.getpgrp(), 'refusing to clean an unowned group')
    anchored_identity(process)
    before = members(group)
    anchored_identity(process)
    try:
        os.killpg(group, signal.SIGTERM)
    except ProcessLookupError:
        pass
    # The harness is a Linux subreaper, so content children orphaned by the
    # native fixture's explicit exit can be reaped. Keep the unreaped leader as
    # the numeric session/group anchor until all other members have disappeared.
    started = time.monotonic()
    deadline = started + 7
    killed = False
    while True:
        anchored_identity(process)
        for row in members(group):
            if row['pid'] == group:
                continue
            try:
                os.waitpid(row['pid'], os.WNOHANG)
            except ChildProcessError:
                pass  # Still owned by a live leader; adoption happens on its exit.
        remaining = members(group)
        if observe_exit(process) is not None and all(row['pid'] == group for row in remaining):
            # The last member is our captured, exited leader. Only now may its
            # original PID/session be released; no later kill uses this number.
            process.wait(timeout=1)
            process._hepta_cleanup_complete = True
            return before
        if not killed and time.monotonic() >= started + 2:
            anchored_identity(process)
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            killed = True
        require(time.monotonic() < deadline, 'owned process group did not disappear after bounded cleanup')
        time.sleep(0.05)


def wait_for(predicate, seconds, process=None):
    deadline = time.monotonic() + seconds
    while True:
        value = predicate()
        if value:
            return value
        require(process is None or observe_exit(process) is None, 'native/helper process exited before readiness')
        require(time.monotonic() < deadline, 'bounded native readiness wait expired')
        time.sleep(0.05)


def capture_burst_topology(process, executable, compiled_executable_identity):
    # Only this unreaped leader and its same-image, same-session direct child
    # are inspected. The opaque content IPC token is never copied into facts.
    deadline = time.monotonic() + 5
    require(observe_exit(process) is None, 'native owner exited before topology capture')
    expected = executable.stat()
    verify_compiled_executable_identity({'device': expected.st_dev, 'inode': expected.st_ino},
                                        compiled_executable_identity)
    identity_keys = ('pid', 'start_time', 'ppid', 'pgid', 'session')
    native = anchored_identity(process)
    native_exe = Path(f'/proc/{process.pid}/exe').stat()
    require((native_exe.st_dev, native_exe.st_ino) == (expected.st_dev, expected.st_ino),
            'captured native executable inode differs')
    candidates = []
    for row in members(process.pid):
        require(time.monotonic() < deadline, 'bounded topology capture expired')
        if row['ppid'] != process.pid:
            continue
        try:
            image = Path(f'/proc/{row["pid"]}/exe').stat()
            with Path(f'/proc/{row["pid"]}/cmdline').open('rb') as stream:
                arguments = stream.read(4097)
        except (FileNotFoundError, ProcessLookupError):
            continue
        require(len(arguments) <= 4096, 'owned content argv exceeds bound')
        if ((image.st_dev, image.st_ino) == (expected.st_dev, expected.st_ino)
                and b'--content-process' in arguments.split(b'\0')):
            candidates.append(row)
    require(len(candidates) == 1, 'expected exactly one live owned content process')
    candidate = candidates[0]
    descriptor = os.pidfd_open(candidate['pid'], 0)
    try:
        import select
        poller = select.poll()
        poller.register(descriptor, select.POLLIN | select.POLLHUP | select.POLLERR)
        require(not poller.poll(0), 'captured content process is not alive')
        current = process_stat(candidate['pid'])
        require(all(current[key] == candidate[key] for key in identity_keys)
            and current['state'] not in {'Z', 'X'}
            and current['ppid'] == process.pid and current['pgid'] == process.pid
            and current['session'] == process.pid, 'content incarnation/ownership changed')
        image = Path(f'/proc/{candidate["pid"]}/exe').stat()
        require((image.st_dev, image.st_ino) == (expected.st_dev, expected.st_ino),
                'retained content executable inode differs')
        with Path(f'/proc/{candidate["pid"]}/cmdline').open('rb') as stream:
            arguments = stream.read(4097)
        require(len(arguments) <= 4096 and b'--content-process' in arguments.split(b'\0'),
                'retained content argv is not the bounded native content entry')
        after = process_stat(candidate['pid'])
        require(all(after[key] == current[key] for key in identity_keys)
            and not poller.poll(0), 'retained content incarnation drifted')
        require(observe_exit(process) is None and time.monotonic() < deadline,
                'native owner or topology budget expired during capture')
        require(all(anchored_identity(process)[key] == native[key] for key in identity_keys),
                'native owner changed during topology capture')
        return {'schema': 'trillionnium.desktop.native-burst-topology.v1',
            'native': {key: native[key] for key in identity_keys},
            'content': {key: current[key] for key in identity_keys},
            'compiled_executable_device': expected.st_dev, 'compiled_executable_inode': expected.st_ino,
            'content_process_flag_observed': True, 'retained_content_pidfd_alive_at_capture': True,
            'ipc_token_recorded': False, 'source_qualification_only': True, 'product_ready': False}
    finally:
        os.close(descriptor)


def verify_compiled_executable_identity(value, expected):
    for item in (value, expected):
        require(type(item) is dict and set(item) == {'device', 'inode'}
            and type(item['device']) is int and item['device'] >= 0
            and type(item['inode']) is int and item['inode'] > 0,
            'compiled executable snapshot is not closed exact integers')
    require(value == expected, 'compiled executable snapshot differs from before-launch identity')


def verify_burst_topology(topology, native, selected, compiled_executable_identity):
    require(type(topology) is dict and set(topology) == {'schema', 'native', 'content',
        'compiled_executable_device', 'compiled_executable_inode', 'content_process_flag_observed',
        'retained_content_pidfd_alive_at_capture', 'ipc_token_recorded', 'source_qualification_only', 'product_ready'},
        'actual burst topology fields differ')
    require(topology['schema'] == 'trillionnium.desktop.native-burst-topology.v1'
        and topology['content_process_flag_observed'] is True
        and topology['retained_content_pidfd_alive_at_capture'] is True
        and topology['ipc_token_recorded'] is False
        and topology['source_qualification_only'] is True and topology['product_ready'] is False,
        'actual burst topology observation/claim differs')
    keys = {'pid', 'start_time', 'ppid', 'pgid', 'session'}
    for role in ('native', 'content'):
        row = topology[role]
        require(type(row) is dict and set(row) == keys
            and all(type(row[key]) is int and row[key] > 0 for key in keys),
            'actual burst topology identity must use closed positive integers')
    require(type(topology['compiled_executable_device']) is int and topology['compiled_executable_device'] >= 0
        and type(topology['compiled_executable_inode']) is int and topology['compiled_executable_inode'] > 0,
        'actual burst executable inode is not exact')
    verify_compiled_executable_identity({'device': topology['compiled_executable_device'],
                                        'inode': topology['compiled_executable_inode']}, compiled_executable_identity)
    owner, content = topology['native'], topology['content']
    require(all(owner[key] == native[key] for key in keys)
        and owner['pid'] == owner['pgid'] == owner['session'] and owner['pid'] > 1,
        'actual burst topology native owner differs')
    require(content['pid'] == selected['pid'] and content['start_time'] == selected['start_time']
        and content['pid'] > 1 and content['pid'] != owner['pid']
        and content['ppid'] == owner['pid'] and content['pgid'] == owner['pgid']
        and content['session'] == owner['session'],
        'actual burst topology does not bind the selected fault incarnation')


def unique_window(environment, title, pid=None):
    arguments = ['xdotool', 'search', '--onlyvisible']
    if pid is not None:
        arguments += ['--pid', str(pid)]
    arguments += ['--name', title]
    try:
        result = command(arguments, environment)
    except subprocess.CalledProcessError:
        return None
    windows = result.splitlines()
    require(len(windows) == 1, 'native stimulus did not bind one visible owned window')
    return int(windows[0])


def pointer(environment):
    x11 = ctypes.CDLL('libX11.so.6')
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XQueryPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)]
    x11.XQueryPointer.restype = ctypes.c_int
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(environment['DISPLAY'].encode())
    require(display, 'could not open the case X11 display for actual button observation')
    try:
        root_window, child = ctypes.c_ulong(), ctypes.c_ulong()
        root_x, root_y, window_x, window_y = (ctypes.c_int() for _ in range(4))
        mask = ctypes.c_uint()
        require(x11.XQueryPointer(display, x11.XDefaultRootWindow(display),
            ctypes.byref(root_window), ctypes.byref(child), ctypes.byref(root_x), ctypes.byref(root_y),
            ctypes.byref(window_x), ctypes.byref(window_y), ctypes.byref(mask)), 'XQueryPointer failed')
        return {'root_x': root_x.value, 'root_y': root_y.value,
                'child_window': child.value, 'button_mask': mask.value & 0x1f00}
    finally:
        x11.XCloseDisplay(display)


def listeners():
    rows = []
    for line in Path('/proc/self/net/tcp').read_text().splitlines()[1:]:
        fields = line.split()
        if fields[3] != '0A':
            continue
        address, port = fields[1].split(':')
        rows.append({'address': socket.inet_ntoa(bytes.fromhex(address)[::-1]),
                     'port': int(port, 16), 'inode': int(fields[9])})
    return rows


def fixture_listener(pid):
    inodes = set()
    for fd in Path(f'/proc/{pid}/fd').iterdir():
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        match = re.fullmatch(r'socket:\[(\d+)\]', target)
        if match:
            inodes.add(int(match[1]))
    owned = [row for row in listeners() if row['inode'] in inodes]
    require(len(owned) == 1 and owned[0]['address'] == '127.0.0.1' and owned[0]['port'] > 0,
            'native fixture did not own exactly one ephemeral IPv4 loopback listener')
    return owned[0]

# This body is installed as a bounded, explicit Linux/Xvfb qualification mode.
# The default prototype lane receives all original rapid pairs without checkpoint pacing.
from tools.browser_codec_reference_security import open_regular_beneath, load_json_strict
import stat

READ_LIMIT = 2 * 1024 * 1024
observed = {}
os.umask(0o077)  # Inherited by the real runtime; facts/logs remain private.


def snapshot(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def regular_bytes(path, limit=READ_LIMIT):
    descriptor = open_regular_beneath(root, path, label='native burst artifact')
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and before.st_nlink == 1 and before.st_mode & 0o022 == 0 and 0 < before.st_size <= limit,
                'native burst artifact is not bounded owned regular single-link data')
        chunks, total = [], 0
        while True:
            chunk = os.read(descriptor, min(65536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            require(total <= limit, 'native burst artifact exceeded read bound')
        require(snapshot(os.fstat(descriptor)) == snapshot(before) and total == before.st_size,
                'native burst artifact changed while reading')
        named = open_regular_beneath(root, path, label='native burst named artifact')
        try:
            require(snapshot(os.fstat(named)) == snapshot(before), 'native burst artifact pathname changed')
        finally:
            os.close(named)
        data = b''.join(chunks)
        observed[str(path.relative_to(root))] = (snapshot(before), hashlib.sha256(data).hexdigest())
        return data
    finally:
        os.close(descriptor)


def read_json(path):
    return load_json_strict(regular_bytes(path).decode('utf-8'))


def verify_queue(queue, native):
    expected = {'schema', 'source_only', 'owner_pid', 'owner_start_time', 'qualification_ack_profile',
        'records', 'queue_idle', 'maximum_pending_events', 'maximum_payload_bytes',
        'busy_episode_budget_seconds', 'ack_is_dom_execution_proof', 'product_ready'}
    require(type(queue) is dict and set(queue) == expected, 'unknown native queue facts')
    require(queue['schema'] == 'trillionnium.desktop.native-input-queue.v1'
        and queue['source_only'] is True and queue['qualification_ack_profile'] is False
        and queue['queue_idle'] is True and queue['ack_is_dom_execution_proof'] is False
        and queue['product_ready'] is False, 'nonce/default/claim/idle mismatch in native queue facts')
    require(type(queue['owner_pid']) is int and queue['owner_pid'] == native['pid']
        and type(queue['owner_start_time']) is int and queue['owner_start_time'] == native['start_time'],
        'native queue does not bind the real fresh process incarnation')
    for key, value in [('maximum_pending_events', 64), ('maximum_payload_bytes', 16384), ('busy_episode_budget_seconds', 5)]:
        require(type(queue[key]) is int and queue[key] == value, 'native queue resource bound drift')
    records = queue['records']
    require(type(records) is list and 0 < len(records) <= 256, 'unbounded/empty native queue facts')
    pending, flight, all_ids, admitted, accepted, views = [], None, set(), [], [], {}
    last_sequence, last_closed = 0, None
    kinds = {'move', 'down', 'up', 'wheel', 'key', 'ime', 'local_ime', 'synthetic_ime'}
    for record in records:
        require(type(record) is dict, 'native input record is not object')
        if record.get('phase') == 'not_admitted':
            require(set(record) == {'phase', 'reason', 'generation', 'epoch'}
                and record['reason'] in {'ime_not_owned', 'keyboard_not_owned', 'wheel_outside_content', 'outside_content', 'stale_owner', 'stale_callback'}
                and type(record['generation']) is int and record['generation'] in {1, 2}
                and type(record['epoch']) is int and record['epoch'] >= 0,
                'unexpected native refusal/unknown callback in successful rapid lane')
            continue
        require(set(record) == {'phase', 'sequence', 'generation', 'view', 'epoch', 'kind', 'point', 'event_id', 'source'},
                'unknown native event record fields')
        require(type(record['sequence']) is int and record['sequence'] > 0
            and type(record['generation']) is int and record['generation'] in {1, 2}
            and type(record['epoch']) is int and record['epoch'] >= 0
            and type(record['view']) is str and 0 < len(record['view']) <= 128
            and record['kind'] in kinds, 'native input record authority shape invalid')
        require(record['generation'] not in views or views[record['generation']] == record['view'],
                'same content generation changed actual owned WebView identity')
        views[record['generation']] = record['view']
        point = record['point']
        require(point is None or (type(point) is list and len(point) == 2
            and all(type(item) in {int, float} and 0 <= item < bound for item, bound in zip(point, (1024, 704)))),
            'native input point invalid')
        require(record['source'] == ('qualification_synthetic' if record['kind'] == 'synthetic_ime' else 'native_winit'),
                'native/synthetic origin drift')
        phase = record['phase']
        if phase == 'admitted':
            require(record['event_id'] is None and record['sequence'] == last_sequence + 1,
                    'native admission sequence/ID drift')
            last_sequence += 1
            if pending or flight is not None:
                previous = pending[0] if pending else flight[0]
                require(all(record[key] == previous[key] for key in ('generation', 'view', 'epoch')),
                        'native episode admitted a different owner')
            pending.append(record)
            admitted.append(record)
        elif phase == 'withdrawn_unsent':
            require(pending and record['event_id'] is None,
                    'unsent withdrawal has no original admission or invents an engine ID')
            original = pending.pop(0)
            require(all(record[key] == original[key] for key in record if key != 'phase'),
                    'unsent withdrawal does not bind the original frozen admission')
        elif phase in {'submitted', 'local_applied'}:
            require(flight is None and pending, 'parallel/unadmitted native submission')
            original = pending.pop(0)
            require(all(record[key] == original[key] for key in record if key not in {'phase', 'event_id'}),
                    'native submission did not preserve exact admission identity/payload point')
            if phase == 'local_applied':
                require(record['kind'] == 'local_ime' and record['event_id'] is None, 'local IME forged engine ACK')
            else:
                identifier = record['event_id']
                require(record['kind'] != 'local_ime' and type(identifier) is str
                    and re.fullmatch(r'InputEventId\([0-9]+\)', identifier) and identifier not in all_ids,
                    'native submission lacks unique actual Servo ID')
                all_ids.add(identifier)
                flight = (record, identifier)
        elif phase == 'accepted':
            require(flight is not None and record['event_id'] == flight[1]
                and all(record[key] == flight[0][key] for key in record if key != 'phase'),
                'native ACK does not bind the sole real submission')
            accepted.append(record)
            last_closed = record
            flight = None
        else:
            require(False, 'unknown native queue transition')
    require(not pending and flight is None and last_closed is not None, 'native lane is not fully settled')
    button = [item for item in accepted if item['generation'] == 1 and item['kind'] in {'down', 'up'}]
    require([item['kind'] for item in button] == ['down', 'up'] * 3, 'rapid lane did not dispatch exactly original three pairs')
    require([item['point'] for item in button] == [[200, 68], [200, 68], [400, 100], [400, 100], [200, 68], [200, 68]],
            'rapid pairs changed physical arrival points')
    require(all(item['source'] == 'native_winit' for item in button), 'button evidence was synthetic')
    admitted_buttons = [item for item in admitted if item['generation'] == 1 and item['kind'] in {'down', 'up'}]
    require([item['sequence'] for item in admitted_buttons] == [item['sequence'] for item in button],
            'rapid lane discarded or invented any original button admission')
    counts = {kind: sum(item['kind'] == kind for item in accepted) for kind in kinds if kind != 'local_ime'}
    require(counts['synthetic_ime'] == 3 and all(item['generation'] == 1 for item in accepted if item['kind'] == 'synthetic_ime'),
            'qualification IME triplet lacks its three actual matching dispatch completions')
    return {'accepted_event_counts': counts, 'accepted_native_button_event_ids': [item['event_id'] for item in button],
            'accepted_native_button_sequences': [item['sequence'] for item in button],
            'total_admitted_events': len(admitted), 'total_matching_engine_acks': len(accepted)}


def verify_burst(directory, native, returncode):
    require(returncode == 0, 'rapid native qualification must actually exit successfully')
    report = read_json(directory / 'runtime-result.json')
    require(report['schema'] == 'trillionnium.desktop.d0a02-headed-runtime.v1'
        and report['status'] == 'PASS_HEADED_LOCAL_FIXTURE_ONLY'
        and report['servo_commit'] == '670ae8a70801b162e186f81cbb5bdd2d59c39108', 'rapid runtime result mismatch')
    for key in ('window_created', 'trusted_chrome_separate_from_content', 'chrome_initial_pixels_verified',
                'chrome_crash_pixels_verified', 'chrome_recovery_pixels_verified', 'content_crash_observed',
                'trusted_window_survived_content_crash'):
        require(report[key] is True, f'original runtime gate failed: {key}')
    require(type(report['logical_content_webview_peak']) is int and report['logical_content_webview_peak'] == 1
        and type(report['initial_generation']) is int and report['initial_generation'] == 1
        and type(report['recovery_generation']) is int and report['recovery_generation'] == 2,
        'runtime generation/topology drift')
    for key in ('native_pointer_events', 'native_wheel_events', 'native_ime_events', 'input_method_controls',
                'popup_requests_denied', 'external_navigation_requests_denied'):
        require(type(report[key]) is int and report[key] > 0, f'original input/denial gate failed: {key}')
    require(type(report['native_button_events']) is int and report['native_button_events'] == 6
        and type(report['native_keyboard_events']) is int and report['native_keyboard_events'] >= 2
        and type(report['synthetic_ime_composition_events']) is int and report['synthetic_ime_composition_events'] == 3
        and type(report['input_handled_callbacks']) is int and report['input_handled_callbacks'] >= 12,
        'rapid native input/IME/handled counters incomplete')
    initial, recovery = report['initial_page_evidence'], report['recovery_page_evidence']
    require(type(initial['generation']) is int and initial['generation'] == 1 and initial['loaded'] is True
        and all(type(initial[key]) is int for key in ('pointerDowns', 'documentClickEvents', 'clicks', 'wheels', 'pointerMoves'))
        and initial['pointerDowns'] == 3 and initial['documentClickEvents'] == 3
        and initial['clicks'] > 0 and initial['wheels'] > 0 and initial['pointerMoves'] > 0,
        'actual DOM requires original three presses AND three document click events AND fixture button click')
    require(initial['inputEventOrderOverflow'] is False and type(initial['inputEventOrder']) is list
        and len(initial['inputEventOrder']) == 9, 'actual DOM input order is absent/overflowed/unexpected')
    for index, event in enumerate(initial['inputEventOrder']):
        require(type(event) is dict and set(event) == {'sequence', 'type', 'button', 'x', 'y'}
            and type(event['sequence']) is int and event['sequence'] == index + 1
            and event['type'] == ['pointerdown', 'pointerup', 'click'][index % 3]
            and type(event['button']) is int and event['button'] == 0
            and [event['x'], event['y']] == [[200, 68], [400, 100], [200, 68]][index // 3],
            'actual bounded DOM down/up/click event order/coordinates mismatch')
    require('k' in [str(value).lower() for value in initial['keyDowns']]
        and 'x' not in [str(value).lower() for value in initial['keyDowns']]
        and initial['popupAttempted'] is True and initial['externalNavigationAttempted'] is True
        and type(recovery['generation']) is int and recovery['generation'] == 2 and recovery['loaded'] is True, 'original page gate failed')
    fault = report['fault_injection']
    require(fault['mechanism'] == 'requested_SIGKILL' and type(fault['generation']) is int and fault['generation'] == 1
        and type(fault['pid']) is int and fault['pid'] > 1
        and type(fault['start_time']) is int and fault['start_time'] > 0
        and fault['exact_termination_observed'] is True, 'actual fault/termination identity missing')
    selected = {'generation': 1, 'pid': fault['pid'], 'start_time': fault['start_time']}
    for name, expected in (
        ('content-process-identity.json', selected),
        ('content-sigkill-sent.json', {**selected, 'signal': 'SIGKILL'}),
    ):
        receipt = read_json(directory / name)
        require(type(receipt) is dict and set(receipt) == set(expected),
                'actual process receipt fields differ')
        require(all(type(receipt[key]) is int for key in ('generation', 'pid', 'start_time')),
                'actual process receipt identity must use exact integers')
        if 'signal' in expected:
            require(type(receipt['signal']) is str and receipt['signal'] == 'SIGKILL',
                    'actual process receipt signal differs')
        require(receipt == expected, 'actual selected/signalled process receipts differ')
    require(all(type(value) is bool for value in report['authority'].values())
        and report['authority'] == {'fixture_listener_loopback_only': True,
        'external_navigation_performed': False, 'webdriver_listener_started': False,
        'browser_actor_started': False, 'agent_port_enabled': False,
        'persistent_credentials_used': False, 'product_ready': False}, 'runtime claim ceiling drift')
    stimulus = read_json(directory / 'native-burst-stimulus.json')
    require(type(stimulus) is dict, 'actual stimulus fact is not an object')
    verify_compiled_executable_identity(stimulus.get('compiled_executable_identity'), binary_identity)
    verify_burst_topology(read_json(directory / 'process-topology-pre-burst.json'), native, selected, binary_identity)
    for name in ('content-generation-1.png', 'content-generation-2.png', 'workspace-generation-1.png',
                 'workspace-crash-placeholder.png', 'workspace-generation-2.png'):
        require(regular_bytes(directory / name, 16 * 1024 * 1024).startswith(b'\x89PNG\r\n\x1a\n'), 'actual screenshot missing')
    queue = verify_queue(read_json(directory / 'native-input-queue.json'), native)
    counts = queue['accepted_event_counts']
    require(report['input_handled_callbacks'] == queue['total_matching_engine_acks']
        and report['native_pointer_events'] == counts['move']
        and report['native_button_events'] == counts['down'] + counts['up']
        and report['native_keyboard_events'] == counts['key']
        and report['native_wheel_events'] == counts['wheel'],
        'runtime dispatch counters do not match the actual complete ACK chain')
    # The existing resource verifier consumes original raw bytes; its predicates
    # remain independent of queue ACK and DOM input verification.
    command(['python3', 'tools/check_servo_resource_gate.py', '--runtime-dir', str(directory)], timeout=10)
    regular_bytes(directory / 'resource-gate-result.json')
    return {**queue, 'actual_dom_document_click_events': 3, 'actual_dom_pointer_down_events': 3,
        'actual_dom_button_event_order': initial['inputEventOrder']}


require(binary.is_file() and os.access(binary, os.X_OK), 'compile the exact pinned native target before burst mode')
identity = {key.lower(): os.environ[key] for key in ('BASE_SHA', 'CANDIDATE_HEAD_SHA', 'TESTED_SHA',
    'TESTED_TREE_SHA', 'EVIDENCE_MODE', 'GITHUB_REPOSITORY', 'GITHUB_EVENT_NAME')}
require(identity['tested_sha'] == command(['git', 'rev-parse', 'HEAD'])
    and identity['tested_tree_sha'] == command(['git', 'rev-parse', 'HEAD^{tree}']), 'rapid lane source object drift')
libc = ctypes.CDLL(None, use_errno=True)
require(libc.prctl(36, 1, 0, 0, 0) == 0, 'real Linux child-subreaper custody is required')
logfile_limit = 16 * 1024 * 1024
resource.setrlimit(resource.RLIMIT_FSIZE, (logfile_limit, logfile_limit))
output.parent.mkdir(parents=True, exist_ok=True)
output.mkdir(mode=0o700)  # Fresh process/profile/markers; rerun is refused.
require(output.stat().st_uid == os.getuid() and stat.S_IMODE(output.stat().st_mode) == 0o700,
        'rapid qualification output is not a private owned directory')
binary_sha256 = digest(binary)
before_launch_binary_stat = binary.stat()
binary_identity = {'device': before_launch_binary_stat.st_dev, 'inode': before_launch_binary_stat.st_ino}
installed_overlay_sha256 = digest(root / 'servo-source/ports/servoshell/examples/trillionnium_headed_runtime.rs')
require(installed_overlay_sha256 == os.environ['FORMATTED_OVERLAY_SHA256'],
        'actual installed compile overlay differs from recorded formatted source')
facts = {'schema': 'trillionnium.desktop.native-burst-stimulus.v1', 'qualification_nonce_enabled': False,
         'per_pair_ack_pacing': False, 'requested_button_pairs': 3, 'extra_clicks_requested': 0,
         'stimulus_attempted': False, 'stimulus_command_completed': False}
native = xvfb = None
fixture = None
verification = None
with ExitStack() as stack:
    try:
        display_path = output / 'display-number'
        display_fd = stack.enter_context(display_path.open('w'))
        xvfb_log = stack.enter_context((output / 'xvfb.log').open('w'))
        xvfb, xvfb_identity = spawn(['Xvfb', '-displayfd', str(display_fd.fileno()),
            '-screen', '0', '1280x900x24', '-nolisten', 'tcp'], dict(os.environ), xvfb_log,
            pass_fds=(display_fd.fileno(),))
        number = wait_for(lambda: display_path.read_text().strip(), 10, xvfb)
        require(re.fullmatch(r'[0-9]+', number), 'Xvfb display number invalid')
        environment = dict(os.environ, DISPLAY=f':{number}', HEPTA_D0A02_OUTPUT=str(output), RUST_BACKTRACE='1')
        environment.pop('WAYLAND_DISPLAY', None)
        environment.pop('HEPTA_D0A02_INPUT_NONCE', None)
        (output / 'xdpyinfo.txt').write_text(command(['xdpyinfo'], environment))
        native_log = stack.enter_context((output / 'runtime.log').open('w'))
        native, native_identity = spawn([str(binary)], environment, native_log)
        facts['native_process'] = native_identity
        facts['xvfb_process'] = xvfb_identity
        require(Path(f'/proc/{native.pid}/exe').resolve() == binary.resolve(), 'fresh native executable drift')
        wait_for(lambda: (output / 'input-ready').is_file(), 60, native)
        facts['compiled_executable_identity'] = dict(binary_identity)
        write_json(output / 'process-topology-pre-burst.json', capture_burst_topology(native, binary, binary_identity))
        fixture = fixture_listener(native.pid)
        facts['fixture_listener'] = fixture
        window = wait_for(lambda: unique_window(environment, 'TrillionniumOS Desktop.*D0A-02', native.pid), 10, native)
        facts['native_window_id'] = window
        (output / 'xwininfo.txt').write_text(command(['xwininfo', '-id', str(window)], environment))
        command(['xdotool', 'windowfocus', '--sync', str(window)], environment)
        require(command(['xdotool', 'getwindowfocus'], environment) == str(window), 'fresh native X11 focus missing')
        require(pointer(environment)['button_mask'] == 0, 'fresh X11 server already holds a mouse button')
        # One XTest command batch, original three content pairs, NO waits on
        # checkpoint/ACK, retries, additional pairs or counter-triggered clicking.
        arguments = ['xdotool', 'mousemove', '--sync', '--window', str(window), '200', '132',
            'mousedown', '1', 'mouseup', '1',
            'mousemove', '--sync', '--window', str(window), '400', '164',
            'mousedown', '1', 'mouseup', '1',
            'mousemove', '--sync', '--window', str(window), '200', '132', 'mousedown', '1', 'mouseup', '1',
            'key', '--delay', '0', 'k', 'click', '--delay', '0', '5']
        facts['original_stimulus_argv'] = arguments
        facts['stimulus_attempted'] = True
        write_json(output / 'native-burst-stimulus.json', facts)
        command(arguments, environment, timeout=10)
        facts['stimulus_command_completed'] = True
        facts['pointer_after_stimulus'] = pointer(environment)
        require(facts['pointer_after_stimulus']['button_mask'] == 0, 'actual rapid pairs did not release Button1')
        write_json(output / 'native-burst-stimulus.json', facts)
        code = wait_exit(native, 120)
        facts['native_exit_code'] = code
        after_execution_binary_stat = binary.stat()
        verify_compiled_executable_identity({'device': after_execution_binary_stat.st_dev,
                                            'inode': after_execution_binary_stat.st_ino}, binary_identity)
        require(digest(binary) == binary_sha256, 'compiled native executable changed during burst')
    except BaseException:
        (output / 'harness-failure.txt').write_text(traceback.format_exc())
        raise
    finally:
        errors = []
        facts['cleanup'] = {}
        for name, process in (('native', native), ('xvfb', xvfb)):
            try:
                facts['cleanup'][name] = {'group_members_before_cleanup': cleanup(process), 'owned_group_absent_after_cleanup': True}
            except BaseException as error:
                errors.append(f'{name}: {error}')
                facts['cleanup'][name] = {'error': str(error)}
        if fixture is not None:
            gone = all(row['inode'] != fixture['inode'] for row in listeners())
            facts['fixture_listener_absent_after_cleanup'] = gone
            if not gone: errors.append('actual fixture listener survives cleanup')
        write_json(output / 'native-burst-stimulus.json', facts)
        require(not errors, 'owned bounded cleanup failed: ' + '; '.join(errors))
# Cleanup finishes the stimulus fact before its immutable validation snapshot.
try:
    verification = verify_burst(output, native_identity, code)
except BaseException:
    (output / 'harness-failure.txt').write_text(traceback.format_exc())
    raise
# Re-open every consumed fact after validation and cleanup; digest receipts bind
# those same strictly decoded raw bytes, rather than a later pathname read.
raw = dict(observed)
for name, expected in raw.items():
    regular_bytes(root / name, 16 * 1024 * 1024)
    require(observed[name] == expected, 'earlier raw native burst fact changed during verification')
for name in ('native-burst-stimulus.json', 'runtime.log', 'xwininfo.txt', 'xdpyinfo.txt'):
    regular_bytes(output / name, logfile_limit)
receipt = {'schema': 'trillionnium.desktop.native-burst-verification.v1',
    'status': 'PASS_NATIVE_ORDERED_BURST_LOCAL_X11_ONLY', 'evidence_identity': identity,
    'servo_commit': '670ae8a70801b162e186f81cbb5bdd2d59c39108',
    'compiled_native_binary_sha256': binary_sha256, 'formatted_overlay_sha256': installed_overlay_sha256,
    'verification': verification,
    'source_sha256': {name: digest(root / name) for name in (
        '.github/workflows/servo-headed-runtime.yml', 'tools/run_servo_headed_runtime_gate.sh',
        'tools/browser_codec_reference_security.py',
        'experiments/servo-headed-runtime/src/main.rs', 'experiments/servo-headed-runtime/src/input_ownership.rs',
        'experiments/servo-headed-runtime/src/resource_gate.rs', 'experiments/servo-headed-runtime/fixture/index.html',
        'manifests/servo.lock.json')},
    'raw_fact_sha256': {str(Path(name).relative_to(output.relative_to(root))): value[1]
        for name, value in observed.items()},
    'claim_ceiling': {'local_native_x11_xtest_only': True, 'qualification_nonce_enabled': False,
        'physical_hardware_input_qualified': False, 'variable_scaling_qualified': False,
        'mouse_cancellation_proven': False, 'os_ime_qualified': False,
        'installed_browser_actor': False, 'product_ready': False}}
write_json(output / 'native-burst-verification.json', receipt)

PY
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
  run-held-gestures-v1)
    step_run_held_gestures_v1
    ;;
  run-native-burst-v1)
    step_run_native_burst_v1
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
