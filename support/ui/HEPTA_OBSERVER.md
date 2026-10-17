# Host Session → Hepta read-only observer

This slice connects the Rust host Session to the existing Hepta Agentd v2
control endpoint. The native Shell renders the resulting typed metadata.
Conversation remains a local draft: authenticated objective submission has
not been assembled. A successful observation is not an AI task result or
a device-effect receipt.

## Ownership and fixed sources

The candidate is stacked on A10 commit
`f093fb3d5e97156e3bdd13fae06d1a3860d874b1`. It consumes A07's
`services/hepta-os` crate, `hepta-os-observer`, whose upstream contract is
pinned to Hepta commit `f8c9419df6ddeb36ff8b522a50219981fb8d9345`.
See that crate's `UPSTREAM_CONTRACT.json` and development notes for the
exact upstream source hashes and supported read protocol.

| Component | Responsibility | Excluded authority |
| --- | --- | --- |
| A07 `services/hepta-os` | Validate the fixed v2 responses, peer credentials, identity, generation, request correlation and event cursor | No generic RPC, objective ingress, run creation, cancellation, terminal write or effect ledger |
| A10 `ui/session/src/hepta.rs` | Explicit launcher configuration, one background observer, bounded volatile display cache | No AuthBus signing, synthesized D/K IDs or HOS2 budget |
| A10 `ui/core/src/hepta.rs` | Serializable read-only Session → Shell projection | No Agentd path, raw event payload or transport method |
| A10 `ui/shell/src/hepta_panel.rs` | Connection state, last successful observation and recent event metadata | No renderer-side Agentd connection or task submission |

The Session's existing host application lifecycle is separate. Host process
IDs and exits still describe the owned Notes/Calculator/Terminal processes,
not Hepta operations. Existing drafts are not uploaded or replayed when the
observer reconnects.

## Runtime path and status semantics

The host Session starts at most one worker after validating its explicit
configuration. The worker calls A07's blocking facade on its own thread.
Each poll reads health, capabilities, a bounded event page, and a closing
health check inside a five-second total deadline. These reads are not an
atomic owner snapshot. The facade validates all replies against the expected
AgentId and spawn generation, the lifecycle's current generation, and the
same kernel-observed peer PID within that poll. The pinned Agentd advances
current generation from `spawn` while starting, to `spawn + 1` while running,
and `spawn + 2` while draining; the spawn identity itself remains fixed.

The Session polls at a one-second interval after each attempt. Only the
worker waits for Agentd; the Session event loop uses `try_recv` on a one-slot
channel and continues to reap applications and answer host IPC. A receiver
backlog cannot become an unbounded event journal. No transport error is
converted into a success.

| State | Meaning |
| --- | --- |
| `not_observed` | No supported projection has arrived, including an older Session snapshot |
| `not_configured` | This Session has no observer endpoint configuration |
| `connecting` | Configuration was accepted and the first complete poll is pending |
| `observed` | The latest complete poll was validated; displayed runtime health can still be not ready |
| `unavailable` | Configuration/connection/validation failed before any successful observation; current runtime state is unknown |
| `stale` | A prior successful observation is retained, but the latest attempt or the host Session transport failed; current runtime state is unknown |

If the worker stops or gives no update for seven seconds, the Session marks
the view unavailable or stale. If Shell stops receiving Session snapshots
for seven seconds, it separately marks its Hepta view stale. Losing host
IPC marks it stale immediately after the bounded request fails. Restarting
the Session creates a new view; it never claims to recover complete history.

The displayed metadata is limited to 16 capabilities and the last 16 event
entries, with 96-byte strings, control characters, bidi overrides/isolates,
direction markers and Unicode line separators stripped before truncation.
A forged right-to-left or line-break event label must never visually impersonate
trusted readiness/fencing/permission state. Ordinary Chinese/Arabic/Emoji
characters remain displayable. Truncated strings are never used as authority
identifiers. Advertised capabilities
are labels and version observations, not callable permissions. Raw event
payloads, workspace/home/run paths, objective text and arbitrary owner
errors do not cross into the renderer. The host IPC retains its 64 KiB
frame limit and existing fail-closed oversized-snapshot error.

`next_cursor` advances only to the last complete event returned by the
facade. Empty pages do not jump ahead. A detected history gap stays marked
for the lifetime of the Session view. If the owner reports the read cursor
ahead of retained history, the worker resets this read cursor to zero and
keeps the gap warning. This is a read resynchronization, not an objective
retry. A changed runtime PID or spawn generation invalidates the previous
event window and is visibly recorded. Normal promotion/draining changes
current generation while retaining the same source and bounded event window.
This cache is volatile and cannot replace
Hepta's durable operation ledger.

## Configure and run on a Linux host

Use the fixed host CI toolchain and the lockfile (see `RUN.md` for the
separate repository nightly development toolchain):

```sh
cargo +1.88.0 build --manifest-path ui/Cargo.toml --workspace --bins --locked
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-ui-core -p trill-session --locked
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-shell --locked
```

The runtime remains the existing Linux host prototype. Follow `RUN.md` for
the private `XDG_RUNTIME_DIR`, compositor, fonts, and host graphics libraries.
The observer adds no new graphics backend or mobile adapter.

Get all four configuration values from the trusted Hepta supervisor/launcher
record. Do not discover a random socket, infer a generation from a response,
or create an AgentId locally. The expected AgentId is the exact upstream
UUID format; the generation is a nonzero integer and UID is a Linux UID.

| Session-only environment variable | Value from the supervisor |
| --- | --- |
| `TRILL_HEPTA_AGENTD_SOCKET` | Absolute private Agentd control socket path |
| `TRILL_HEPTA_AGENT_ID` | Expected AgentId |
| `TRILL_HEPTA_SPAWN_GENERATION` | Expected spawn generation |
| `TRILL_HEPTA_PEER_UID` | Expected Linux peer UID |

For example, after the launcher has populated the `OWNER_*` values:

```sh
TRILL_HEPTA_AGENTD_SOCKET="${OWNER_AGENTD_SOCKET:?}" \
TRILL_HEPTA_AGENT_ID="${OWNER_AGENT_ID:?}" \
TRILL_HEPTA_SPAWN_GENERATION="${OWNER_SPAWN_GENERATION:?}" \
TRILL_HEPTA_PEER_UID="${OWNER_PEER_UID:?}" \
  ui/target/debug/trill-session
```

Apply this environment to the Session process only. In another terminal with
the same private `XDG_RUNTIME_DIR`, start `ui/target/debug/trill-shell`, then
open **Hepta / Runtime**. `ui/target/debug/trill-ctl snapshot` also returns
the same projection under `hepta`. If `CARGO_TARGET_DIR` is set, use the
corresponding binary directory instead of `ui/target/debug`.

`trill-shell --page hepta` opens the runtime page directly. Normal startup
still opens Conversation. An additional explicit `--hepta-layout-probe`
prints exactly one `TRILL_HEPTA_LAYOUT_V1` JSON line to stdout after that page
has completed an egui widget update while the Session is connected and the
projection is `observed`. Both the last snapshot receipt and its runtime
sample must be no older than seven seconds. The line binds the displayed
AgentId, spawn/current generations, PID and sample timestamp. No endpoint,
payload or objective text is logged. It is a layout diagnostic, not proof
of compositor presentation or an executed operation.

With all four variables absent, host applications and drafts continue to
work and the Hepta view says `NOT CONFIGURED`. Partial or malformed
configuration fails closed. Endpoint changes require a Session restart;
there is no renderer endpoint editor. The Session removes these four
configuration variables before spawning its child applications.

This is an application architecture boundary. The existing private socket
permissions and `SO_PEERCRED` check do not isolate malicious processes
sharing the same UID and do not provide cryptographic Hepta authentication.
A05/A07 must supply the trusted launcher configuration and any stronger
cross-domain process boundary.

The IPC schema changed additively. The new Shell can read an older snapshot
as `NOT OBSERVED`; an older strict Shell may reject a new snapshot. Deploy
the Session, Shell and `trill-ctl` built from the same source together.

## Validation and limits

`ui/session/tests/hepta_observer.rs` runs the real Session executable and
private Unix IPC. It checks the unconfigured default, rejects renderer
objective/generic-RPC messages, and puts a deliberately stalled private Unix
peer behind the observer. During the five-second timeout, snapshots and
host action dispatch must remain responsive; no Hepta success is inferred.
The stalled peer is an explicit fault fixture, not a successful Agentd run.

The blocking host gate also runs `tests/ui/probe-hepta-session.py`, which
starts the actual Session binary and A07's scripted fixed-v2 Unix fixture.
It verifies successful bounded projection, rejection of renderer write
messages, then stale-state retention and responsive host dispatch after
stopping the fixture. Its JSON evidence explicitly records
`upstream_agentd_started: false`, `objective_submitted: false` and
`device_effect_tested: false`. To reproduce just this gate after building:

```sh
python3 tests/ui/probe-hepta-session.py \
  --session ui/target/debug/trill-session \
  --output ui/target/a10/session-observer-probe.json
```

The default fixture lives at `tests/integration/hepta/agentd_fixture.py`
and is owned by A07. This requires real host Unix sockets; an invocation
denied `AF_UNIX` by a sandbox is blocked, not a passed probe.

The Weston gate also runs `tests/ui/probe-hepta-wayland.py`. It starts the
actual Session and Shell plus the explicitly scripted A07 Unix fixture,
passes observer configuration only to Session, and requires the specific
fresh Hepta-page marker. The ordinary Conversation first-layout marker is
insufficient. It compares the layout identity/generation/PID to a live
Session snapshot and the fixture process, and retains binary/source hashes,
JSON evidence and raw logs even on failure. With an existing test compositor:

```sh
python3 tests/ui/probe-hepta-wayland.py \
  --binaries "${CARGO_TARGET_DIR:-$PWD/ui/target}/debug" \
  --output "${RUNNER_TEMP:?}/hepta-layout-new-run"
```

The output directory must be new or empty. This gate reports
`scripted_socket_fixture_hepta_page_layout_not_daemon` and explicitly sets
upstream Agentd, objective/device effects and compositor pixel presentation
to unverified. It cannot substitute for the original-daemon acceptance below.

Projection tests cover bounded metadata, JSON frame size with a full host
task view, stale evidence retention, sticky gaps and source-change window
invalidation. Existing Session peer-UID, lifecycle, reconnect, draft and
renderer-input tests remain independent gates. A07's tests separately own
fixed v2 wire fixtures and source-contract verification.

For an actual Agentd acceptance run, record the upstream SHA, AgentId,
generation, peer identity, successful projection, and its timestamp. Stop
or disconnect that Agentd and verify stale/unknown state while host apps
continue. A protocol fixture does not satisfy that acceptance by itself.
An observed runtime does not satisfy AuthBus objective submission,
trusted permission prompts, HOS2 device effects, target-kernel graphics,
CJK/IME, Android/iOS or physical-device acceptance.

The next write-side step belongs to A07/A05: assemble the existing
`AuthBusObjectiveIngress` with its authorized signing/owner context, then
expose a narrow typed submission interface with owner-issued receipt
identity and uncertain-delivery reconciliation. Do not turn the local
composer, event metadata or a provider message into a success receipt.
