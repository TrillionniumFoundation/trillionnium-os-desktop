# Rust chat workspace and source-bound context

The default native Shell opens **Workspace / Chat**. Personal, Research and
Build each retain their own unsent composer, context attachments and selected
Tasks / Context / Console tab. Saved drafts are filtered by their workspace.
These labels organize the UI; they do not create OS security namespaces.

## User flow

1. Choose a workspace and write a local draft.
2. Open Notes or Calculator through the explicit host-app buttons. Session
   owns their processes and lifecycle. The Tasks tab displays the rows from
   the latest complete Session snapshot.
3. Use **Quote in draft** to attach an observed host task. **Save local draft**
   retains the text and reference together. It does not queue a Session
   operation, contact Hepta or generate an assistant response.
4. A saved card shows the immutable quoted capture and, when available, a
   separately labelled current observation. **Open task in workspace** selects
   the matching current task in the Context tab without leaving the chat.
5. The Context tab can quote a current read-only Hepta runtime source. The
   detailed runtime diagnostics are embedded there. This reference is not an
   association between the host task and a Hepta objective.
6. The Console tab displays observed host process records and volatile local
   notices beside the same conversation. It has no command input. The Shell
   launcher exposes Notes and Calculator; the existing restricted-terminal
   backend/CLI remains compatible with earlier host tests, but is not a new
   standalone Console entry in this workspace.

The Console process and notice regions have distinct stable scroll IDs,
scoped to the workspace and region. Scrolling one region preserves the
other region's position. Switching workspaces and returning restores each
workspace's two positions; rendering order does not serve as their identity.

The wide layout places chat and the workspace tabs side by side. A narrow
host window keeps the same state and exposes the tabs in an expandable panel.
This responsive layout does not establish an Android/mobile build or device
control qualification. `--page tasks`, `--page workspaces` and `--page console`
are legacy startup routes into this workspace. Explicit `--page hepta` and its
opt-in layout probe retain the separate diagnostic path used by existing gates.

## Rust modules and ownership

| Module | Responsibility | Source of truth |
| --- | --- | --- |
| `ui/core/src/conversation.rs` | `LocalDraft`, typed `ContextRef`, exact task/runtime source keys, validation and reference resolution | Immutable local quotes and independently supplied owner observations |
| `ui/core/src/observation.rs` | One pure predicate for source wall age and caller-supplied monotonic age | Caller-supplied clocks; no clock reads, lifecycle changes or IPC |
| `ui/shell/src/conversation.rs` | Per-workspace composer/tab state, bounded draft book, complete host snapshot cache, cards and embedded panels | Actual `Response::Snapshot` for current task rows; expired Hepta projection for runtime rows |
| `ui/shell/src/main.rs` | Actual response queue, expiry before every page, existing host launch/cancel transport | The independent Session, fenced by its observed instance |
| `ui/shell/src/hepta_panel.rs` | Runtime health, independent known-run card and one-shot health layout diagnostic | Read-only Session projections; runtime and known-run each use their own monotonic total-age bound and source wall-time check |
| `ui/shell/src/local_drafts.rs` | Private background v4 recovery, preserving v3 during migration; separate explicit v2 export/import and v1 compatibility | Local file content is historical input, never a live receipt |
| `ui/shell/src/draft_recovery.rs` | Renderer-independent open, queued snapshots, warning projection and normal-close drain | Existing `DraftBook` checkpoint and one background recovery writer |

Snapshot, Launch and Cancel retain their existing host lifecycle roles. The
separately configured [Objective bridge](../../ui/session/OBJECTIVE_BRIDGE.md)
adds bounded intent/status/cancel messages; the
[native text adapter](../../services/hepta-session-host/TEXT_SESSION.md) uses
the original Root/Agentd lane. Saving, quoting, navigating or importing local
context enters neither execution path and supplies no issuer, signed envelope
or grant. Session remains the host process owner; original Hepta owns execution.

## Identity, history and current observations

`HostTaskKey = (session_instance, task_id)`. Session task numbers restart after
a Session replacement, so task number alone is not a reference. A matching
reference must also retain the quoted workspace and app kind. A new Session
with the same task number cannot reopen/rebind the old card. If a task has
fallen out of the bounded current snapshot, the UI reports an unknown outcome;
absence does not imply completion or cancellation.

A Hepta reference records the observing Session, original agent ID, spawn
generation and process ID. Normal current-generation/lifecycle advancement
within that source may update its current observation. A changed Session,
agent/spawn or process keeps the quote historical. Host task IDs never serve
as Hepta objective IDs, and runtime readiness is not AI task completion.

Every quote retains the capture made when it was attached. Later card updates
do not rewrite that capture. Imported captures can have been edited in a local
file: schema validation is not authentication. They initially carry no live
status; an independently received current snapshot with the exact source key
is necessary to resolve the card. Displaying or selecting that reference
does not authorize an operation.

## Shared freshness rule

The Shell consumes queued responses, samples its clocks, expires observations
and only then paints any page. Bridge records actual IPC receipt before queue
delivery; dequeue does not create a new receipt time. Host task rows require
both source wall age and local receipt age to be at most **7,000 ms**. Runtime
health and known-run observations each require a separate complete monotonic
age bound at most **7,000 ms**, as described below, as well as a valid source
wall age. At **7,001 ms** the respective view is stale. Missing/future local
receipt times and missing/future source samples are unknown, never zero-age
success.

For host task rows, the source clock is
`Response::Snapshot.resources.sampled_unix_ms`; the row's
`TaskRecord.updated_unix_ms` records the last lifecycle change and is not a
freshness clock. A task can remain Running for hours while snapshots are
current. `HostObservation` keeps a separate bounded copy of the complete
snapshot rows and their receipt time. `Response::Task` may report an action
result but cannot update this cache, renew every row or recover stale status.
Only a later complete Snapshot can do that; clock recovery alone cannot.

For Hepta runtime health, Session records the beginning of the complete
successful poll and exposes its advancing age in `runtime_sample_clock`,
alongside a nonzero successful-read sequence. Shell adds the full IPC round
trip and elapsed time since actual receipt. The **sum** must remain at most
7,000 ms; `sampled_unix_ms` also remains subject to the source wall-time check.
Wall-clock rollback, failed polls and independent known-run reads cannot
renew the runtime sample. Repeated snapshots of the same successful sequence
retain the larger advancing age bound; same-Session missing history cannot
reset it. Missing or invalid clock metadata leaves history unknown.

The complete last observation, original attempt timestamp and rule that only
Observed is downgraded remain in place. Existing non-Observed diagnostics are
retained; new clock failures have their documented error codes. The actual
visible state and optional Hepta layout marker use the same predicate.
Session, Shell and ctl require matching builds from compatible source: a new Shell treats
older runtime history without the clock as unknown, while older strict
decoders reject the new field. A current observation is not a compositor
frame, device effect or owner-completion receipt.

The optional known-run card has an independent total-age bound. Session
reports the retained run sample's monotonic age at snapshot creation, rounded
up to milliseconds. Shell adds the full IPC round trip and elapsed time after
actual receipt; their **sum** must remain at most 7,000 ms, and source wall age
must also pass. The full round trip is a conservative transfer bound. Repeated
snapshots of the same run read retain the larger advancing bound, without
renewing the sample or repeatedly adding overlapping round trips. Health
updates do not renew run observations. Missing age is unknown, and a null
run projection cannot prove non-admission, completion or cancellation.
See [the known-run contract](HEPTA_OBSERVER.md#observe-one-already-known-run)
and [the total-age specification](../../ui/shell/OBSERVATION_FRESHNESS.md#independently-sampled-known-run).

## Local storage and bounds

Automatic all-workspace recovery uses the v4 checkpoint contract in
[PRODUCT](PRODUCT.md#upgrade-rollback-and-uninstall), including its 64 MiB
bound, principal partitions, migration, single-writer lock and close behavior.
The v1/v2 files below are separate explicit exports with their own 4 MiB bound.

The draft book has a global limit of 127 saved drafts. Each draft has at most
16 KiB of UTF-8 text and eight context references. Full/oversized/duplicate
attempts preserve earlier drafts, all unsent text and existing references.
Switching workspaces does not silently export, submit or discard text.

Explicit export writes `local-context-drafts-v2.json` beneath the existing
`$XDG_STATE_HOME/trillionnium-ui` state directory (or the existing HOME
fallback). The typed schema is `{version: 2, drafts: [{workspace, text,
contexts}]}`. Export includes all workspaces and refuses while **any**
workspace has unsaved text or context, so a backup cannot silently omit them.
No live/current flag, operation, grant or authority object is serialized.

The existing 0700 directory, 0600 regular file, final-component no-follow,
nonblocking open followed by a regular-file descriptor check, 4 MiB bound,
create-new temporary file, atomic rename and durability checks
are shared by both schemas. Import requires an entirely empty in-memory
draft book and all composers empty. It prefers v2. Only true v2 absence permits
legacy `local-drafts-v1.json` import; corrupted, oversized, insecure or symlink
v2 files cannot trigger fallback. Legacy text has no workspace or references,
so explicit import assigns it to the currently selected workspace. The old
v1 file is not deleted or rewritten by a v2 export.

## Validation and evidence boundary

The Rust regression suite covers same-numbered tasks across Session changes,
missing/pruned tasks, metadata mismatch, independent Hepta source changes,
workspace isolation of unsent text, lossless Unicode/context serialization,
capacity/duplicate preservation, strict unknown-field refusal and legacy
import with corrupt-v2 refusal. The full existing draft/IME pointer-safety
and R6 visible-freshness regressions remain present.

`workspace_context_tests` consumes synthetic messages through the real
Desktop response queue and pre-paint expiry path, renders actual egui text,
and clicks the actual Quote / Save / Context / Console widgets. It requires
the host operation queue to remain empty and verifies that an action reply
cannot freshen a delayed complete snapshot. These are in-process contract
tests, not original-Agentd execution or presented pixels.

Console regressions render both overflowing regions through that same
workspace path. They place the pointer inside a clipped visible row, deliver
real egui wheel events, check that the other region's painted row and vertical
position stay unchanged, then switch workspaces and verify restoration.
Another check enables egui's ID warnings and refuses a painted ScrollArea
collision. Neither test injects scroll state or compares generated ID strings.

The actual Desktop import regression creates a private 0600 FIFO with no
writer and requires rejection within two seconds, no fallback to an existing
v1 file, an unchanged empty draft book and an empty operation queue. A RED
timeout is cleaned up by opening only that owned FIFO's nonblocking writer
after the failed deadline, then joining the reader. This cleanup cannot count
as a successful no-writer rejection. Normal regular v2 imports and true
v2-absence legacy imports remain separate positive controls.

Run the pinned UI workspace tests, strict Clippy, formatter and native binary
build with the commands in [RUN.md](RUN.md). Record the exact source, command,
toolchain, raw exit result and binary hashes for any actual execution. New
native pixel/IME qualification must use newly built source-bound binaries.
The current `x11-ime-client.py` finish oracle checks v2 text/context export;
changing that oracle alone does not qualify a new IME run. The R6
[original Session/Shell captures](../../tests/ui/evidence/2026-10-17-original-hepta-shell/README.md)
and [freshness RED/GREEN evidence](../../tests/ui/evidence/2026-10-17-observation-freshness/README.md)
retain their recorded sources and scopes.
