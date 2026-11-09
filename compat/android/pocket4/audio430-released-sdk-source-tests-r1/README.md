# Complete Audio source-library CI inputs

This candidate runs the complete `droidloom-source` library test module against the
published 32-path SDK extension and the followup that repairs its historical-lock
tests. It preserves the production library bytes. No Rust command, new normal
tool build, AOSP synchronization, Soong build, or Android runtime has executed for
this candidate yet.

## Why the followup is required

The published SDK patch changes the Audio lock from `45496b24...` to `aab71dbc...`
but leaves the source library's current-lock assertion and prior-lock reconstruction
unchanged. The 7037-byte `patches/source-lib-history-followup.patch` changes only
`cfg(test)` code: it reconstructs the actual prior lock by removing exactly the
32 new paths, then preserves the preceding four-API-leaf and older source history.
It updates the current expected lock and adds one monotonic-extension regression.
The complete library therefore contains 26 tests, with no filter or ignored test.
`REVIEW.json` preserves the independent patch review with private session/location
identifiers removed; its original byte hash is disclosed.

## Complete inputs and exact dependencies

`harness/` is an isolated Cargo package with the entire library, the current
239256-byte Audio lock, and the exact 145316-byte historical 321-project fixture.
The fixture was recovered from the full original added-file hunk in the already
published Audio425 patch and matches the normal recipe's recorded SHA256.
`preimages/` and the two original patches support a real byte-for-byte replay.
No source function is extracted or replaced for CI.

The six direct dependencies are `hex=0.4.3`, `serde=1.0.229` with `derive`,
`serde_json=1.0.151`, `sha2=0.10.9`, `tempfile=3.27.0`, and `thiserror=2.0.19`.
All are exact version requirements. `tempfile` is a regular dependency because
the production library uses its builder. The original CLI's `clap` dependency
is unnecessary for a complete `--lib` run. The unchanged production crate's
Cargo manifest is retained as provenance.

The existing public broker harness has a real Cargo-resolved lock containing
`thiserror` and `thiserror-impl` 2.0.19. Its original bytes are preserved at
`provenance/broker-harness-Cargo.lock`. It is a seed, not a resolved lock for this
new package. The actual normal recipe's 51836-byte workspace lock was not present
as a raw file in the complete inspected public tree. Current upstream's different
53891-byte lock is not substituted for it. Registry checksums are never invented
or edited.

## First actual CI execution

`A08-FIRST-RUN.yml` is a proposed step for the existing A08 Linux job, after its
already configured Rust 1.93.0 installation. It does not modify that workflow or
the existing applications harness. Root must add the capsule to the existing
source-integrity registration before publishing the step.

The helper first validates every input SHA, replays both patches against complete
preimages, checks the unchanged production prefix and exact 26-test inventory,
and copies the complete package into a new runner temporary directory. Cargo then
performs a normal `generate-lockfile` using the real seed and registry. The generated
lock is copied to the evidence directory before a normal `cargo test --locked
--lib -j 1 -- --test-threads=1`. The result consumer requires all 26 named tests,
the exact all-pass summary, no ignored or filtered test, unchanged source bytes,
and unchanged resolved lock. It never runs Cargo itself or fabricates test output.

The existing A08 artifact step already preserves `$RUNNER_TEMP/a08/`, including
the generated `Cargo.lock`, preparation result, compiler versions, actual complete
logs, and result. CI must actually succeed before any source-test pass is recorded.
Three tests create and use temporary local Git repositories; they need normal Git,
a Unix filesystem with symlinks, and writable temporary storage. They do not need
AOSP network fetches, root, Android devices, or any production source tree.

## Freeze the first real lock

After a successful first run, root should retrieve the actual artifact lock,
verify its bytes/SHA against `result.json`, add those unchanged bytes as
`harness/Cargo.lock`, and refresh the capsule and source-integrity manifests.
The subsequent step must change preparation to `--mode locked --lock-file
"$capsule/harness/Cargo.lock"` and remove `cargo generate-lockfile`. It retains
the copy-before-test, `--locked`, complete-test, and post-test comparison steps.
The helper does not silently choose bootstrap when a frozen lock is missing.

This standalone run covers the actual lock-history regression and the complete
source library controls. It does not qualify the normal recipe executables,
the 55 physical original SDK Git blobs, 430-project materialization, strict
Soong graph, whole APEX, QPR1 ABI, or audio runtime. Those remain separate actual
continuation gates.
