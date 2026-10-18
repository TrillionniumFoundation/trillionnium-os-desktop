#!/usr/bin/env bash
# Linux /proc regression: a zombie PID still passes kill -0, but is NOT alive.
# Uses only child processes owned by this test, no Cargo/Wayland needed.
set -euo pipefail
cd "$(dirname "$0")/../.."
source support/ui/smoke-cleanup.sh

root="$(mktemp -d "${TMPDIR:-/tmp}/a10-zombie.XXXXXXXX")"
parent_pid=""
cleanup_fixture() {
    if [[ -n "$parent_pid" ]]; then
        touch "$root/release" 2>/dev/null || true
        wait "$parent_pid" 2>/dev/null || true
    fi
    rm -rf -- "$root"
}
trap cleanup_fixture EXIT

# The Python supervisor intentionally withholds waitpid until Bash checks the
# dead child. The child stays a real zombie in this private process family.
python3 -W ignore::DeprecationWarning - "$root/child.pid" "$root/release" <<'PY' &
import os, sys, time
child = os.fork()
if child == 0:
    os._exit(0)
with open(sys.argv[1], 'w', encoding='ascii') as out:
    out.write(str(child))
for _ in range(500):
    if os.path.exists(sys.argv[2]):
        break
    time.sleep(0.01)
os.waitpid(child, 0)
PY
parent_pid=$!

zombie=""
for _ in {1..200}; do
    if [[ -s "$root/child.pid" ]]; then
        zombie="$(cat "$root/child.pid")"
        stat="$(cat "/proc/$zombie/stat" 2>/dev/null || true)"
        stat="${stat##*) }"
        state="${stat%% *}"
        if [[ "$state" == Z ]]; then break; fi
    fi
    sleep 0.01
done
[[ -n "$zombie" && "$state" == Z ]] || { echo "Could not observe real zombie state" >&2; exit 1; }
# A kernel check of PID existence is insufficient for process health.
kill -0 "$zombie" || { echo "Expected zombie PID to exist" >&2; exit 1; }
if host_process_alive "$zombie"; then
    echo "ZOMBIE FALSE POSITIVE: host_process_alive accepted a dead client" >&2
    exit 1
fi
# Ensure the test's child is eventually reaped by its supervisor.
touch "$root/release"
wait "$parent_pid"
parent_pid=""
! host_process_alive "$zombie" || { echo "Reaped process still considered live" >&2; exit 1; }
printf 'A10 actual zombie process liveness guard: PASS\n'
