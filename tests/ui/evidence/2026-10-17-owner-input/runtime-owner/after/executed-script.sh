#!/usr/bin/env bash
# Real Linux-host Rust Session effective-UID ownership acceptance.
# Only temporary /tmp files, not A05 CapSpace, a trusted broker or OS kernel.
set -euo pipefail
source_dir="${1:?Usage: a10-test-runtime-owner.sh <absolute Rust executable directory>}"
[[ "$source_dir" = /* && -x "$source_dir/trill-session" ]] || {
    echo 'Missing absolute real Rust Session executable directory' >&2
    exit 2
}
for tool in sudo timeout stat; do command -v "$tool" >/dev/null; done
sudo -n true
root="$(mktemp -d "${TMPDIR:-/tmp}/a10-runtime-owner.XXXXXXXX")"
cleanup() {
    local status=$?
    trap - EXIT
    sudo -n rm -rf -- "$root"
    exit "$status"
}
trap cleanup EXIT

# Denial MUST be an immediate effective-UID mismatch with the correct
# diagnostic; an unrelated startup failure or timeout is not a pass.
require_owner_denial() {
    local scope="$1" diagnostic="$2" runtime="$root/$1" status=0
    sudo -n timeout --signal=TERM --kill-after=2s 1s env \
        XDG_RUNTIME_DIR="$runtime" "$source_dir/trill-session" \
        >"$root/$scope.log" 2>&1 || status=$?
    if [[ "$status" == 0 || "$status" == 124 || "$status" == 137 ]]; then
        echo "OWNER_BYPASS_$scope: foreign-owned resource accepted by real Rust Session" >&2
        cat "$root/$scope.log" >&2
        exit 1
    fi
    if ! grep -Fq "$diagnostic" "$root/$scope.log"; then
        echo "OWNER_WRONG_ERROR_$scope: failure was unrelated to effective UID" >&2
        cat "$root/$scope.log" >&2
        exit 1
    fi
    if sudo -n test -e "$runtime/trillionnium-ui/session.sock"; then
        echo "OWNER_SIDE_EFFECT_$scope: Session bound before rejecting UID mismatch" >&2
        exit 1
    fi
}

# Mode=0700 does not prevent root from entering somebody else's directory;
# the old real Rust ELF unexpectedly started inside this nobody-owned path.
mkdir -m 700 "$root/foreign_runtime"
sudo -n chown 65534:65534 "$root/foreign_runtime"
require_owner_denial foreign_runtime 'XDG_RUNTIME_DIR owner UID differs from Session effective UID'
if sudo -n test -e "$root/foreign_runtime/trillionnium-ui"; then
    echo 'Session created UI subdir in foreign runtime before denial' >&2
    exit 1
fi

# A caller may own XDG_RUNTIME_DIR while the existing UI subtree was
# replaced by another UID. Opening an old subtree must fail before binding.
mkdir -m 700 "$root/foreign_subdir"
mkdir -m 700 "$root/foreign_subdir/trillionnium-ui"
sudo -n chown 0:0 "$root/foreign_subdir"
sudo -n chown 65534:65534 "$root/foreign_subdir/trillionnium-ui"
require_owner_denial foreign_subdir 'UI socket directory owner UID differs from Session effective UID'

# The lock itself can be mode 0600 but belong to a different UID. Root can
# open and flock it unless the service checks the actual file owner.
mkdir -m 700 "$root/foreign_lock" "$root/foreign_lock/trillionnium-ui"
touch "$root/foreign_lock/trillionnium-ui/session.lock"
chmod 600 "$root/foreign_lock/trillionnium-ui/session.lock"
sudo -n chown 0:0 "$root/foreign_lock" "$root/foreign_lock/trillionnium-ui"
sudo -n chown 65534:65534 "$root/foreign_lock/trillionnium-ui/session.lock"
require_owner_denial foreign_lock 'session.lock owner UID differs from Session effective UID'

# Positive: exact same Rust Session under this effective UID's own 0700
# runtime must reach socket bind and stay alive until our bounded timeout.
mkdir -m 700 "$root/owned"
sudo -n chown 0:0 "$root/owned"
owned_code=0
sudo -n timeout --signal=TERM --kill-after=2s 1s env \
    XDG_RUNTIME_DIR="$root/owned" "$source_dir/trill-session" \
    >"$root/owned.log" 2>&1 || owned_code=$?
if [[ "$owned_code" != 124 ]] || ! sudo -n test -S "$root/owned/trillionnium-ui/session.sock"; then
    echo "Owned runtime did not serve private Unix socket (code $owned_code)" >&2
    cat "$root/owned.log" >&2
    exit 1
fi
[[ "$(sudo -n stat -c %a "$root/owned/trillionnium-ui/session.sock")" == 600 ]] || {
    echo 'Legitimate Session socket is not 0600' >&2
    exit 1
}
printf 'A10 REAL RUNTIME OWNERSHIP PASS: foreign 0700 runtime, child directory and 0600 lock refused; same-UID Session socket 0600 served (Linux host only)\n'
