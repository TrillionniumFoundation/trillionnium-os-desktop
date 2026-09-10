# trillionnium-contract-core

**Work package:** S02 / D0C-01  
**Claim ceiling:** platform-neutral contract primitives only; no parsing, transport,
browser, policy, operating-system, effect, image, hardware, signing, or release
authority.

## Responsibilities

This crate is the bottom of the desktop contract dependency graph. It owns:

- bounded request, session, and lease identifiers;
- lowercase SHA-256 textual values;
- DNS-label validation for synthetic origin components;
- Unix-millisecond wrappers;
- the four-layer revision clock;
- reference freshness classification.

All validation is deterministic and independent of locale, filesystem, network,
clock, process, and browser state.

## Non-responsibilities

A value accepted by this crate is not an authorization decision. The crate does
not serialize the Browser API, authenticate peers, own a session, issue
capabilities, resolve live page nodes, execute operations, or persist receipts.

## Public API

The principal public types are:

- `BoundedId`, `RequestId`, `SessionId`, and `LeaseId`;
- `Sha256Hex` and `DnsLabel`;
- `UnixMillis`;
- `RevisionClock`, `RevisionError`, `RefFreshness`, and
  `classify_reference`.

Identifier limits are UTF-8 byte limits. Current identifier syntax is ASCII, so
byte count and character count coincide for valid identifiers.

## Overflow and atomicity

Revision identities are security boundaries. They never wrap and never
silently saturate.

`RevisionClock::on_dom_commit`, `on_semantic_snapshot`,
`on_navigation_commit`, and `on_process_recovery` return
`Result<(), RevisionError>`. Multi-field transitions preflight every successor
before changing any field. On error, the complete clock remains byte-for-byte
unchanged.

A caller receiving `RevisionError` must stop the affected transition. It may
retire the session and establish a separately authenticated incarnation; it
must not continue with the old identity, reset a counter, fabricate a success
event, or retry an external effect.

The machine-readable limits and initial values are in
`contracts/contract-core-constraints.v1.json`.

## Dependency and build boundary

The crate has no dependencies. Cargo binary auto-discovery and package build
scripts are disabled. Introducing a dependency, binary, build script, platform
type, application policy, or ambient authority requires a new security review.

## Testing

Minimum checks:

```bash
python3 tools/validate_contract_foundation.py
python3 -m unittest discover -s tests -p 'test_contract_foundation.py'
cargo test --locked -p trillionnium-contract-core
cargo clippy --locked -p trillionnium-contract-core --all-targets -- -D warnings
```

Tests cover valid and invalid identifier characters, digest and DNS-label
boundaries, layered reference invalidation, explicit single-field exhaustion,
and atomic multi-field exhaustion.

## Versioning and unknown values

The crate is internal and pre-1.0, but its public types are compatibility
surfaces. Adding an enum variant may break exhaustive downstream matches.
Changing identifier syntax, byte limits, digest encoding, initial revision
values, field meaning, or overflow policy is a contract change and must not be
silently backported.

Unknown values received from a wire format are rejected by the owning versioned
codec. A future compatible extension must use a new protocol/schema version or
an explicitly documented migration; this crate does not guess an interpretation.

## Compatibility and change protocol

A behavior-changing change must update, as applicable:

1. this implementation and its tests;
2. `contracts/contract-core-constraints.v1.json`;
3. dependent Browser API schemas and canonical codec;
4. cross-language references and golden vectors;
5. module and architecture documentation;
6. gate invalidation paths and explicit non-claims.

Exact-head source evidence, independent review, and exact-main evidence are
separate promotion steps.
