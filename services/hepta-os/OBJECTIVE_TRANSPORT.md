# Original ObjectiveStart transport contract

## Scope and evidence boundary

The **default-disabled** `objective-transport` feature adds an independent Linux
trusted-host API. It accepts an existing raw `AuthBusObjectiveIngress`, checks
its structure, and makes at most one bounded ObjectiveStart connection to an
explicitly configured original Agentd. It keeps the original envelope attached
to the immutable result, including `SubmitUnknown`.

`ObserverClient`, `READ_ONLY_METHODS`, `hepta-observe`, Session IPC and the Rust
Shell do not gain a submission command. `TrustedReadOnlyOrganV1` still performs
no I/O and gains no endpoint or authority. This crate creates no issuer,
signature, key, authority epoch, objective profile, durable operation record,
process, model call or device effect.

The R7 tests exercise real **disposable local Unix sockets against scripted
responses** and source-derived serialization. Their input copies the fixed
original protocol test's expired envelope and all-zero, 64-byte signature
value. These are deliberately unauthenticated wire fixtures, never credentials.
They do not qualify original-owner authentication, publication, model execution,
reconciliation or HOS2/device delivery. The separately recorded
[R6 original Agentd and continuous Session runs](../../tests/integration/hepta/evidence/2026-10-17-original-session-runtime/README.md)
remain evidence for the read-only lifecycle boundary.

## Fixed original contracts

All claims below target
[`hepta-private-ci@f8c9419df6ddeb36ff8b522a50219981fb8d9345`](https://github.com/TrillionniumFoundation/hepta-private-ci/tree/f8c9419df6ddeb36ff8b522a50219981fb8d9345).
[OBJECTIVE_UPSTREAM_CONTRACT.json](OBJECTIVE_UPSTREAM_CONTRACT.json) records
fourteen reviewed files, their immutable Git blobs, SHA-256 hashes and sizes.
The source check accepts exact source-file snapshots or an authorized checkout;
verifying those files does not certify an entire checkout or executable.

| Original source | Reused contract |
| --- | --- |
| [protocol/lib.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agent-protocol/src/lib.rs#L203-L210) | AgentdRequest, schema 2, ObjectiveStart variant, response envelope and payload tags |
| [protocol/authbus.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agent-protocol/src/authbus.rs#L27-L81) | Original ingress/body, publication receipt, conflict and client-facing outcome fields |
| [contracts/agent_id.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-contracts/src/agent_id.rs) | Canonical AgentId representation |
| [types/identity.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-types/src/identity.rs#L100-L124) and [types/digest.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-types/src/digest.rs#L103-L128) | Bounded stable IDs and lowercase digest representation |
| [state_control.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/state_control.rs#L206-L228) | The compiled ObjectiveStart route calls the existing ObjectiveRuntimeHost::submit |
| [objective_runtime.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/objective_runtime.rs#L140-L327) | Owner authentication, durable publication, later readiness/trust checks and admission dispositions |
| [control.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/control.rs#L96-L164) and [client.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/client.rs#L718-L760) | One-frame UDS exchange, shutdown, error wrapper and identity fields |
| [authbus_trust.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/authbus_trust.rs), [authbus_ingress.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/authbus_ingress.rs), [authbus/lib.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-authbus/src/lib.rs) and [signed.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-authbus/src/signed.rs) | Existing issuer trust, signature/replay ownership and readiness boundary; no local replacement |
| [protocol/objective_tests.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agent-protocol/src/objective_tests.rs#L7-L27) | Exact expired/all-zero wire fixture used by these local tests |

The full original protocol crate imports fleet/automation types and the daemon
client imports the Agentd/App Server composition. The production module uses a
private exact wire subset to retain the existing lightweight dependency graph.
The source-derived checker compiles the actual original serde declarations and
AgentId implementation, without constructing the original daemon or owners.

## Complete request wire

The only request variant is:

```text
{
  "schema_version": 2,
  "request_id": 41,
  "spawn_generation": 3,
  "method": {
    "type": "objective_start",
    "request": <the original AuthBusObjectiveIngress object>
  }
}
```

This structural illustration expands whitespace for readability. Its angle
brackets are a placeholder, not literal wire data. The `request` value is the
original **JSON object**, not a JSON string. The
actual frame is one line followed by one LF. Schema, request ID and outer spawn
are set only from the explicitly supplied trusted configuration.

`AuthBusObjectiveIngress` has exactly these seven fields:

| Field | Wire type | Local structural rule |
| --- | --- | --- |
| `issuer_id` | string | 1–128 ASCII bytes from letters, digits, `.`, `_`, `:`, `-` |
| `key_epoch` | u64 | Nonzero; never allocated or refreshed here |
| `message_id` | string | Same stable-ID alphabet and bound |
| `sequence` | u64 | Nonzero; retained exactly, no replay-window update here |
| `expires_at_ms` | u64 | Nonzero; the original owner checks time, expiry and the five-minute window |
| `signature_hex` | string | Exactly **128 ASCII hex characters = 64 bytes**; upper/lower hex accepted structurally |
| `body` | object | Exactly the following ten fields |

`AuthBusObjectiveBody` preserves the original field types and canonical
serialization order:

| Field | Wire type | Local structural rule |
| --- | --- | --- |
| `spawn_generation` | u64 | Nonzero and equal to the trusted endpoint's immutable spawn before connecting |
| `run_id` | string | Same stable-ID alphabet and bound; never replaced |
| `objective_revision` | u64 | Nonzero and retained exactly |
| `source_envelope_json` | string | Nonempty, at most **32,768 decoded UTF-8 bytes**; inner content is not normalized or semantically authenticated |
| `runtime_body_digest` | string | Exactly 64 lowercase hexadecimal characters, nonzero |
| `preference_state_digest` | string | Same digest rule |
| `model_tuple_digest` | string | Same digest rule |
| `prompt_registry_digest` | string | Same digest rule |
| `artifact_set_digest` | string | Same digest rule |
| `authority_epoch` | u64 | Nonzero and retained exactly; this is not a local grant |

Unknown fields, duplicate fields, missing fields, wrong types and invalid
integer representations fail structural parsing. The canonical serialized body
must fit **49,152 bytes**; the complete outer frame, including its final LF,
must fit **65,536 bytes**. A 32 KiB source string containing JSON escape-heavy
characters can exceed the body limit and is rejected.

`ProvidedObjective::parse_json` accepts a single object with **no outer
whitespace or literal CR/LF**. Escaped newlines within strings are valid. This
is a deliberately narrow local framing profile: it rejects pretty-printed raw
input rather than altering supplied bytes. A `RawValue` preserves the original
signature, source string escaping, object field order and internal spaces.
The complete outgoing frame is checked before any socket connection.

Structural success is never named authenticated or authorized. The original
owner still derives its subject/scope, checks the configured issuer and key,
authenticates the signature, enforces replay/expiry/readiness/fencing, decodes
the actual source envelope and evaluates its original objective profile.

## Host API and delivery accounting

The trusted caller supplies `EndpointConfig`, an independently trusted nonzero
peer PID and a nonzero request ID. The transport discovers no endpoint, learns
no trusted identity from an arbitrary socket, and allocates no request/run ID.
These inputs belong to a dedicated host worker, not a renderer or organ handler.

```rust,ignore
// existing_raw comes from the independently configured original issuer.
// This parse proves structure only. No key, signature or source is assembled here.
let provided = ProvidedObjective::parse_json(existing_raw)?;
let transport = ObjectiveTransport::new(trusted_endpoint, trusted_pid, original_request_id)?;
let attempt = transport.submit_once(provided);
```

The consuming `submit_once(self, provided)` API permits one connection and one
request. Neither the input nor the transport is cloneable; the attempt retains
the same raw envelope but provides no extraction/resubmit/rebind method. The
caller can inspect bounded identity/status metadata and compare an independently
retained raw envelope through `matches_original_json`; raw source and signature
have no public getter, `Debug`, `Display` or serializer.

Before writing, the transport applies the observer's existing canonical path,
private directory/socket mode and UID checks, then checks the connected kernel
peer's **exact UID and PID**. The expected AgentId, spawn and request ID must
also match the eventual response. Same-UID processes and privileged host access
remain in the existing local trust boundary; these checks are not code attestation.

One five-second asynchronous deadline covers filesystem admission, connection,
all writes and all response reads. The filesystem job keeps its one-slot permit
until the actual syscall returns; dropping a timed-out runtime does not block
the caller while waiting for that job. A host must not create unlimited workers
to bypass this bounded admission.

The write loop records each positive write before the next await. A later
cancellation retains that count. Partial writes only finish the same frame on
the same connection; there is no reconnect or semantic replay. The recorded
count means bytes accepted by the local socket, **not proof of owner receipt**.
Any positive count makes an unresolved result `SubmitUnknown`.

The response reader consumes at most 65,537 bytes and requires the original
server's write-half EOF within the same deadline. Exactly one LF-terminated
frame is accepted. A valid-looking prefix followed by another frame or a blank
line cannot establish admission or a certain refusal. A lost/truncated response,
extra data or missing EOF keeps the attempt unknown.

## Complete response and typed outcomes

The response envelope has exactly `schema_version`, `request_id`, `agent_id`,
`spawn_generation`, `current_generation` and `payload`. The first four must
match the original configured request/source. The captured current generation
must be in the existing spawn-through-spawn+2 lifecycle range, using checked
arithmetic. It is a response field, **not a fresh health/readiness sample**;
the original generic error wrapper even sets it to the request spawn.

The permitted original payloads are:

| Payload tag | Exact additional fields | Local result |
| --- | --- | --- |
| `objective_run` | `run_id`, `objective_digest`, `hard_constraint_digest`, `publication_digest`, `chain_digest`, `disposition`, `idempotent` | `Admitted(AdmissionReceipt)` |
| `objective_conflict` | `run_id`, `conflict_digest` | `Conflict(ConflictReceipt)` |
| `error` | `code`, `message` | Classified below; raw message is discarded |

`objective_run` is **flat inside payload**. The separately declared
`ObjectiveStartOutcome::Admitted { receipt }` is the original client's returned
type; it is not the Agentd wire payload. Mixing those shapes fails closed.
Run IDs must match the original input. This local receipt profile requires
64-character lowercase nonzero digests and accepts exactly the original five
dispositions: `compiled`, `explicit_abstain`, `canonical_ready`,
`canonical_abstained` and `canonical_slow_path`. Unknown future shapes remain
unknown until the pinned source/profile is deliberately reviewed.

| Condition | Result | Meaning |
| --- | --- | --- |
| Local rejection, connection/peer failure or timeout with exactly zero request bytes written | `NotSent(issue)` | This attempt wrote nothing; says nothing about earlier attempts |
| Valid matching `objective_run` | `Admitted(receipt)` | Original publication/admission response; not model or device completion |
| Valid matching `objective_conflict` | `Conflict(receipt)` | Original conflict publication; never permission to allocate a different run |
| Matching `objective_unavailable` + exact `no owner objective profile is configured` message | `RefusedBeforePublication(ObjectiveUnavailable)` | This sent request took the original no-host pre-dispatch path |
| Matching `unsupported_schema` + exact `unsupported agentd control schema` message and response generation equal to spawn | `RefusedBeforePublication(UnsupportedSchema)` | This sent request took the original schema pre-dispatch path |
| `request_rejected`, regardless of message | `SubmitUnknown(OwnerRequestRejected)` | The original wrapper covers both pre-publication and post-publication failures |
| Unknown code, known refusal code with a different message, malformed fields or unmatched response identity after writing | `SubmitUnknown(issue)` | No admissible original result for this request |
| Bare original `overloaded` frame | `SubmitUnknown(Overloaded)` after writing | It has no request/source identity; `retry_after_ms` does not trigger any retry |
| Timeout, EOF, partial write/read or I/O failure after any positive write | `SubmitUnknown(issue)` | The original owner may already have accepted/published |

Only finite `EnvelopeError`/`SubmissionIssue` codes are printable. No underlying
I/O error, owner message, socket path, signature or source body is returned in an
error. The original owner's error message is structurally bounded to 512 Unicode
characters and then discarded.

## Why unknown cannot become an automatic retry

The compiled route is the original `state_control` handler invoking
`ObjectiveRuntimeHost::submit`. The host authenticates the request, then
[publishes to its own durable journal before later checks](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/objective_runtime.rs#L206-L327).
Readiness, current trust or runtime admission can fail after publication.
The original server's two-second connection deadline can also cancel a request
whose durable publication has already happened. The generic `request_rejected`
code and connection loss therefore do not prove non-admission.

The original
[RunStatus handler](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/state_control.rs#L523-L531)
reads an in-memory run projection. `null` does not prove absence from the
durable publication journal; an admitted abstention can also lack a runtime run.
This transport exposes no RunStatus-based reconciliation path. A RunStatus
payload received as an ObjectiveStart response is invalid and remains unknown.

The original owner permits a consumed replay sequence only for the exact
recorded authentication and run ID, with expiry/revocation/readiness/spawn gates
still enforced. Its canonical path may wait for an exact authenticated retry.
That owner-specific recovery behavior is not an authorization for this transport
to retry. It never refreshes expiry/key epoch/signature, changes message/run/request
ID, advances authority/revision/sequence, swaps source JSON or rebinds to a new
spawn to escape an unknown outcome. A refusal from a later attempt cannot clear
uncertainty from an earlier one.

Attempt retention here is in-memory only. Dropping the object or losing the host
process does not undo original publication. An actual embedding must bind
in-flight intent to the existing owner recovery contract before enabling
submission, and preserve unknown after crashes or lost responses. This change
does not install a second durable ledger or claim cross-process exactly-once
submission.

## Validation and remaining integration blockers

The [frozen R7 local run](../../tests/integration/hepta/evidence/2026-10-18-objective-transport/README.md)
on source `19c2185d27c1d788354e14af27999406bc927c4f` passed both feature profiles,
35 Rust tests, strict Clippy/fmt, fourteen original-file identities and seven
original-declaration wire checks. Its original logs and source/lock/toolchain
bindings are retained. These results have the local fixture/source scope above.

The regression suite covers exact raw transport, all five dispositions,
conflict, precise refusal paths, ambiguous owner errors, unscoped overload,
request/source/peer fencing, EOF and partial-response faults, extra frames,
duplicates, non-UTF-8, frame/body/source bounds and a full-frame read timeout.
Every socket fixture waits for the client to return before checking that no
second connection was attempted. One separate three-byte Tokio duplex test
forces a real partial buffer write followed by cancellation and write failure;
it qualifies byte-accounting logic, not kernel UDS behavior or owner admission.
Compile-fail examples check that the transport cannot be called twice and the
raw envelope cannot be printed with `Debug`.

Reproducible commands and the source-declaration check are in [RUN.md](RUN.md).
The existing observer baseline runs with the new feature enabled as a regression
gate, and both feature-off and feature-on targets must compile. No Cargo package
version/lock is changed; the optional `serde_json/raw_value` feature supplies raw
preservation without a cryptography or original-daemon dependency.

Before a real objective can enter this path, the original owners must provide
the configured issuer/trust and replay checkpoint, frozen objective profile,
actual existing authenticated ingress, and a reviewed durable reconciliation
handoff. An independently bound executable/endpoint/PID must be used. Actual
owner admission, unknown-after-publication, revocation, restart and exact
identity recovery still require their own original-runtime evidence. HOS2 K/D,
acknowledgement, retirement and device-effect acceptance remain a separate gate.
