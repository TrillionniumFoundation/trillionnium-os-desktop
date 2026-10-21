#!/usr/bin/env bash
set -euo pipefail
umask 077
c_root="$(pwd -P)"
test -f "$c_root/SOURCE_HEAD.txt"
bin_dir="$c_root/target/debug"
for program in trill-app-window examples/notes_host_probe; do
  test -x "$bin_dir/$program"
done
for program in Xvfb xauth xdpyinfo xdotool xwininfo python3 timeout; do
  command -v "$program" >/dev/null
done
mkdir -p "$c_root/evidence"
probe_dir="$(mktemp -d "$c_root/evidence/notes-x11.XXXXXXXX")"
mkdir -m 700 "$probe_dir/runtime"
xserver_pid=''; probe_pid=''
cleanup() {
  local status=$?
  trap - EXIT
  # The bounded Rust probe owns/reaps its Notes child on normal/error return.
  # Waiting preserves that cleanup instead of terminating the owner first.
  if [[ -n "$probe_pid" ]]; then wait "$probe_pid" 2>/dev/null || true; fi
  if [[ -n "$xserver_pid" ]]; then
    kill "$xserver_pid" 2>/dev/null || true
    wait "$xserver_pid" 2>/dev/null || true
  fi
  printf '%s\n' "$probe_dir"
  exit "$status"
}
trap cleanup EXIT
unset DISPLAY WAYLAND_DISPLAY
for number in {195..225}; do
  if [[ ! -S "/tmp/.X11-unix/X$number" && ! -f "/tmp/.X$number-lock" ]]; then
    export DISPLAY=":$number"; break
  fi
done
test -n "${DISPLAY:-}"
auth="$probe_dir/xauthority"
touch "$auth"; chmod 600 "$auth"
export XAUTHORITY="$auth" XDG_RUNTIME_DIR="$probe_dir/runtime"
export WINIT_UNIX_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1
xauth -f "$auth" add "$DISPLAY" . "$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
Xvfb "$DISPLAY" -nolisten tcp -screen 0 1280x800x24 -auth "$auth" >"$probe_dir/xvfb.log" 2>&1 &
xserver_pid=$!
ready=0
for _ in {1..100}; do
  if xdpyinfo -display "$DISPLAY" >"$probe_dir/xdpyinfo.txt" 2>/dev/null; then ready=1; break; fi
  kill -0 "$xserver_pid" 2>/dev/null || break
  sleep 0.05
done
test "$ready" = 1
if XAUTHORITY="$probe_dir/no-cookie" xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
  printf 'isolated Xvfb failed its authorization negative check\n' >&2; exit 1
fi
TRILL_NOTES_PROBE_ISOLATED=1 TRILL_NOTES_PROBE_CAPTURE_MS=10000 \
  "$bin_dir/examples/notes_host_probe" "$bin_dir/trill-app-window" \
  >"$probe_dir/target-receipt.json" 2>"$probe_dir/probe.stderr.log" &
probe_pid=$!
app_pid=''
for _ in {1..300}; do
  if app_pid="$(python3 - "$probe_dir/target-receipt.json" <<'PY'
import json,sys
try:
    value=json.load(open(sys.argv[1])); pid=value['app_pid']
    assert isinstance(pid,int) and pid>0
    print(pid)
except Exception: sys.exit(1)
PY
)"; then break; fi
  kill -0 "$probe_pid" 2>/dev/null || break
  sleep 0.1
done
test -n "$app_pid"
test "$(readlink "/proc/$app_pid/exe")" = "$bin_dir/trill-app-window"
xdotool search --onlyvisible --pid "$app_pid" > "$probe_dir/windows.txt"
window="$(head -n 1 "$probe_dir/windows.txt")"
test -n "$window"
xwininfo -id "$window" > "$probe_dir/window.txt"
python3 - "$probe_dir/window.txt" <<'PY'
import sys
assert 'Map State: IsViewable' in open(sys.argv[1]).read()
PY
if command -v import >/dev/null; then
  timeout 8s import -window "$window" "$probe_dir/notes.png" \
    2>"$probe_dir/capture.stderr.log" || true
elif command -v xwd >/dev/null; then
  timeout 8s xwd -silent -id "$window" -out "$probe_dir/notes.xwd" \
    2>"$probe_dir/capture.stderr.log" || true
fi
wait "$probe_pid"; probe_pid=''
python3 - "$probe_dir" "$c_root/SOURCE_HEAD.txt" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]); receipt=json.loads((p/'target-receipt.json').read_text())
image=p/'notes.png'; nonblank=None
if image.is_file():
    try:
        from PIL import Image
        extrema=Image.open(image).convert('RGB').getextrema()
        nonblank=any(low!=high for low,high in extrema)
    except ImportError: pass
data={'source_head':Path(sys.argv[2]).read_text().strip(),'profile':'owned_xvfb_notes_destination','isolated_display_cookie_negative':True,'app_pid':receipt['app_pid'],'window_is_viewable':True,'target_receipt':receipt,'screenshot_png_sha256':hashlib.sha256(image.read_bytes()).hexdigest() if image.is_file() else None,'screenshot_nonblank':nonblank,'hepta_production_owner_run':False,'asterinas_run':False}
(p/'summary.json').write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
print(json.dumps(data,sort_keys=True))
PY
