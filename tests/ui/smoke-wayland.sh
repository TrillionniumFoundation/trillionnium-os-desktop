#!/usr/bin/env bash
# Checks real Linux Wayland app/shell process survival, NOT target-kernel boot.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${XDG_RUNTIME_DIR:?Run inside an active Wayland desktop session}"
: "${WAYLAND_DISPLAY:?A Wayland compositor socket is required}"
if [[ "$WAYLAND_DISPLAY" = /* ]]; then
    compositor_socket="$WAYLAND_DISPLAY"
else
    compositor_socket="$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY"
fi
[[ -S "$compositor_socket" ]] || { echo "No Wayland socket: $compositor_socket" >&2; exit 2; }
cargo build --manifest-path ui/Cargo.toml --workspace --bins
ctl=./ui/target/debug/trill-ctl
session_bin=./ui/target/debug/trill-session
shell_bin=./ui/target/debug/trill-shell
runtime="$(mktemp -d "${XDG_RUNTIME_DIR%/}/trill-ui-smoke.XXXXXXXX")"
chmod 700 "$runtime"
export XDG_RUNTIME_DIR="$runtime" WAYLAND_DISPLAY="$compositor_socket"
# Do not allow a healthy X11 fallback to masquerade as a Wayland smoke.
unset DISPLAY
session_pid=""
shell_pid=""
task_id=""
task2_id=""
app_pid=""
app2_pid=""

# Reuse the same ownership-scoped cleanup tested without a compositor.
source support/ui/smoke-cleanup.sh

cleanup() {
    # Logs are retained only at an explicitly supplied path.
    if [[ -n "${A10_SMOKE_LOG_DIR:-}" ]]; then
        mkdir -p -- "$A10_SMOKE_LOG_DIR" || true
        cp "$runtime/"*.log "$A10_SMOKE_LOG_DIR/" 2>/dev/null || true
    fi
    if [[ -n "$task_id" ]]; then "$ctl" cancel "$task_id" "$instance" >/dev/null 2>&1 || true; fi
    if [[ -n "$task2_id" ]]; then "$ctl" cancel "$task2_id" "$instance" >/dev/null 2>&1 || true; fi
    # The separate Session process may already have crashed, leaving native
    # clients running. Clean up only the exact, uniquely scoped test clients.
    kill_owned_app "$app_pid"
    kill_owned_app "$app2_pid"
    if [[ -n "$shell_pid" ]]; then kill "$shell_pid" 2>/dev/null || true; wait "$shell_pid" 2>/dev/null || true; fi
    if [[ -n "$session_pid" ]]; then kill "$session_pid" 2>/dev/null || true; wait "$session_pid" 2>/dev/null || true; fi
    [[ -d "$runtime" ]] && rm -rf -- "$runtime"
}
trap cleanup EXIT
"$session_bin" >"$runtime/session.log" 2>&1 &
session_pid=$!
initial=""
for _ in {1..100}; do
    if initial="$("$ctl" snapshot 2>/dev/null)"; then break; fi
    host_process_alive "$session_pid" 2>/dev/null || { cat "$runtime/session.log" >&2; exit 1; }
    sleep 0.1
done
[[ -n "$initial" ]] || { echo "Session startup timeout" >&2; exit 1; }
instance="$(printf '%s' "$initial" | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_instance"])')"
"$shell_bin" >"$runtime/shell.log" 2>&1 &
shell_pid=$!
sleep 3
host_process_alive "$shell_pid" || { echo "Shell startup failed" >&2; cat "$runtime/shell.log" >&2; exit 1; }
response="$("$ctl" launch personal notes)"
task_id="$(printf '%s' "$response" | python3 -c 'import json,sys;print(json.load(sys.stdin)["task"]["id"])')"
app_pid="$(printf '%s' "$response" | python3 -c 'import json,sys;d=json.load(sys.stdin)["task"];assert d["state"]=="running" and d["pid"];print(d["pid"])')"
second="$("$ctl" launch research calculator)"
task2_id="$(printf '%s' "$second" | python3 -c 'import json,sys;print(json.load(sys.stdin)["task"]["id"])')"
app2_pid="$(printf '%s' "$second" | python3 -c 'import json,sys;d=json.load(sys.stdin)["task"];assert d["state"]=="running" and d["pid"];print(d["pid"])')"
[[ "$app_pid" != "$app2_pid" ]] || { echo "Distinct apps must have distinct PIDs" >&2; exit 1; }
for pid in "$app_pid" "$app2_pid"; do
    real_exe="$(readlink "/proc/$pid/exe" 2>/dev/null || true)"
    [[ "$real_exe" == */trill-app-window ]] || {
        echo "PID $pid is not the expected native Rust app executable: $real_exe" >&2
        exit 1
    }
done
# PID existence alone cannot prove the Rust GUI even reached App::update.
# The session reads an exact one-frame marker from each owned child pipe.
ready=0
for _ in {1..100}; do
    observed="$("$ctl" snapshot)"
    if printf '%s' "$observed" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for id,pid in ((int(sys.argv[1]),int(sys.argv[2])),(int(sys.argv[3]),int(sys.argv[4]))):
    task=next(t for t in d["tasks"] if t["id"] == id)
    assert task["pid"] == pid and task["state"] == "running", task
    assert task["ui_first_frame_unix_ms"] is not None, task
' "$task_id" "$app_pid" "$task2_id" "$app2_pid"; then
        ready=1
        break
    fi
    sleep 0.1
done
if [[ "$ready" -ne 1 ]]; then
    echo "At least one native app never reached its first egui update" >&2
    cat "$runtime/session.log" >&2
    exit 1
fi
host_process_alive "$app_pid" || { echo "Notes died before shell restart" >&2; exit 1; }
host_process_alive "$app2_pid" || { echo "Calculator died before shell restart" >&2; exit 1; }
kill "$shell_pid"
wait "$shell_pid" 2>/dev/null || true
shell_pid=""
host_process_alive "$app_pid" || { echo "Shell exit killed Notes" >&2; exit 1; }
host_process_alive "$app2_pid" || { echo "Shell exit killed Calculator" >&2; exit 1; }
actual="$("$ctl" snapshot)"
printf '%s' "$actual" | python3 -c '
import json,sys
d=json.load(sys.stdin)
assert d["session_instance"] == sys.argv[1]
assert any(t["id"] == int(sys.argv[2]) and t["state"] == "running" and
           t["pid"] == int(sys.argv[3]) and t["ui_first_frame_unix_ms"] is not None
           for t in d["tasks"]), "Notes ownership/first frame lost"
assert any(t["id"] == int(sys.argv[4]) and t["state"] == "running" and
           t["pid"] == int(sys.argv[5]) and t["ui_first_frame_unix_ms"] is not None
           for t in d["tasks"]), "Calculator ownership/first frame lost"
' "$instance" "$task_id" "$app_pid" "$task2_id" "$app2_pid"
"$shell_bin" >"$runtime/shell-restart.log" 2>&1 &
shell_pid=$!
sleep 3
host_process_alive "$shell_pid" || { echo "Shell restart failed" >&2; cat "$runtime/shell-restart.log" >&2; exit 1; }
"$ctl" cancel "$task_id" "$instance" >/dev/null
"$ctl" cancel "$task2_id" "$instance" >/dev/null
terminal=""
for _ in {1..100}; do
    terminal="$("$ctl" snapshot)"
    if printf '%s' "$terminal" | python3 -c '
import json,sys
d=json.load(sys.stdin)
tasks=[t for t in d["tasks"] if t["id"] in (int(sys.argv[1]),int(sys.argv[2]))]
sys.exit(0 if len(tasks) == 2 and all(t["state"] in ("cancelled","failed","completed") for t in tasks) else 1)
' "$task_id" "$task2_id"; then break; fi
    sleep 0.1
done
printf '%s' "$terminal" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for id in (int(sys.argv[1]),int(sys.argv[2])):
    t=next(t for t in d["tasks"] if t["id"] == id)
    assert t["state"] == "cancelled", f"Expected SIGKILL confirmation, got {t}"
' "$task_id" "$task2_id"
task_id=""
task2_id=""
printf 'Wayland host Shell restart, two Rust first frames and observed cancellation: PASS\n'
printf 'NOT VERIFIED: real CJK candidates, compositor restart, GPU reset or Asterinas boot.\n'
