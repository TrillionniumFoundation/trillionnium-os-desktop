# hepta-d3-development

**Module registry ID:** `hepta-d3-development`  
**Workspace path:** `crates/hepta-d3-development`  
**Owner class:** `d3-development-security`

Isolated persistent D3 development session, fixture client/corpus, and journal checker.

## Status and claim ceiling

**Current status:** `d3_development_candidate`

**Claim ceiling:** explicit non-default development/qualification graph using deterministic fixture semantic resolution; no Servo, production activation, external effect, hardware, signing, or release authority.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Provide a non-default `development` feature that links the D3 AgentPort, BrowserActor, semantic fixture runtime, peer attestation, and receipt journal without entering the default product graph.
- Run a persistent systemd-owned development session service and deterministic hostile corpus for principal, revisions, atomic semantic resolution, receipts, cancellation, deadlines, and restart behavior.
- Reject unsupported rotated journal stores until complete predecessor-chain import is available.

## Non-responsibilities

- This package is not a production daemon, Servo adapter, product AgentPort enablement, external network/effect implementation, hardware qualification, or release path.
- Static trusted executable attestation is development-only and cannot be relabelled as live procfs executable proof.

## Dependency and call direction

The package is a top-level development graph composed from AgentPort, transport, BrowserActor, codec, peer attestation, and session core. It is feature gated and must remain absent from default product installation. Runtime fixture code adapts the actor; it must not bypass actor admission.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Feature-gated binaries are `hepta-agent-port-development-sessiond`, `hepta-agent-d3-fixture`, and `hepta-d3-journal-check`. Internal modules separate activation, service, storage, runtime, fixture client, corpus, and model.

Public types and executable names are compatibility surfaces. Rust source remains
the API truth, while this document explains the intended boundary and correct use.
Callers must not infer authority from a type being constructible or a binary being
present in a non-production feature graph.

## Configuration and features

Activation requires the explicit development feature/profile, systemd socket/service, administrator marker, fixed paths/ownership, and exact expected executable digest. Journal/session paths and fixture inputs are bounded. Missing or malformed configuration fails before serving.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

The session daemon preserves one actor/session/journal authority surface. The fixture runtime applies one bounded atomic semantic operation with revision/uniqueness/drift/action checks. Restart imports only supported complete journal state; unresolved effects remain non-replayable.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

Default graph isolation, separate socket pathname, root-owned non-symlink executable path, live pidfd/process identity, dispatch refresh, exact principal binding, one PageOwner, atomic semantic resolver, durable receipts, and no external-effect authority are mandatory.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run all-feature Rust checks, D3 validator, fixture corpus, journal checker, installed systemd verification, path hostile tests, and source semantic resolver workflows. Final D3 promotion still requires a Servo-owned resolver in the exact integrated image.

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

On startup failure inspect feature/profile, marker, socket/service closure, service identities, executable path/digest, journal chain, then fixture model. Never enable production units or weaken path/identity checks to diagnose development.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Any binary, feature, marker, socket, service, environment key, state/journal format, or fixture scenario change must update Cargo, packaging, validator, this document, module registry, tests, and D3 claim ceiling. Promotion to a real Servo runtime is a separate reviewed package.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
