#!/usr/bin/env bash
# Host-only real kernel SO_PEERCRED acceptance; temporary unprivileged Session.
set -euo pipefail
export PYTHONOPTIMIZE=0
source_dir="${1:?Usage: a10-test-cross-uid-peer.sh <directory with trill-session and trill-ctl>}"
[[ -x "$source_dir/trill-session" && -x "$source_dir/trill-ctl" ]] || { echo 'Rust host ELF missing' >&2; exit 2; }
command -v sudo >/dev/null
sudo -n true
root="$(mktemp -d "${TMPDIR:-/tmp}/a10-uid-replay.XXXXXXXX")"
runtime="$root/runtime"
launcher=""
ready=0
cleanup() {
    local status=$? child="" exe="" cleanup_ok=1
    trap - EXIT
    # The runtime belongs to nobody (0700): an ordinary Ubuntu Runner is
    # unable to read session.pid. Use the already-authorized sudo only for
    # verified ownership and targeted teardown, never just rm the socket.
    if sudo -n test -e "$runtime/session.pid"; then
        if sudo -n test -L "$runtime/session.pid"; then
            echo 'Refusing symlinked unprivileged Session PID marker' >&2
            cleanup_ok=0
        else
            child="$(sudo -n cat -- "$runtime/session.pid" 2>/dev/null || true)"
            if [[ "$child" =~ ^[1-9][0-9]*$ ]]; then
                if sudo -n test -d "/proc/$child"; then
                    # /proc/<pid>/exe and environ can be ptrace-restricted
                    # even for sudo-root inside Docker or a hardened runner.
                    # /proc/<pid>/cmdline, comm and status are kernel-owned and
                    # readable without depending on CAP_SYS_PTRACE.
                    exe="$(sudo -n cat "/proc/$child/cmdline" 2>/dev/null | tr '\0' '\n' | sed -n '1p')"
                    local name owner
                    name="$(sudo -n cat "/proc/$child/comm" 2>/dev/null || true)"
                    owner="$(sudo -n awk '/^Uid:/ {print $3; exit}' "/proc/$child/status" 2>/dev/null || true)"
                    if [[ "$exe" == "$root/bin/trill-session" && "$name" == trill-session && "$owner" == 65534 ]]; then
                        sudo -n kill "$child" 2>/dev/null || cleanup_ok=0
                    else
                        echo 'Refusing to kill an unverified Session process/UID' >&2
                        cleanup_ok=0
                    fi
                fi
            else
                echo 'Unparseable Session PID; cannot assert cleanup' >&2
                cleanup_ok=0
            fi
        fi
    elif [[ "$ready" == 1 ]]; then
        echo 'Live Session marker inaccessible during teardown' >&2
        cleanup_ok=0
    fi
    if [[ -n "$launcher" ]]; then
        kill "$launcher" 2>/dev/null || true
        wait "$launcher" 2>/dev/null || true
    fi
    if [[ "$child" =~ ^[1-9][0-9]*$ ]] && sudo -n test -d "/proc/$child"; then
        if [[ "$(sudo -n cat "/proc/$child/cmdline" 2>/dev/null | tr '\0' '\n' | sed -n '1p')" == "$root/bin/trill-session" ]]; then
            echo 'Disposable Session remained live after teardown' >&2
            cleanup_ok=0
        fi
    fi
    sudo -n rm -rf -- "$root" || cleanup_ok=0
    if [[ "$cleanup_ok" != 1 ]]; then status=1; fi
    if [[ "$status" == 0 ]]; then
        printf 'A10 SO_PEERCRED live BIDIRECTIONAL refusal PASS: root CLI distrusts nobody server, raw root client refused, same-UID owner served, verified Session teardown\n'
    fi
    exit "$status"
}
trap cleanup EXIT
chmod 755 "$root"
mkdir -m 755 "$root/bin"
install -m 755 "$source_dir/trill-session" "$root/bin/trill-session"
install -m 755 "$source_dir/trill-ctl" "$root/bin/trill-ctl"
mkdir -m 700 "$runtime"
sudo -n chown 65534:65534 "$runtime"
sudo -n -u nobody env XDG_RUNTIME_DIR="$runtime" sh -c '
    printf "%s\n" "$$" > "$XDG_RUNTIME_DIR/session.pid"
    exec "$1"
' sh "$root/bin/trill-session" >"$root/session.log" 2>&1 &
launcher="$!"
for _ in {1..100}; do
    if sudo -n -u nobody env XDG_RUNTIME_DIR="$runtime" "$root/bin/trill-ctl" snapshot >"$root/owner.json" 2>/dev/null; then
        ready=1
        break
    fi
    sleep 0.05
done
[[ "$ready" == 1 ]] || { echo 'Unprivileged Session startup failed' >&2; cat "$root/session.log" >&2; exit 1; }
python3 - "$root/owner.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]));assert s['type']=='snapshot' and s['tasks']==[],s
PY
# Verify CLIENT-SIDE rejection before trusting a different UID's server.
if sudo -n env XDG_RUNTIME_DIR="$runtime" "$root/bin/trill-ctl" snapshot >"$root/foreign.json" 2>"$root/foreign.err"; then
    echo 'CROSS_UID_SERVER_TRUSTED: root CLI accepted nobody Session' >&2
    exit 1
fi
grep -Fq 'Cross-UID host UI IPC request refused' "$root/foreign.err" || {
    echo 'Cross-UID CLI failed for a reason other than SO_PEERCRED mismatch' >&2
    cat "$root/foreign.err" >&2
    exit 1
}
sudo -n python3 - "$runtime/trillionnium-ui/session.sock" <<'PYFOREIGN'
import socket,sys
peer=socket.socket(socket.AF_UNIX)
peer.settimeout(2)
peer.connect(sys.argv[1])
try:
    peer.sendall(b'{"type":"snapshot"}\n')
    received=peer.recv(4096)
except (BrokenPipeError,ConnectionResetError):
    received=b''
finally:
    peer.close()
if received:
    raise SystemExit("Cross-UID raw client received unauthorized Session bytes")
PYFOREIGN
seen=0
for _ in {1..50}; do
    if grep -Fq 'Cross-UID host UI IPC request refused' "$root/session.log"; then
        seen=1
        break
    fi
    sleep 0.05
done
[[ "$seen" == 1 ]] || {
    echo 'Kernel Session did not record server-side foreign UID refusal' >&2
    cat "$root/session.log" >&2
    exit 1
}
sudo -n -u nobody env XDG_RUNTIME_DIR="$runtime" "$root/bin/trill-ctl" snapshot >"$root/post-denial.json"
python3 - "$root/owner.json" "$root/post-denial.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));y=json.load(open(sys.argv[2]));assert x['session_instance']==y['session_instance'] and not y['tasks']
PY
