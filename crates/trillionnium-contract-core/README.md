# trillionnium-contract-core

**Module registry ID:** `trillionnium-contract-core`  
**Workspace path:** `crates/trillionnium-contract-core`  
**Owner class:** `contract-foundation`

Platform-neutral contract primitives shared by desktop crates.

## Status and claim ceiling

**Current status:** `integrated_contract_foundation`

**Claim ceiling:** platform-neutral bounded identifiers, digests, time and revision primitives only.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Define bounded identifiers, lowercase SHA-256 values, DNS labels, Unix time wrappers, revision clocks, and reference-freshness classification.
- Provide deterministic validation errors with no transport, browser, policy, or operating-system side effects.
- Keep shared primitives free of Android, ADB, root-shell, Servo, and product authority semantics.

## Non-responsibilities

- The crate does not serialize the Browser API, authenticate a peer, own a session, authorize an action, access the OS, or interpret product policy.
- A valid primitive is necessary but never sufficient for admission or effect authority.

## Dependency and call direction

This is the bottom of the local contract graph and should remain dependency-light. Browser contracts, session core, BrowserActor, and product policy consume it. Reverse dependencies must not leak application-specific types into this crate.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Public types include `BoundedId`, request/session/lease aliases, `Sha256Hex`, `DnsLabel`, `UnixMillis`, `RevisionClock`, `RefFreshness`, and `classify_reference`. Constructors validate before values enter higher layers.

Public types and executable names are compatibility surfaces. Rust source remains
the API truth, while this document explains the intended boundary and correct use.
Callers must not infer authority from a type being constructible or a binary being
present in a non-production feature graph.

## Configuration and features

All size and character limits are compile-time contract constants. There are no Cargo features or environment inputs.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

Revision clocks advance distinct session, document, semantic snapshot, and mutation layers. Saturating behavior is explicit in current APIs; callers requiring overflow refusal must add a reviewed checked transition rather than assume it.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

Reject empty, overlong, path-like, whitespace/control, uppercase digest, malformed DNS, and stale revision values before they reach authority layers. Keep validation deterministic and independent of locale or host state.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run unit tests for every boundary value, invalid character class, digest/DNS form, and revision transition. Higher-level schema/codec tests must cross-check these constraints.

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

There is no runtime service. Failures should be returned as typed contract violations and mapped once by the owning protocol layer. Avoid logging rejected secret-bearing values.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Changing a bound or character set is a wire/security change. Update dependent schemas, Rust types, Python references, golden vectors, documentation, and migration/version policy atomically.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
