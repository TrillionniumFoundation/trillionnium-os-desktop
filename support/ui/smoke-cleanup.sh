#!/usr/bin/env bash
# Sourced by A10 smoke scripts; Linux /proc host-only process provenance.
# Expects runtime to name the unique private test directory.
# Only terminate an app when /proc still identifies the process as our
# launched native binary AND it still belongs to this unique test runtime.
# Numeric PIDs may be reused; never kill an arbitrary later occupant.
kill_owned_app() {
    local pid="$1"
    [[ -n "$pid" && -r "/proc/$pid/environ" ]] || return 0
    local exe
    exe="$(readlink "/proc/$pid/exe" 2>/dev/null || true)"
    [[ "$exe" == */trill-app-window ]] || return 0
    if tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null |
        grep -Fx "XDG_RUNTIME_DIR=$runtime" >/dev/null; then
        kill "$pid" 2>/dev/null || true
    fi
}

# kill -0 succeeds for a zombie on Linux, which is NOT a live GUI client.
# This is an observational test guard, not a trusted process identity.
host_process_alive() {
    local pid="${1:-}" stat state
    [[ "$pid" =~ ^[1-9][0-9]*$ && -r "/proc/$pid/stat" ]] || return 1
    IFS= read -r stat < "/proc/$pid/stat" || return 1
    # /proc/<pid>/stat field 2 is a parenthesized command that may have
    # spaces; strip through its final ") " before taking state field 3.
    state="${stat##*) }"
    state="${state%% *}"
    [[ -n "$state" && "$state" != Z && "$state" != X && "$state" != x ]] || return 1
    kill -0 "$pid" 2>/dev/null
}
