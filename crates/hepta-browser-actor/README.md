# hepta-browser-actor

**Module registry ID:** `hepta-browser-actor`  
**Workspace path:** `crates/hepta-browser-actor`  
**Owner class:** `browser-actor-security`

One-PageOwner BrowserActor admission, dispatch, semantic-action, and receipt boundary.

## Status and claim ceiling

**Current status:** `d3_source_candidate`

**Claim ceiling:** engine-neutral PageOwner/principal/dispatch/receipt core with deterministic local runtime; no promoted Servo adapter, production AgentPort, external effect, or integrated-image authority.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Bind an attested mechanism identity to an exact TaskFlow semantic principal and revalidate it before each dispatch.
- Own at most one active PageOwner/WebView token, enforce session/revision/control state, and map validated Browser API operations to typed runtime calls.
- Require `page_act` to use a dedicated atomic semantic resolver hook and wrap admitted operations in durable requested/dispatched/terminal or indeterminate receipts.

## Non-responsibilities

- The crate does not create a listener, own systemd activation, hold browser DOM nodes itself, issue capabilities, provide external network authority, or promote a release.
- The deterministic local runtime has no real DOM and intentionally cannot claim semantic `page_act` execution.

## Dependency and call direction

BrowserActor composes AgentPort, transport identity, codec models, peer attestation, session admission/journal, and neutral contracts. A concrete engine runtime implements the downward `PageRuntime` boundary; it must not call around the actor to mutate PageOwner state.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Principal binding, actor construction, PageOwner lifecycle, typed dispatch, cancellation/deadline inputs, lifecycle observer integration, and `PageRuntime::dispatch_page_act` are key surfaces. The default semantic-action hook is unsupported to prevent unsafe fallback.

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

Runtime/profile policy and identity expectations are injected. No ambient browser handle, credentials, external URL allowlist, or production activation is discovered from environment. Development configuration is owned by the separate D3 app.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

Duplicate Requested callbacks are rejected without replacing the first
in-flight admission coordinates, even if PageOwner has changed meanwhile.
The journal binds all later lifecycle facts to that first identity and request
hash. The `duplicate_requested_preserves_admission_coordinates_across_owner_change`
regression exercises the observer's real callbacks. The implementation and
failure contract are in `docs/architecture/RECEIPT_ADMISSION_IDENTITY.md`.

Every operation validates principal, session, generation, phase/control, cancellation, and deadline before runtime work. Observation/mutation/navigation acquire explicit control and release on all terminal paths. Close performs local terminal cleanup even if runtime acknowledgement fails.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

One PageOwner, no hidden second page, exact principal/mechanism binding, dispatch-time re-attestation, stale reference refusal, atomic current-frame semantic resolution, exactly-once action cardinality, durable receipt-before-response ordering, and no automatic potential-effect replay are mandatory.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run actor unit/state tests, hostile principal/revision/control/deadline/cancellation/runtime-failure cases, semantic resolver reference and Rust fixture, D3 profile corpus, journal recovery, and eventually the complete exact D2I Servo adapter corpus.

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

Classify failures before runtime dispatch versus after dispatch. Preserve requested/dispatched/terminal/indeterminate receipt status, response-commit status, principal snapshot, PageOwner revisions, cancellation/deadline, and engine error without page secrets.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Trait changes affect all runtimes and security proofs. New operation mappings must be added to contracts, codec, actor admission, runtime trait, receipts, tests, and claim ceilings. `page_act` may never be routed through a generic unverified action fallback.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.

## Managed observer rotation

`ReceiptLifecycleObserver::managed_rotation_due` requires no in-flight request
and a quiescent managed journal. `rotate_managed` consumes an idle observer,
retains PageOwner sharing, principal/image identity and logical time, and
returns no observer on uncertain storage failure. It executes no browser action.
See [`MANAGED_RECEIPT_STORE.md`](../../docs/architecture/MANAGED_RECEIPT_STORE.md)
and the executable `managed_observer` regressions for the ownership contract.

## Optional engine-thread scheduler

`engine_dispatch::engine_thread_pair` creates a non-cloneable actor port and a
non-Send/non-Sync engine owner on its creating thread. It owns no listener or
thread and is not automatically installed in either daemon. `pump_one` invokes
at most one backend hook. Original monotonic controls, private one-shot replies,
permanent closure after abandonment, strict local-only input bounds, and atomic
PageAct-only routing are specified in
[`ENGINE_THREAD_DISPATCH.md`](../../docs/architecture/ENGINE_THREAD_DISPATCH.md).
The matching contract is `contracts/engine-thread-dispatch.v1.json`.

The host corpus includes real connected Unix streams, canonical codec, actor,
thread-affine fixture engine and disk receipts. The fixture does not prove real
Servo node resolution, native input, service attestation or an integrated image.
Run `cargo test --locked -p hepta-browser-actor --doc` in addition to all-target
tests to preserve negative Send/Sync compile tests. The existing module status,
claim ceiling and D3 promotion requirements are unchanged.

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

## Callback-shaped engine scheduling

The optional `callback_engine_pair` / `CallbackEngineOwner` path starts an
operation on its creator thread and accepts a single-use `EngineCompletion`
from a later callback. The application continues native events between pumps;
its timer follows the original deadline and bounded cancellation-check schedule.
Ordinary Act never substitutes for the dedicated atomic semantic hook. The
existing request endpoint now wakes on abandonment and Drop as well as enqueue.
Wakes may be coalesced and are not a count of dispatched operations.
See `docs/architecture/EVENT_LOOP_COMPLETION.md` and
`contracts/event-loop-completion.v1.json` for APIs, ordering, tests and limits.
This is source/host fixture evidence only: no Servo/native event loop, process
IPC, installed image or product authority is added. The development daemon
continues selecting its synchronous fixture backend; no activation changes.


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
