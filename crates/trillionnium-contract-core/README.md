# `trillionnium-contract-core` technical development contract

This leaf crate defines the smallest platform-neutral values shared across the desktop product. Constructors enforce bounded identifier, digest and DNS-label invariants. Revision transitions use checked, preflighted updates so exhaustion is typed and multi-counter operations are all-or-nothing.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_atomic_bounded_contract_primitives`  
Claim ceiling: `platform-neutral bounded identifiers, digests, Unix time and checked atomic revision primitives only; no transport, policy, browser, capability, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Provide bounded request/session/lease identifiers with one reviewed ASCII alphabet.
- Validate lowercase SHA-256 hex and lowercase DNS labels.
- Represent Unix milliseconds without owning a system clock.
- Model session/document/snapshot/mutation revisions and classify stale references.
- Reject revision exhaustion before mutating any field.

## Non-responsibilities

- Do not parse wire JSON, perform I/O, select policy or grant authority.
- Do not import Android, Servo, shell, ADB, transport or product dependencies.
- Do not silently saturate, wrap or reset security-relevant revision counters.

## Dependency and call direction

This is a dependency leaf. Browser contracts, session state and workspace composition may depend on it. It has no external dependencies and no binaries. Higher layers must wrap these values rather than reimplement weaker string/counter validation.

Relevant architecture:

- `docs/architecture/SESSION_STATE_MACHINE.md`
- `docs/plan/PRODUCT_ARCHITECTURE.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `BoundedId`, `RequestId`, `SessionId`, `LeaseId`, `Sha256Hex`, `DnsLabel`, `UnixMillis`, `RevisionClock`, `RevisionError`, `RefFreshness` and `classify_reference` form the public surface.
- Constructors are fallible and fields remain encapsulated where validation would otherwise be bypassed.
- Checked revision methods return typed errors and preserve the original clock on failure.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

There are no features, environment variables, files or runtime services. All byte ceilings and alphabets are bound by `contract-core-constraints.v1.json` and executable tests.

Registered Cargo features: none.

## Overflow and atomicity

Revision transitions preflight every affected counter with checked arithmetic. Exhaustion returns a typed error before any field changes, and multi-counter navigation/recovery updates are committed atomically or not at all. Silent saturation, wrapping, partial advancement and automatic counter reset are forbidden.

## State, concurrency, and failure semantics

Only caller-owned value state exists. Navigation and recovery precompute every successor before committing the complete revision clock. A failed single- or multi-counter transition leaves the full value byte-for-byte unchanged.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Never accept empty or overlength identifiers.
- Do not treat visually similar Unicode as valid protocol identity.
- Digest strings are lowercase fixed-length hex only.
- Revision overflow must fail closed and force a higher-level terminal/new-incarnation decision.
- These values are mechanism constraints, not authorization.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/trillionnium-contract-core/src/lib.rs`
- `tests/test_contract_foundation.py`

Applicable workflows:

- `.github/workflows/ci.yml`

Contract references:

- `contracts/contract-core-constraints.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run `validate_contract_foundation.py` plus Rust overflow/constructor tests.
- A `RevisionError` at runtime is a terminal consistency event; do not catch it and reuse stale identity.
- Changing a bound requires hostile tests at limit-1, limit and limit+1.
- No migration is needed for in-memory values, but persisted/wire users require an explicit version decision.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Identifiers, alphabets, lengths, DNS rules and revision semantics are cross-module contracts. Changes require machine registry, all consumers, golden tests and compatibility review. Existing evidence cannot be rebound to a changed primitive.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
