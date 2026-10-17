#!/usr/bin/env bash
# Host-only real kernel SO_PEERCRED acceptance; temporary unprivileged Session.
set -euo pipefail
source_dir="${1:?Usage: a10-test-cross-uid-peer.sh <directory with trill-session and trill-ctl>}"
[[ -x "$source_dir/trill-session" && -x "$source_dir/trill-ctl" ]] || { echo 'Rust host ELF missing' >&2; exit 2; }
command -v sudo >/dev/null
sudo -n true
root="$(mktemp -d "${TMPDIR:-/tmp}/a10-uid-replay.XXXXXXXX")"
runtime="$root/runtime"
launcher=""
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -r "$runtime/session.pid" ]]; then
        local child
        child="$(cat "$runtime/session.pid" 2>/dev/null || true)"
        if [[ "$child" =~ ^[1-9][0-9]*$ ]] && [[ -r "/proc/$child/environ" ]]; then
            local exe
            exe="$(readlink "/proc/$child/exe" 2>/dev/null || true)"
            if [[ "$exe" == "$root/bin/trill-session" ]] &&
                tr '\0' '\n' <"/proc/$child/environ" | grep -Fxq "XDG_RUNTIME_DIR=$runtime"; then
                sudo -n kill "$child" 2>/dev/null || true
            fi
        fi
    fi
    [[ -z "$launcher" ]] || { kill "$launcher" 2>/dev/null || true; wait "$launcher" 2>/dev/null || true; }
    sudo -n rm -rf -- "$root"
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
ready=0
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
if env XDG_RUNTIME_DIR="$runtime" "$root/bin/trill-ctl" snapshot >"$root/foreign.json" 2>"$root/foreign.err"; then
    echo 'CROSS_UID_PEER_ACCEPTED: root requester read nobody Session (the old binary lacks SO_PEERCRED)' >&2
    exit 1
fi
grep -Fq 'Cross-UID host UI IPC request refused' "$root/session.log" || {
    echo 'Foreign client denied for a reason other than SO_PEERCRED UID mismatch' >&2
    cat "$root/session.log" >&2
    exit 1
}
sudo -n -u nobody env XDG_RUNTIME_DIR="$runtime" "$root/bin/trill-ctl" snapshot >"$root/post-denial.json"
python3 - "$root/owner.json" "$root/post-denial.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));y=json.load(open(sys.argv[2]));assert x['session_instance']==y['session_instance'] and not y['tasks']
PY
printf 'A10 SO_PEERCRED live cross-UID rejection PASS: kernel socket denies root client to nobody Session, legitimate same-UID client still served\n'
