#!/usr/bin/env bash
# Run on a Linux host with Cargo and crates available. Never prints "passed"
# until each command has actually exited zero.
set -euo pipefail
# Many validation probes use Python assert: -O must never disable blockers.
export PYTHONOPTIMIZE=0
cd "$(dirname "$0")/../.."
test "$(wc -c < README.md)" -eq 0

# Even when compilation fails before fmt, preserve the exact-source
# formatter diagnosis and review patch on a GitHub-hosted runner.
# This EXIT hook never changes the result of the primary build/test failure.
capture_fmt_on_exit() {
    local status=$?
    trap - EXIT
    if command -v cargo >/dev/null 2>&1; then
        local evidence=""
        if [[ -n "${RUNNER_TEMP:-}" ]]; then
            evidence="$RUNNER_TEMP/a10"
            mkdir -p "$evidence"
        fi
        local fmt_status=0 manifest
        local manifests=(ui/Cargo.toml support/ui/Cargo.toml tests/ui/Cargo.toml)
        if [[ -n "$evidence" ]]; then
            : > "$evidence/rustfmt-check.log"
        fi
        for manifest in "${manifests[@]}"; do
            if [[ -n "$evidence" ]]; then
                cargo fmt --manifest-path "$manifest" --all -- --check >>"$evidence/rustfmt-check.log" 2>&1 || fmt_status=1
            else
                cargo fmt --manifest-path "$manifest" --all -- --check || fmt_status=1
            fi
        done
        if [[ "$fmt_status" -ne 0 ]]; then
            echo 'A10 Rustfmt check FAILED in one or more owned crates; preserving exact-source patch' >&2
            for manifest in "${manifests[@]}"; do
                cargo fmt --manifest-path "$manifest" --all >/dev/null 2>&1 || true
            done
            if [[ -n "$evidence" ]]; then
                git diff -- ui support/ui tests/ui > "$evidence/rustfmt.patch" || true
            else
                git diff -- ui support/ui tests/ui >&2 || true
            fi
            if [[ "$status" -eq 0 ]]; then status=1; fi
        fi
    fi
    exit "$status"
}
trap capture_fmt_on_exit EXIT

bash -n tests/ui/smoke-wayland.sh tests/ui/headless-weston.sh tests/ui/compositor-restart.sh support/ui/package-host-binaries.sh tests/ui/test-package-host-binaries.sh tests/ui/replay-packaged-host.sh tests/ui/test-cross-uid-peer.sh
python3 tests/ui/test-session-lock.py
bash tests/ui/test-smoke-cleanup.sh
bash tests/ui/test-zombie-liveness.sh
# This real Linux ELF fixture verifies the artifact packager's fail-closed
# behavior independently of Rust compilation. It does not count as GUI smoke.
bash tests/ui/test-package-host-binaries.sh
# Fetch every package recorded in the lockfile, including target-specific
# entries that are not compiled by the Linux host build. The CI lock gate
# intentionally runs `cargo metadata --offline` after the real tests; without
# this prefetch, an uncached Android-only package can make that final
# reproducibility check fail even though the host build is complete.
cargo fetch --manifest-path ui/Cargo.toml --locked
# Build and test first so a formatting failure cannot conceal compiler evidence.
cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked
cargo test --manifest-path ui/Cargo.toml --workspace --locked
# A10's read-only HOS2 adapter consumes the real shared A02 crate. Changes
# to main ABI must break this same blocking host gate if the consumer regresses.
# The tests/ui model is a separate host contract, NOT a synthetic UI success.
cargo test --manifest-path support/ui/Cargo.toml --locked
cargo test --manifest-path tests/ui/Cargo.toml --locked
# Real Linux SO_PEERCRED negative. The CI runner already provisions
# passwordless sudo for host dependencies; use it only to start a disposable
# nobody-owned Session under a separate private /tmp runtime. A root caller
# must be refused with an actual peer-UID diagnostic. The same-UID client
# must continue to work; old unguarded Rust binaries fail this check.
bash tests/ui/test-cross-uid-peer.sh "$PWD/ui/target/debug"
# Probe the ACTUAL native Session through raw Unix-socket JSON, not serde
# unit models. Exact Snapshot/Launch/Cancel schemas must reject duplicate
# keys or unknown metadata before any task effect can occur.
python3 tests/ui/test-strict-request-ipc.py "$PWD/ui/target/debug"
# The binaries are packaged only when all three suites and strict Rustfmt
# have passed; the separate Weston smoke still owns its independent gate.
for manifest in ui/Cargo.toml support/ui/Cargo.toml tests/ui/Cargo.toml; do
    cargo fmt --manifest-path "$manifest" --all -- --check
done
if [[ -n "${RUNNER_TEMP:-}" ]]; then
    bash support/ui/package-host-binaries.sh "$RUNNER_TEMP/a10"
    # Run the exact built ELF files from the new CI archive independently
    # of Cargo, with no display. Assert real IPC ownership, stale-generation
    # rejection, FAILED headless client, and fresh Session identity.
    # This is deliberately separate from the later Weston graphics smoke.
    bash tests/ui/replay-packaged-host.sh         "$RUNNER_TEMP/a10/a10-linux-host-binaries.tar.gz" "$(git rev-parse HEAD)"
fi
# The EXIT hook still preserves a formatter patch on any earlier failure.

printf 'A10 host Rust checks passed (NOT a kernel/Wayland/IME pass).\n'
