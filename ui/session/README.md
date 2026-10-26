# trill-session and trill-ctl

Session owns host application processes and serves the bounded host IPC socket.
The CLI is a client of that socket. Shell does not own the application process
table or infer task completion from a window.

## Code and lifecycle

[main.rs](src/main.rs) owns spawn, kill requests, wait/reap, Session generation
and finite task retention. [hepta.rs](src/hepta.rs) manages the explicitly
configured read-only observer. [notes_bootstrap.rs](src/notes_bootstrap.rs)
handles the trusted parent's private Notes bootstrap v2, including separate effect and recovery descriptors. [deadline.rs](src/deadline.rs) supplies one monotonic deadline across partial reads and response writes. [ipc.rs](src/ipc.rs) advances bounded nonblocking peers without giving a reply a fresh deadline.

[objective_forwarder.rs](src/objective_forwarder.rs) moves the configured
Objective RPC onto one bounded FIFO worker. It holds no effect authority or
task state. The existing [bridge](src/objective_bridge.rs) still authenticates
the exact trusted endpoint and validates original-owner observations. A
separate typed local refusal lets the matching Shell release only a request
that Session definitely did not enqueue; an admitted transport retains its
original unknown-outcome rules.

The socket is under an absolute private XDG_RUNTIME_DIR. Both peers check
kernel-reported UID; same-UID hostile processes remain outside this prototype's
trust boundary. A Session restart creates a new generation. Detached tasks
must not be represented as reattached or successfully cancelled.

An accepted connection has one 500 ms I/O allowance; partial progress does not renew it. Each tick reaps exited children and advances at most 32 accepted peers with bounded reads and writes. An incomplete request or blocked reader cannot occupy the whole loop until its timeout. This bounds transport occupancy, not Linux scheduling or process-creation time. A lost response after dispatch leaves the real action outcome intact and requires a fresh snapshot. The startup advisory lock protects competing Session starters; it is not a credential. See [IPC scheduling](../../support/ui/SESSION_IPC.md) for exact limits and the real-binary regression.

Standalone Session does not install a production Hepta effect owner. The
private Notes bootstrap is separate from public Snapshot/Launch/Cancel.

The explicit `--notes-root-bootstrap-stdin` startup mode adds a trusted-parent
reservation barrier before the existing bootstrap v2. Session starts its actual
initial Notes target, retains both private descriptors, and sends only
`notes_target_reserved` metadata (schema version 1, actual target/destination,
fresh 128-bit nonce) over the inherited unnamed stdin datagram pair. It waits
at most 30 seconds for `activate_notes_bootstrap` matching all those values.
Only then does the unchanged two-descriptor Offer → Attached/Rejected exchange
begin its existing two-second deadline. Neither reservation nor activation is
an attachment ACK, grant, effect, or terminal receipt; wrong activation closes
the initial application's channels through the existing startup failure path.

The real Root launcher consumes that Reserved metadata, authenticates the held
Session process, registers the exact original Notes policy/lease and seals the
same target/nonce into its deployment descriptor. The original Agentd factory
sends Activate only after its real Root/MCP/recovered-writer startup is ready.
Root and Agentd consume the shared receiving endpoint in that order, never
concurrently. Root may authenticate Reserved with SO_PASSCRED enabled before
Session is spawned; it must disable that option after Reserved so the original
two-rights handoff receives no extra credential message. The old explicit
`--notes-bootstrap-stdin` direct mode and all effect deadlines remain unchanged.

The startup wire is defined in `ui/core/src/notes_startup.rs`. The Session tests
hold a real reservation longer than two seconds, prove no descriptors accompany
it, then complete the original handoff. A wrong nonce transfers no endpoints.
These are physical transport fixtures, separate from genuine Root policy and
whole-owner production execution evidence.

## Build, run and verify

Use [workspace setup](../README.md), then run trill-session and trill-shell
in the same owned graphical session. The CLI syntax is:

```text
trill-ctl snapshot
trill-ctl launch <personal|research|build> <notes|calculator|terminal>
trill-ctl cancel <task-id> <session-generation>
```

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-session --locked
```

[tests](tests/) exercise real process/socket lifecycle within their declared
scope. Use [HEPTA_OBSERVER](../../support/ui/HEPTA_OBSERVER.md),
[NOTES_ORGAN](../../support/ui/NOTES_ORGAN.md) and
[BOUNDARIES](../../support/ui/BOUNDARIES.md) when changing runtime integration.
