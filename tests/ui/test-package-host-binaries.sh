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
# A selected target directory must be used consistently by Cargo consumers.
# Keep spaces in this private path to catch accidentally unquoted paths.
scratch="$root/fixture-scratch"
export CARGO_TARGET_DIR="$scratch/selected target"
mkdir -p "$root/support/ui" "$CARGO_TARGET_DIR/debug" "$scratch/evidence" "$scratch/mock-bin"
cp -- support/ui/package-host-binaries.sh "$root/support/ui/package-host-binaries.sh"
cat > "$scratch/test-probe.c" <<'SOURCE'
int main(void) { return 0; }
SOURCE
for name in trill-shell trill-session trill-app-window trill-ctl trill-notes-recovery; do
    cc "$scratch/test-probe.c" -o "$CARGO_TARGET_DIR/debug/$name"
done
cat > "$scratch/mock-bin/rustc" <<'MOCK'
#!/usr/bin/env sh
printf 'rustc fixture-only, not a Rust build\n'
MOCK
cat > "$scratch/mock-bin/cargo" <<'MOCK'
#!/usr/bin/env sh
printf 'cargo fixture-only, not a Cargo test\n'
MOCK
chmod 755 "$scratch/mock-bin/rustc" "$scratch/mock-bin/cargo"
git -C "$root" init -q
# Track the actual source under test; only disposable compiler/artifact inputs
# live in the single ignored scratch directory. Production clean-source checks
# continue to reject every tracked edit and any other new source file.
printf '/fixture-scratch/\n' > "$root/.gitignore"
git -C "$root" add -- .gitignore support/ui/package-host-binaries.sh
git -C "$root" -c user.name=fixture -c user.email=fixture@example.invalid \
    commit -q -m 'packager fixture, never production source'
[[ -z "$(git -C "$root" status --porcelain=v1 --untracked-files=all)" ]]
source_sha="$(git -C "$root" rev-parse HEAD)"

PATH="$scratch/mock-bin:$PATH" bash "$root/support/ui/package-host-binaries.sh" "$scratch/evidence"
(cd "$scratch/evidence" && sha256sum -c a10-linux-host-binaries.tar.gz.sha256)
tar -xzf "$scratch/evidence/a10-linux-host-binaries.tar.gz" -C "$scratch/evidence"
archive_dir="$scratch/evidence/a10-linux-host-binaries"
(cd "$archive_dir" && sha256sum -c SHA256SUMS)
[[ "$(grep -c '^Source commit: ' "$archive_dir/PROVENANCE.txt")" -eq 1 ]]
grep -Fxq "Source commit: $source_sha" "$archive_dir/PROVENANCE.txt"
for name in trill-shell trill-session trill-app-window trill-ctl trill-notes-recovery; do
    [[ -x "$archive_dir/$name" ]]
    [[ "$(head -c 4 "$archive_dir/$name" | od -An -tx1 | tr -d ' \n')" == 7f454c46 ]]
done

# Both kinds of real dirty source must be refused before touching the archive.
archive_before="$(sha256sum "$scratch/evidence/a10-linux-host-binaries.tar.gz")"
for dirty_kind in tracked untracked; do
    if [[ "$dirty_kind" == tracked ]]; then
        printf '\n# unexpected tracked edit\n' >> "$root/support/ui/package-host-binaries.sh"
    else
        printf 'unreviewed source\n' > "$root/untracked-source.rs"
    fi
    if PATH="$scratch/mock-bin:$PATH" bash "$root/support/ui/package-host-binaries.sh" "$scratch/evidence" \
        >"$scratch/dirty-rejection.log" 2>&1; then
        echo "DIRTY_SOURCE_REJECTED check failed: $dirty_kind source accepted" >&2
        exit 1
    fi
    grep -Fq 'Refusing to label binaries with HEAD from a modified source checkout' "$scratch/dirty-rejection.log"
    [[ "$(sha256sum "$scratch/evidence/a10-linux-host-binaries.tar.gz")" == "$archive_before" ]]
    if [[ "$dirty_kind" == tracked ]]; then
        cp -- support/ui/package-host-binaries.sh "$root/support/ui/package-host-binaries.sh"
    else
        rm -- "$root/untracked-source.rs"
    fi
done
[[ -z "$(git -C "$root" status --porcelain=v1 --untracked-files=all)" ]]

# A missing native executable must fail before replacing a previously valid
# archive. This is a negative check; a mock program cannot count as A10 ELF.
archive_before="$(sha256sum "$scratch/evidence/a10-linux-host-binaries.tar.gz")"
rm -f "$CARGO_TARGET_DIR/debug/trill-ctl"
if PATH="$scratch/mock-bin:$PATH" bash "$root/support/ui/package-host-binaries.sh" "$scratch/evidence" \
    >"$scratch/expected-rejection.log" 2>&1; then
    echo 'MISSING_BINARY_REJECTED check failed: packager returned success' >&2
    exit 1
fi
grep -Fq 'Missing built Rust program' "$scratch/expected-rejection.log"
[[ "$(sha256sum "$scratch/evidence/a10-linux-host-binaries.tar.gz")" == "$archive_before" ]]

# Do not allow a caller to turn a relative path into an uncontrolled artifact
# destination. A10 CI supplies an absolute per-runner temporary directory.
if PATH="$scratch/mock-bin:$PATH" bash "$root/support/ui/package-host-binaries.sh" 'relative/path' \
    >"$scratch/relative-rejection.log" 2>&1; then
    echo 'RELATIVE_PATH_REJECTED check failed' >&2
    exit 1
fi
grep -Fq 'A10 evidence path must be absolute' "$scratch/relative-rejection.log"
printf 'A10 packager fixture PASS: five fixture ELF hashes, provenance, tracked/untracked dirty source, missing binary and relative destination rejection (NO Rust/Weston claim)\n'
