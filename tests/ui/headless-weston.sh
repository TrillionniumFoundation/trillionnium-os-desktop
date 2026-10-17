#!/usr/bin/env bash
# A10 CI: genuine Linux/Weston headless Wayland process exercise.
# No real monitor/GPU, no real IME, no Asterinas guest boot is claimed.
set -euo pipefail
# Many validation probes use Python assert: -O must never disable blockers.
export PYTHONOPTIMIZE=0
cd "$(dirname "$0")/../.."
command -v weston >/dev/null || { echo "weston executable not installed" >&2; exit 2; }
command -v wayland-info >/dev/null || { echo "wayland-info executable not installed" >&2; exit 2; }
command -v cargo >/dev/null || { echo "cargo toolchain not installed" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 not installed" >&2; exit 2; }

runtime="$(mktemp -d "${TMPDIR:-/tmp}/a10-weston.XXXXXXXX")"
chmod 700 "$runtime"
export XDG_RUNTIME_DIR="$runtime"
export WAYLAND_DISPLAY="wayland-a10"
export LIBGL_ALWAYS_SOFTWARE=1
export EGL_PLATFORM=wayland
unset DISPLAY
weston_pid=""

cleanup() {
    status=$?
    trap - EXIT
    if [[ "$status" -ne 0 ]]; then
        echo "A10 headless Weston smoke FAILED (exit $status)" >&2
        if [[ -f "$runtime/weston.log" ]]; then tail -120 "$runtime/weston.log" >&2; fi
        for log in "$runtime"/smoke/*.log; do
            if [[ -f "$log" ]]; then
                echo "== $log ==" >&2
                tail -80 "$log" >&2
            fi
        done
    fi
    if [[ -n "$weston_pid" ]]; then
        kill "$weston_pid" 2>/dev/null || true
        wait "$weston_pid" 2>/dev/null || true
    fi
    if [[ -n "${A10_HEADLESS_LOG_DIR:-}" ]]; then
        # Only export explicit text logs. Never copy Wayland/session Unix
        # sockets or transient runtime files into a CI artifact.
        mkdir -p -- "$A10_HEADLESS_LOG_DIR" || true
        for log in "$runtime/weston.log" "$runtime/weston.stdout" "$runtime"/smoke/*.log; do
            if [[ -f "$log" ]]; then
                cp -- "$log" "$A10_HEADLESS_LOG_DIR/" 2>/dev/null || true
            fi
        done
        if [[ -d "$runtime/hepta-layout" ]]; then
            mkdir -p -- "$A10_HEADLESS_LOG_DIR/hepta-layout" || true
            for log in "$runtime"/hepta-layout/*.log "$runtime"/hepta-layout/*.json; do
                [[ ! -f "$log" ]] || cp -- "$log" "$A10_HEADLESS_LOG_DIR/hepta-layout/" 2>/dev/null || true
            done
        fi
    fi
    rm -rf -- "$runtime"
    exit "$status"
}
trap cleanup EXIT

weston --backend=headless-backend.so --renderer=pixman --no-config --socket="$WAYLAND_DISPLAY" \
    --idle-time=0 --log="$runtime/weston.log" \
    >"$runtime/weston.stdout" 2>&1 &
weston_pid=$!

ready=0
for _ in {1..100}; do
    # Socket creation alone is not client readiness. Wait for a successful
    # Wayland registry round-trip from an actual client.
    if [[ -S "$runtime/$WAYLAND_DISPLAY" ]] &&
        timeout 2s wayland-info >/dev/null 2>&1; then
        ready=1
        break
    fi
    if ! kill -0 "$weston_pid" 2>/dev/null; then
        echo "Headless compositor exited before accepting Wayland clients" >&2
        exit 1
    fi
    sleep 0.1
done
[[ "$ready" -eq 1 ]] || { echo "Weston client connection timeout" >&2; exit 1; }

# The inner smoke script creates another private XDG_RUNTIME_DIR and connects
# to this exact compositor socket using an absolute WAYLAND_DISPLAY.
export A10_SMOKE_LOG_DIR="$runtime/smoke"
bash tests/ui/smoke-wayland.sh
python3 tests/ui/probe-hepta-wayland.py \
    --binaries "${CARGO_TARGET_DIR:-$PWD/ui/target}/debug" \
    --output "$runtime/hepta-layout"
# A separate private Weston is destroyed and restarted while its own Session
# stays alive. Do not interpret a fresh client's layout as old-client reattach.
bash tests/ui/compositor-restart.sh
printf 'A10 Weston headless client/session and crash/restart smoke: PASSED on this Linux runner\n'
printf 'NOT PROVEN: monitor mapping, real GPU buffer presentation, Chinese IME or Rust kernel boot\n'
