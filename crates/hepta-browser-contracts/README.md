# hepta-browser-contracts

**Module registry ID:** `hepta-browser-contracts`  
**Workspace path:** `crates/hepta-browser-contracts`  
**Owner class:** `browser-contract-security`

Engine-neutral typed browser operations, targets, errors, and trust identities.

## Status and claim ceiling

**Current status:** `integrated_contract_foundation`

**Claim ceiling:** engine-neutral typed Browser API and risk/reference model; no wire parsing, browser runtime, capability, or effect authority.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Define typed profiles, trusted app identities, navigation targets, element references, observations, waits, page actions, operations, and Browser error codes.
- Bind semantic references to layered revisions and classify action risk.
- Provide synthetic trusted origin construction and fixture/external navigation shape checks.

## Non-responsibilities

- The crate does not parse canonical JSON, authenticate a connection, resolve a live DOM/accessibility node, issue a permit, execute a browser action, or perform network I/O.
- String shape validation does not establish DNS, TLS, redirect, connected-peer, or publisher trust.

## Dependency and call direction

The crate builds only on platform-neutral contract primitives. Codec and BrowserActor consume it. It must not depend on transport, systemd, Servo, product services, or update/release code.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Public enums and structs model browser operations and errors. `ElementRef::freshness`, `PageAction::interaction_risk`, navigation validation, trusted synthetic origin construction, and freshness-to-error mapping are key helpers.

Public types and executable names are compatibility surfaces. Rust source remains
the API truth, while this document explains the intended boundary and correct use.
Callers must not infer authority from a type being constructible or a binary being
present in a non-production feature graph.

## Configuration and features

There are no features or runtime configuration. Protocol limits and operation sets are versioned through the contracts and codec rather than environment flags.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

Types are immutable values; layered revisions distinguish stale session, document, and semantic snapshot. Mutating actions are never labelled read-only. BrowserActor must re-resolve action targets atomically before execution.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

Trusted and untrusted navigation classes stay distinct. Local HTTP is loopback fixture only; external navigation is HTTPS-shaped but still requires D6 policy. Unknown/ambiguous target behavior is fail closed in higher layers.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run unit tests for origin uniqueness, URL classes, action risk, freshness, errors, and all schema operation/error mappings. Codec and semantic resolver corpora provide cross-layer conformance.

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

No service is operated. Typed errors should be preserved through codec and response construction without weakening retry directives. Do not log target names/text unless privacy policy permits.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Rust operations and error codes must remain synchronized with JSON schemas, canonical codec, reference models, and golden vectors. Breaking enum changes require a new protocol version or explicit migration.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
