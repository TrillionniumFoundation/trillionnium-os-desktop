# ktest private SDK handoff

The four source files were published as `ff0d09a2c2e0cba1d528d11a06083f588989a9f3`; their captured Git blobs match the tested snapshots. The ktest runner now installs its source-built SDK with `cargo +nightly-2026-07-21 install --locked cargo-osdk --path osdk --root <new-output>/osdk`, using a new mode0700 prefix. It calls that absolute `bin/cargo-osdk` with `osdk test` arguments and records the selected binary, source/install roots, SHA256 and command receipts. A missing, linked or nonexecutable private SDK and an installation failure stop the run. The deprecated `--skip-osdk-install` exits2 before opening the workspace lock or creating output. No global SDK is selected or installed by this path.

This phase validates source and **in-process host mocks only**: 11/11 tests pass under isolated ordinary Python and 11/11 under isolated optimized Python. The same final test source, applied to the frozen old runner, reports seven expected failures out of eleven. All command execution interfaces are mocked and subprocess entry points are refused inside those tests. These mock tests created or executed no SDK file or competing helper binary, and no real Cargo/SDK installation, kernel build, QEMU or native kernel-test success is claimed here.

The existing lifecycle fixture was statically adjusted to the private install location and parsed, but was **not executed** in this phase. `OwnedSession`, `run`, both signal-related classes/functions and the other protected helpers remain byte-for-byte and AST identical to the old runner. Existing environment/flock/output logic after the new early guard is also unchanged. Native OSTD/aster-core and subprocess lifecycle tests require their own actual execution records.

`source-before/` retains fixed09aea source snapshots and the unchanged upstream CLI, which explicitly parses `osdk` before `test`. `source-after/` retains the four tested files. `raw/` preserves commands, exact output, source hashes and the unchanged-function proof, including the initial mock-fixture digest error and its corrected control. `execution-stop/` preserves the earlier delegated turn failure, its empty tracked Git diff, and its Git status listing an untracked old `test_sdk_isolation.py`. An earlier parent message incorrectly called that status empty; the original raw status and receipts remain unchanged. The old fixture was subsequently captured through a stable FD, verified untracked and renamed unchanged into scratch quarantine without execution; its original bytes and provenance limits are retained under `execution-stop/quarantine/`.

Only a generic content-risk flag was exposed; **no specific rejected tool command or old-file author was established**, and this phase does not attribute rejection to any particular SDK command. The failed delegated task was not retried. This implementation followed the separately authorized static/source-and-mock alternative.

Offline integrity/count/source verification does not execute any captured source:

```bash
python3 -I /absolute/checkout/support/build/evidence/2026-10-17-ktest-private-sdk/verify.py
python3 -I -O /absolute/checkout/support/build/evidence/2026-10-17-ktest-private-sdk/verify.py
```
