# Original Objective signed-request inbox

This Linux host slice adds a separate **Signed requests** page to the real
Shell. A trusted launcher supplies existing signed envelopes and an exact
original Hepta Agentd connection. The renderer can inspect an entry, explicitly
submit it once, or query its original admission history. It cannot sign local
conversation drafts, change an envelope, select a control endpoint, invoke a
shell, issue FinalUse authority, or manufacture a task ledger.

Normal Session startup has no configured inbox and cannot submit. The crate
includes the existing `hepta-os-observer/objective-history` client feature;
that compile-time inclusion does not supply a producer, trust configuration,
endpoint, or production issuer. A deployed original issuer is still required.
The qualification fixture uses a fresh isolated test signing key outside the
Shell and Session. Its admission grants no device authority and starts no
model turn.

## Product flow and ownership

1. The launcher obtains a complete original `AuthBusObjectiveIngress` from its
   trusted producer and writes the exact compact UTF-8 JSON bytes into a private
   file. The current test producer is not a production signing service.
2. Session starts with `--objective-config-fd N`, taking an inherited regular
   file descriptor, setting close-on-exec, and validating the config below.
   No environment discovery or public IPC configuration is supported.
3. Shell lists only entry IDs and bounded claimed metadata. Selecting an entry
   shows its `body.source_envelope_json` as plain, untrusted **content claimed
   by the signed envelope**. Authentication is decided by the original owner.
4. A primary-pointer click after the review checkbox selects that fixed entry.
   This review is UX, not an additional authorization issuer. The existing
   same-UID host IPC domain is not an adversarial process boundary.
5. Before opening the original transport, Session atomically persists the exact
   raw envelope in a one-way client attempt marker. The existing
   `ObjectiveTransport::submit_once` performs one original `ObjectiveStart`.
   Original AgentId, spawn generation, peer UID/PID, signed identity and reply
   bindings are checked by the existing client and original owner.
6. `ObjectiveHistoryClient::query_once` uses `ObjectiveAdmission` and the same
   retained original envelope. An absent or unverifiable result is Unknown.
   History does not resend the signed request or create effect authority.

Local conversation drafts retain their existing local save/import/export flow.
They are never inserted into the supplied envelope or reported as submitted.
Admission means the original owner published admission, not that a model ran
or a device action finished. A historical publication likewise does not mean a
current run was resumed.

## Trusted startup configuration

The config descriptor must be at least 3, regular, current-UID owned, mode
0600, and at most 16 KiB. It cannot alias inherited X11 or cookie descriptors.
The config has exactly these fields:

```json
{
  "schema_version": 1,
  "owner": {
    "socket_path": "/absolute/original/control.sock",
    "agent_id": "33333333-3333-4333-8333-333333333333",
    "spawn_generation": 1,
    "peer_uid": 1000,
    "peer_pid": 1234
  },
  "retention_dir": "/absolute/private/client-attempts",
  "entries": [{
    "id": "provided-request",
    "envelope_path": "/absolute/private/provided.json",
    "submit_request_id": 101,
    "history_request_id": 102
  }]
}
```

There are 1–8 entries. IDs are 1–32 ASCII alphanumeric, `_`, or `-`; IDs,
request IDs, original attempt identities and raw-envelope hashes must be unique. Request IDs are positive.
Envelope files are regular, current-UID owned, mode 0600, have one hard link,
and reside in an owned 0700 directory. Path components are opened with
`O_NOFOLLOW`; relative paths, symlinks and nonregular files fail closed. Original
wire validation bounds the signed source to 32 KiB and checks its exact schema.
Session also verifies that the resulting selected-detail response fits its
64 KiB IPC frame. It keeps immutable raw bytes in its worker; the renderer
never receives the signature, full envelope, endpoint or filesystem paths.

The only added public requests are `objective_list`, `objective_inspect`,
`objective_submit` and `objective_query`. Every request carries
`expected_instance`; all but list carry an existing `id`. Extra, missing or
duplicate fields are rejected by the real strict host request parser. Stale
Session generations and unknown IDs are rejected before a command is queued.

## Client attempt retention and uncertainty

`objective-client.lock` is exclusively flocked. The storage directory identity
and lock inode are rechecked before use; replacement is rejected. Each marker
is keyed by a domain-separated hash of original owner, issuer, key epoch,
message ID, sequence, run ID and original spawn generation, independently of
entry names, transport request IDs and JSON presentation. It also retains the
exact raw-envelope SHA-256 and bytes. Reordering JSON fields, changing internal
spaces or changing the signature's hex case cannot reopen a submission slot.
The same original attempt identity with different raw bytes is rejected during
startup; the trusted launcher must restore the originally retained bytes for
query-only recovery. No normalization is applied to bytes sent to the owner. The write sequence is create-exclusive temporary file, complete
write, file fsync, no-replace atomic rename, directory fsync, and identity
recheck. Any persistence failure prevents transport; a failed write poisons
that live store. There is no marker delete or rearm API.

An existing marker after restart forces query-only Unknown, even if the prior
process died before observing a reply. This is intentionally conservative.
A marker is not an authoritative admission record, an effect receipt or a
rollback-resistant ledger. An administrator that rolls back storage or supplies
a fresh retention directory is outside this local anti-resend guarantee; the
original owner's identity, signature and durable replay rules remain decisive.

Delivery statuses distinguish Ready, Submitting, NotSent, Refused, Admitted,
Conflict and Unknown. NotSent only means that this attempt wrote zero transport
bytes; it does not rearm the entry. History has its own status and last observed
publication digest; it never erases uncertain delivery. An already published
history blocks a first local submission too. An envelope from an older owner
spawn is query-only from startup. A closed worker turns pending operations into
Unknown. There is no reconnect-driven submission, retry button or automatic
re-signing.

All owner I/O and persistence execute on a dedicated bounded worker. The public
Session loop only enqueues commands and reads finite projections, so a slow
original owner does not hold up snapshots or child reaping. Original transport
uses its existing whole-operation deadline. The queue holds one waiting command;
commands that cannot be queued are explicitly rejected.

## Developer map and qualification

| Source | Responsibility |
| --- | --- |
| `ui/core/src/objective.rs` | Renderer-safe delivery/history projections |
| `ui/core/src/lib.rs` | Strict generation-fenced host request schema |
| `ui/session/src/objective.rs` | Trusted config, immutable entries, bounded worker and original clients |
| `ui/session/src/objective_store.rs` | Private raw-envelope retention and anti-resend marker |
| `ui/shell/src/objective_panel.rs` | Explicit selection/review/submit/query presentation |
| `services/hepta-os/src/objective/` | Existing exact original transport and history protocol |
| `tests/integration/hepta/original_objective_export.rs` | Actual Supervisor/Agentd export-ready qualification mode |
| `tests/ui/test-objective-shell.py` | Authenticated private Xvfb, actual Shell clicks and independent original evidence |

Unit regressions exercise write-before-send with an actual socket, lost replies,
reopen fencing, equivalent envelope presentations, lock and directory replacement,
corruption, old generations,
worker closure, strict renderer fields and render-without-click behavior.
The GUI test takes explicit input ELFs; it never discovers an active owner or
display. It records all ELF hashes, original readiness, selected UI projections,
PNG captures, original run reads and the stopped original journal. The optional
`--objective-layout-probe` reports bounded UI button geometry and projected
metadata only. Geometry coordinates are test instrumentation, not evidence of
admission: the harness compares actual original publication digests and inspects
the stopped journal through original library code.

The new original probe mode is:

```text
hepta-original-objective-probe AGENTD OBSERVER SUBMITTER FRESH-PRIVATE-ROOT --export-ready
```

It keeps the original Supervisor alive until `shell-inbox/stop` appears, with a
180-second deadline, and exports `ready.json`, private envelope/config files and
a final read-only journal inspection. It never serializes the test signing key.
Current qualification results are recorded with the implementation evidence;
no UI state alone raises the production-authority gate.

## 2026-10-25 host qualification checkpoint

The actual authenticated Xvfb/Shell/Session + original f91a5d6 Agentd and
Supervisor run passed all seven acceptance groups. It verified default-off
submission, strict selection and generation fences, invalid-signature
Unknown without publication or retry, real GUI admission plus an independent
original run/history read, Session responsiveness during an original-owner
SIGSTOP, real Session SIGKILL and query-only reopen, and read-only original
journal inspection after controlled shutdown. The final journal held exactly
one publication for the accepted request. The stalled-owner Session snapshot
returned in about 18 ms. Input ELFs were unchanged before and after the run.

The UI workspace passed 213 tests with two existing ignored tests. Workspace
all-target Clippy with warnings denied and formatting checks passed. The stable
attempt-identity regression additionally confirms that equivalent JSON field
order, whitespace and signature-hex presentation do not rearm an attempt.

Evidence is retained in the task's `work/goal-logs/ui/objective-real-qualified/`
(result JSON, actual process logs, screenshots and fixture inbox evidence), with
`objective-workspace-final-2.log`, `objective-identity-final.log`,
`objective-clippy-source-final.log` and `objective-fmt-source-final.log` beside it.
The earlier `objective-real-1` startup timeout occurred before Session launch;
`objective-real-2` reached original admission/history but the test input helper
waited for motion at an already-selected coordinate. Both failures are retained.
The helper now moves without that inapplicable motion wait. Display startup has
its own infrastructure budget; original transport deadlines are unchanged.
`objective-real-final` also passed, and the last qualified run waits for actual
painting before preserving the result screenshots.

This is host integration qualification with an isolated test issuer. It does
not qualify production Root issuance, model execution, kernel enforcement,
physical-device control, or an external rollback witness.
