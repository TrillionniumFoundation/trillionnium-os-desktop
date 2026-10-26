#!/usr/bin/env bash
# Real Linux /proc-based test. Kills ONLY the processes it directly starts.
# No Cargo, GUI, Wayland compositor, privileged action or hardware required.
set -euo pipefail
cd "$(dirname "$0")/../.."
source support/ui/smoke-cleanup.sh

root="$(mktemp -d "${TMPDIR:-/tmp}/a10-cleanup.XXXXXXXX")"
runtime="$root/ours"
other_runtime="$root/other"
mkdir -m 700 "$runtime" "$other_runtime"
# Build a real, directly owned ELF instead of renaming a host multicall applet.
# GNU and uutils can dispatch a copied sleep differently, even with exec -a.
# The original cleanup checks still require this exact /proc/<pid>/exe path.
cat > "$root/fixture.c" <<'C'
#include <unistd.h>

int main(void) {
    sleep(30);
    return 0;
}
C
cc -std=c11 -O2 -Wall -Wextra -Werror "$root/fixture.c" -o "$root/trill-app-window"
sleep_exe="$(readlink -f /bin/sleep)"
ours=""
other=""
different=""
cleanup_fixture() {
    if [[ -n "$ours" ]]; then kill "$ours" 2>/dev/null || true; wait "$ours" 2>/dev/null || true; fi
    if [[ -n "$other" ]]; then kill "$other" 2>/dev/null || true; wait "$other" 2>/dev/null || true; fi
    if [[ -n "$different" ]]; then kill "$different" 2>/dev/null || true; wait "$different" 2>/dev/null || true; fi
    rm -rf -- "$root"
}
trap cleanup_fixture EXIT

XDG_RUNTIME_DIR="$runtime" "$root/trill-app-window" &
ours=$!
XDG_RUNTIME_DIR="$other_runtime" "$root/trill-app-window" &
other=$!
# Matching runtime is insufficient when the executable is not the app.
env XDG_RUNTIME_DIR="$runtime" /bin/sleep 30 &
different=$!

# Ensure the /proc entry represents the exec'd app, not an intermediate env.
ready=0
for _ in {1..100}; do
    a="$(readlink "/proc/$ours/exe" 2>/dev/null || true)"
    b="$(readlink "/proc/$other/exe" 2>/dev/null || true)"
    c="$(readlink "/proc/$different/exe" 2>/dev/null || true)"
    if [[ "$a" == "$root/trill-app-window" && "$b" == "$root/trill-app-window" && "$c" == "$sleep_exe" ]]; then
        ready=1
        break
    fi
    sleep 0.01
done
[[ "$ready" == 1 ]] || { echo "Test clients never exec'd" >&2; exit 1; }
host_process_alive "$ours" || { echo "Own process not active" >&2; exit 1; }
host_process_alive "$other" || { echo "Other process not active" >&2; exit 1; }
host_process_alive "$different" || { echo "Different binary not active" >&2; exit 1; }
# An invalid PID, zero, or a process we deliberately reaped cannot pass.
! host_process_alive 0 || { echo "PID zero incorrectly active" >&2; exit 1; }
! host_process_alive not-a-pid || { echo "Malformed PID incorrectly active" >&2; exit 1; }


# The same executable in another runtime must not be killed.
kill_owned_app "$other"
kill -0 "$other" || { echo "Cross-runtime process was killed" >&2; exit 1; }

# A real app in our runtime is also not owned if its executable differs.
kill_owned_app "$different"
kill -0 "$different" || { echo "Different executable was killed" >&2; exit 1; }

# Require prompt SIGTERM, NOT natural completion after 30 seconds.
kill_owned_app "$ours"
terminated=0
for _ in {1..200}; do
    if [[ ! -r "/proc/$ours/stat" ]]; then
        terminated=1
        break
    fi
    state="$(awk '{print $3}' "/proc/$ours/stat" 2>/dev/null || true)"
    if [[ "$state" == Z || "$state" == X ]]; then
        terminated=1
        break
    fi
    sleep 0.01
done
[[ "$terminated" == 1 ]] || { echo "Owned app did not terminate promptly" >&2; exit 1; }
dead_ours="$ours"
rc=0
wait "$ours" 2>/dev/null || rc=$?
ours=""
[[ "$rc" == 143 ]] || { echo "Expected SIGTERM (143), observed $rc" >&2; exit 1; }
! host_process_alive "$dead_ours" || { echo "Reaped process reported alive" >&2; exit 1; }
kill -0 "$other" || { echo "Cross-runtime process was killed" >&2; exit 1; }
kill -0 "$different" || { echo "Different executable was killed" >&2; exit 1; }
printf 'A10 scoped smoke cleanup: PASS (SIGTERM; other runtime + other executable intact)\n'
