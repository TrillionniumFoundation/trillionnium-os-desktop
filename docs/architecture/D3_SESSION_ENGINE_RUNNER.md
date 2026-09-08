# D3 development service engine runner

**Plan:** `2026-08-29-d6`<br>
**Gate:** `D3-01`<br>
**Status:** source candidate; local host tests only<br>
**Contract:** `contracts/d3-session-engine-runner.v1.json`

## Scope and non-claims

The non-default `hepta-agent-port-development-sessiond` now uses the bounded
engine-thread bridge in its actual service path. Its `AtomicFixtureRuntime`
is still a deterministic local fixture, NOT a Servo adapter. This is not a
native Wayland/Servo event loop, process IPC, systemd activation qualification,
installed-image proof, or production authority. The older single-connection
development binary is unchanged. No new binary, Cargo feature, environment
selector, network listener, dependency, executable permission or install entry
is introduced. Exact-image evidence for the old daemon must be invalidated.

## Startup and thread ownership

Main validates the explicit development profile and administrator marker,
consumes the one systemd-owned listener, resolves the expected peer accounts,
checks the root-owned static executable pin, and opens/reconciles the selected
journal before entering the runner. The marker descriptor remains alive on main.
The listener becomes nonblocking before it is moved to the connection worker.
No fallback listener is bound and no startup error creates a replacement log.

`engine::run_on_owner` wraps its fixture with `ImmediateCallbacks` and calls
`run_callback_on_owner`, which constructs `callback_engine_pair` on main and launches
exactly one scoped worker, named `hepta-d3-connections`, via Builder. OS thread
creation errors propagate without serving a connection. The runtime/owner can
be !Send; only `EngineThreadRuntime` and validated owned startup inputs move.
`BrowserActor` and its Rc-backed observer are created inside the worker on first
attested connection and remain there for their complete lifetime. Main pumps
one engine call at a time and never accesses actor/observer state.

The callback runner wakes main through a private latched condition variable,
cleared before draining events. Idle main has no periodic timer; pending calls
honor the callback owner's original deadline. The connection worker's idle
accept polling still uses a requested 5 ms park_timeout. Worker completion is
published before its wake; explicit join remains mandatory. This is not a
native input loop or real-time bound. See `D3_CALLBACK_SERVICE_RUNNER.md` for
callback driver, notification, immediate-backend and error-teardown details.

## Connection and process-birth continuity

`engine::accept_next` checks a one-way retirement signal before accepting and
again before returning a connection. A connection observed after retirement is
dropped. If accept races retirement, an accepted descriptor can exist briefly;
this is not a claim of atomic OS accept revocation. No additional request is
queued to a retired engine. Accepted streams explicitly switch to blocking mode
so existing AgentPort read/write deadlines remain effective.

For every connection, the service verifies the exact socket path, obtains real
SO_PEERCRED, and obtains a fresh pidfd-backed static-executable attestation.
The first snapshot is retained in SessionState. Every subsequent connection
must match PID, UID, GID AND the complete first PeerRuntimeSnapshot, including
start_time_ticks, cgroup, unit and executable digest. A recycled PID with the
same UID/GID/unit cannot inherit the previous session. A rejected mismatch does
not replace the snapshot, actor, engine endpoint or journal.

The request-scoped attestation retains its own pidfd and original executable
source. `handle_attested` now creates revocable custody propagated to the engine
queue; full identity is checked before and after backend work and before actor
return. `ensure_alive` is also called before the service returns its result. The added
snapshot is a continuity check, not a substitute for live attestation, semantic
principal binding or trusted-path custody. Static executable checking still
does not prove the bytes of a cross-UID live `/proc/<pid>/exe`. Attestation is
sampled at admission, engine entry/return and actor return; these samples are not
atomic with process exit or exec and cannot retroactively undo an effect.

## Request flow and lifetime

```text
systemd inherited listener -> bounded accept polling -> exact path / peer attestation
 -> complete first-snapshot continuity -> attach one actor and observer once
 -> canonical request / Requested / Dispatched -> actor principal + PageOwner gates
 -> one-slot EngineThreadRuntime -> callback owner -> ImmediateCallbacks
 -> main-thread AtomicFixtureRuntime
 -> actor transition / terminal receipt -> original response
 -> retirement gate -> quiescent managed rotation -> next connection
```

No new budget is assigned by the engine runner: the original request control
and deadline travel through the existing bridge. The daemon still permits one
request per connection and one active connection at a time. Managed journal
rotation still waits for a quiescent lifecycle and preserves actor, endpoint,
first process snapshot and all previous receipts. A consumed uncertain writer
is not replaced. Session-close ends a page, not the systemd listener lifetime.

## Shutdown and failure semantics

| Event | Service behavior |
| --- | --- |
| Invalid connection/identity before dispatch | Reject that connection; preserve original state |
| Ordinary policy denial from a healthy engine | Commit the ordinary failure receipt; keep the same pair |
| Callback owner Retired | Set retirement permanently and wake the worker; never recreate a pair |
| Idle listener during retirement | Poll exits without waiting for another client |
| In-flight codec/transport I/O | Existing absolute connection deadline still bounds protocol waits; no budget reset |
| Journal rotation error | Exit the worker, propagate the error, and drop the engine on main |
| Worker returns or panics | Wake main and explicitly join the scoped worker; no detached state |
| Backend blocks/non-cooperative wait | Cannot be preempted; main cannot pump retirement until it returns |

The runner returns only after joining its worker; R is dropped on the calling
thread during callback retirement, which may precede the join. The Rust panic hook can still log a panic payload. Only the returned
worker-panic error is fixed; this is not a process-wide panic-log redaction
policy. No global signal handler or restart policy changes; Restart=no remains.
The 5 ms poll and protocol budgets do not bound arbitrary filesystem/attestation
latency, OS scheduling, backend code, or Drop implementations.

## Configuration and operations

No configuration flag selects a second mode: this is the updated internal
implementation of the already opt-in persistent development binary. Existing
profile, marker, account, executable digest, socket and journal requirements
are unchanged. `--self-check --profile development` reports wiring only;
`engine_thread_dispatch_exercised=false` and `servo_adapter_exercised=false`
remain explicit. Ready output occurs inside the successfully started worker.

A process-identity mismatch requires ending the old session/service through its
existing operational procedure. Do not accept a new PID by editing a snapshot,
reset the journal, broaden account checks, or silently construct another engine.
An engine retirement requires inspecting the preserved receipt outcomes and
restarting only under the existing reviewed development procedure.

## Tests and acceptance

`sessiond/engine_tests.rs` exercises the actual private runner with an Rc-owned
backend, thread/drop identity, worker error/panic, backend panic, deadline
abandonment, idle-accept retirement, queued-connection refusal and blocking
stream I/O. `service_threaded_tests.rs` checks every first-snapshot field and
recycled-PID rejection. Its sequential control chain uses actual UnixStream,
SO_PEERCRED, authenticated transport, codec, actor, the daemon runner, the actual
AtomicFixtureRuntime implementation and a managed disk journal. An owner-local
wrapper verifies Dispatched exists before each backend call. Response digests
are compared to terminal records; stale-target denial does not recreate state.
Unit/cgroup/executable evidence there is a fixture, not independent attestation.
Existing managed-rotation tests keep an engine owner alive and exercise the new
endpoint-bearing SessionState. No test assertion or negative case is removed.

```sh
cargo test --locked -p hepta-d3-development --features development --bin hepta-agent-port-development-sessiond
cargo test --locked -p hepta-browser-actor --doc
python3 tools/validate_d3_development_profile.py
python3 -m unittest tests.test_d3_session_engine_runner -v
```

Full default/all-feature Rust, Python discovery, documentation, truth and
source-governance checks remain mandatory. Source mutation tests check local
function bodies and exact contract types but are not a semantic Rust parser or
formal proof. Real pidfd/systemd activation, kernel-backed retirement races,
new image qualification and native Servo control require their independent
producers and evidence; this source package does not promote D3 or later gates.

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
