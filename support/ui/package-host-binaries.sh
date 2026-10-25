#!/usr/bin/env bash
# Package the five actually built Rust Linux-host executables for CI evidence.
# This is NOT an Asterinas boot artifact or a verified GPU/IME implementation.
set -euo pipefail
cd "$(dirname "$0")/../.."
output="${1:?Usage: package-host-binaries.sh <absolute output directory> [absolute verified SDK receipt]}"
[[ $# -le 2 ]] || { echo 'Expected an output directory and optional verified SDK receipt' >&2; exit 2; }
[[ "$output" = /* ]] || { echo 'A10 evidence path must be absolute' >&2; exit 2; }
profile="${TRILL_UI_BUILD_PROFILE:-debug}"
[[ "$profile" = debug || "$profile" = release ]] || {
    echo 'TRILL_UI_BUILD_PROFILE must be debug or release' >&2
    exit 2
}
sdk_receipt="${2:-}"
sdk_receipt_sha=""
if [[ -n "$sdk_receipt" ]]; then
    [[ "$sdk_receipt" = /* ]] || { echo 'SDK receipt path must be absolute' >&2; exit 2; }
    sdk_receipt_sha="$(python3 -B - "$sdk_receipt" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, "support/ui/product")
from desktop import regular_bytes
from native_sdk import validate_profile

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate SDK receipt key: " + key)
        result[key] = value
    return result

data = regular_bytes(Path(sys.argv[1]), 1024 * 1024)
validate_profile(json.loads(data, object_pairs_hook=unique))
print(hashlib.sha256(data).hexdigest())
PY
)"
fi
mkdir -p -- "$output"
command -v sha256sum >/dev/null
command -v tar >/dev/null
command -v strip >/dev/null || { echo 'GNU strip is required for bounded CI artifacts' >&2; exit 2; }
[[ -z "$(git status --porcelain=v1 --untracked-files=all)" ]] || {
    echo 'Refusing to label binaries with HEAD from a modified source checkout; commit the exact tested source first.' >&2
    exit 2
}
source_commit="$(git rev-parse HEAD)"
source_tree="$(git rev-parse 'HEAD^{tree}')"

stage="$(mktemp -d "${output%/}/.a10-bin-stage.XXXXXXXX")"
cleanup() { [[ -z "${stage:-}" ]] || rm -rf -- "$stage"; }
trap cleanup EXIT
bundle="$stage/a10-linux-host-binaries"
mkdir -p -- "$bundle"
for name in trill-session trill-shell trill-app-window trill-ctl trill-notes-recovery; do
    src="${CARGO_TARGET_DIR:-ui/target}/$profile/$name"
    [[ -f "$src" && -x "$src" ]] || { echo "Missing built Rust program: $src" >&2; exit 1; }
    install -m 0755 -- "$src" "$bundle/$name"
    # The native text graph includes the original Agentd/App Server crates.
    # Retaining every static symbol makes even debug=0 exceed the installer's
    # existing 128 MiB single-file bound. Keep runtime-required symbols while
    # removing debug/static symbol tables from the distribution copy only.
    strip --strip-unneeded -- "$bundle/$name"
done
{
    printf 'A10 Rust Linux-host executable evidence (NOT target kernel)\n'
    printf 'Source repo: TrillionniumFoundation/trillionnium-os-desktop\n'
    printf 'Source commit: %s\n' "$source_commit"
    printf 'Source tree: %s\n' "$source_tree"
    printf 'Cargo build profile: %s\n' "$profile"
    printf 'Distribution transform: GNU strip --strip-unneeded (build inputs retained)\n'
    if [[ -n "$sdk_receipt_sha" ]]; then
        printf 'Makepad source profile SHA256: %s\n' "$sdk_receipt_sha"
    fi
    printf 'Host: %s\n' "$(uname -s -m)"
    printf 'Rust compiler: %s\n' "$(rustc --version)"
    printf 'Cargo: %s\n' "$(cargo --version)"
    printf 'These bytes were packaged after host Cargo tests and Rustfmt check.\n'
    printf 'The separate Weston/IME/GPU/kernel gates must be verified independently.\n'
} > "$bundle/PROVENANCE.txt"
(cd "$bundle" && sha256sum trill-session trill-shell trill-app-window trill-ctl trill-notes-recovery > SHA256SUMS)
archive="$output/a10-linux-host-binaries.tar.gz"
tar -czf "$stage/a10-linux-host-binaries.tar.gz" -C "$stage" a10-linux-host-binaries
tar -tzf "$stage/a10-linux-host-binaries.tar.gz" >/dev/null
mv -- "$stage/a10-linux-host-binaries.tar.gz" "$archive"
(cd "$output" && sha256sum a10-linux-host-binaries.tar.gz > a10-linux-host-binaries.tar.gz.sha256)
printf 'A10 Linux-host native bundle staged: %s (NOT compositor/kernel acceptance)\n' "$archive"
