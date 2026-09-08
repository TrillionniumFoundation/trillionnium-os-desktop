# Engine-thread dispatch boundary

**Plan:** `2026-08-29-d6`<br>
**Gate:** `D3-01`<br>
**Status:** source candidate, host integration tested only<br>
**Contract:** `contracts/engine-thread-dispatch.v1.json`

## Purpose and non-claims

`hepta_browser_actor::engine_dispatch` connects the existing synchronous
`PageRuntime` boundary to an engine instance which must stay on its creating
thread. It lets a socket/actor worker request one bounded engine operation while
an independently driven native event loop owns and pumps the engine. This is an
in-process Rust scheduling mechanism, not a new wire protocol or a process IPC.

There is no Servo adapter in this module. An engine accepting an action must
still resolve, retain, and revalidate a real node in one engine-owned operation.
Copying `PageOwnerSnapshot` into the queue conveys the actor's expectations, not
proof of the engine's live document, frame, node, or mutation epoch. The existing
`ATOMIC_SEMANTIC_RESOLVER.md` requirements remain mandatory.

The persistent D3 development daemon now uses this scheduler with its existing
AtomicFixtureRuntime; see `D3_SESSION_ENGINE_RUNNER.md` for the actual runner,
startup, shutdown and complete process-birth continuity. The headed Servo
experiment is NOT switched. Product installation, markers, sockets, credentials,
input locks, Servo patch ledger, and production authorization are unchanged.
Passing host tests does not close D3, D2I, D4-D9, or integrated-main gates.

## Types, ownership, and call direction

`engine_thread_pair(runtime, waker)` is called on the engine event-loop thread.
It returns an `EngineThreadRuntime` port and an `EngineThreadOwner<R>`. The port
implements `PageRuntime` and may be moved to the actor worker. The owner keeps R
on the constructing thread and is deliberately neither Send nor Sync, even
when R itself would be Send. Thus an Rc/RefCell-backed engine is supported
without an unsafe Send implementation, a second WebView, or sharing its handle.

The constructor does not spawn any threads. The caller supplies the event loop
and an `Arc<dyn EngineEventLoopWaker>`. The waker must post an event and return
promptly; it may not wait for the actor, call back synchronously into it, or pump
recursively. A blocking waker or non-cooperative engine is a trusted adapter bug,
not a problem this mechanism can preempt.

The intended call direction is:

```text
connected AF_UNIX request -> canonical codec -> principal/PageOwner admission
 -> durable Requested and Dispatched facts -> EngineThreadRuntime
 -> one-slot typed queue -> EngineThreadOwner::pump_one on its creating thread
 -> engine PageRuntime hook -> bounded private reply channel
 -> actor transition -> canonical response -> durable terminal fact -> transport
```

The existing AgentPort observer's Dispatched fact precedes entry to the actor;
it is conservative about whether the backend actually began an operation. This
scheduler adds no claim that a queued request has already mutated a real page.

## Admission and resource limits

The port is non-cloneable and requires mutable access. Exactly one request and
one per-request reply slot exist. Sending uses `try_send`, never a blocking
capacity wait. An unexpected full queue closes the pair instead of retrying.
Every call has a fresh private response channel, so a late result cannot be
matched to a later request even when callers reuse textual IDs. Journal ID
uniqueness remains independently enforced by the receipt layer.

Before copying owner identifiers, preflight checks the original shared control,
owner thread identity, request ID, and bounded local PageOwner fields. Calls
from the creating engine thread are rejected to avoid synchronous self-deadlock.
The existing Browser API codec validates and bounds the typed operation before
queueing. The bridge accepts only ephemeral profile creation and loopback HTTP
navigation, consistent with D3's frozen local-only policy. A reserved create
session ID is transported separately because it is assigned by the actor, not
by a wire caller. Wait duration must be exactly representable in milliseconds;
it is not rounded or given a new deadline.

The backend receives an owned, bounded copy of the expected PageOwner, including
its full revision tuple, control state, and human lease. It must check its own
live state before effects. Backend success data is checked with the bounded
canonical JSON encoder without first recursively cloning it. Actor and
AgentPort envelope limits are additional, sometimes narrower, checks. Bounds
on accepted messages are not memory or CPU isolation of code inside R.

`RuntimeFailure::Internal` text from the backend is replaced with a fixed
non-sensitive diagnostic. This prevents ordinary error results from copying
page data into responses or receipts. The process-wide Rust panic hook is not
controlled by this module; engine panic logging must have its own privacy policy.

## Atomic action routing

An ordinary `BrowserActorMessage::Act` is always rejected. The dedicated
`dispatch_page_act` port method creates the only PageAct queue item. The owner
routes that item directly to `R::dispatch_page_act`; it never synthesizes a
coordinate action, generic Act, selector fallback, or a second resolve/act call.
A backend with the default unsupported hook remains unsupported through the
bridge. These are routing guarantees, not proof that a backend's DOM algorithm
is correct.

## Deadline, cancellation, and failure state machine

The actor's original monotonic `Instant` and shared cancellation token are
preserved. Queueing does not reset the clock and the bridge does not consult the
wall clock. The waiting thread polls cancellation with at most a 5 ms requested
receive interval; this is not a real-time scheduling guarantee. Controls are
checked before enqueue, immediately before backend entry, after return/encoding,
and before delivering the result to the actor.

| Event | Backend may have acted? | Result and future admission |
|---|---|---|
| Invalid request, owner, profile, or same-thread call | No bridge dispatch | Pure preflight rejection; pair remains usable |
| Unsupported atomic hook or explicit policy denial | Backend promises no effect | Error returned; pair remains usable |
| Cancellation/deadline while queued | Not after abandonment is observed | Queue is revoked; pair permanently closed |
| Cancellation/deadline after backend entry | Yes | Shared cancellation requested; late reply discarded; pair permanently closed |
| Owner loss, waker panic, backend panic, internal error | Unknown/conservative | Pair permanently closed; no automatic retry |
| Full queue, lost result receiver, malformed result | Unknown/conservative | Pair permanently closed; no successful replacement response |
| Valid result on live pair and active control | Per engine result | Original private reply returned once |

A drop guard revokes the original token and closes the pair when an enqueued
wait exits abnormally, including unwinding. Closing does not execute Close on a
possibly stuck backend, undo an action, or kill a thread. The owner must be
retired/cleaned up on its own thread by an external reviewed lifecycle path.
A new pair is not an authorization to recreate a second hidden WebView.

`pump_one()` never waits for queue data and invokes at most one backend hook.
`Replied` means a result (success OR error) was sent, not that an action passed.
`Discarded` and `Closed` must not be converted into retries. Native events must
be processed between pumps. Long waits inside an engine hook still require
bounded/cooperative engine work; this API alone does not guarantee UI latency.

## Executable host integration and evidence

`src/engine_dispatch/tests.rs` covers thread affinity using an Rc-owned backend,
self-deadlock rejection, action routing, one-slot admission, control expiry,
queued and running cancellation, owner/client loss, panic handling, late replies,
codec limits, private diagnostic redaction, and safe policy-denied follow-ups.
Rustdoc compile-fail tests check the owner's negative Send and Sync contracts.

`src/engine_dispatch/transport_tests.rs` exercises actual UnixStream pairs,
SO_PEERCRED, the authenticated transport handshake, canonical request/response
encoding, BrowserActor, this scheduler, and a real disk journal. Before every
backend call it reads the journal and requires Requested then Dispatched. The
success corpus creates, observes, performs one fixture action, rejects a consumed
target and foreign session, and closes. Every response digest is compared to
the durable terminal record. A stalled navigation corpus returns no response
and records Indeterminate, with PageOwner entering Recovering. A principal-tuple
mismatch reaches no engine call.

The engine nodes, executable digest and systemd-unit facts in these tests are
explicit fixtures. No systemd activation, real web page, Servo, new image,
physical hardware, network service, production effect, or signing is exercised.

Run from the repository root with the locked Rust 1.93.0 toolchain:

```sh
cargo test --locked -p hepta-browser-actor engine_dispatch -- --test-threads=16
cargo test --locked -p hepta-browser-actor --doc
python3 -m unittest tests.test_engine_thread_dispatch_contract -v
```

The normal workspace/default/all-feature suites remain required. Integration
and documentation changes invalidate exact-source D3 evidence. The Python
contract checks protect source wiring; they are not substitutes for Rust tests,
engine semantics, independent review, or exact-image qualification.

## Servo integration and remaining work

A future reviewed package must construct a real fixed-pin Servo backend on the
native event-loop thread, implement all live-node operations, bind native human
input to the same PageOwner, and service engine events/requests without blocking
the UI. Engine termination, callback reentrancy, document changes between enqueue
and dispatch, and retained-node invalidation need actual engine tests. The
product process topology also needs a separately attested process-IPC adapter;
this in-process channel is not that adapter.

No Servo pin/patch changes, production activation, or gate promotion is made by
this source package. Independent security review and the complete exact-image
principal/dispatch/receipt/cancellation/recovery corpus remain open.

## Request-scoped identity across queueing

`AttestedPeer::request_custody` retains the original pidfd and identity source for
one handler lifecycle. All queued RequestControl copies share a revocable
verifier; original attestor selection, engine entry/return and final actor return
are rechecked. Identity loss never becomes a confirmed success or replayable
refusal after an uncertain effect. See
`docs/architecture/REQUEST_PEER_CUSTODY.md` and
`contracts/request-peer-custody.v1.json` for APIs, configuration, failure and
resource limits. No production activation or actual Servo proof is introduced.

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
