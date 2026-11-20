# Additional CI job

Keep the existing `runtime-current-complete-producer` job and its inventory pin
unchanged. Add a separate Ubuntu 24.04 job with Rust 1.93.0 and a 30-minute limit.
The containing workflow and source guard must pin this packet's `FILES.sha256`.
Use the current commit's complete checkout, and substitute that reviewed pin for
`$MATERIALIZATION_INVENTORY_SHA256` below. All output paths must be fresh.

```bash
set -euo pipefail
parent="$GITHUB_WORKSPACE/compat/android/pocket4/runtime-current-source-r1"
packet="$GITHUB_WORKSPACE/compat/android/pocket4/vendor-source-materialization-20261120/rust"
parent_pin=075affecd123cc60e30eadf70ae95cc9ec34d5686694bedf0914014c36d04c0b
printf '%s  %s\n' "$MATERIALIZATION_INVENTORY_SHA256" "$packet/FILES.sha256" | sha256sum --check --status
(cd "$packet" && sha256sum --quiet -c FILES.sha256)
printf '%s  %s\n' "$parent_pin" "$parent/FILES.sha256" | sha256sum --check --status
(cd "$parent" && sha256sum --quiet -c FILES.sha256)
python3 -I -B "$packet/test_replay.py"
python3 -I -B "$parent/verify.py" --inventory-sha256 "$parent_pin" \
  --output "$RUNNER_TEMP/materialization-parent" \
  --report "$RUNNER_TEMP/materialization-parent.json"
python3 -I -B "$packet/verify.py" --inventory-sha256 "$MATERIALIZATION_INVENTORY_SHA256" \
  --parent-packet "$parent" --parent-source "$RUNNER_TEMP/materialization-parent" \
  --output "$RUNNER_TEMP/materialization-successor" \
  --report "$RUNNER_TEMP/materialization-replay.json"
python3 -I -B "$packet/run_ci.py" --inventory-sha256 "$MATERIALIZATION_INVENTORY_SHA256" \
  --producer "$RUNNER_TEMP/materialization-successor" \
  --work "$RUNNER_TEMP/materialization-build" \
  --report "$RUNNER_TEMP/materialization-ci.json" --jobs 2 --fetch
```

The only network-capable Cargo operation is the explicitly requested
`cargo +1.93.0 fetch --locked`. Compilation uses `--offline --locked`, an
independent target directory and two jobs. `Cargo.toml` and `Cargo.lock` are
unchanged and covered by source bookends. The runner records toolchain, command
exit codes, full stdout/stderr hashes, reaping and process-group status, exact
compiled harness identities, complete catalogs, actual terminals and the final
source bookend. It fails if any catalog member disappears or an additional
member appears.

Always upload `materialization-parent.json`, `materialization-replay.json`,
`materialization-ci.json` and `materialization-build/logs/*.stdout` and `*.stderr`.
These are fresh execution artifacts, kept outside the source packet to avoid a
self-referential evidence/inventory hash. Do not add new binaries to the old
19-release artifact or transfer the original release qualification to this tree.

The four Python controls validate replay admission only. They are separate from
the 100 real Rust cases and must not be added to that Rust count. An existing
formatting failure is not a pass and is not suppressed by this additional job.
