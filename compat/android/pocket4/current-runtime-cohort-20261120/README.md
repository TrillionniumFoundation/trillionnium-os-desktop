# Complete current runtime cohort

This packet binds the existing full ordinary-test runner to the complete current
source tree `7bfb70d7107cb5c95e9aec307124e1369aa735d1`: 2,352 files and 44,260,146
source bytes. The original 14-file `runtime-current-source-r1` capsule remains
unchanged. Its full archive and overlay are authenticated, followed by the exact
required-materialization successor and current leaf-selection successor.

The historical full job ran 1,523 ordinary cases on tree `64f57a4d…`. The current
source adds six actual source-library cases and five actual application-library
cases. The current complete catalog therefore contains **1,534 ordinary cases
and the same 30 ignored cases**, spread across the same 49 harness targets and
28 packages. Every historical test name remains present. Ignored cases remain
ignored; VM, device, optional-feature and production qualification is not added.

## Preserved gates

`RUNNER.patch` is replayed strictly against the externally pinned complete
original `run_ci.py`. The candidate runner differs only in `configuration` and
`main`: the exact current counts, source-chain provenance, current report/state
names and a final full input-packet verification. Every other function, import,
constant and module entry has the same Python AST as the original runner. The
original catalog, terminal, Cargo artifact, ownership, child retirement, alias,
deadline, actual executable and metadata gates are reused without replacement.

The complete original `EXPECTED-TARGETS.json`, `EXPECTED-BINS.json`,
`EXTRA-TARGETS.json`, `UPDATER-EXACT64.json` and `test_runner.py` are byte identical.
The exact 64 updater cases and disjoint remaining updater group retain their
original selection and actual-output checks. All 19 normal release binaries,
three example binaries, nine separate recipe tests and 20 actual rustdoc targets
remain required. The nine recipe tests are additional to the ordinary count.

The original 5,400-second complete-run budget, one Cargo job, one test thread,
two reserved logical CPUs, original command timeouts and process retirement
checks remain unchanged. The existing CI job retains 140 minutes, including its
original native preparation with a 1,800-second limit. No original feature,
target, lockfile or dependency requirement is removed or stubbed.

## Execution in the complete repository

First authenticate and reconstruct the original capsule using its original
`verify.py`. Replay `vendor-source-materialization-20261120/rust/verify.py`, then
`current-leaf-selection-20261120/rust/verify.py`, with their fixed inventories.
Both replay outputs must be fresh, separate directories. The new full runner
accepts the final complete leaf source directory as `--producer`.

Run `python3 -I -B test_adapter.py` and the unchanged `test_runner.py` in this
packet. The source controls authenticate the complete original archive and both
successors and reject stale catalogs, omitted historical names, changed ignored
status, changed original gates and reduced scope. These Python controls do not
compile or execute Rust and do not stand in for the actual cohort.

Prepare native dependencies with the unchanged original `prepare_ci.sh`. Invoke
this packet's `run_ci.py` with its externally bound `FILES.sha256` SHA256 and the
same original `--producer`, `--work`, `--report` and `--erofs-prefix` arguments.
The report must say `ALL1534_ORDINARY_AND19_NORMAL_RELEASE_BUILDS_PASSED` and retain
the actual named Rust case results, Cargo streams, fresh ELF identities, example
and rustdoc results, unchanged complete source and packet bookends, and actual
process-retirement evidence. Preserve all stdout and stderr, even on failure.

No historical successful test or ELF is counted as fresh. This source packet
does not claim a fresh full-cohort result, Pocket4 ABI compatibility, Android
build or boot, app installation, business-flow acceptance, activation or
production readiness. Those require their own actual current evidence.
