# hepta-browser-codec

**Module registry ID:** `hepta-browser-codec`  
**Workspace path:** `crates/hepta-browser-codec`  
**Owner class:** `browser-contract-security`

Product-owned canonical Browser API v1 wire codec.

## Status and claim ceiling

**Current status:** `host_validated_contract_boundary`

**Claim ceiling:** canonical Browser API parsing, validation, encoding, hashing, and effect classification only; no listener, authorization, or dispatch.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Perform bounded UTF-8 JSON parsing with recursive duplicate-key rejection and signed-64-bit integer enforcement.
- Convert exact request/response shapes, validate session/reference/URL fields, and require byte-for-byte canonical re-encoding.
- Publish canonical SHA-256 inputs and classify operations as observation, local interaction, or potential external effect.

## Non-responsibilities

- Classification is not authorization. The codec does not grant a capability, map a principal, call a browser runtime, start a listener, or execute an effect.
- Network namespace, resolver, redirect, peer-IP, credential, and reconciliation policy belong to later layers.

## Dependency and call direction

Transport supplies opaque authenticated bytes; the codec returns typed validated values to AgentPort/BrowserActor. It must not depend on AgentPort, Servo, systemd, product policy, or operating-system authority.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Primary APIs decode canonical requests/responses, encode canonical responses, validate typed models, and expose canonical digests/effect classes. Model modules separate requests, responses, shared types, errors, validation, and the bounded parser.

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

Byte size, depth, aggregate item, integer, URL, and canonicalization limits are source/contract constants. There are no runtime feature flags. A future version negotiator must not accept ambiguous v1 encodings.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

The codec is deterministic and stateless per call. Parsing is ordered fail closed: byte/UTF-8 checks, bounded syntax, duplicate/integer limits, typed conversion, semantic validation, canonical encoding, exact byte equality, digest publication.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

Unknown fields, duplicate members, floats, non-canonical whitespace/order, BOM, trailing data, out-of-domain integers, malformed URLs, partial session binding, and stale reference shapes are rejected. Navigation and mutating UI operations remain potential effects.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run Rust tests, 27-vector independent Python reference, golden byte equality, hostile depth/item/integer/Unicode cases, and static cross-contract audit. Add fuzzing around parser resource limits and canonical round trips.

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

Log only typed error code, bounded location/classification, request digest, and source identity; do not log raw page text or credentials. A canonical mismatch is a client/protocol error, not a reason to normalize and accept attacker bytes.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Schema, Rust model, Python reference, golden vectors, error codes, and documentation must change atomically. Enum or field additions require an explicit version/unknown-field policy. v1 canonical bytes must remain stable.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
