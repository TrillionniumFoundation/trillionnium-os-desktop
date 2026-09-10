# hepta-browser-contracts

**Work package:** S02 / D0C-01  
**Claim ceiling:** engine-neutral typed Browser API and trust/risk model only; no
wire parsing, peer authentication, live semantic resolution, browser runtime,
capability issuance, external effect, image, hardware, signing, or release
authority.

## Responsibilities

This crate defines the engine-neutral domain vocabulary used by higher layers:

- profiles and UI mode;
- trusted application identity and synthetic origin construction;
- trusted, external, and local-fixture navigation targets;
- layered semantic element references;
- observations, waits, page actions, and Browser operations;
- interaction-risk classification;
- stable Browser error codes and freshness-to-error mapping.

The crate depends only on `trillionnium-contract-core`.

## Non-responsibilities

The types describe intent and boundaries. They do not prove URL reachability,
DNS or TLS identity, publisher trust, live node identity, user consent,
principal authority, capability admission, effect safety, or successful browser
execution.

`NavigationTarget::ExternalHttps` is only a domain class. The canonical wire
codec and later controlled-egress layer must perform stricter parsing and
network enforcement.

## Reference and effect semantics

An `ElementRef` binds session, document, semantic snapshot, frame, and
structural evidence. Higher layers must re-resolve and revalidate the target at
the execution boundary. A stale or ambiguous target is rejected; it is never
converted to coordinate, text-search, JavaScript, WebDriver, or cross-frame
fallback.

Click, type, press, select, and navigation can produce external effects.
Classification is not authorization. No potentially completed effect may be
blindly retried after timeout, crash, disconnect, stale identity, or an
indeterminate result.

## Dependency and build boundary

The crate has no operating-system, transport, Servo, storage, policy, update, or
release dependency. Cargo binary auto-discovery and package build scripts are
disabled. New dependencies require a contract-security review.

## Testing

Minimum checks:

```bash
python3 tools/validate_contract_foundation.py
cargo test --locked -p hepta-browser-contracts
cargo clippy --locked -p hepta-browser-contracts --all-targets -- -D warnings
```

Tests cover synthetic-origin separation, navigation classes, action risk, and
layered reference freshness. Canonical byte conformance belongs to S03 and must
cross-check these domain constraints rather than silently redefine them.

## Versioning and unknown values

The public operation and error enums are versioned compatibility surfaces.
Unknown wire operation, action, persistence, target, wait-condition, and error
values fail closed in the owning codec. They must not be mapped to a nearby
known variant.

Adding or changing an operation, error, retry meaning, field, trust class, or
interaction-risk class requires either:

- a backward-compatible change proven against the existing version; or
- a new protocol/schema version with an explicit migration and downgrade rule.

Rust source is the domain-model authority for this crate. Wire shape,
canonicalization, byte limits, and serialization are owned by the versioned
schema/codec layer.

## Operations and troubleshooting

There is no runtime process. Preserve typed errors across layers and avoid
logging page text, accessible names, target values, or credentials unless an
explicit privacy policy permits it.

## Compatibility and change protocol

A behavior-changing change must update the domain types, schemas, codec,
cross-language reference, golden vectors, tests, documentation, gate
invalidation paths, and non-claims together. Passing unit tests does not prove a
BrowserActor, a Servo runtime, an installed image, physical hardware, or a
release.
