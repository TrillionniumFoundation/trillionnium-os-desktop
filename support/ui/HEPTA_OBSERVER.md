# Host Session → Hepta read-only observer

This slice connects the Rust host Session to the existing Hepta Agentd v2
control endpoint. The native Shell renders the resulting typed metadata.
Conversation remains a local draft, with no Shell submission command. The
separate default-off [trusted ObjectiveStart command](../../services/hepta-os/OBJECTIVE_TRANSPORT.md#trusted-single-attempt-command)
can carry a pre-existing issuer envelope to the original owner. Session and
Shell receive only read-only observations. A successful observation is not
an AI task result or a device-effect receipt.

## Ownership and fixed sources

The candidate is stacked on A10 commit
`f093fb3d5e97156e3bdd13fae06d1a3860d874b1`. It consumes A07's
`services/hepta-os` crate, `hepta-os-observer`, whose upstream contract is
pinned to Hepta commit `f8c9419df6ddeb36ff8b522a50219981fb8d9345`.
See that crate's `UPSTREAM_CONTRACT.json` and development notes for the
exact upstream source hashes and supported read protocol.

| Component | Responsibility | Excluded authority |
| --- | --- | --- |
| A07 `services/hepta-os` default observer profile | Validate the fixed v2 responses, peer credentials, identity, generation, request correlation and event cursor | No generic RPC, objective ingress, run creation, cancellation, terminal write or effect ledger in this read-only profile |
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

The Session polls at a one-second interval after each iteration. Only the
worker waits for Agentd; the Session event loop uses `try_recv` on a two-slot
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

Session records the complete runtime poll's monotonic start and conservative
`sampled_unix_ms` before its first health read. Only a validated success
advances the runtime success sequence; `last_attempt_unix_ms` records the
attempt's completion separately. Failed attempts and known-run reads do not
advance the successful runtime sequence or retimestamp its original clock.

Each snapshot with runtime history includes `hepta.runtime_sample_clock`
containing `observation_sequence` and `sample_age_at_snapshot_ms`. This age
runs from the complete poll's start to snapshot creation, rounded up to
milliseconds. The Session expires an over-seven-second or invalid successful
sample. Shell separately bounds the sum of that source age, the whole IPC
round trip and time since actual transport receipt, while also rejecting an
expired/future source wall timestamp. Wall-clock rollback cannot renew an
old sample. Same-source repeated frames preserve the larger advancing bound,
without repeatedly adding overlapping round trips. The source includes
Session instance, original AgentId, spawn generation and process PID; normal
current-generation lifecycle changes do not reset it. Same-Session missing
history cannot erase an earlier successful clock.

Losing host IPC marks the view stale immediately after the bounded request
fails. A lost worker preserves existing history as stale; a first poll that
remains connecting beyond seven seconds becomes unavailable. Restarting the
Session creates a new view; it never claims to recover complete history.
All expiry paths preserve any
retained owner observation and the original attempt timestamp.

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
cargo +1.96.0 build --manifest-path ui/Cargo.toml --workspace --bins --locked
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-ui-core -p trill-session --locked
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-shell --locked
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
| `TRILL_HEPTA_RUN_ID` (optional) | One exact, already-known run ID; requires all four endpoint values |

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
projection is `observed`. Its runtime total monotonic age bound and source
wall age must each be no older than seven seconds. The line binds the displayed
AgentId, spawn/current generations, PID and sample timestamp. No endpoint,
payload or objective text is logged. It is a layout diagnostic, not proof
of compositor presentation or an executed operation.

With all five variables absent, host applications and drafts continue to
work and the Hepta view says `NOT CONFIGURED`. Partial or malformed
configuration fails closed. Endpoint changes require a Session restart;
there is no renderer endpoint editor. The Session removes these five
configuration variables before spawning its child applications.

This is an application architecture boundary. The existing private socket
permissions and `SO_PEERCRED` check do not isolate malicious processes
sharing the same UID and do not provide cryptographic Hepta authentication.
A05/A07 must supply the trusted launcher configuration and any stronger
cross-domain process boundary.

The IPC schema changed additively. Older snapshots without any Hepta view
remain `NOT OBSERVED`. A snapshot with runtime history but no
`runtime_sample_clock` parses in the new Shell and becomes stale/unknown;
absence is never a zero-age success. New snapshots add this clock even when
no known run is configured. An older strict decoder rejects the added field.
Deploy Session, Shell and `trill-ctl` built from matching source together;
strict unknown-field rejection remains enabled.

## Observe one already-known run

The trusted launcher may additionally set `TRILL_HEPTA_RUN_ID` to a run ID
it already knows from the original owner. The exact grammar is 1–128 ASCII
bytes from `[A-Za-z0-9._:-]`. Empty, non-UTF-8, whitespace, path-like or
overlong values fail closed before a worker or socket connection is created.
The ID is neither trimmed nor synthesized from a host task number. It is
displayed in full, independently of the 96-byte event-text display bound.

All four existing endpoint values remain mandatory when the run ID is set.
Apply all five variables only to Session, for example by adding
`TRILL_HEPTA_RUN_ID="${OWNER_KNOWN_RUN_ID:?}"` to the launcher command above.
This does not connect the local draft composer to any submission path. The
Session has no signing, cancellation, terminal acknowledgment, submission
retry, run discovery or durable run ledger API.

The same bounded worker first completes the runtime poll and publishes its
health sample. It then calls the existing typed `ObserverClient::run_status`
for that single configured ID. This is an independent health → run status →
health read with the facade's five-second total deadline and peer/identity/
generation checks. No new worker is created per read. The Session event loop
continues to serve snapshots and host actions while either read is pending.

With the run variable absent, `hepta.run` is omitted entirely. The independent
runtime clock is still included when runtime history exists. With a run
configured, older strict decoders also cannot read the additional run field;
matching Session, Shell and `trill-ctl` builds are required in both cases.
The exact additional structure is:

```json
{
  "run_id": "known:run-1",
  "connection": "observed",
  "last_attempt_unix_ms": 1792300000000,
  "error_code": null,
  "last_observation": {
    "sampled_unix_ms": 1792300000000,
    "observation_sequence": 1,
    "run_id": "known:run-1",
    "revision": 4,
    "phase": "indeterminate",
    "authority_epoch": 9,
    "generation": 6,
    "terminal_observed": false,
    "idempotent": false
  },
  "sample_age_at_snapshot_ms": 1,
  "observation_gap": false
}
```

| Run connection state | Meaning |
| --- | --- |
| `connecting` | The first complete read for the exact known ID is pending |
| `observed` | A fresh, validated typed run observation is available |
| `projection_missing` | `run_status` returned null: only the owner's current in-memory projection lacks the ID; admission and durable outcome remain unknown |
| `unavailable` | No successful run sample has been received and observation is unavailable |
| `stale` | A previous run sample is retained, but current state is unknown after failure, transport loss or expiry |

Null, old-spawn rejection and disconnection preserve `last_observation`.
After any interruption following a successful read, `observation_gap` stays
true for this Session. A first null response has no previous sample and
keeps that flag false; this is not evidence of complete owner history.
If runtime polling fails before the next run read, the run's last-attempt
timestamp also stays unchanged. A fresh health poll alone never restores a
stale or missing run to `observed`.

The seven owner fields are copied from the facade's `RunObservation`.
`generation` belongs to the run receipt and may differ from the current
daemon generation. A preceding runtime health PID is not attached to the
run as though the run API had returned it. `terminal_observed` states only
what the original owner observed; neither it nor `phase` proves that a
desktop, mobile or other device effect completed.

`sampled_unix_ms` and the nonwrapping `observation_sequence` belong to this
Session's successful reads, not the owner's operation revision or an
admission receipt. Run sampling time is conservatively bound to the start
of the completed `run_status` call; `last_attempt_unix_ms` records its
completion. The closing health check's delay therefore counts toward the
run payload's age. Health and run reads carry separate monotonic times
through the bounded delivery channel. Run success or delay cannot renew
the health sample. Session expires each run sample independently after
seven seconds, checks source wall-clock age and rejects future timestamps.
For each snapshot with run history, Session also reports
`sample_age_at_snapshot_ms`: the sample's independent monotonic age when
forming that snapshot, rounded **up** to milliseconds. This changing age is
outside `last_observation`, so retained history and its attempt timestamp
remain intact. Before any successful run sample, the age field is omitted.
A consumer receiving an observed run from an older producer without this
field must treat its freshness as unknown; deploy the matching binaries.

Shell's IPC worker records request start and actual transport return before
sending into the response queue. Its run age bound is the Session sample
age **plus the full IPC round trip plus the time after transport receipt**.
The full round trip conservatively bounds the unmeasured transfer from the
Session snapshot to Shell; it adds up to one round trip of conservative age
in addition to the sub-millisecond upward rounding.
The combined bound must be at most 7,000 ms, not merely each component
separately. A bound over 7,000 ms, invalid/missing time, or a future source
wall timestamp makes current state unknown. This also protects the first
queued frame when the wall clock has rolled back to just after its sample.

Shell keeps an age anchor for each
`(session_instance, run_id, observation_sequence)`. For a repeated sample,
it retains the larger of the old bound advanced to the new receipt and the
new source-age-plus-round-trip bound. This cannot rejuvenate the sample and
does not repeatedly add overlapping round trips. A higher successful-read
sequence or an explicit new Session/run source starts a new age bound.
Runtime health uses the same total-age arithmetic with its own independent
successful sample and source identity. Neither projection can renew the
other's clock. See `ui/shell/OBSERVATION_FRESHNESS.md` for the exact source
bindings, wire compatibility and regressions.

The **Hepta / Runtime** page displays an independent known-run card even
when only stale run history remains. It shows the exact run ID, original
phase/revision/generation/authority epoch and owner terminal observation.
It neither creates a `HostTask` nor upgrades a local draft into a submitted
objective. The existing `TRILL_HEPTA_LAYOUT_V1` marker still describes only
runtime health; it does not certify this card or a run outcome.

## Validation and limits

`ui/session/tests/hepta_observer.rs` runs the real Session executable and
private Unix IPC. It checks the unconfigured default, rejects renderer
objective/generic-RPC messages, and puts a deliberately stalled private Unix
peer behind the observer. During the five-second timeout, snapshots and
host action dispatch must remain responsive; no Hepta success is inferred.
The stalled peer is an explicit fault fixture, not a successful Agentd run.

`ui/session/tests/hepta_run.rs` runs the actual Session against a scripted
fixed-v2 UDS peer. It verifies a full 128-byte selected ID, typed owner-only
projection, null and old-spawn history retention, omitted run data with the
independent runtime clock, and responsive host dispatch during held runtime
and run reads. A slow successful runtime poll must report its complete read
age. A delayed successful run read must retain the earlier runtime sample,
attempt timestamp and success sequence exactly. Two later failed runtime
polls preserve the complete runtime history and success sequence while its
monotonic age continues to advance.
Session and Shell tests independently cover the 7,000/7,001 ms boundary,
monotonic expiry, clock rollback, queued samples and repeated snapshots.
Runtime and configured-run regressions also check rounded source age, a first
queued frame across rollback, a combined age over the limit when every
component is below it, and preservation of the advancing bound without
double counting round trips. Runtime cases additionally cover source changes,
same-Session missing history, missing clock metadata and visible/layout
agreement. A bounded channel handshake checks actual Bridge timestamp
ordering without a scheduling sleep. The real Session UDS fixture checks
that a held run read contributes at least its hold time to the reported age.
An egui runtime-page test checks the visible run fields and unknown-state
wording. These are scripted host and widget tests, separate from the
original-owner results recorded below.

The cancellation lifecycle regression uses an already-built Rust test child
and a private, bounded UDS readiness handshake. It exercises the ordinary
Session ownership and SIGKILL/reap path, without creating and immediately
executing a temporary shell script during parallel tests. It retains the
`Running → CancelRequested → Cancelled` assertions and checks the exact
owned child PID before cancellation. The command selection exists only
under `cfg(test)`; production application arguments are unchanged. This
removes the script-execution fixture hazard identified while investigating
CI job `117592973270`, whose original log proves spawn failure but does not
record its errno. It does not establish that ETXTBSY caused that failure.

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

The [original-owner continuous Session/Shell gate](ORIGINAL_HEPTA_SHELL.md)
adds six held phases to A07's real original probe: Starting, Running,
Draining, old-spawn stale, explicit trusted Session replacement and stopped
stale. A10 keeps one native Shell alive and captures six actual X11 frames
with same-process Session snapshots before and after each capture. The
first-layout marker remains one-shot; all six images require independent
visual review. An acknowledgment file coordinates the lifecycle and is not
a renderer or original-runtime receipt.

## Recorded original-owner run projection

The [R8 ObjectiveStart and desktop result](../../results/integration/2026-10-18-objective-desktop/README.md)
records the separate trusted-host ingress qualification and a known run
observed through the real Session and one continuous native Shell. Its three
held phases are a compiled run projected as admitted, old-endpoint rejection
with unchanged run history, and an explicitly replaced Session whose current
owner projection lacks that same run ID. The latter remains unknown even
when durable admission is established separately by the original owner.

The source-bound capture includes actual Session snapshots before and after
each frame. Stale history preserves the run sample and attempt timestamp
while its independent age advances. Replacement null has no prior sample,
omits sample age and retains gap=false. These are observations of the
original owner; no host task is synthesized from the run ID.

Those frames qualify the English Runtime card on a private Linux X11 display.
The Chinese suffix in the submission-unavailable label has missing glyphs,
so they do not qualify CJK fonts or IME. Their owner phase and terminal flag
also do not qualify model execution, HOS2 or desktop/mobile device effects.
The R6 six-phase capture and the scripted fixture results above retain their
own original source and execution scope.

## Next production issuer and provider handoff

The independent `hepta-submit` path already targets the pinned compiled
`state_control → objective_runtime::ObjectiveRuntimeHost::submit` entry.
The next A07/A05 step is to connect the existing production AuthBus issuer
and its trusted provider/launcher to that boundary, including the original
owner's recovery contract. The local draft composer remains unsent until an
explicitly designed and authorized application handoff exists.

The trusted caller must retain the original raw signed envelope before
starting the command, supply its exact endpoint/agent/spawn/UID/PID/request
identity, close stdin, and bound the whole child process lifetime. Structural
parsing does not authenticate the input; issuer trust, signatures, replay,
expiry, profile and durable publication remain with the original owners.
An interrupted process or missing/partial stdout preserves uncertainty.
Read-only `run_status: null` cannot reconcile it into non-admission, and a
new spawn or fresh signature is not an automatic retry mechanism. Preserve
intent through the original recovery contract without adding a UI or Session
submission ledger.

For observation, the launcher can pass one already-known run ID and the four
explicit observer endpoint values to Session as documented above. A provider
message, readiness label or local draft cannot serve as an owner-issued
admission receipt or a device-effect receipt.
The undeclared `objective_ingress.rs` file is not the compiled Agentd entry;
see A07's [fixed-source review](../../tests/integration/hepta/LIVE_SOURCE_REVIEW.md).
