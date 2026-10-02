# `hepta-browserd` technical development contract

The desktop browser daemon package is the product composition point for the bounded contracts, transport, AgentPort, session state and receipt foundations. On this source line its executable remains a deliberately non-listening scaffold: it reports build identity and runs deterministic self-checks, but it does not create a Servo instance or claim that the desktop product is operational.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `integrated_d0_scaffold_with_candidate_actor_contracts`  
Claim ceiling: `deterministic D0 self-check and source composition only; no product Servo runtime, enabled AgentPort, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Publish the active plan revision and integrated implementation-stage constants used by repository truth checks.
- Compose transport, canonical codec, AgentPort and session-state self-checks without widening their authority.
- Expose one stable command-line surface for build information, deterministic verification and future supervised product startup.
- Remain the eventual owner of one PageOwner and one product browser runtime after the S08 gate is separately reviewed.

## Non-responsibilities

- Do not bind or accept the AgentPort socket; systemd and the connection service own that lifecycle.
- Do not invent a BrowserActor, Servo frame, user consent, capability or external-effect result from a self-check.
- Do not own PID 1, update/signing keys, raw devices, arbitrary filesystem authority or release promotion.

## Dependency and call direction

`hepta-browserd` is an application-layer consumer of `hepta-agent-transport`, `hepta-browser-codec`, `hepta-agent-port`, `hepta-browser-actor`, `hepta-browser-contracts`, `hepta-peer-attestation`, `hepta-session-core`, and `trillionnium-contract-core`. Those lower layers must never depend back on this application. The current self-check calls into each mechanism in dependency order and then exercises the engine-neutral session state machine. The native Servo adapter must remain a distinct concrete, reviewed path rather than a generic caller-injected runtime.

Relevant architecture:

- `docs/architecture/RUNTIME_TOPOLOGY_AND_FAILURE_MODEL.md`
- `docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md`
- `docs/architecture/SESSION_STATE_MACHINE.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `ACTIVE_PLAN_REVISION` and `IMPLEMENTATION_STAGE` are immutable build-truth sentinels.
- `run_self_check()` returns a bounded `SelfCheckReport`; it is development evidence, not readiness.
- Binary `hepta-browserd` supports `--self-check`, `--print-build-info`, and `--help`. Unknown arguments fail with exit status 2.
- `BrowserdRuntimeSupervisor<A, F>` is the source-level supervision API; `ProductServoRuntime<F>` binds its actor parameter to the concrete `ServoBrowserActor`. The executable does not yet call this supervisor to start a product runtime.
- `RuntimeGeneration`, `SemanticReference`, `RuntimeState`, `DispatchCompletion<T>`, `RestartPolicy`, `CrashTransition` and `ProductRuntimeError` describe its checked lifecycle and redacted results.

The supervision operations have the following contract. The complete signatures
and Rust API examples live with `apps/hepta-browserd/src/servo_product_runtime.rs`
and its public package exports in `apps/hepta-browserd/src/lib.rs`.

| Operation | Preconditions and result | Failure/ownership semantics |
| --- | --- | --- |
| `RestartPolicy::new(u32)` | Positive crash threshold; returns a policy | Zero returns `invalid_restart_policy` |
| `BrowserdRuntimeSupervisor::start(factory, policy)` | Factory creates generation one; returns a ready supervisor | Factory error becomes redacted `reconstruction_failed` |
| `semantic_reference(revision)` / `validate_reference(reference)` | Reference carries current runtime generation | A previous generation returns `stale_generation`; opaque revision validation remains BrowserActor's responsibility |
| `dispatch(reference, FnOnce)` | Current reference, ready actor, no replay latch or open crash loop | Calls the closure once; possible dispatch without completion latches reconciliation; no retry |
| `content_process_crashed()` | Invalidates generation and drops the actor | Never calls the factory; generation exhaustion and crash threshold leave terminal lockout |
| `reconstruct()` | Explicit caller action with no replay latch or open crash loop | Constructs the reserved generation; failure does not create success or replay |
| `acknowledge_stable_cycle()` | A ready actor, no replay latch, and closed crash-loop breaker | Resets the consecutive-crash count only; never reopens terminal lockout |
| `reconcile_indeterminate()` | Caller has separately accepted the durable reconciliation evidence | Clears replay uncertainty only; no replay, implicit reconstruction or reopening of terminal lockout |

The reconciliation method does not itself validate or issue a durable receipt.
The product coordinator must establish that authority before calling it; a
generic supervisor test does not prove the installed reconciliation path.

The separate `product_dispatch` source module provides concrete request composition:

| API | Contract |
| --- | --- |
| `AcceptedProductConnection::attest` | Retain the original connected Unix stream, kernel credentials, opaque pidfd-backed live attestation, and one monotonic budget including admission and queue residence; maximum 20 seconds |
| `AcceptedProductConnection::from_received` (Linux) | Consume opaque `ReceivedAcceptedStream` through its one-shot callback; retain the original stream and exact absolute deadline while performing separate live pidfd-backed identity admission; transfer/receiver delay cannot restart the budget |
| `AcceptedProductConnection::deadline` | Read the same fixed Instant after creator-PID, cancellation and expiry checks; this does not refresh identity or grant dispatch |
| `product_connection_queue` / `try_submit` / `try_next` | Nonblocking bounded handoff of original connections; capacity 1–8; overflow closes the rejected connection |
| `ProductConnectionCancellation::cancel` | Revoke a queued/active connection, interrupt blocking socket operations and cancel active actor work; grants no dispatch or recovery authority |
| `ProductRequestCoordinator::from_connection` | Bind a concrete `ServoRuntimeEndpoint` and a complete managed receipt journal to the admitted principal; refuse nonterminal or terminal-uncertain prior history |
| `from_connection_after_reconciliation` | Trusted recovery caller explicitly acknowledges every terminal uncertain request by exact ID and canonical digest, checked against complete live journal facts; nonterminal history remains blocked |
| `serve_connection` | Semantic preflight before durable admission, durable dispatch intent before engine work, and terminal receipt acknowledgment before response publication; deduplication includes sealed predecessor segments |
| `reconcile_request` | Validate the exact currently blocked request against a sealed terminal fact from the live complete journal; no replay, receipt rewrite or implicit reconstruction |
| `content_process_crashed` / `reconstruct` | Native owner first withdraws old content/input and retires its bridge; checked generation invalidation then explicit fresh endpoint binding; crash-loop lockout remains closed |

The handoff consumer and raw `attest` share the private `attest_before` helper.
It checks the absolute deadline before/after kernel peer observation, after live
attestation before the interrupt clone, after cloning/liveness and after local
setup before return. Late results close the original owned stream and any clone.
The attestor's existing synchronous procfs calls are not preempted mid-syscall;
this API refuses a late result rather than claiming a hard syscall timeout.
The closed source contract/API inventory is
[`accepted-stream-handoff.v1.json`](../../contracts/accepted-stream-handoff.v1.json).

`cargo test --locked -p hepta-browserd --test product_handoff_kernel` exercises
real SCM_RIGHTS, an actual same-UID child `/proc`/pidfd identity, original fixed
Instant after receiver delay, queue expiry, cancellation/EOF and actual fork.
It does not establish an approved systemd principal, cross-UID product custody,
installed service or Servo action. Existing synthetic composition tests retain
their separate scope.

The coordinator and actor are constructed on their worker thread after moving
the concrete endpoint there. The native creator thread must own and pump the
matching `ServoRuntimeOwner`, retain current native semantic nodes, and call
`ServoRuntimeCompletion::ensure_current_peer` immediately before the action.
No installed embedder currently fulfills this composition/startup contract.
The executable and default AgentPort service remain disabled. Cross-UID live
executable attestation also requires an approved broker or equivalent narrowly
reviewed authority; qualification static attestation is not a product fallback.
Trusted recovery UI/policy and durable operator-decision records remain open.
Startup therefore requires explicit exact acknowledgments again after reopening;
source receipt inspection does not claim a persisted operator decision.

The coordinator, supervisor, connection queue and cancellation owner bind to
their creating PID. Inherited fork objects refuse dispatch/recovery before a
copied mutex or channel can be touched. Foreign cancellation is a no-op and
foreign teardown only closes child descriptor copies; it never shuts down the
parent's original socket or changes its journal lease. Intended worker-thread
handoff remains available within the creating process. Native Servo owner-thread
checks remain separate and mandatory.

Registered binaries:

- `hepta-browserd` at `src/main.rs`; required features: `none`.

## Configuration and features

There are currently no Cargo features or runtime configuration files. The package intentionally starts no listener, window, network stack or credential profile. S08 may add an explicit non-default host-integration profile, but production activation must remain fail closed and must not be inferred from source presence.

Registered Cargo features: none.

## State, concurrency, and failure semantics

The executable's state is local to its self-check call. Session transitions use `SessionMachine`; navigation, human focus, IME, crash and recovery advance typed revisions. The separate source-level supervisor owns one optional actor, a factory, checked runtime generation, consecutive-crash count and replay latch. The concrete coordinator co-owns one Servo actor and managed receipt observer; storage failure permanently closes admission for that instance. Terminal uncertainty and interruptions after durable dispatch require explicit exact-request reconciliation. Neither API automatically repeats work or reconstructs an actor. Native pixels/input withdrawal, installed process startup, trusted recovery UI and persisted recovery decisions remain integration work.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Self-check success cannot be translated into a product or release claim.
- Trusted chrome and untrusted content must never share a DOM authority realm.
- Only one logical PageOwner/content surface may be authoritative in v1.
- External navigation, credentials, capabilities and effects stay closed until their independent gates pass.
- Diagnostic output must contain no raw peer identity, credentials, page content or secret receipt detail.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

`apps/hepta-browserd/tests/product_fork_custody.rs` is a standalone single-thread
actual-fork regression. It exercises inherited queue, cancellation, dispatch,
recovery and supervisor refusal, parent socket continuity and sole-writer
custody. Its procfs/native owner inputs are explicitly source fixtures; it does
not qualify installed Servo or service startup.

Primary source or test references:

- `apps/hepta-browserd/src/lib.rs`
- `apps/hepta-browserd/src/servo_product_runtime.rs`
- `apps/hepta-browserd/src/product_dispatch.rs`
- `apps/hepta-browserd/src/product_dispatch/tests.rs` (real Unix framing, synthetic procfs facts and controlled callbacks; source tests only)
- `tests/test_s06_browser_actor.py`
- `tests/test_s08_product_supervision.py`

Applicable workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/s06-browser-actor.yml`
- `.github/workflows/s08-product-servo-runtime.yml`

Contract references:

- `contracts/browser-api.v1.schema.json`
- `contracts/browser-actor.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run `cargo run --locked -p hepta-browserd -- --self-check` after repository validation.
- Use `--print-build-info` to compare the binary with machine truth; a mismatch is a build/repository defect.
- A self-check failure should be investigated at the first named lower-layer error. Do not suppress it or widen the claim ceiling.
- Review [`S08_PRODUCT_SERVO_SUPERVISION.md`](../../docs/architecture/S08_PRODUCT_SERVO_SUPERVISION.md) before changing crash, generation, dispatch or reconciliation semantics.
- There is no supported service installation or user-data migration on this source line.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Changing the plan/stage constants, dependency graph, command line, self-check sequence or future startup profile requires synchronized updates to machine truth, tests, this document and the module registry. Any runtime adapter or activation change is a new trust boundary and must receive exact-head, prospective-merge and independent review evidence.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
