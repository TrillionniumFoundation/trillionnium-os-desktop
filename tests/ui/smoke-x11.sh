#!/usr/bin/env bash
# Actual Rust Linux/X11 host compatibility with a test-owned Xvfb server.
# NOT Wayland, Asterinas, trusted Xwayland isolation, a live IME or a GPU test.
set -euo pipefail
export PYTHONOPTIMIZE=0
bin_dir="${1:?Usage: smoke-x11.sh <absolute directory of built Rust binaries>}"
[[ "$bin_dir" = /* ]] || { echo 'X11 binary directory must be absolute' >&2; exit 2; }
for tool in Xvfb xdpyinfo xwininfo xprop xauth python3 sha256sum; do
    command -v "$tool" >/dev/null || { echo "Missing X11 test tool: $tool" >&2; exit 2; }
done
for program in trill-shell trill-app-window trill-session trill-ctl; do
    [[ -x "$bin_dir/$program" ]] || { echo "Missing real Rust ELF: $program" >&2; exit 2; }
done
root="$(mktemp -d "${TMPDIR:-/tmp}/a10-real-x11.XXXXXXXX")"
chmod 700 "$root"
mkdir -m 700 "$root/runtime"
xserver_pid=''; shell_pid=''; session_pid=''; app_pids=(); task_ids=()
cleanup() {
    local status=$? pid exe
    trap - EXIT
    if [[ -n "$shell_pid" ]]; then kill "$shell_pid" 2>/dev/null || true; wait "$shell_pid" 2>/dev/null || true; fi
    if [[ -n "$session_pid" ]]; then kill "$session_pid" 2>/dev/null || true; wait "$session_pid" 2>/dev/null || true; fi
    if [[ -n "$xserver_pid" ]]; then kill "$xserver_pid" 2>/dev/null || true; wait "$xserver_pid" 2>/dev/null || true; fi
    # Kill only verified children we ourselves launched via this Session.
    for pid in "${app_pids[@]}"; do
        if [[ -r "/proc/$pid/exe" ]]; then
            exe="$(readlink "/proc/$pid/exe" 2>/dev/null || true)"
            [[ "$exe" != "$bin_dir/trill-app-window" ]] || kill "$pid" 2>/dev/null || true
        fi
    done
    if [[ "$status" -ne 0 ]]; then
        echo "A10 X11 smoke FAILED (Linux-host only)" >&2
        for f in "$root"/*.log; do if [[ -f "$f" ]]; then tail -n 35 "$f" >&2; fi; done
        if [[ "${A10_X11_EVIDENCE_DIR:-}" = /* ]]; then
            mkdir -p -- "$A10_X11_EVIDENCE_DIR"
            for f in window-tree.txt window-report.txt session.log shell-before.log shell-after.log xvfb.log; do
                if [[ -f "$root/$f" ]]; then cp -- "$root/$f" "$A10_X11_EVIDENCE_DIR/"; fi
            done
            printf '%s\n' "$status" > "$A10_X11_EVIDENCE_DIR/failed-exit-code.txt"
        fi
    fi
    rm -rf -- "$root"
    exit "$status"
}
trap cleanup EXIT
unset DISPLAY WAYLAND_DISPLAY
for number in {105..135}; do
    if [[ ! -S "/tmp/.X11-unix/X$number" && ! -f "/tmp/.X$number-lock" ]]; then
        export DISPLAY=":$number"
        break
    fi
done
[[ -n "${DISPLAY:-}" ]] || { echo 'No free private Xvfb display number' >&2; exit 2; }
auth="$root/.Xauthority"
touch "$auth"
chmod 600 "$auth"
export XAUTHORITY="$auth" XDG_RUNTIME_DIR="$root/runtime"
export WINIT_UNIX_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1
unset WAYLAND_DISPLAY
xauth -f "$auth" add "$DISPLAY" . "$(python3 -c 'import secrets; print(secrets.token_hex(16))')" >/dev/null
Xvfb "$DISPLAY" -nolisten tcp -screen 0 1280x800x24 -auth "$auth" >"$root/xvfb.log" 2>&1 & xserver_pid=$!
ready=0
for _ in {1..100}; do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then ready=1; break; fi
    kill -0 "$xserver_pid" 2>/dev/null || break
    sleep 0.05
done
[[ "$ready" == 1 ]] || { echo 'Private Xvfb server startup failed' >&2; exit 1; }
# A test-only private X11 server must actually require the test cookie.
# This is NOT domain isolation between clients that share the cookie.
if XAUTHORITY="$root/unknown-cookie" xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    echo 'Test-owned Xvfb accepted an unauthenticated client' >&2
    exit 1
fi
"$bin_dir/trill-session" >"$root/session.log" 2>&1 & session_pid=$!
ctl="$bin_dir/trill-ctl"
initial=''
for _ in {1..100}; do
    if initial="$("$ctl" snapshot 2>/dev/null)"; then break; fi
    kill -0 "$session_pid" 2>/dev/null || { echo 'Rust Session exited' >&2; exit 1; }
    sleep 0.05
done
[[ -n "$initial" ]] || { echo 'Rust Session IPC not ready' >&2; exit 1; }
instance="$(printf '%s' "$initial" | python3 -c 'import json,re,sys; d=json.load(sys.stdin); assert d["type"]=="snapshot" and not d["tasks"]; assert re.fullmatch("[0-9a-f]{32}",d["session_instance"]); print(d["session_instance"])')"
"$bin_dir/trill-shell" >"$root/shell-before.log" 2>&1 & shell_pid=$!
wait_shell_layout() {
    local output=$1
    for _ in {1..150}; do
        if grep -Fxq 'TRILL_SHELL_FIRST_FRAME_V1' "$output"; then return 0; fi
        kill -0 "$shell_pid" 2>/dev/null || break
        sleep 0.1
    done
    echo 'No actual Rust Shell first egui layout' >&2
    return 1
}
wait_shell_layout "$root/shell-before.log"
for app in notes calculator terminal; do
    response="$("$ctl" launch research "$app")"
    read -r id pid <<<"$(printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); t=d["task"]; assert d["type"]=="task" and t["state"]=="running" and t["pid"]; print(t["id"],t["pid"])')"
    task_ids+=("$id")
    app_pids+=("$pid")
    first=0
    for _ in {1..150}; do
        snap="$("$ctl" snapshot)"
        result="$(printf '%s' "$snap" | python3 -c 'import json,sys; d=json.load(sys.stdin);t=next(x for x in d["tasks"] if x["id"]==int(sys.argv[1]));print(t["state"],t["ui_first_frame_unix_ms"] or 0, t["pid"])' "$id")"
        read -r state frame observed_pid <<<"$result"
        [[ "$state" == failed ]] && break
        if [[ "$state" == running && "$frame" != 0 && "$observed_pid" == "$pid" ]]; then first=1; break; fi
        sleep 0.1
    done
    [[ "$first" == 1 ]] || { echo "No real $app native layout: $result" >&2; exit 1; }
done
assert_mapped_windows() {
    python3 - "$root/window-tree.txt" "$root/window-report.txt" <<'PYMAP'
from pathlib import Path
import re,subprocess,sys,time
# An egui layout can precede X11 MapNotify. Observe the actual server state
# under a separate bounded presentation deadline; layout markers never pass it.
deadline=time.monotonic()+15
def query(*command):
    left=deadline-time.monotonic()
    if left<=0:
        raise TimeoutError("X11 presentation deadline elapsed")
    return subprocess.check_output(command,text=True,timeout=min(2,left))
last="No X11 server observation"
while time.monotonic()<deadline:
    reports=[]
    try:
        s=query("xwininfo","-root","-tree")
        Path(sys.argv[1]).write_text(s)
        ids=[]
        for klass,required in (("trill-shell",1),("trill-app-window",3)):
            matches=re.findall(r'^\s*(0x[0-9a-fA-F]+).*?\("'+klass+r'" "'+klass+r'"\)',s,re.M)
            if len(matches)!=required:
                raise ValueError((klass,len(matches),s))
            ids.extend(matches)
        if len(set(ids))!=4:
            raise ValueError(("nonunique windows",ids))
        for wid in ids:
            report=query("xwininfo","-id",wid)
            props=query("xprop","-id",wid,"WM_CLASS")
            reports.append(report+props)
            if "Map State: IsViewable" not in report or 'trill-' not in props:
                raise ValueError((wid,report,props))
        if time.monotonic()>=deadline:
            raise TimeoutError("X11 observation completed after deadline")
        Path(sys.argv[2]).write_text("\n".join(reports))
        break
    except (OSError,ValueError,TimeoutError,subprocess.SubprocessError) as error:
        last=str(error)
        Path(sys.argv[2]).write_text("\n".join(reports)+"\n"+last+"\n")
        time.sleep(min(.05,max(0,deadline-time.monotonic())))
else:
    raise RuntimeError("Four real mapped X11 windows not observed: "+last)
print("A10 mapped X11 windows verified: 1 Rust Shell + 3 independently spawned Rust apps")
PYMAP
}
assert_mapped_windows
# A Shell restart must not terminate/relabel independently Session-owned apps.
kill "$shell_pid"
wait "$shell_pid" 2>/dev/null || true
shell_pid=''
"$bin_dir/trill-shell" >"$root/shell-after.log" 2>&1 & shell_pid=$!
wait_shell_layout "$root/shell-after.log"
snap="$("$ctl" snapshot)"
printf '%s' "$snap" | python3 -c '
import json,sys
d=json.load(sys.stdin)
assert d["session_instance"]==sys.argv[1]
byid={str(t["id"]):t for t in d["tasks"]}
for task,pid in zip(sys.argv[2::2],sys.argv[3::2]):
    assert byid[task]["state"]=="running",byid[task]
    assert byid[task]["pid"]==int(pid),byid[task]
    assert byid[task]["ui_first_frame_unix_ms"],byid[task]
' "$instance" "${task_ids[0]}" "${app_pids[0]}" "${task_ids[1]}" "${app_pids[1]}" "${task_ids[2]}" "${app_pids[2]}"
assert_mapped_windows
# Optional independent framebuffer capture; the mandatory X11 gate above
# does not invent evidence of rendered pixels when scrot/Pillow are absent.
if command -v scrot >/dev/null && python3 -c 'from PIL import Image' >/dev/null 2>&1; then
    scrot -o "$root/x11-frame.png"
    python3 - "$root/x11-frame.png" <<'PYPIX'
import hashlib,sys
from PIL import Image
p=sys.argv[1]
im=Image.open(p).convert('RGB')
colors=im.getcolors(maxcolors=1000000)
assert im.size==(1280,800),im.size
assert colors is None or len(colors)>128,"Blank or unrendered virtual X11 framebuffer"
print("A10 X11 framebuffer pixels VERIFIED:",im.size,"colors",">1000000" if colors is None else len(colors),"SHA256",hashlib.sha256(open(p,'rb').read()).hexdigest())
PYPIX
else
    echo 'A10 X11 framebuffer pixels NOT VERIFIED: scrot/Pillow not installed'
    if [[ "${A10_REQUIRE_X11_PIXELS:-0}" = 1 ]]; then
        echo 'This qualification requires an actual framebuffer capture.' >&2
        exit 2
    fi
fi
for id in "${task_ids[@]}"; do "$ctl" cancel "$id" "$instance" >/dev/null; done
for _ in {1..100}; do
    snap="$("$ctl" snapshot)"
    if printf '%s' "$snap" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for id in sys.argv[1:]:
    assert next(t for t in d["tasks"] if t["id"]==int(id))["state"]=="cancelled"
' "${task_ids[@]}" 2>/dev/null; then
        all_cancelled=1
        break
    fi
    sleep 0.05
done
[[ "${all_cancelled:-0}" == 1 ]] || { echo 'At least one X11 child was not observed cancelled' >&2; exit 1; }
# Machine receipt is created only after all real host checks pass.
python3 - "$bin_dir" "$root/x11-frame.png" "$root/receipt.json" <<'PYRECEIPT'
import hashlib,json,sys
from pathlib import Path
binary_dir=Path(sys.argv[1])
frame=Path(sys.argv[2])
receipt=Path(sys.argv[3])
programs={}
for name in ('trill-session','trill-shell','trill-app-window','trill-ctl'):
    h=hashlib.sha256()
    with open(binary_dir/name,'rb') as data:
        for block in iter(lambda:data.read(1<<20),b''):
            h.update(block)
    programs[name]=h.hexdigest()
pixels={'status':'not_verified_no_scrot_or_pillow'}
if frame.is_file():
    from PIL import Image
    im=Image.open(frame).convert('RGB')
    colors=im.getcolors(maxcolors=1000000)
    pixels={'status':'verified_nonblank_xvfb','width':im.width,'height':im.height,
            'unique_colors':'>1000000' if colors is None else len(colors),
            'sha256':hashlib.sha256(frame.read_bytes()).hexdigest()}
receipt.write_text(json.dumps({
    'schema':'a10-real-linux-x11-mapped-windows-v1',
    'source':'actual executable ELF under isolated Xvfb; no Wayland or kernel grant',
    'elf_sha256':programs,
    'mapped_x11_window_classes':{'trill-shell':1,'trill-app-window':3},
    'mapped_x11_state':'IsViewable',
    'shell_first_egui_layout_before_and_after_restart':True,
    'same_independent_session_and_three_client_pids_across_shell_restart':True,
    'all_three_clients_cancelled_by_observed_reap':True,
    'virtual_framebuffer':pixels,
    'not_attested':['Wayland presentation','real CJK candidate window',
                    'per-trust-domain Xwayland isolation','physical GPU reset',
                    'A05/A07 authority','Asterinas graphical boot']
},indent=2)+'\n')
PYRECEIPT
if [[ -n "${A10_X11_EVIDENCE_DIR:-}" ]]; then
    [[ "$A10_X11_EVIDENCE_DIR" = /* ]] || { echo 'X11 evidence directory must be absolute' >&2; exit 2; }
    mkdir -p -- "$A10_X11_EVIDENCE_DIR"
    cp -- "$root/receipt.json" "$root/window-tree.txt" "$A10_X11_EVIDENCE_DIR/"
    if [[ -f "$root/x11-frame.png" ]]; then
        cp -- "$root/x11-frame.png" "$A10_X11_EVIDENCE_DIR/"
    fi
fi
printf 'A10 real Linux/X11 smoke PASSED: Shell + 3 independent mapped native windows, Shell restart, observed child lifecycle (NOT Wayland/IME/kernel)\n'
