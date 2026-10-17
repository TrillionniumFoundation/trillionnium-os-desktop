#!/usr/bin/env bash
# Host-only destructive compositor restart test. Kills only the Weston that
# this script starts, never the user's compositor or an unrelated client.
set -euo pipefail
cd "$(dirname "$0")/../.."
for cmd in weston wayland-info cargo python3 timeout; do
    command -v "$cmd" >/dev/null || { echo "Missing host test tool: $cmd" >&2; exit 2; }
done
cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked >/dev/null
ctl=./ui/target/debug/trill-ctl
session_bin=./ui/target/debug/trill-session
runtime="$(mktemp -d "${TMPDIR:-/tmp}/a10-compositor-restart.XXXXXXXX")"
chmod 700 "$runtime"
export XDG_RUNTIME_DIR="$runtime" WAYLAND_DISPLAY="wayland-a10-restart"
export LIBGL_ALWAYS_SOFTWARE=1 EGL_PLATFORM=wayland
unset DISPLAY
source support/ui/smoke-cleanup.sh
weston_pid=""
session_pid=""
old_pid=""
new_pid=""
old_id=""
new_id=""
instance=""

cleanup() {
    local status=$?
    trap - EXIT
    if [[ "$status" -ne 0 ]]; then
        echo "A10 owned Weston crash/restart smoke FAILED (exit $status)" >&2
        for log in "$runtime"/*.log; do
            [[ -f "$log" ]] && { echo "== $log ==" >&2; tail -65 "$log" >&2; }
        done
    fi
    if [[ -n "$instance" ]]; then
        [[ -z "$old_id" ]] || "$ctl" cancel "$old_id" "$instance" >/dev/null 2>&1 || true
        [[ -z "$new_id" ]] || "$ctl" cancel "$new_id" "$instance" >/dev/null 2>&1 || true
    fi
    kill_owned_app "$old_pid"
    kill_owned_app "$new_pid"
    if [[ -n "$session_pid" ]]; then
        kill "$session_pid" 2>/dev/null || true
        wait "$session_pid" 2>/dev/null || true
    fi
    if [[ -n "$weston_pid" ]]; then
        kill "$weston_pid" 2>/dev/null || true
        wait "$weston_pid" 2>/dev/null || true
    fi
    if [[ -n "${A10_HEADLESS_LOG_DIR:-}" ]]; then
        mkdir -p -- "$A10_HEADLESS_LOG_DIR/compositor-restart" || true
        for log in "$runtime"/*.log "$runtime"/*.stdout; do
            [[ -f "$log" ]] && cp -- "$log" "$A10_HEADLESS_LOG_DIR/compositor-restart/" || true
        done
    fi
    rm -rf -- "$runtime"
    exit "$status"
}
trap cleanup EXIT

start_owned_weston() {
    local log="$1" ready=0
    weston --backend=headless-backend.so --socket="$WAYLAND_DISPLAY" \
        --idle-time=0 --log="$log" >"${log%.log}.stdout" 2>&1 &
    weston_pid=$!
    for _ in {1..100}; do
        if [[ -S "$runtime/$WAYLAND_DISPLAY" ]] &&
            timeout 2s wayland-info >/dev/null 2>&1; then
            ready=1
            break
        fi
        if ! host_process_alive "$weston_pid"; then
            echo "Owned Weston exited before registry round-trip" >&2
            return 1
        fi
        sleep 0.1
    done
    [[ "$ready" == 1 ]] || { echo "Owned Weston registry timeout" >&2; return 1; }
}

await_app_layout() {
    local id="$1" pid="$2" snapshot=""
    for _ in {1..100}; do
        snapshot="$("$ctl" snapshot)"
        if printf '%s' "$snapshot" | python3 -c '
import json,sys
s=json.load(sys.stdin)
wanted=int(sys.argv[2]); pid=int(sys.argv[3])
if s["session_instance"] != sys.argv[1]:
    raise SystemExit(1)
if not any(t["id"] == wanted and t["pid"] == pid and
           t["state"] == "running" and t["ui_first_frame_unix_ms"] is not None
           for t in s["tasks"]):
    raise SystemExit(1)
' "$instance" "$id" "$pid"; then
            host_process_alive "$pid" || { echo "App died after first layout" >&2; return 1; }
            return 0
        fi
        sleep 0.1
    done
    echo "New/old native client never reached a real egui layout" >&2
    printf '%s\n' "$snapshot" >&2
    return 1
}

start_owned_weston "$runtime/weston-before.log"
"$session_bin" >"$runtime/session.log" 2>&1 &
session_pid=$!
initial=""
for _ in {1..100}; do
    if initial="$("$ctl" snapshot 2>/dev/null)"; then break; fi
    host_process_alive "$session_pid" || { echo "Session died before socket setup" >&2; exit 1; }
    sleep 0.1
done
[[ -n "$initial" ]] || { echo "Host Session start timeout" >&2; exit 1; }
instance="$(printf '%s' "$initial" | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_instance"])')"
initial_socket_epoch="$(printf '%s' "$initial" | python3 -c '
import json,sys
o=json.load(sys.stdin)["resources"]["wayland"]
assert o["status"] == "socket_observed", o
assert o["socket_observation_epoch"] >= 1, o
print(o["socket_observation_epoch"])
')"

old_response="$("$ctl" launch personal notes)"
read -r old_id old_pid <<<"$(printf '%s' "$old_response" | python3 -c '
import json,sys
t=json.load(sys.stdin)["task"]
assert t["state"] == "running" and t["pid"]
print(t["id"], t["pid"])
')"
[[ -n "$old_id" && -n "$old_pid" ]] || { echo "Missing initial app identity" >&2; exit 1; }
old_launch_epoch="$(printf '%s' "$old_response" | python3 -c '
import json,sys
task=json.load(sys.stdin)["task"]
epoch=task["wayland_socket_epoch_at_launch"]
assert epoch is not None and epoch == int(sys.argv[1]), task
print(epoch)
' "$initial_socket_epoch")"
await_app_layout "$old_id" "$old_pid"

# Destroy only the private compositor while keeping the same session alive.
kill "$weston_pid"
wait "$weston_pid" 2>/dev/null || true
weston_pid=""
if timeout 2s wayland-info >/dev/null 2>&1; then
    echo "Wayland registry still connects after owned Weston exit" >&2
    exit 1
fi
host_process_alive "$session_pid" || { echo "Compositor death killed independent Session" >&2; exit 1; }
after="$("$ctl" snapshot)"
old_state="$(printf '%s' "$after" | python3 -c '
import json,sys
s=json.load(sys.stdin)
assert s["session_instance"] == sys.argv[1], "Session generation unexpectedly changed"
t=next(t for t in s["tasks"] if t["id"] == int(sys.argv[2]))
assert t["pid"] == int(sys.argv[3]), "Session lost original child identity"
assert t["state"] != "completed" or t["exit_code"] == 0, "fabricated host completion"
print(t["state"])
' "$instance" "$old_id" "$old_pid")"

# Remove only the dead private compositors own stale socket/lock paths. The
# old Weston has exited and registry probing has already failed closed.
rm -f -- "$runtime/$WAYLAND_DISPLAY" "$runtime/$WAYLAND_DISPLAY.lock"
missing_snapshot="$("$ctl" snapshot)"
missing_epoch="$(printf '%s' "$missing_snapshot" | python3 -c '
import json,sys
o=json.load(sys.stdin)["resources"]["wayland"]
assert o["status"] == "missing", o
assert o["socket_observation_epoch"] > int(sys.argv[1]), o
print(o["socket_observation_epoch"])
' "$initial_socket_epoch")"
start_owned_weston "$runtime/weston-after.log"
reconnected="$("$ctl" snapshot)"
printf '%s' "$reconnected" | python3 -c '
import json,sys
s=json.load(sys.stdin)
o=s["resources"]["wayland"]
assert s["session_instance"] == sys.argv[1]
assert o["status"] == "socket_observed", o
assert o["socket_observation_epoch"] > int(sys.argv[2]), o
old=next(t for t in s["tasks"] if t["id"] == int(sys.argv[3]))
assert old["wayland_socket_epoch_at_launch"] == int(sys.argv[4]), old
assert old["wayland_socket_epoch_at_launch"] < o["socket_observation_epoch"], old
' "$instance" "$missing_epoch" "$old_id" "$old_launch_epoch"
host_process_alive "$session_pid" || { echo "Session did not survive compositor restart" >&2; exit 1; }

new_response="$("$ctl" launch research calculator)"
read -r new_id new_pid <<<"$(printf '%s' "$new_response" | python3 -c '
import json,sys
t=json.load(sys.stdin)["task"]
assert t["state"] == "running" and t["pid"]
print(t["id"], t["pid"])
')"
[[ -n "$new_id" && -n "$new_pid" && "$old_pid" != "$new_pid" ]] || {
    echo "New compositor client identity invalid" >&2; exit 1;
}
printf '%s' "$new_response" | python3 -c '
import json,sys
task=json.load(sys.stdin)["task"]
epoch=task["wayland_socket_epoch_at_launch"]
assert epoch is not None and epoch > int(sys.argv[1]), task
' "$old_launch_epoch"
await_app_layout "$new_id" "$new_pid"
"$ctl" cancel "$new_id" "$instance" >/dev/null
new_state=""
for _ in {1..100}; do
    response="$("$ctl" snapshot)"
    new_state="$(printf '%s' "$response" | python3 -c '
import json,sys
s=json.load(sys.stdin)
assert s["session_instance"] == sys.argv[1]
print(next(t["state"] for t in s["tasks"] if t["id"] == int(sys.argv[2])))
' "$instance" "$new_id")"
    [[ "$new_state" != "cancel_requested" && "$new_state" != "running" ]] && break
    sleep 0.1
done
[[ "$new_state" == "cancelled" ]] || {
    echo "New client cancellation was not confirmed by observed SIGKILL: $new_state" >&2
    exit 1
}
echo "Compositor crash/restart PASS: same Session, socket epoch change, new Wayland client first layout, confirmed cancellation"
echo "Old client process after compositor loss: $old_state (NOT proof of surface reattach)"
echo "NOT VERIFIED: pre-crash client window continuity, CJK candidates, GPU reset or target OS"
