#!/usr/bin/env bash
# Replay the REAL Rust binaries from a CI-produced, hash-verified Linux ELF
# bundle. This is independent of Cargo. This test needs no compositor and
# MUST NOT be counted as graphics, IME, GPU, HOS2 effect or kernel success.
set -euo pipefail
# The assertions below are security/test gates, never permit -O to disable them.
export PYTHONOPTIMIZE=0
bundle="${1:?Usage: replay-packaged-host.sh <tar.gz bundle> <40-hex source SHA>}"
source_sha="${2:?Missing exact source commit SHA}"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid exact source SHA' >&2; exit 2; }
[[ -f "$bundle" ]] || { echo 'Missing CI binary archive' >&2; exit 2; }
for command in tar sha256sum timeout python3; do
    command -v "$command" >/dev/null || { echo "Missing host utility: $command" >&2; exit 2; }
done
bundle="$(cd "$(dirname "$bundle")" && pwd -P)/$(basename "$bundle")"
checksums="$(dirname "$bundle")/$(basename "$bundle").sha256"
[[ -f "$checksums" ]] || { echo 'Missing outer artifact SHA256' >&2; exit 1; }
(cd "$(dirname "$bundle")" && sha256sum -c "$(basename "$checksums")" >/dev/null)

# Reject unexpected tar members, aliases, symlinks, devices or oversized
# decompressed contents before extraction. The archive is unprivileged CI data.
python3 - "$bundle" <<'PYTAR'
import sys, tarfile
root="a10-linux-host-binaries"
files={root+"/"+name for name in (
    "trill-session", "trill-shell", "trill-app-window", "trill-ctl", "trill-notes-recovery",
    "PROVENANCE.txt", "SHA256SUMS")}
with tarfile.open(sys.argv[1],"r:gz") as tar:
    entries=tar.getmembers()
    assert len(entries)==8, "expected exactly one directory and seven files"
    assert set(member.name for member in entries)==files|{root}, "unexpected tar members"
    assert sum(member.size for member in entries)<512*1024*1024, "unbounded tar"
    for member in entries:
        if member.name==root:
            assert member.isdir(), "archive root is not a directory"
        else:
            assert member.isfile() and member.size<128*1024*1024, "unsafe binary entry"
PYTAR
root="$(mktemp -d "${TMPDIR:-/tmp}/a10-elf-replay.XXXXXXXX")"
chmod 700 "$root"
runtime="$root/runtime"
mkdir -m 700 "$runtime"
session_pid=""
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -n "$session_pid" ]]; then
        kill "$session_pid" 2>/dev/null || true
        wait "$session_pid" 2>/dev/null || true
    fi
    if [[ "$status" -ne 0 ]]; then
        echo "A10 real ELF replay failed with $status (NOT graphics acceptance)" >&2
        [[ ! -f "$runtime/session.log" ]] || tail -50 "$runtime/session.log" >&2
    fi
    rm -rf -- "$root"
    exit "$status"
}
trap cleanup EXIT
# Archive already has fixed names; extract under an owned 0700 temporary dir.
tar -xzf "$bundle" -C "$root"
programs="$root/a10-linux-host-binaries"
(cd "$programs" && sha256sum -c SHA256SUMS >/dev/null)
grep -Fxq "Source commit: $source_sha" "$programs/PROVENANCE.txt" || {
    echo 'Source HEAD mismatch: running archive is not the requested commit' >&2
    exit 1
}
for bin in trill-session trill-shell trill-app-window trill-ctl trill-notes-recovery; do
    [[ -f "$programs/$bin" && -x "$programs/$bin" ]] || { echo "Missing ELF $bin" >&2; exit 1; }
    [[ "$(head -c 4 "$programs/$bin" | od -An -tx1 | tr -d ' \n')" == 7f454c46 ]] || {
        echo "Not an ELF: $bin" >&2; exit 1;
    }
done
export XDG_RUNTIME_DIR="$runtime"
unset WAYLAND_DISPLAY DISPLAY
ctl="$programs/trill-ctl"
service="$programs/trill-session"
"$service" >"$runtime/session.log" 2>&1 &
session_pid=$!
initial=""
for _ in {1..100}; do
    if initial="$("$ctl" snapshot 2>/dev/null)"; then break; fi
    kill -0 "$session_pid" 2>/dev/null || { echo 'Session executable exited' >&2; exit 1; }
    sleep 0.05
done
[[ -n "$initial" ]] || { echo 'Rust Session did not bind host socket' >&2; exit 1; }
instance="$(printf '%s' "$initial" | python3 -c '
import json,re,sys
s=json.load(sys.stdin)
assert s["type"]=="snapshot" and s["tasks"]==[],s
assert s["resources"]["wayland"]["status"]=="unconfigured",s
assert re.fullmatch("[0-9a-f]{32}",s["session_instance"])
print(s["session_instance"])
')"
[[ "$(stat -c %a "$runtime/trillionnium-ui/session.sock")" == 600 ]] || {
    echo 'Live Rust private IPC socket is not 0600' >&2; exit 1;
}
duplicate_status=0
timeout 3s "$service" >"$runtime/duplicate.log" 2>&1 || duplicate_status=$?
if [[ "$duplicate_status" == 0 || "$duplicate_status" == 124 || "$duplicate_status" == 137 ]]; then
    echo 'A second session was allowed to run or hung instead of promptly rejecting the held flock' >&2
    exit 1
fi
if ! grep -Eq 'Resource temporarily unavailable|os error 11|WouldBlock' "$runtime/duplicate.log"; then
    echo 'A second session exited for an unrelated reason rather than exclusive flock denial' >&2
    cat "$runtime/duplicate.log" >&2
    exit 1
fi
same="$("$ctl" snapshot)"
printf '%s' "$same" | python3 -c 'import json,sys;s=json.load(sys.stdin);assert s["session_instance"]==sys.argv[1]' "$instance"

launch="$("$ctl" launch research notes)"
read -r id pid <<<"$(printf '%s' "$launch" | python3 -c '
import json,sys
s=json.load(sys.stdin);t=s["task"]
assert s["type"]=="task" and t["state"]=="running" and t["pid"]
assert t["hos2_revision"] is None
assert t.get("wayland_socket_epoch_at_launch") is None
print(t["id"],t["pid"])
')"
[[ -n "$id" && -n "$pid" ]] || { echo 'Unobserved host launch' >&2; exit 1; }
if "$ctl" cancel "$id" 00000000000000000000000000000000 >"$runtime/stale.json" 2>&1; then
    echo 'Stale generation unexpectedly acknowledged' >&2; exit 1
fi
python3 - "$runtime/stale.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]));assert s['type']=='error' and 'NOT attempted' in s['message'],s
PY
state=""
for _ in {1..100}; do
    snapshot="$("$ctl" snapshot)"
    state="$(printf '%s' "$snapshot" | python3 -c '
import json,sys
s=json.load(sys.stdin)
t=next(t for t in s["tasks"] if t["id"]==int(sys.argv[1]))
assert t["hos2_revision"] is None
print(t["state"])
' "$id")"
    [[ "$state" == failed ]] && break
    sleep 0.05
done
[[ "$state" == failed ]] || { echo "Headless app was not observed FAILED: $state" >&2; exit 1; }
kill "$session_pid"
wait "$session_pid" 2>/dev/null || true
session_pid=""
"$service" >"$runtime/session-restart.log" 2>&1 &
session_pid=$!
restarted=0
for _ in {1..100}; do
    if new_snapshot="$("$ctl" snapshot 2>/dev/null)" &&
        printf '%s' "$new_snapshot" | python3 -c '
import json,sys
s=json.load(sys.stdin)
assert s["type"]=="snapshot" and s["session_instance"]!=sys.argv[1] and not s["tasks"]
' "$instance" 2>/dev/null; then
        restarted=1
        break
    fi
    kill -0 "$session_pid" 2>/dev/null || { echo 'Restarted Rust Session exited' >&2; exit 1; }
    sleep 0.05
done
[[ "$restarted" == 1 ]] || { echo 'Host Session restart did not fence old generation' >&2; exit 1; }
if "$ctl" cancel "$id" "$instance" >"$runtime/old-cancel.json" 2>&1; then
    echo 'Old-generation cancellation incorrectly acknowledged' >&2; exit 1
fi
printf 'A10 REAL Linux ELF replay PASSED: checksum/provenance, private Session IPC, flock, stale fence, failed GUI without display, fresh Session (NOT Weston/IME/kernel)\n'
