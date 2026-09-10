# `hepta-browser-contracts` technical development contract

This crate defines the engine-neutral domain vocabulary used by session and workspace logic. It distinguishes trusted shell/app, external HTTPS and loopback fixture targets; carries layered semantic-reference identity; and classifies page actions by risk without authorizing them.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_engine_neutral_browser_domain_contracts`  
Claim ceiling: `engine-neutral typed browser operations, navigation targets, semantic references, risk classes and stable errors only; no wire parsing, listener, runtime, capability, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Define profile, UI, navigation, semantic element, observation, wait and page-action types.
- Construct synthetic trusted-app tuple origins from validated publisher/app labels.
- Bind element references to session, document and semantic snapshot revisions.
- Classify actions as observation, local-only or potential external effect.
- Expose stable browser error codes and stale-reference mapping.

## Non-responsibilities

- Do not parse or canonicalize untrusted JSON bytes; the codec owns wire admission.
- Do not contact Servo, resolve DNS, validate TLS, grant capabilities or execute actions.
- Do not let direct construction bypass validated URL/identifier types in future extensions.

## Dependency and call direction

The crate depends only on `trillionnium-contract-core`. Session state consumes its element and error types. The wire codec has a separate strict DTO representation and must convert through an explicit validated boundary; neither copy may silently drift.

Relevant architecture:

- `docs/architecture/CANONICAL_BROWSER_CODEC.md`
- `docs/architecture/SESSION_STATE_MACHINE.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `ProfileSpec`, `ProfilePersistence`, `TrustedAppIdentity`, `NavigationTarget`, `ElementRef`, `PageAction`, `ObservationFields`, `WaitCondition`, `BrowserOperation`, `BrowserErrorCode` and `error_for_freshness` are the main types.
- Trusted origin generation uses distinct `<app>.<publisher>.apps.hepta.invalid` tuple hosts.
- Risk classification is descriptive and never a permit.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

There are no Cargo features or runtime configuration. Synthetic origins and v1 operation vocabulary are compile-time contracts. Network behavior, credentials and trusted app bundle verification live in later gates.

Registered Cargo features: none.

## State, concurrency, and failure semantics

Values are immutable caller-owned data. `ElementRef::freshness` compares all revision layers. No queue, clock, browser object or persistence is owned here. Validation failure must occur before higher layers enqueue work.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- External and fixture URL semantics must remain aligned with the strict codec; prefix-only interpretations are forbidden.
- Trusted shell/app origin values cannot be supplied by page content.
- Every mutating UI action is a potential external effect.
- Stale session/document/snapshot references map to distinct typed errors.
- Domain constructors must not become an alternate weaker admission path.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-browser-contracts/src/lib.rs`
- `tests/test_contract_foundation.py`

Applicable workflows:

- `.github/workflows/ci.yml`

Contract references:

- `contracts/browser-api.v1.schema.json`
- `contracts/contract-core-constraints.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run contract-foundation tests and codec/domain parity tests after changing operations or URLs.
- A mismatch between this crate and wire schemas is a blocker; do not patch at the adapter layer.
- Document unsupported operations rather than accepting opaque extension maps.
- No standalone service or file migration exists.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Versioning and unknown values

The v1 operation and error vocabulary is closed. Unknown operation variants, fields, trust classes and retry meanings are rejected rather than stored as opaque extension data. A new value requires an explicit protocol/schema version, codec parity, migration/compatibility decision and hostile regression coverage.

## Compatibility and change protocol

Operation variants, error codes, trusted origins and reference fields require explicit versioning and coordinated codec/schema changes. Removing or reclassifying an operation requires security review because retry/effect behavior may change.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
