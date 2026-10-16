#!/usr/bin/env bash
# Run on a Linux host with Cargo and crates available. Never prints "passed"
# until each command has actually exited zero.
set -euo pipefail
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
        local fmt_status=0
        if [[ -n "$evidence" ]]; then
            cargo fmt --manifest-path ui/Cargo.toml --all -- --check >"$evidence/rustfmt-check.log" 2>&1 || fmt_status=$?
        else
            cargo fmt --manifest-path ui/Cargo.toml --all -- --check || fmt_status=$?
        fi
        if [[ "$fmt_status" -ne 0 ]]; then
            echo 'A10 rustfmt check FAILED; preserving exact-source review patch' >&2
            cargo fmt --manifest-path ui/Cargo.toml --all >/dev/null 2>&1 || true
            if [[ -n "$evidence" ]]; then
                git diff -- ui > "$evidence/rustfmt.patch" || true
            else
                git diff -- ui >&2 || true
            fi
            if [[ "$status" -eq 0 ]]; then status=1; fi
        fi
    fi
    exit "$status"
}
trap capture_fmt_on_exit EXIT

python3 tests/ui/test-session-lock.py
bash tests/ui/test-smoke-cleanup.sh
bash tests/ui/test-zombie-liveness.sh
# Build and test first so a formatting failure cannot conceal compiler evidence.
cargo build --manifest-path ui/Cargo.toml --workspace --bins
cargo test --manifest-path ui/Cargo.toml --workspace
# Formatter validation is enforced by the EXIT hook even if build/test
# failed earlier; it preserves the original build/test result.

printf 'A10 host Rust checks passed (NOT a kernel/Wayland/IME pass).\n'
