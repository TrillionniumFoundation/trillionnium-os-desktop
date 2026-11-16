# Pocket4 source corrections and application candidate contracts

This capsule preserves two independently reproduced source defects and a corrected
42-package candidate catalog. It does not install a runtime, launch Android, or
grant production readiness.

## Source changes

- **Readiness snapshots.** Android property publication can change a shared area
  during a bounded read. A valid publication could therefore leave an old used-size
  beside a new trie offset and fail parsing before the serial checks. The corrected
  observer compares one bounded second snapshot after a parse rejection. Changed
  bytes request another poll; stable malformed bytes remain rejected. The second
  snapshot is never used to grant readiness directly.
- **Control request deadlines.** The request reader enforces one total deadline
  across descriptor arrival and all JSON fragments. A peer cannot extend the
  request indefinitely by sending each fragment before a fresh idle timeout.
  Existing peer identity, SCM descriptor rules, progress messages and exact message
  size limits remain covered by actual control-module tests.

`SOURCE-PINS.json` binds each original repository file, exact patch and delivered
postimage. The qualifier copies the original into a new private tree, runs
`git apply --check` and `git apply`, rejects additional files, and compares the
result byte for byte with the delivered source. Earlier source capsules remain
unchanged. The control change is based on the published Settings successor so its
new application functionality is preserved.

## Tests that CI actually executes

The readiness harness imports the delivered production module with `#[path]`;
its five tests run against that module. The control workspace retains the actual
supervisor and its internal source dependencies; all six new request-deadline
tests run against its delivered `control.rs`. These are not copies of the
algorithms or static searches for code patterns.

Both workspaces use Rust 1.93.0 and locked dependencies. CI checks every external
package name, version, source and checksum against the original retained
workspace lock. `EXPECTED-TESTS.json` fixes the exact test names. The qualifier
requires each name once and a successful, zero-failure, zero-ignored summary.

The top-level `FILES.json` covers the source, patches, dependency locks, harnesses,
qualifier and candidate records. A08 pins that manifest's SHA-256 and member count,
checks every file's size and digest, and rejects extra files, symlinks and hard
links. The qualifier checks the inventory again after executing the tests.

## Application candidate scope

The application checker reads `application-candidates/CANDIDATE42.json` and its
qualification record. It verifies exactly 42 distinct packages, all six common
acceptance gates, nonempty business-gate definitions, the six Firefox business
gates, and the matching bindings for 13 official candidate inputs. Artifact,
source-catalog, signer and retained-evidence references must agree across the two
records; conflicting references fail qualification.

Pocket4 APK paths are references to retained host observations. CI does not open
those remote APKs, execute their signature verifier, establish authenticated store
delivery, or convert host source evidence into application acceptance. The catalog
remains unadopted: canonical selection is unchanged, installations and Android
actions remain zero, and runtime acceptance remains 0/42.

## Reproduce

From this repository, use the commands in A08's **Replay and execute current
Pocket4 source corrections** step. They compile the qualifier, replay both
patches, validate the application contracts, execute the real Rust tests, check
their exact names and summaries, and confirm that retained inputs did not change.
Set `CARGO_TARGET_DIR` outside this capsule so build outputs never become source
inputs.
