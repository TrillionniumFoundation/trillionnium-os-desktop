# D3 callback-capable development service runner

**Plan:** `2026-08-29-d6`<br>
**Gate:** `D3-01`<br>
**Status:** source candidate; local host execution only<br>
**Contract:** `contracts/d3-callback-service-runner.v1.json`

## Scope and non-claims

The persistent development daemon now routes its actual service path through
`run_on_owner -> run_callback_on_owner -> callback_engine_pair`. Its production
activation defaults, socket paths, installation, peer policy, wire format and
receipt format do not change. The backend remains `AtomicFixtureRuntime`, an
immediate deterministic local fixture. This is not a Servo adapter, winit event
loop, systemd activation test, installed-image qualification or release proof.
The older single-connection daemon is not changed.

The new runner supports deferred host callbacks for testing and integration
work. An actual winit application must retain its own native `run_app` loop and
pump `CallbackEngineOwner` there; sleeping this host runner on a condition
variable is NOT a replacement for the platform's window event loop. No native
window, clipboard, new listener, new thread per request or external effect is
created by this change. D2I/D3 and later promotion gates remain open.

## APIs and original request control

`ImmediateCallbacks<R: PageRuntime>` is a public opt-in bridge in
`engine_dispatch::event_loop`. It calls the original immediate backend with the
same borrowed RequestControl, including deadline, cancellation and peer custody.
It does not turn blocking code into asynchronous code. Generic Act is refused;
`start_page_act` delegates only to `dispatch_page_act`. Retirement takes and drops
the backend once on the owner's thread, never invokes another action, and does
not imply that a native shutdown or external rollback completed.

The daemon-private `run_callback_on_owner(runtime, advance, work)` creates the
callback owner on its calling thread and launches one named scoped connection
worker. `advance` services already-ready host events and returns its next
absolute timer, or None. It stays on the owner thread, must return promptly and
must not block awaiting the actor worker or recursively pump the runner. Tests
use it to complete queued fixture operations on a later turn. The default
immediate bridge has no independent event source and returns no timer.

One request and one completion remain bounded by the existing callback pair.
The one non-cloneable actor endpoint, first-peer snapshot, request custody and
journal observer remain on the worker. No PageOwner is reconstructed from a
receipt; no additional request or deadline is synthesized by the runner.

## Notification and wait algorithm

A private `Mutex<bool>` and `Condvar` own the main-thread wake state. Request
queueing, completion, retirement and worker exit latch the bit before notifying.
There is no arbitrary backend code while that mutex is held. Unrelated code
calling thread::park cannot consume this private notification.

Each cycle clears notifications BEFORE draining ready driver events and pumping
the callback owner. A notification arriving during or after that drain remains
latched, so the wait returns without sleeping. Old, duplicate or coalesced
notifications do not authorize an operation. The condition wait loops on its
predicate, tolerates spurious notifications and always recomputes duration from
the original absolute Instant. It never clears the bit after the drain.

The wait deadline is the earlier of the event driver's existing absolute timer
and `CallbackEngineOwner::next_wake_deadline`. While an operation is pending,
that owner still requests its original deadline or cancellation check. There
is no periodic main-thread polling while idle; the worker's inherited-listener
accept loop still uses the existing requested 5 ms check. Neither is a real-time
bound on OS scheduling, mutex acquisition, backend code, procfs I/O or destructors.

The worker guard publishes `finished=true` with Release BEFORE notifying; main
reads it with Acquire before waiting. `JoinHandle::is_finished` is not used as
this predicate, since a final closure guard can run before that handle reports
completion. Explicit join still occurs, including final thread unwinding.

Rust's park/unpark documentation describes the separate per-thread token and
the risk of unrelated code consuming it. This private predicate avoids depending
on that token in the main runner; it is not a general claim about all primitives.
Reference: [Rust park documentation](https://doc.rust-lang.org/std/thread/fn.park.html).

## Failure, retirement and teardown

| Event | Required result |
| --- | --- |
| Callback pending | Service driver yields; no repeated start or fabricated reply |
| Callback result | Existing owner checks bounds and full request identity before actor delivery |
| Original deadline or cancellation | Retire callback owner, discard late result, retain facts-only receipt semantics |
| Driver returns error or panics | Fixed returned diagnostic; retire owner and stop worker before explicit join |
| Worker returns/error/panics | Publish finished before wake; retire owner and join; no detached worker |
| Wake-state mutex poisoned | Fail closed, retain poison, wake if necessary; never recreate state silently |
| Backend already retired | Do not advance driver or create a replacement backend |
| Idle accepted connection races retirement | Existing stop checks apply; no claim of atomic OS accept revocation |

Retire is idempotent. It invalidates callback tickets before backend cleanup.
An immediate bridge may therefore drop its R BEFORE the worker has finished
joining, but only on the creator thread. This is safe because the worker owns
no reference to R; the runner returns only after the join. The event-driver
closure itself is dropped as the runner returns. A native integration must
release its own registrations; storing a ticket elsewhere cannot revive it.

Worker protocol I/O retains its existing deadlines. The runner cannot forcibly
interrupt arbitrary code, filesystem I/O, a blocking backend or a destructor.
The Rust panic hook may print a panic payload despite the fixed returned error;
no global panic-hook or signal-handler changes are made.

## Configuration and operation

There are no new environment variables, arguments, features, dependencies,
installation entries, default activation markers or public APIs for fault
injection. Existing development profile, marker, inherited FD and root-owned
executable checks remain mandatory. Restart=no is unchanged. Self-check and
ready output identify `callback_service_runner_wired=true`, while
`callback_service_runner_exercised=false` and `servo_adapter_exercised=false`
remain explicit. A readiness field is not a test result.

## Tests, reproducibility and invalidation

`callback_runner_tests.rs` covers later-turn completion, original deadline,
callback cancellation, driver failure/panic, worker exit/panic, notification
coalescing, unrelated parking, poison, spurious condition notification, absolute
timer selection and the finished-before-notify predicate. Actual service-state
transport tests run both immediate and deferred fixture paths, each checking
five UnixStream/SO_PEERCRED/handshake/codec requests and fifteen receipt records,
including old-target rejection and unchanged response digests. These service
fixtures use the compatibility actor handler and synthetic unit facts; they do
not constitute live attested-service, Servo, systemd or image proof. The separate
existing attested callback/transport suites remain mandatory in the full matrix.

```sh
cargo test --locked -p hepta-d3-development --features development --bin hepta-agent-port-development-sessiond
cargo test --locked -p hepta-browser-actor --lib
python3 tools/validate_d3_development_profile.py
python3 -m unittest tests.test_callback_service_runner -v
```

The module/component registries, three affected workflow trigger inventories
and D0C-05/D0C-06/D3 invalidation inputs include this contract, documentation,
audit and tests. Function-local mutation checks are regression guards, not a
formal Rust proof. No source/host test or local artifact can promote exact-image,
independent-review, fixed-hardware or signing status.
