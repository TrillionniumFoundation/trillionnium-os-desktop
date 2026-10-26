# Session host IPC scheduling and deadlines

## Owner and wire contract

The existing `trill-session` process owns application launch, cancellation
requests, exit observation and bounded task retention. The public newline JSON
request/response schemas, strict field validation, Session generation fencing
and kernel-reported same-UID checks remain in use. Public host IPC does not
issue a grant or export the private Notes effect/recovery descriptors. The
original typed Objective bridge retains its configured trusted endpoint and
the original Hepta owner retains effect authorization and terminal outcomes.

| Source | Responsibility |
| --- | --- |
| `ui/core/src/lib.rs` | Bounded frames, strict public schemas and client helpers |
| `ui/session/src/main.rs` | Application lifecycle, generation and single state owner |
| `ui/session/src/ipc.rs` | Bounded nonblocking peer scheduling and response buffering |
| `ui/session/src/deadline.rs` | One monotonic allowance shared by request and response I/O |
| `ui/session/src/objective_bridge.rs` | Existing typed requests to the configured original owner |
| `ui/session/src/objective_forwarder.rs` | One bounded FIFO transport worker and disposable reply tickets |
| `ui/session/src/notes_bootstrap.rs` | Trusted-parent bootstrap v2, separate private effect and recovery channels |

## Fair service within explicit bounds

Each owner tick refreshes child lifecycle state, advances each accepted peer
once, refreshes again, then accepts at most eight new peers. The outer loop
sleeps 10 ms. At most 32 accepted connections are retained. A peer performs at
most one 8192-byte read and one 8192-byte write per tick; request and reply frames
retain the shared 64 KiB bound. When capacity is full, additional connections
remain subject to the kernel listen backlog until an accepted slot is free.

The existing **single 500 ms deadline** starts at acceptance and covers the
whole request and response. Partial input does not renew it; preparing a reply
does not grant a new deadline. The transport checks time after successful reads
and before dispatch, and checks the same allowance before and after writes.
An expired request cannot begin a launch, cancellation or Objective forwarding.
EOF without a complete newline-terminated frame cannot make a request valid.

After local dispatch, the connection retains its serialized response. An
Objective request instead retains one disposable reply receiver until its
transport completes, then retains its serialized response. Neither state
re-reads or redispatches the command. A response that cannot be fully delivered
before expiry does not roll back a possible action or prove that nothing
happened. Clients obtain a fresh observation through the existing owner API;
they do not automatically replay a mutating request.

An incomplete peer, blocked response or slow Objective endpoint does not occupy
the sole lifecycle owner until its timeout. Local process creation, bounded
response serialization and kernel scheduling remain outside a hard real-time
guarantee. The per-peer I/O allowance and bounded connection count are not
authentication between mutually hostile processes sharing a UID.

## Objective transport ordering and uncertainty

One worker executes Objective RPCs serially, with at most one additional queued
command. Accepted commands preserve FIFO forwarding order. Validation failure,
an unavailable local worker, and `try_send` refusal produce a separate
`objective_transport_rejected` response before that command is enqueued. Its
typed request kind/intent ID, reason and Session generation are transport
backpressure, not an original-owner `NotSent` or cancellation terminal. The
worker holds no task state, effect authority, recovery ledger or new owner.
Configured socket ownership/mode, kernel UID/PID and typed response identity
checks remain in the existing bridge.

The original 150 ms RPC bound is clipped to the accepted connection's original
500 ms deadline. Queue wait consumes that same outer allowance. The worker
checks expiry and abandonment before starting and again immediately before
first-write admission. Dropping a pending connection, observing a Linux full
peer hangup, or stopping Session abandons transport that has not won that
admission race. A legitimate request-side half-close can still receive its
reply. Other Unix platforms retain the same expiry and explicit-drop checks.

After first-write admission, the original owner may already have received a
mutation. A client disconnect or missing reply cannot prove cancellation or
rollback: submission remains `SubmitUnknown`, cancellation remains `Unknown`,
and no automatic replay occurs. A valid owner response is forwarded unchanged,
including exact Notes document observations. The host loop continues local
snapshot service, process cancellation and actual child reaping while waiting.

The shared Shell bridge retains the original request kind, ID, expected Session
and a nonwrapping local RPC sequence with each reply. Only a matching transport
refusal releases the corresponding pending UI mutation; duplicate or old
generation receipts cannot release a later cancel attempt. A refused Submit
keeps its original ID and draft as a disposable local view. Fresh availability
and the normal draft checks are still required before a user can explicitly
start another intent. Owner retention/publication/run evidence overrides any
local refusal assumption. Ordinary owner `Capacity`, status absence and lost
replies never become this local refusal and never trigger automatic replay.
The new response variant is used by the matching Session/Shell product pair;
request schemas and original Objective observation schemas remain unchanged.

### Historical synchronous delay and retained regression

On the frozen `f36664310b7bb0074a16846f2c1c600e90844f05` baseline, the
bridge ran four successive 150 ms exchanges on the Session thread. The actual
isolated binary reproduced a snapshot reset after 617.7 ms, with four observed
availability calls and the same Session generation recovering afterward.
The partial-input regression alone did not cover that parsed-request failure.

The bounded worker above removes that inline wait. The same read-only case is
retained in `reproduce-objective-ipc-delay.py`: its default mode verifies the
old failure; `--expect responsive` requires the changed binary to serve the
snapshot within its original allowance and return typed bounded replies.
A barrier proves all affected peers were accepted before the requests start.
Neither mode starts an original owner, app task or effect, and neither is
production authority qualification. Deployment acceptance still requires the
configured original host and actual concurrent UI/gateway traffic.

## Development and regression evidence

From the repository root:

```sh
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-session --locked
cargo +1.96.0 build --manifest-path ui/Cargo.toml -p trill-session --bins --locked
python3 tests/ui/test-session-fairness.py ui/target/debug/trill-session
python3 tests/ui/reproduce-objective-ipc-delay.py ui/target/debug/trill-session --expect responsive
```

Use the corresponding binary directory when `CARGO_TARGET_DIR` is configured.
The existing deadline, stale generation, malformed schema, expiry-before-launch
and child-reaping tests drive the same nonblocking connection implementation as
the production loop. Additional tests exercise a pending input peer and blocked
response together with another snapshot and an actual child exit, response
budget preservation, EOF, frame size and one request per connection.

The Python regression launches only its own isolated Session, proves a snapshot
completes while another request is incomplete, then checks service behind 32
idle peers. It asserts one unchanged Session generation and no dispatched task,
and is included in `tests/ui/check-host.sh`. These are Linux host transport and
lifecycle checks; compositor, physical device and original-owner end-to-end
qualification remain separate gates.

The Objective diagnostic retains the same isolated, read-only slow endpoint
case used before this change. Its default `--expect serialized` reproduces the
old snapshot expiry; `--expect responsive` requires a snapshot within its
original allowance and bounded typed backpressure replies. Neither launches
an original owner or effect. Rust regressions additionally exercise actual
socket FIFO/at-most-once mutation forwarding, queue expiry/abandonment, worker
shutdown uncertainty, exact reply retention under backpressure, half-close
handling and a real owned child exit during a pending Objective exchange.
The core golden `tests/ui/objective-transport-rejection-v1.json` and shared
Shell Notes regressions additionally exercise correlated Submit/Cancel refusal,
fresh manual retry, duplicate receipts, stale generation and owner evidence.

See [Session development](../../ui/session/README.md), [Notes organ](NOTES_ORGAN.md),
[Notes durability](NOTES_DURABILITY.md) and [integration boundaries](INTEGRATION_CONTRACTS.md).
