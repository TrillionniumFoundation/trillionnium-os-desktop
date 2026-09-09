# `hepta-browser-codec` technical development contract

The codec is the sole boundary allowed to turn untrusted Browser API bytes into typed requests and responses. It owns a strict JSON implementation, closed operation shapes, canonical re-encoding, semantic-reference and URL validation, stable error/retry taxonomy and canonical SHA-256 inputs for later receipts.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_canonical_browser_wire_boundary`  
Claim ceiling: `bounded canonical Browser API parsing, validation, encoding, hashing and risk classification only; no listener, peer authorization, BrowserActor dispatch, Servo execution, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Reject invalid UTF-8, BOMs, duplicate members, floats, non-canonical key order, unknown fields and trailing bytes.
- Apply equal byte, depth, item, key and string limits to decoded input and programmatically constructed output.
- Validate request/session generations, semantic references, action fields, timeouts and URL authorities.
- Classify operations as observation, local interaction or potential external effect without authorizing them.
- Produce byte-for-byte canonical JSON and its digest.

## Non-responsibilities

- Do not create sockets, select a peer/principal, start Servo, dispatch BrowserActor or grant a capability.
- Do not treat HTTPS syntax as proof of resolver, redirect, connected-peer or TLS trust.
- Do not provide raw JavaScript evaluation or permissive unknown-field compatibility.

## Dependency and call direction

Transport hands opaque bytes to this crate only after mechanism admission. AgentPort consumes the resulting typed request and copies validated identity into the response. BrowserActor may consume only decoded types. The codec depends only on exact `sha2`; it must not depend on applications, network stacks or Servo.

Relevant architecture:

- `docs/architecture/CANONICAL_BROWSER_CODEC.md`
- `docs/architecture/RUST_BROWSER_CODEC.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `decode_request`, `decode_response`, `encode_request`, `encode_response` and `self_check` are the primary entry points.
- `BrowserRequest`, `BrowserOperation`, `BrowserResponse`, `BrowserWireError`, `ElementReference`, `NavigationTarget`, `PageAction` and `WaitCondition` are wire-domain types.
- `JsonValue` and `JsonObject` are bounded canonical values, not general JSON containers.
- Resource constants are mirrored by `browser-codec-resource-limits.v1.json`.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

The crate has no features or runtime configuration. All limits are compile-time reviewed constants. External URLs are credential-free HTTPS syntax; fixture URLs are loopback HTTP only. Network access remains disabled elsewhere until controlled egress is implemented.

Registered Cargo features: none.

## State, concurrency, and failure semantics

Codec operations are pure with respect to product state. Parsing uses bounded recursive accounting; encoding revalidates constructed values so internal callers cannot bypass parser limits. Failures return typed `CodecError` and produce no partially validated request.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Received bytes must equal canonical re-encoding; attacker-selected formatting is never hashed as authority.
- Recursive duplicate-key rejection and signed-64-bit numeric rules must remain aligned with the independent Python reference.
- URL validation rejects userinfo, backslashes, control characters, invalid ports, ambiguous IPv6 and non-loopback fixtures.
- Semantic actions require non-zero published revisions; the engine must still re-resolve atomically.
- Every navigation/click/type/press/select remains a potential external effect.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-browser-codec/src/tests.rs`
- `tests/test_validate_rust_browser_codec.py`

Applicable workflows:

- `.github/workflows/browser-codec-reference.yml`
- `.github/workflows/ci.yml`

Contract references:

- `contracts/browser-codec.v1.json`
- `contracts/browser-codec-resource-limits.v1.json`
- `contracts/browser-api.v1.schema.json`
- `contracts/browser-wire.v1.schema.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run the codec workflow, Rust tests, Python differential/reference tests and source audit.
- Execute the validator with `PYTHONPATH=.` or as `python3 -m tools.validate_rust_browser_codec`; direct-script behavior is also regression-tested.
- A golden mismatch requires regenerating only through the deterministic reference tool and reviewing the semantic change.
- Do not edit checked evidence to make an old host result appear current.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Wire changes require a versioned schema/contract and explicit compatibility window. Unknown fields remain rejected. Any divergence between Rust, Python reference, JSON schemas, golden vectors or resource manifest is a release blocker.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
