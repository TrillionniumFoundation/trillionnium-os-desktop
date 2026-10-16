#!/usr/bin/env bash
set -euo pipefail
# The archived provenance/nonce checks use assertions; keep them active.
unset PYTHONOPTIMIZE
if [[ $# != 2 ]]; then
    echo "usage: bash reproduce.sh REPOSITORY NEW_SCRATCH_DIRECTORY" >&2
    exit 2
fi
evidence_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
probe_repository=$1
probe_work=$2
python3 "$evidence_dir/assemble_harnesses.py" --repository "$probe_repository" --output "$probe_work"
export CARGO_TARGET_DIR="$probe_work/target"
cargo +nightly-2026-07-21 build --locked --offline --manifest-path "$probe_work/harness/Cargo.toml"
python3 "$probe_work/run_probe.py"
set +e
python3 "$probe_work/check_measurements.py"
old_status=$?
set -e
if [[ $old_status != 1 ]]; then
    echo "old-code lifecycle failure was not reproduced as expected" >&2
    exit 1
fi
export CARGO_TARGET_DIR="$probe_work/patched-target"
cargo +nightly-2026-07-21 build --locked --offline --manifest-path "$probe_work/patched-harness/Cargo.toml"
python3 "$probe_work/run_patched_probe.py"
python3 "$probe_work/check_patched_measurements.py"
