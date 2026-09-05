# hepta-session-core

**Module registry ID:** `hepta-session-core`  
**Workspace path:** `crates/hepta-session-core`  
**Owner class:** `session-and-receipt-security`

Transactional session ownership state machine and crash-consistent receipt journal.

## Status and claim ceiling

**Current status:** `host_validated_state_and_journal_core`

**Claim ceiling:** deterministic session admission, queueing, revisions, and durable non-replaying receipt facts; no browser, socket, clock, policy, or effect executor.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Own deterministic session phase/control transitions, layered revisions, human leases, queue admission, cancellation/recovery, and rejected-transition rollback.
- Normalize event time before authority checks so expired leases cannot authorize Human work or indefinitely deny Agent work.
- Persist bounded hash-chained receipt lifecycle facts, recover torn tails, verify segment chains, export redacted records, and identify safe retention candidates.

## Non-responsibilities

- The crate owns no Servo object, socket, thread, OS clock, capability policy, external-effect executor, updater, or automatic replay API.
- A journal record states a fact supplied by an admitted layer; it does not prove that the external world applied an effect.

## Dependency and call direction

The core consumes browser contract types and neutral primitives. BrowserActor and D3 services drive it with explicit events/timestamps/receipt facts. It must not depend on those adapters or perform callbacks into them.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

`SessionAdmission` is the public transition owner; raw machine internals remain private. Public snapshots/effects/errors expose deterministic outcomes. `ReceiptJournal` APIs open/inspect/append/recover/rotate/export without executing operations.
`open_chain(paths, expected_journal_id, policy)` pins the complete predecessor
chain and restores its global receipt namespace; standalone `open` accepts
segment one only. The unchanged binary format has explicit aggregate limits
(64 segments, 128 MiB and 131072 records). See
`docs/architecture/D3_JOURNAL_CHAIN_RECOVERY.md` for remaining head-selection
and retention limits; inode locks do not authenticate an offline snapshot.

Public types and executable names are compatibility surfaces. Rust source remains
the API truth, while this document explains the intended boundary and correct use.
Callers must not infer authority from a type being constructible or a binary being
present in a non-production feature graph.

## Configuration and features

Cargo binary auto-discovery and package build scripts are disabled explicitly
with `autobins = false` and `build = false`. Only registered `[[bin]]` targets
may execute as module binaries. Adding a conventional `src/main.rs`, `src/bin`
entrypoint, or `build.rs` without a reviewed inventory change fails the module
gate; this does not disable integration-test discovery.

Human lease bounds, queue limits, record/segment/detail sizes, file modes, and format versions are constants or explicit open policies. Time is supplied as monotonic/wall observations; no hidden clock reads are allowed in admission logic.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

Transitions clone/apply/validate/commit transactionally. Agent work requires Ready/Idle/no active Human lease; Human/IME requires the exact active lease and allowed phase. Journal append is validate → encode → write_all → sync_data → publish memory state. Uncertain writes poison the writer.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

All lifecycle facts keep the admission request digest, session/revisions,
operation/build identity, source, effect and privacy classification immutable.
One shared helper verifies append, restart, complete-chain recovery and both
export paths; a rehashed complete-record mismatch is corruption, not a torn
tail to repair. Existing multiclock observations remain supported. See
`docs/architecture/RECEIPT_ADMISSION_IDENTITY.md` for encoding, migration limits
and executable negative tests.

Reject stale/mismatched leases, non-Ready interaction, revision races, illegal receipt lifecycle changes, duplicate IDs, chain/digest/sequence corruption, symlink/non-regular paths, unsafe permissions, and automatic replay of unresolved potential effects.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run unit tests, lease admission boundaries, bounded state-space exploration, journal restart/rotation/torn-tail/disk-full/tamper/concurrency/privacy/retention tests, independent verifier, and exact-head receipt workflow.

Minimum local verification:

```bash
python3 tools/validate_module_documentation.py
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
cargo fmt --all --check
cargo check --workspace --all-targets --all-features --locked
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-targets --all-features --locked
```

Interpret every result under the claim ceiling and evidence tier recorded by the
gate registry. A skipped, cancelled, historical, or differently bound run is not
current evidence.

## Operations and troubleshooting

For state errors record event form, supplied time, phase/control/revisions before and typed rejection; rejected state must be byte/behavior unchanged. For journal errors stop writes, preserve files, inspect from the first segment, distinguish torn tail from hard corruption, and never auto-repair complete records.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Journal format, lifecycle transitions, revision semantics, lease boundary (`now >= expires_at`), and error mapping are persistent contracts. Format changes require versioned migration/reader tests and must never reinterpret old potential-effect records as replayable.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.

## Managed receipt storage

The opt-in `ReceiptJournal::create_managed`, `open_managed` and consuming
`rotate_managed` APIs select a complete chain from a closed private directory
inventory and publish only a synced linked header by atomic rename plus
directory sync. `ManagedOpenPolicy` separates pending completion from tail
repair. The fixed 4 MiB idle rotation trigger does not change chain bounds.
Unmanaged writer APIs reject managed segments. Legacy explicit-path behavior
remains unchanged outside a managed root. See
[`MANAGED_RECEIPT_STORE.md`](../../docs/architecture/MANAGED_RECEIPT_STORE.md)
for format, recovery matrix, threat assumptions, tests and deployment. This is
source/local storage behavior, not installed-image, physical power-loss or
authenticated offline rollback evidence.

## Receipt persistence-cut regression

The managed reopen path re-establishes file and directory durability before it
returns a writer. Development and maintenance details are in
`docs/architecture/RECEIPT_PERSISTENCE_FAULT_MODEL.md`. The private cfg(test)
library corpus exercises 128 injected I/O-error combinations; the separate
`journal_persistence_process` Cargo test target executes 64 actual SIGKILL
cutpoint cases over the exact journal source. Neither is physical power loss
or a product fault-control interface. Run both focused targets plus the full
workspace/default/all-feature and Python discovery matrices. The independent
process test has a custom harness; libtest name filters should use `--lib`.
Module/component registration and `tests/test_receipt_persistence_cuts.py` guard
source wiring, conditional compilation, durability order and claim ceilings.

## Explicit offline legacy copy

`ReceiptJournal::copy_legacy_chain_to_managed` copies a strictly validated, read-only locked legacy chain into a new private managed directory without changing any original record or lease bytes. `ReceiptMigrationReport` records byte identities, not a service cutover or deletion permit. Interrupted staging remains refused, sources are never repaired, and unresolved effects are never replayed. See `docs/architecture/LEGACY_RECEIPT_MIGRATION.md` and `contracts/legacy-receipt-migration.v1.json`. The dedicated `journal_migration_process` test compiles the actual journal source; it is not an installed executable.
