# Original Hepta owner → Desktop Session: executed host evidence

The final host source passed all **14 real original-owner and Unix-domain-socket
integration tests**, with no failures, ignored tests or filters. Replacing only
the active host's acknowledged recovery snapshot with the previous generic
snapshot produced **three expected ACK assertion failures**. Restoring the exact
original source then passed all 14 tests again. The final source also passed
format checking and Clippy with warnings denied.

## Fixed source

| Input | Exact identity |
| --- | --- |
| Desktop source commit | `bf0a0a0a582d7c93c191488e762c12bd6d75561a` |
| Desktop source tree | `ad26a0b6396a02ad5b5ff47e3f9fa7ed47da1c61` |
| Desktop stack base, PR #255 | `2c88b9d3929ec64e7a2bb20ee2f869d87bea7792` |
| Original Hepta Git dependency | `db91f9ec316ba1472e7adf97f8415949de012469` |
| Original Hepta tree | `81c03af04be56659d3eb4da71bf61aeac34c949f` |
| Host Cargo.lock SHA-256 | `4526bdd7356d4682ee0320372ade378d243ea1aa0d8b5155f174d1e22daa2d19` |
| Original fourteen-file publication manifest SHA-256 | `ae26826a3f3cfa84c2a092dbb1ccebf98b11e4737c722285e25fb1d15a549c67` |

[SOURCE_INDEX.json](SOURCE_INDEX.json) binds every candidate file to its exact
fixed-commit source link, byte count, mode, Git blob and SHA-256. The unchanged
original publisher manifest is [source-manifest.json](source-manifest.json).
The evidence-only commit that contains this directory is separate from the
source commit above.
The coordinating publisher also read back the complete remote tree: all 7,846
leaf paths, blobs, modes and types matched the expected base plus this candidate,
with no additional change. That separate unmodified receipt is
[receipts/source-readback.json](receipts/source-readback.json).

## Actual gates and historical failures

| Gate | Actual outcome | Original receipt inside the archive |
| --- | --- | --- |
| Final real Git graph resolution | Cargo exit 0; 628 packages, 30 original Hepta Git packages at one exact revision | `validation/git-host-resolution.json` |
| Initial full host test run | 14 passed | `validation/git-host-original-owner-01.json` |
| Initial Clippy | Exit 101: four collapsible `if` statements | `validation/git-host-clippy-01.json` |
| Source-matched final baseline after equivalent `let`-chain cleanup | 14 passed, 0 failed/ignored/filtered | `validation/git-host-original-owner-02.json` |
| Final format | Exit 0, source unchanged | `validation/git-host-format-02.json` |
| Final Clippy, `-D warnings` | Exit 0, source unchanged | `validation/git-host-clippy-02.json` |
| Temporary old recovery call | Cargo exit 101; 3 expected assertion failures, 11 filtered; no compilation failure | `validation/git-host-ack-red-green-01-red-recovery.json` |
| Exact restored final source | 14 passed, 0 failed/ignored/filtered | `validation/git-host-ack-red-green-01-green.json` |
| Original Git checkout before and after the sequence | All 9,145 files, 1,239 tree objects, HEAD/index, modes and symlink bytes matched | `validation/host-git-review/git-host-ack-red-green-01-git-{before,after}.json` |

The old call caused each recovery test to fail at
`tests/original_owner.rs:208`, where the test requires `PersistenceUnknown` while
the independent current-cut ACK is unavailable. These are real test assertion
failures after compilation. The controller then restored the original bytes
before the full green command. Its event journal, both temporary source images,
source snapshots, executable hashes, commands and complete raw logs are retained.

Each recovery test loops over refusal and an asynchronous checkpoint timeout.
The old call fails in the **first REFUSE iteration**; that red execution does not
reach its later HOLD iteration. The final green suite completes both iterations.
This distinction is part of [RESULTS.json](RESULTS.json), not inferred away from
the test count.

The first complete Git proof was recorded during the initial host build, not
before it. Later preflight and postflight proofs performed the full audit again
and compared it with that retained complete baseline. Their compact output is
lossless by reference to the full baseline's exact hash; the complete 3 MB
baseline is present in the archive.

## Scope of the implementation

The host adapts Desktop's existing `ObjectiveSubmission` state machine to the
original `ProductionObjectiveSender`, `ProductionDurableWriter` and
`CognitiveStore`. It retains the exact request before connect, consumes the
original send fence before transport, and retries only an immutable receipt
handoff after an unknown result. It neither creates another persistence owner
nor rearms a submission after failure.

Publication validation and observation append use the original checked
transaction. Recovered metadata is projected only after the original
`snapshot_acknowledged` operation reads the snapshot and obtains the independent
current-cut ACK within the original write transaction. A committed local row is
not sufficient to promote an observation to confirmed metadata. Recovery grants
no send or local-cancel permission. Canonical signed-body mismatches and
contradictory publications are not displayed as new established facts; a retained
first publication and its original response generation remain available.

The 14 integration tests use real original owner/store APIs and real disposable
Unix sockets. They cover retention before connect, one send opportunity, lost
reply enumeration and recovery, original authority revocation before I/O,
checkpoint failures after commit, receipt-only retry, admission/publication/unknown
views, contradictory concurrent history, exact body binding, local cancellation,
runtime-context refusal, and recovery without promoting an unacknowledged row.
They include facade drop/recovery, not a host process-crash or power-loss test.

## Dependency and qualification boundaries

The final host was built from a real fixed Git checkout. Earlier local-path
metadata attempts remain in the archive: the offline attempt failed and the
online attempt resolved a local candidate. Those are historical environment
records and are not final Git qualification. Final compilation and tests used
the Git source and the Cargo-generated, locked standalone host graph.

This host graph is intentionally distinct from the original Hepta workspace's
lock. It resolves serde 1.0.229, serde_json 1.0.151,
Tokio 1.52.3 and libc 0.2.190 under the unchanged
original package constraints and the Desktop constraints. No original package
was substituted or removed to make this host compile. Rust 1.95 matches the
original Hepta packages; the Desktop UI's independent Rust 1.88 gate remains a
separate validation.

The original memory package's **322 passing tests** were executed separately
under its original workspace and lock. They must not be added to the 14 host
tests or used to claim the original Agentd factory/Notes/issuer/bridge package
tests passed. Those owning-package gates have their own evidence requirements.

The host fixture's verifier, signature-shaped inputs and checkpoint are explicitly
test-only. These results do not supply a production signed Objective issuer,
independently protected checkpoint service, the seven production composition
inputs, RunCancel integration, real Notes readback/revocation, or native device
evidence. The standalone renderer's Send action remains unavailable. No
production eligibility follows from a test echo checkpoint.

The retention and checkpoint deadlines remain cooperative: a blocking callback
or future poll cannot be preempted by Tokio timeout. The trusted embedding must
supply bounded nonblocking verification/clock/checkpoint behavior, including
checkpoint cancellation. Unknown results never authorize another send.

The validation controller's observed process groups and final source equality
describe this actual run. Its `/proc` polling is not an atomic process-isolation
guarantee and does not establish the product's sandbox or native-device boundary.

## Complete retained evidence

[raw-evidence.tar.gz](raw-evidence.tar.gz) contains every original host validation
file except reproducible `__pycache__` bytecode: **62 validation files**, plus the
three source-publication/readback inputs and four exact external inputs referenced by the
audit receipts. It preserves empty logs, the complete Cargo metadata, the full
Git baseline, historical failure logs, exact Clippy cleanup preimages/patches,
red/green source images and logs, all controllers, and cache-transition records.
The parser's old memory failure log is included only to substantiate the real
Rust panic-format parser check; it is not a new memory qualification.

[RAW_INDEX.json](RAW_INDEX.json) enumerates all **69 archive members**,
their original paths, roles, permissions, byte counts, SHA-256 and Git blob IDs.
The archive contains **13,155,558 raw bytes** and occupies
**1,836,361 compressed bytes**. Its SHA-256 is `ca9bbc9e0b8b135869a293bc483ef0bb36727f4d7c902411186c9d3daa1bce03`.

[archive-validation.json](archive-validation.json) records two deterministic
archive builds with identical bytes and a complete decode/roundtrip comparison
against every original file. Members are regular files with safe relative paths;
UID/GID and timestamps are normalized. No raw file was edited to reduce size.

The `receipts/` directory exposes the principal final summaries without requiring
archive extraction. All original raw `.stdout`, `.stderr` and JSON files remain
in the archive. [MANIFEST.json](MANIFEST.json) hashes every published evidence
file other than itself; publication tooling also hashes that manifest.

The final integration executable was 33,224,616 bytes with SHA-256
`09ef4d9b56f11995ce7b6f923c2003bc1f4e8609c44dc95e6365f290dc740f3d`.
After the gates completed and the source and binary identities were retained,
the coordinator removed only this task's reproducible target and temporary
Rust 1.95 toolchain to release the next validation window. The source checkout,
registry, all raw receipts and executable hashes were retained. This package
does not claim to include the deleted executable itself.
