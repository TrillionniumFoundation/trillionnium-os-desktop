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

After dispatch, the connection retains only its serialized response. A blocked
reader cannot redispatch the command. A response that cannot be fully delivered
before expiry does not roll back a possible action or prove that nothing
happened. Clients obtain a fresh observation through the existing owner API;
they do not automatically replay a mutating request.

An incomplete peer or blocked response no longer occupies the sole state owner
until its timeout. The loop remains synchronous while a parsed command runs:
process creation, kernel scheduling and the configured Objective bridge's
existing bounded exchange are outside a hard real-time guarantee. The per-peer
I/O allowance and bounded connection count are not authentication between
mutually hostile processes sharing a UID.

### Remaining synchronous Objective queue delay

`ObjectiveBridge::request` still performs its fixed authenticated exchange on
the Session thread with `Runtime::block_on` and a 150 ms timeout. Four accepted
`ObjectiveAvailability` requests whose configured endpoint accepts but does
not reply can therefore occupy that thread for approximately 600 ms. A ready
snapshot accepted behind them can exhaust its original 500 ms allowance before
dispatch and close without a response. This is a source-level, reproducible
failure case for slow parsed requests; the partial-input and blocked-output
regressions do not establish fairness for every business request.

The isolated diagnostic below uses the actual Session binary and a private
synthetic endpoint, checks the kernel peer PID/UID, and forwards only read-only
availability commands. A barrier snapshot proves the affected connections
were accepted before the four requests are sent. It records the binary digest,
actual bridge call count, snapshot closure and recovery under the same Session
generation with no tasks. Exit zero means this limitation was reproduced; it
is not a product acceptance gate or evidence about a deployed original owner.

```sh
python3 tests/ui/reproduce-objective-ipc-delay.py ui/target/debug/trill-session
```

Actual UI/gateway acceptance must measure this behavior with the configured
original host and real concurrent read traffic. Until that evidence exists,
Notes refresh and Session responsiveness under a slow original host remain an
open product risk. This diagnostic neither changes the original owner/writer
nor submits, cancels or automatically repeats an effect.

## Development and regression evidence

From the repository root:

```sh
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-session --locked
cargo +1.96.0 build --manifest-path ui/Cargo.toml -p trill-session --bins --locked
python3 tests/ui/test-session-fairness.py ui/target/debug/trill-session
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

See [Session development](../../ui/session/README.md), [Notes organ](NOTES_ORGAN.md),
[Notes durability](NOTES_DURABILITY.md) and [integration boundaries](INTEGRATION_CONTRACTS.md).
