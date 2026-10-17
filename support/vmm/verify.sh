#!/usr/bin/env bash
# A09-owned test entrypoint for future A00-scoped GitHub Actions.
# Never performs GPU reset, driver rebind, VFIO assignment or hardware compute.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/../.." && pwd -P)"
manifest="${script_dir}/device_lifecycle/Cargo.toml"

if [[ ! -f "${repo_root}/README.md" ]] || [[ -s "${repo_root}/README.md" ]]; then
  echo "A09 FAIL: root README.md absent or not 0 bytes" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "A09 BLOCKED: Python 3 unavailable" >&2
  exit 2
fi
echo "A09: CPU-only Python hardware contract suite (NOT actual GPU verification)"
python3 -m unittest discover -s "${repo_root}/tests/hardware" -p 'test_*.py' -v

if ! command -v rustc >/dev/null 2>&1 || ! command -v cargo >/dev/null 2>&1; then
  echo "A09 BLOCKED: rustc/cargo unavailable; Rust state contract NOT validated" >&2
  exit 2
fi
echo "A09: Rust toolchain: $(rustc --version), Cargo: $(cargo --version)"
if [[ ! -f "${script_dir}/device_lifecycle/Cargo.lock" ]]; then
  echo "A09 FAIL: lockfile absent, cannot claim locked Rust test" >&2
  exit 1
fi

# Target directory is scoped to the execution environment; no root/system writes.
# The crate has NO third-party Rust dependencies and must work fully offline.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-${TMPDIR:-/tmp}/a09-device-lifecycle-target}"
cargo test --manifest-path "${manifest}" --locked --offline --all-targets --verbose
cargo test --manifest-path "${manifest}" --locked --offline --doc --verbose
echo "A09 PASS: Python fixtures + Rust unit/doctests; physical GPU remains UNTESTED"
