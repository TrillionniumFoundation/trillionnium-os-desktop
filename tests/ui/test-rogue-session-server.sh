#!/usr/bin/env bash
# Real Linux-host client test: reject a forged cross-UID Session BEFORE reading
# its fabricated task state. No production sockets, no A05 grant authority.
set -euo pipefail
export PYTHONOPTIMIZE=0
source_dir="${1:?Usage: test-rogue-session-server.sh <real Rust binary directory>}"
[[ -x "$source_dir/trill-ctl" ]] || { echo 'Missing real Rust trill-ctl' >&2; exit 2; }
command -v sudo >/dev/null
sudo -n true
root="$(mktemp -d "${TMPDIR:-/tmp}/a10-rogue-session.XXXXXXXX")"
server_pid=""
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -n "$server_pid" ]]; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    sudo -n rm -rf -- "$root"
    exit "$status"
}
trap cleanup EXIT
chmod 755 "$root"
mkdir -m 755 "$root/bin"
install -m 755 "$source_dir/trill-ctl" "$root/bin/trill-ctl"
mkdir -m 700 "$root/runtime"
sudo -n chown 65534:65534 "$root/runtime"
cat >"$root/rogue-server.py" <<'PY'
import json,os,socket,sys
runtime=sys.argv[1]
private=os.path.join(runtime,'trillionnium-ui')
os.mkdir(private,0o700)
path=os.path.join(private,'session.sock')
s=socket.socket(socket.AF_UNIX)
s.settimeout(6)
s.bind(path)
os.chmod(path,0o600)
s.listen(1)
try:
    conn,_=s.accept()
    conn.settimeout(3)
    request=conn.recv(8192)
    with open(os.path.join(runtime,'received-size'),'w') as out:
        out.write(str(len(request)))
    if request:
        response={'type':'snapshot','tasks':[],'resources':{
            'sampled_unix_ms':1,'mem_total_kib':None,'mem_available_kib':None,
            'load_average_1m':None,'source':'FORGED_CROSS_UID_SESSION',
            'wayland':{'status':'unconfigured','socket_observation_epoch':0,'sampled_unix_ms':0}},
            'session_instance':'forged-generation'}
        conn.sendall(json.dumps(response,separators=(',',':')).encode()+b'\n')
    conn.close()
finally:
    s.close()
PY
chmod 644 "$root/rogue-server.py"
sudo -n -u nobody python3 "$root/rogue-server.py" "$root/runtime" >"$root/server.log" 2>&1 &
server_pid=$!
ready=0
for _ in {1..100}; do
    # The listener is inside nobody's 0700 directory. The ordinary CI runner
    # cannot stat it, so use the already-required sudo for this owned path.
    if sudo -n test -S "$root/runtime/trillionnium-ui/session.sock"; then ready=1; break; fi
    kill -0 "$server_pid" 2>/dev/null || break
    sleep 0.05
done
[[ "$ready" == 1 ]] || { echo 'Rogue test listener was not established' >&2; cat "$root/server.log" >&2; exit 1; }
if sudo -n env XDG_RUNTIME_DIR="$root/runtime" "$root/bin/trill-ctl" snapshot >"$root/forged.json" 2>"$root/ctl.err"; then
    echo 'FORGED_SERVER_ACCEPTED: real Rust CLI trusted a cross-UID fake Snapshot' >&2
    exit 1
fi
if grep -Fq 'FORGED_CROSS_UID_SESSION' "$root/forged.json"; then
    echo 'FORGED_STATUS_DELIVERED despite failed exit code' >&2
    exit 1
fi
grep -Fq 'Cross-UID host UI IPC request refused' "$root/ctl.err" || {
    echo 'Cross-UID server was refused for an unrelated reason' >&2
    cat "$root/ctl.err" >&2
    exit 1
}
wait "$server_pid"
server_pid=""
[[ "$(sudo -n cat "$root/runtime/received-size")" == 0 ]] || {
    echo 'CLI sent a request before authenticating socket peer UID' >&2
    exit 1
}
printf 'A10 REAL forged Session refusal PASS: cross-UID server cannot deliver task snapshots or receive a CLI request (not A05 authentication)\n'
