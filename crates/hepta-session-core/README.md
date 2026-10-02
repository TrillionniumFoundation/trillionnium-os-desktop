# `hepta-session-core` technical development contract

The session core combines the human/Agent state machine with bounded queueing and a crash-consistent receipt journal. Adapters supply events, time and operation facts. The crate records what was requested, dispatched and observed; it never performs or retries a browser or external operation.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_session_arbitration_and_managed_receipt_store`  
Claim ceiling: `deterministic session arbitration, bounded queueing, checked revisions and durable non-replaying receipt facts only; no browser engine, listener, OS clock, semantic policy, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Arbitrate one human lease, IME ownership and one Agent operation against explicit session phases.
- Advance checked revision layers for DOM, semantic snapshot, navigation and recovery transitions.
- Bound pending work and reject incompatible state transitions.
- Append canonical chained receipt records with single-writer custody, sync and recovery semantics.
- Support managed publication, rotation, redacted export, retention planning and explicit legacy copy migration.

## Non-responsibilities

- Do not own Servo, sockets, threads, policy, wall/monotonic clocks or external-effect providers.
- Do not infer completion when a write, dispatch or process result is uncertain.
- Do not automatically replay a potentially dispatched external effect.
- Do not auto-repair complete-record corruption or silently delete history.

## Dependency and call direction

BrowserActor consumes the state machine and receipt APIs. Browser contracts and core primitives are dependencies. Durable storage adapters must call the public journal in its specified order. This crate does not depend on application, systemd or platform layers.

Relevant architecture:

- `docs/architecture/SESSION_STATE_MACHINE.md`
- `docs/architecture/DURABLE_RECEIPT_JOURNAL.md`
- `docs/architecture/MANAGED_RECEIPT_STORE.md`
- `docs/architecture/RECEIPT_PERSISTENCE_FAULT_MODEL.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `SessionMachine`, `SessionSnapshot`, `SessionEvent`, `SessionEffect`, `SessionPhase`, `ControlState`, `ArbiterQueue` and related errors model arbitration.
- `ReceiptJournal`, `ManagedReceiptStore`, envelope/lifecycle/privacy/effect types, recovery reports, export and retention functions model durable facts.
- Open/create/append/inspect/seal/rotate operations are explicit and fallible.
- `contains_receipt`, `has_unresolved_receipts`, `receipt_fact` and `execution_reconciliation_facts` revalidate the complete locked journal chain, including sealed predecessors. Lookup never readmits a request.
- `DurableReceiptFact` has private fields and can only be obtained by authoritative journal lookup. Its exact request digest, latest lifecycle and record digest are evidence, not execution or replay permission. Every accessor checks the creating PID and returns a fallible `Result`; an inherited fork fact cannot be translated into a new process's authority.

The fact accessor signatures are:

```rust
receipt_id(&self) -> Result<&str, JournalError>
request_sha256(&self) -> Result<Digest, JournalError>
lifecycle(&self) -> Result<ReceiptLifecycleState, JournalError>
record_sha256(&self) -> Result<Digest, JournalError>
```

These are checked source API signatures. The v1 on-disk record format is unchanged.

Structural terminal state and execution certainty are distinct.
`has_unresolved_receipts` reports nonterminal lifecycle history;
`execution_reconciliation_facts` separately preserves `indeterminate` and
`interrupted` after durable dispatch for explicit recovery review, even after
rotation/reopen. An interruption before dispatch needs no execution decision.
Neither query changes receipts or records an operator acknowledgment.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

There are no features. Human lease ceilings, record/segment sizes and storage modes are reviewed constants. Callers provide timestamps and selected paths; managed store code validates ownership, modes, no-follow path custody and publication rules.

Registered Cargo features: none.

## State, concurrency, and failure semantics

The session machine applies each event atomically or returns a typed error. Journal append encodes the complete record, writes at the known complete offset, syncs, then advances in-memory sequence/chain state. Uncertain writes poison the writer until reopen. Only a verified torn tail may be explicitly truncated; mid-log corruption fails hard.

Live journals, managed directory custody and sealed facts belong to the creating
process. A writer may move to another thread in that process. Fork copies are
refused before file/lock validation, append, sync, lookup, sealing or rotation.
Child Drop only closes its inherited descriptors; it never writes a clean-release
marker or explicitly unlocks the parent's open file description. The parent
retains its sole writer lease. A child must obtain a new independently admitted
store after the original writer releases custody.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Human focus/IME excludes Agent mutation unless a later reviewed policy says otherwise.
- Revision exhaustion and lease-time overflow leave whole state unchanged.
- Receipt lifecycle transitions and chain digests prevent invented completion.
- Secret-redacted records cannot persist detail; exports omit sensitive detail.
- Potential external effects expose `never_automatic` after uncertain dispatch.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-session-core/src/tests.rs`
- `tests/test_s05_receipt_recovery.py`
- `crates/hepta-session-core/tests/journal_fork_custody.rs` (single-thread actual fork; legacy and managed writers, inherited sealed facts and parent lease preservation)

Applicable workflows:

- `.github/workflows/receipt-journal.yml`
- `.github/workflows/ci.yml`

Contract references:

- `contracts/receipt-journal.v1.json`
- `contracts/receipt.v1.schema.json`
- `contracts/legacy-receipt-migration.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Managed store directories use `0700`; journal files use `0600`. Use one writer.
- On crash, reopen with explicit recovery policy, inspect the complete chain and handle unresolved receipts before rotation.
- Treat disk full, sync failure or complete-record corruption as degraded mode, not success.
- Run SIGKILL/cutpoint, torn-tail, tamper, rotation, migration and concurrent-reader corpora after storage changes.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Journal format, lifecycle, digest chain, migration or retention changes require a versioned reader/writer and rollback plan. Session event semantics require state-space tests. Never rewrite historical records to fit a new schema.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
