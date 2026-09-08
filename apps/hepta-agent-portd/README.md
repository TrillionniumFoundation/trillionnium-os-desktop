# hepta-agent-portd

**Module registry ID:** `hepta-agent-portd`  
**Workspace path:** `apps/hepta-agent-portd`  
**Owner class:** `agent-port-custody`

Profile-separated systemd inherited-stream AgentPort executables.

## Status and claim ceiling

**Current status:** `profile_separated_candidate`

**Claim ceiling:** production binary remains fail closed; fixture, D1 qualification, and development binaries are opt-in and non-production.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Provide the default product `hepta-agent-portd` process that accepts only a systemd-inherited AF_UNIX stream, revalidates peer identity, and fails closed until a promoted BrowserActor binding exists.
- Keep fixture, D1 qualification, and development executables physically and feature separated from the default product dependency graph.
- Expose deterministic self-checks for inherited descriptor shape, pathname custody, executable identity, and profile separation.

## Non-responsibilities

- No binary in this package calls `bind(2)` or creates a public TCP/WebDriver endpoint.
- Qualification and development binaries do not grant production authority, external navigation, credentials, capabilities, hardware status, or release readiness.

## Dependency and call direction

The default graph depends on transport and peer attestation only. Optional features pull in AgentPort, codec, BrowserActor, and session journaling for explicitly bounded fixture/qualification/development binaries. Call direction is inherited stream → attestation → bounded protocol/handler; lower-level crates never depend on this app.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Binaries: `hepta-agent-portd`; `hepta-agent-port-fixture` under `fixture`; `hepta-agent-port-qualificationd` and `hepta-agent-d1-fixture` under `d1-qualification`; and `hepta-agent-port-developmentd` under `development`. These names and required features are machine-audited.

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

Systemd owns socket paths and process identities. Development activation additionally requires the documented marker/profile and expected executable SHA-256. Configuration values must be exact, bounded, and absent by default. Test markers and override units must be audited out of production images.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

Each accepted connection has bounded lifetime and one request lifecycle. A protocol or transport failure is fail-stop. Attested process identity is retained and refreshed before dispatch. Journal ordering is requested → dispatched → terminal/indeterminate before a response commit. Process exit must not affect later connections or the socket custodian.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

The central invariant is profile and binary separation. The default product binary may not link fixture handlers or a development BrowserActor. Peer UID/GID alone is insufficient: PID, start time, pidfd liveness, cgroup, unit, executable/path custody, nonce, sequence, digest, and deadlines remain required as applicable.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run default and all-feature Cargo trees, daemon self-checks, systemd-analyze verification, pathname-custody tests, D1 QEMU qualification, and D3 profile tests. Inspect the final install map to prove that qualification/development artifacts are absent from production.

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

The older per-connection development binary continues to reject rotated journals before tail repair; only the separate persistent session daemon supports an explicit predecessor list. See `docs/architecture/D3_JOURNAL_CHAIN_RECOVERY.md`.

For activation failures inspect the inherited descriptor, local pathname, service user/group, expected peer unit/cgroup, marker presence, executable digest, and journal directory in that order. Do not add capabilities or broaden procfs access to make an identity check pass.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Adding or renaming a binary, feature, socket, unit, marker, environment variable, or installation path requires simultaneous updates to this document, the module registry, Cargo manifest, systemd/package files, validators, image tests, and claim ceiling.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.

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
