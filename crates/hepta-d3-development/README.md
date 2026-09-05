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
- Restore explicitly configured complete journal chains through the core lock-owning API; reject partial chains and preserve secret redaction during recovery classification.

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

Cargo binary auto-discovery and package build scripts are disabled explicitly
with `autobins = false` and `build = false`. Only registered `[[bin]]` targets
may execute as module binaries. Adding a conventional `src/main.rs`, `src/bin`
entrypoint, or `build.rs` without a reviewed inventory change fails the module
gate; this does not disable integration-test discovery.

Activation requires the explicit development feature/profile, systemd socket/service, administrator marker, fixed paths/ownership, and exact expected executable digest. Journal/session paths and fixture inputs are bounded. The optional
`HEPTA_D3_RECEIPT_PREDECESSORS` is an ordered colon-separated list of up to 63
archived paths within the development journal root, excluding the active file.
Omit it for single-segment stores; empty, duplicate or noncanonical lists fail.
See `docs/architecture/D3_JOURNAL_CHAIN_RECOVERY.md` for the full contract. Missing or malformed configuration fails before serving.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

The local atomic fixture prepares the complete i64-bounded JSON action result
before its final control check and state mutation. Failed encoding does not
consume the action count or target; failed Observe invalidates the old target
and publishes no new unreturnable one. `sessiond/runtime_atomic_tests.rs` covers
these boundaries through real PageRuntime entry points. This remains a fixture,
not a Servo-owned retained-node implementation. See
`docs/architecture/RECEIPT_ADMISSION_IDENTITY.md`.

The session daemon preserves one actor/session/journal authority surface. The fixture runtime applies one bounded atomic semantic operation with revision/uniqueness/drift/action checks. Restart imports the validated complete chain and logical clock; unresolved effects remain non-replayable. Missing active files never become new empty chains. SecretRedacted recovery records retain no detail.

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

## Opt-in managed receipt directory

`HEPTA_D3_RECEIPT_STORE` selects a new private store under the development state
root. Its presence conflicts with either legacy journal variable; no default
changes, migration, production marker or network authority are introduced.
The service opens the complete managed chain, reconciles facts without replay,
and rotates idle/quiescent journals at the fixed 4 MiB threshold. Rotation
errors terminate the service rather than replacing its writer or session.
See [`MANAGED_RECEIPT_STORE.md`](../../docs/architecture/MANAGED_RECEIPT_STORE.md)
for exact configuration, filename/identity rules, failure matrix and non-claims.

## Persistent development engine-thread runner

The persistent `hepta-agent-port-development-sessiond` now uses the main-thread
AtomicFixtureRuntime through EngineThreadRuntime. Its single scoped connection
worker owns the actor and receipt observer, retains the first complete attested
process snapshot (including start_time_ticks), and refuses later identity drift.
Engine retirement stops accept polling and is never an implicit engine restart.
No new configuration, production listener, executable, dependency or Servo API
is added. The old single-connection binary remains unchanged. See
`docs/architecture/D3_SESSION_ENGINE_RUNNER.md` and
`contracts/d3-session-engine-runner.v1.json` for lifecycle, bounds, failure and
source-test evidence. This remains a local fixture, not an installed Servo claim.

## Request-scoped identity across queueing

`AttestedPeer::request_custody` retains the original pidfd and identity source for
one handler lifecycle. All queued RequestControl copies share a revocable
verifier; original attestor selection, engine entry/return and final actor return
are rechecked. Identity loss never becomes a confirmed success or replayable
refusal after an uncertain effect. See
`docs/architecture/REQUEST_PEER_CUSTODY.md` and
`contracts/request-peer-custody.v1.json` for APIs, configuration, failure and
resource limits. No production activation or actual Servo proof is introduced.

## Session reconstruction isolation

Actor creation now lazily obtains an OS-sourced incarnation at the first valid
SessionCreate; session/WebView tokens are namespaced across actor reconstruction.
The atomic fixture scopes frame identity by session and WebView before publishing
a target. Entropy failure has no predictable fallback; deadlines and bounded
opaque Browser API v1 fields remain enforced. No old PageOwner is resurrected
from receipts and no operation is replayed. See
`docs/architecture/SESSION_INCARNATION.md` and
`contracts/session-incarnation.v1.json` for APIs, failure ordering, compatibility,
regressions and limits. This is source/host evidence, not actual Servo, systemd,
image, hardware, anti-rollback, production activation or release proof.


## Callback development service integration

The persistent development service now uses the callback owner with an explicit
ImmediateCallbacks bridge for its existing deterministic fixture. The main
runner waits on a private notification predicate; worker completion is published
before wake and errors retire before join. This does not implement Servo, winit,
systemd activation or an installed image. See
`docs/architecture/D3_CALLBACK_SERVICE_RUNNER.md` and
`contracts/d3-callback-service-runner.v1.json`; the source regression guard is
`tools/audit_callback_service.py`, tested by
`tests/test_callback_service_runner.py`. Existing controls and promotion limits
remain unchanged. The immediate bridge does not make a blocking backend async.
