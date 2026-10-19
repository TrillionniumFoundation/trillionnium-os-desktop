#!/usr/bin/env bash
# Package the four actually built Rust Linux-host executables for CI evidence.
# This is NOT an Asterinas boot artifact or a verified GPU/IME implementation.
set -euo pipefail
cd "$(dirname "$0")/../.."
output="${1:?Usage: package-host-binaries.sh <absolute output directory>}"
[[ "$output" = /* ]] || { echo 'A10 evidence path must be absolute' >&2; exit 2; }
mkdir -p -- "$output"
command -v sha256sum >/dev/null
command -v tar >/dev/null
command -v strip >/dev/null || { echo 'GNU strip is required for bounded CI artifacts' >&2; exit 2; }

stage="$(mktemp -d "${output%/}/.a10-bin-stage.XXXXXXXX")"
cleanup() { [[ -z "${stage:-}" ]] || rm -rf -- "$stage"; }
trap cleanup EXIT
bundle="$stage/a10-linux-host-binaries"
mkdir -p -- "$bundle"
for name in trill-session trill-shell trill-app-window trill-ctl; do
    src="${CARGO_TARGET_DIR:-ui/target}/debug/$name"
    [[ -f "$src" && -x "$src" ]] || { echo "Missing built Rust program: $src" >&2; exit 1; }
    install -m 0755 -- "$src" "$bundle/$name"
    strip --strip-debug -- "$bundle/$name"
done
{
    printf 'A10 Rust Linux-host executable evidence (NOT target kernel)\n'
    printf 'Source repo: TrillionniumFoundation/trillionnium-os-desktop\n'
    printf 'Source commit: %s\n' "$(git rev-parse HEAD)"
    printf 'Host: %s\n' "$(uname -s -m)"
    printf 'Rust compiler: %s\n' "$(rustc --version)"
    printf 'Cargo: %s\n' "$(cargo --version)"
    printf 'These bytes were packaged after host Cargo tests and Rustfmt check.\n'
    printf 'The separate Weston/IME/GPU/kernel gates must be verified independently.\n'
} > "$bundle/PROVENANCE.txt"
(cd "$bundle" && sha256sum trill-session trill-shell trill-app-window trill-ctl > SHA256SUMS)
archive="$output/a10-linux-host-binaries.tar.gz"
tar -czf "$stage/a10-linux-host-binaries.tar.gz" -C "$stage" a10-linux-host-binaries
tar -tzf "$stage/a10-linux-host-binaries.tar.gz" >/dev/null
mv -- "$stage/a10-linux-host-binaries.tar.gz" "$archive"
(cd "$output" && sha256sum a10-linux-host-binaries.tar.gz > a10-linux-host-binaries.tar.gz.sha256)
printf 'A10 Linux-host native bundle staged: %s (NOT compositor/kernel acceptance)\n' "$archive"
