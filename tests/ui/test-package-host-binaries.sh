#!/usr/bin/env bash
# Independent Linux-host packager regression. Fixture executables are C ELFs,
# NOT A10 Rust compiler, compositor, kernel, GPU or Chinese IME evidence.
set -euo pipefail
cd "$(dirname "$0")/../.."
for tool in cc git tar strip sha256sum; do
    command -v "$tool" >/dev/null || { echo "A10 package fixture missing $tool" >&2; exit 2; }
done

root="$(mktemp -d "${TMPDIR:-/tmp}/a10-package-check.XXXXXXXX")"
trap 'rm -rf -- "$root"' EXIT
mkdir -p "$root/support/ui" "$root/ui/target/debug" "$root/evidence" "$root/mock-bin"
cp -- support/ui/package-host-binaries.sh "$root/support/ui/package-host-binaries.sh"
cat > "$root/test-probe.c" <<'SOURCE'
int main(void) { return 0; }
SOURCE
for name in trill-shell trill-session trill-app-window trill-ctl; do
    cc "$root/test-probe.c" -o "$root/ui/target/debug/$name"
done
cat > "$root/mock-bin/rustc" <<'MOCK'
#!/usr/bin/env sh
printf 'rustc fixture-only, not a Rust build\n'
MOCK
cat > "$root/mock-bin/cargo" <<'MOCK'
#!/usr/bin/env sh
printf 'cargo fixture-only, not a Cargo test\n'
MOCK
chmod 755 "$root/mock-bin/rustc" "$root/mock-bin/cargo"
git -C "$root" init -q
git -C "$root" -c user.name=fixture -c user.email=fixture@example.invalid \
    commit -q --allow-empty -m 'packager fixture, never production source'
source_sha="$(git -C "$root" rev-parse HEAD)"

PATH="$root/mock-bin:$PATH" bash "$root/support/ui/package-host-binaries.sh" "$root/evidence"
(cd "$root/evidence" && sha256sum -c a10-linux-host-binaries.tar.gz.sha256)
tar -xzf "$root/evidence/a10-linux-host-binaries.tar.gz" -C "$root/evidence"
archive_dir="$root/evidence/a10-linux-host-binaries"
(cd "$archive_dir" && sha256sum -c SHA256SUMS)
[[ "$(grep -c '^Source commit: ' "$archive_dir/PROVENANCE.txt")" -eq 1 ]]
grep -Fxq "Source commit: $source_sha" "$archive_dir/PROVENANCE.txt"
for name in trill-shell trill-session trill-app-window trill-ctl; do
    [[ -x "$archive_dir/$name" ]]
    [[ "$(head -c 4 "$archive_dir/$name" | od -An -tx1 | tr -d ' \n')" == 7f454c46 ]]
done

# A missing native executable must fail before replacing a previously valid
# archive. This is a negative check; a mock program cannot count as A10 ELF.
archive_before="$(sha256sum "$root/evidence/a10-linux-host-binaries.tar.gz")"
rm -f "$root/ui/target/debug/trill-ctl"
if PATH="$root/mock-bin:$PATH" bash "$root/support/ui/package-host-binaries.sh" "$root/evidence" \
    >"$root/expected-rejection.log" 2>&1; then
    echo 'MISSING_BINARY_REJECTED check failed: packager returned success' >&2
    exit 1
fi
grep -Fq 'Missing built Rust program' "$root/expected-rejection.log"
[[ "$(sha256sum "$root/evidence/a10-linux-host-binaries.tar.gz")" == "$archive_before" ]]

# Do not allow a caller to turn a relative path into an uncontrolled artifact
# destination. A10 CI supplies an absolute per-runner temporary directory.
if PATH="$root/mock-bin:$PATH" bash "$root/support/ui/package-host-binaries.sh" 'relative/path' \
    >"$root/relative-rejection.log" 2>&1; then
    echo 'RELATIVE_PATH_REJECTED check failed' >&2
    exit 1
fi
grep -Fq 'A10 evidence path must be absolute' "$root/relative-rejection.log"
printf 'A10 packager fixture PASS: four fixture ELF hashes, provenance, missing binary and relative destination rejection (NO Rust/Weston claim)\n'
