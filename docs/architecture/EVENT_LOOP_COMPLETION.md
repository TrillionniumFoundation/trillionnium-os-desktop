# Callback completion for an event-driven engine owner

## Purpose and non-claims

This D3 source candidate closes a scheduling prerequisite for a native event
loop: the engine-owner thread can initiate work and return to native events
before a result exists. It is not a Servo adapter, retained-node resolver,
process IPC, installed-image result, hardware qualification, or release proof.
The persistent development daemon still selects its synchronous
AtomicFixtureRuntime runner. Production AgentPort and all effect/release gates
are unchanged.

At the locked Servo revision `670ae8a70801b162e186f81cbb5bdd2d59c39108`,
`components/servo/webview.rs` exposes load requests and delegate callbacks. A
synchronous dispatch that waits for such a callback on the same thread would
prevent that thread from advancing the engine loop. The Servo embedding guide
requires the embedder to call `Servo::spin_event_loop` in response to its waker.
This package supplies the missing callback-shaped scheduling boundary without
claiming that an engine's ordinary accessibility or input APIs implement D3's
atomic current-node action contract.

Upstream references: the exact pinned
[WebView source](https://github.com/servo/servo/blob/670ae8a70801b162e186f81cbb5bdd2d59c39108/components/servo/webview.rs)
and the [Servo embedding API guide](https://doc.servo.org/servo/).
The guide is background, not a replacement for the repository's immutable pin.

## Public API and ownership

`hepta_browser_actor::engine_dispatch::event_loop` exports:

| Item | Responsibility |
| --- | --- |
| `callback_engine_pair(runtime, waker)` | Construct a request endpoint and callback owner on the current thread. No thread, timer, window, listener or engine is created. |
| `CallbackPageRuntime::start` | Initiate a bounded ordinary operation, retain its completion, and return without waiting for a native callback. |
| `CallbackPageRuntime::start_page_act` | Separate semantic action initiation; default Unsupported. A real adapter must retain/revalidate/act atomically at the actual engine boundary. |
| `CallbackPageRuntime::retire` | Promptly detach callback registrations and drop retained state; never retry, navigate or create a replacement engine. |
| `CallbackEngineOwner::pump_one` | Start at most one operation or consume one ready callback result. It never waits on a response channel. |
| `CallbackEngineOwner::next_wake_deadline` | Request a native timer while a callback is outstanding; never renew the original operation deadline. |
| `CallbackEngineOwner::retire` | Permanently close the pair, invalidate callbacks, discard queued work and run cleanup at most once. |
| `EngineCompletion` | Unforgeable, non-Clone, consuming return address for one call; contains no engine or DOM pointer. |
| `EngineCompletion::complete` | Consume the token and queue one bounded success/refusal/failure. Queued is not delivered or durably journaled. |
| `request_id`, `deadline`, `ensure_active`, `ensure_current_peer` | Read the token's original bounded identity/deadline and recheck its still-live request authority. |

The owner contains `PhantomData<Rc<()>>` and cannot be Send or Sync even when its
backend is Send/Sync. Backend construction, start and retirement stay on the
creator thread. Completion tokens may be sent across threads because they own
only control/channel state, not a native object. Only trusted backend code
receives tokens; page content and Agent callers never select a completion ID.
The request endpoint is the existing non-cloneable EngineThreadRuntime.

## Native loop integration sequence

1. Construct the callback owner on the native/Servo owner thread. Move only the
   request endpoint to the actor worker. Keep native engine state on its owner.
2. The existing endpoint enqueues one typed request and schedules a waker event.
3. On that event, call `pump_one`. It validates the request-scoped process
   identity, installs one active call, then invokes start. The backend registers
   a native callback and returns; it must not recursively pump the application.
4. Process ordinary native input, rendering and engine events. Advance Servo's
   event loop in the embedder, not by synchronously waiting in start.
5. In the callback, recheck the completion's current identity and the backend's
   own live PageOwner/node/revisions before any actual action. Call complete
   only after the result or refusal is known. Completion schedules a wake.
6. Pump again to validate the result and full request identity and deliver it
   to the actor. Existing actor/AgentPort code writes terminal or indeterminate
   facts and controls transport response commitment.

While Pending, schedule the native loop to wake no later than
`next_wake_deadline()`: the minimum of the original Instant and a requested
5 ms cancellation-check interval. This interval is not a real-time guarantee.
The application must both process wake events and honor this timer; constructing
this library does not install a scheduler. Never spin pump_one as a substitute
for native events. Wakes are hints and may be duplicated or coalesced.

The request endpoint now also wakes on wait abandonment and Drop. Consequently
an old test assumption that every wake means a new request is invalid; tests now
assert exact backend-call inventories separately from retirement wakes. A
polling development runner was already able to notice closure; this change is
required for a dormant, event-driven owner and is not a claim that the existing
polling daemon was deadlocked.

## Bounds and single-use completion

There is one request queue slot, one active call, and one completion slot per
call. The single non-cloneable endpoint serializes normal callers. Unexpected
request-queue saturation closes the pair without waiting or retrying. Both
synchronous and callback owners reuse one ordinary-message mapping and the
canonical Browser API codec. Generic Act has no ordinary representation.

Complete consumes its token. Duplicate completion is a Rust move error; no
public constructor or Clone implementation exposes another sender. Every call
has a fresh channel, so even identical request IDs cannot redirect a stale
completion to a later request. Identity/permission is not inferred from a
request ID, callback wake or expected PageOwner snapshot.

Results are bounded before entering the completion channel and again on the
owner's final path; oversized canonical JSON and non-local URLs fail closed.
Internal error strings returned through this API are replaced by a fixed
message. Panics are converted to failure but the application's Rust panic hook
may still run and log its payload. This package does not change global panic
hooks or claim panic-output redaction.

## Failure and retirement state machine

| Situation | Outcome |
| --- | --- |
| Preflight refusal before enqueue | Existing endpoint semantics; no backend invocation. |
| Pending operation, native callback not ready | Pending; no repeat start and no reply. |
| Inline completion during start | Active state already exists; one bounded reply can be consumed safely. |
| PolicyDenied / Unsupported callback result | Valid only for a side-effect-free backend refusal; pair may remain usable. |
| Callback token lost without completion | BrowserCrashed, never a successful empty object. |
| Cancellation, deadline, peer revocation, internal error or backend panic | Retire pair; existing actor classifies potentially effectful work as indeterminate. |
| Identity changes after a callback queued success | Full owner-side refresh refuses the buffered success. |
| Endpoint closes or owner is explicitly retired/dropped | Invalidate all old callback tokens and discard queued work; cleanup at most once. |
| Late callback | Retired or ReceiverGone; cannot satisfy another request. |
| Waker panics | Catch unwind, retire relevant pair; it remains closed even if no wake can be delivered. |

Retirement never means an external effect was undone. It cannot force an engine
that ignores cancellation to stop. The backend must detach native registrations
and check token validity at its eventual action boundary. Peer verification and
JSON validation are synchronous work; no hard upper bound or forced preemption
of that work is claimed. The mechanism has no power to make process exec/exit,
node changes, or asynchronous native callbacks atomic with those checks.

## Executable host tests

`event_loop_tests.rs` covers yielding until a later callback, inline completion,
cross-thread completion, single-use channels, creator-thread lifecycle, queue
cancellation, original deadlines, callback loss, explicit retirement, ordinary
Act refusal, the distinct atomic hook, bounded replies, diagnostic handling,
waker/backend failures and identity changes before and after callback completion.
Rustdoc tests reject Clone, double consumption and Send/Sync owner movement;
a positive example proves external API construction compiles.

`event_loop_transport_tests.rs` executes actual UnixStream/SO_PEERCRED,
authenticated transport, canonical codec, handle_attested, BrowserActor, callback
queues and disk journal. Four deferred operations produce twelve checked receipt
records; native fixture events run between start and completion. A second
create/navigation corpus produces six records and rejects execution-after-
identity-change as Indeterminate with no fabricated success/outcome digest.
Procfs identity material and the native/page engine are fixtures. These tests do
not run a Servo, winit or systemd event loop and are not exact-image evidence.

Run the locked workspace default/all-feature matrices and
`cargo test --locked -p hepta-browser-actor --doc`. Python tests exercise strict
contract types, source routing/order mutations, wait-free owner structure,
inventories and workflow invalidation. Structural checks are regression guards,
not a formal proof of Rust semantics or a substitute for native integration.

## Configuration, compatibility and remaining work

This is a new opt-in constructor/trait, not a new Cargo feature, environment
selector, executable, IPC protocol or installation profile. The old constructor
and public PageRuntime trait are compatible. Old event-loop integrations must
treat wake notifications as hints and handle closure, not assume wake==request.
All original time, request, journal, capacity and production bounds remain.

A real Servo adapter, atomic retained-node operation, native callback wiring,
attested process IPC, exact-image tests and independent security review remain
required. D2I/D3 and later gates stay open. Do not replace this contract's
source/host claim with a completed Servo claim or switch production activation.


## Persistent development service bridge

The persistent development daemon now uses `callback_engine_pair` through
`run_callback_on_owner`. Its backend remains the immediate AtomicFixtureRuntime,
wrapped explicitly in `ImmediateCallbacks<R>`; original control is passed by
reference and ordinary Act has no fallback. A private latched condition-variable
runner handles host events and original timers. Deferred fixture tests exercise
this exact runner, but no winit or Servo loop is installed. See
`D3_CALLBACK_SERVICE_RUNNER.md`; a real native application must still retain its
own native loop rather than blocking it in this host runner.
