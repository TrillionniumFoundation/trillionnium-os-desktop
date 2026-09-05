# Atomic semantic resolver boundary

**Gate:** `D3-01`  
**Current evidence tier:** source contract and independent reference  
**Promotion authority:** none

## Threat model

A `page_act` request carries an element reference created from an earlier
semantic snapshot. Its frame identifier, semantic identifier, role, accessible
name, and structural fingerprint are untrusted claims supplied by the caller.
They are not proof that the same node is still present, unique, visible,
enabled, or safe to act on.

Forwarding those fields through the generic BrowserActor `Act` message creates a
time-of-check/time-of-use and retargeting boundary. A navigation, frame swap,
DOM mutation, accessibility-tree update, duplicate semantic identity, or role
change could otherwise redirect the operation to a materially different node.

## Required engine operation

The canonical contract is
[`contracts/semantic-resolver.v1.json`](../../contracts/semantic-resolver.v1.json).
A real engine adapter must execute all of the following as one bounded,
engine-owned operation without yielding to another document or semantic-tree
mutation:

1. bind the request to the current PageOwner session and all four revision
   layers;
2. search only the current frame and current semantic snapshot;
3. require exactly one current node for the semantic identity;
4. compare role, accessible name, and structural fingerprint;
5. retain the resolved engine node rather than retaining caller fields;
6. revalidate PageOwner revisions and retained-node identity immediately before
   action;
7. apply one role-authorized action at most once;
8. advance the mutation epoch and return a typed receipt;
9. return a typed fail-closed error on cancellation, deadline, ambiguity,
   absence, cross-frame fallback, drift, or mutation race.

The adapter must not retry by selecting another candidate and must not fall back
to coordinates, DOM order, accessible name alone, or a generic action path.

## Independent reference

`tools/semantic_resolver_reference.py` is a standard-library-only state model.
It exercises exact revision binding, current-frame uniqueness, structural and
semantic drift, role/action policy, cancellation, deadline, mutation races, and
exactly-once action cardinality. The adversarial corpus is in
`tests/d3/test_semantic_resolver_reference.py`.

The reference intentionally owns no Servo object and performs no external
effect. Its result must remain `PASS_SOURCE_REFERENCE_ONLY`; it cannot set a
BrowserActor, integrated-image, AgentPort, hardware, or release promotion flag.

## Servo promotion requirement

D3 remains blocked until a Servo-owned adapter maps an engine-retained DOM or
accessibility node into this contract and the exact integrated image proves:

- authorized and unauthorized TaskFlow principals;
- PageOwner session/revision binding;
- unique current-frame observation and action;
- ambiguity and drift rejection;
- cancellation and deadline cleanup;
- browser/content crash and recovery;
- requested, dispatched, terminal, indeterminate, and recovered receipt facts;
- production AgentPort still default-disabled.

A passing source/reference workflow is a prerequisite, not a substitute for
that runtime evidence or independent security review.

## Development fixture failure atomicity

The isolated D3 fixture now checks response representability before applying a
local action or publishing an observed target. This closes an error-after-state-
change path at the u64/i64 JSON boundary without making the fixture an engine
adapter. [RECEIPT_ADMISSION_IDENTITY.md](RECEIPT_ADMISSION_IDENTITY.md) specifies
its commit ordering and failure cases. All Servo promotion requirements above
remain unchanged.

## Optional in-process engine-thread dispatch

[ENGINE_THREAD_DISPATCH.md](ENGINE_THREAD_DISPATCH.md) defines the bounded
actor-to-engine scheduling mechanism and real connected-stream/receipt host
corpus. Its engine remains a fixture in tests; the mechanism is not installed
in the product, does not implement cross-process IPC, and does not prove live
Servo node resolution, native input or exact-image D3. Existing topology,
authority and promotion requirements remain unchanged.

## Persistent development engine-thread runner

The persistent `hepta-agent-port-development-sessiond` now uses the main-thread
AtomicFixtureRuntime through EngineThreadRuntime. Its single scoped connection
worker owns the actor and receipt observer, retains the first complete attested
process snapshot (including start_time_ticks), and refuses later identity drift.
Engine retirement stops accept polling and is never an implicit engine restart.
No new configuration, production listener, executable, dependency or Servo API
is added. The old single-connection binary remains unchanged. See
`docs/architecture/D3_SESSION_ENGINE_RUNNER.md` and
`contracts/d3-session-engine-runner.v1.json` for lifecycle, bounds, failure and
source-test evidence. This remains a local fixture, not an installed Servo claim.

## Session reconstruction isolation

Actor creation now lazily obtains an OS-sourced incarnation at the first valid
SessionCreate; session/WebView tokens are namespaced across actor reconstruction.
The atomic fixture scopes frame identity by session and WebView before publishing
a target. Entropy failure has no predictable fallback; deadlines and bounded
opaque Browser API v1 fields remain enforced. No old PageOwner is resurrected
from receipts and no operation is replayed. See
`docs/architecture/SESSION_INCARNATION.md` and
`contracts/session-incarnation.v1.json` for APIs, failure ordering, compatibility,
regressions and limits. This is source/host evidence, not actual Servo, systemd,
image, hardware, anti-rollback, production activation or release proof.

## Callback-shaped engine scheduling

The optional `callback_engine_pair` / `CallbackEngineOwner` path starts an
operation on its creator thread and accepts a single-use `EngineCompletion`
from a later callback. The application continues native events between pumps;
its timer follows the original deadline and bounded cancellation-check schedule.
Ordinary Act never substitutes for the dedicated atomic semantic hook. The
existing request endpoint now wakes on abandonment and Drop as well as enqueue.
Wakes may be coalesced and are not a count of dispatched operations.
See `docs/architecture/EVENT_LOOP_COMPLETION.md` and
`contracts/event-loop-completion.v1.json` for APIs, ordering, tests and limits.
This is source/host fixture evidence only: no Servo/native event loop, process
IPC, installed image or product authority is added. The development daemon
continues selecting its synchronous fixture backend; no activation changes.
