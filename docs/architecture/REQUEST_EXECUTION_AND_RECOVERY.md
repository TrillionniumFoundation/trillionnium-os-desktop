# Request execution and recovery: cross-module acceptance contract

**Plan revision:** `2026-08-29-d6`
**Status:** proposed integration acceptance detail; implementation and qualification remain separate

This document refines the S08–S11 work without activating a product listener,
declaring an installed test passed, or changing project truth. The
existing transport, actor, journal, runtime-supervision and update contracts
remain authoritative for their individual mechanisms. Resolve a disagreement
by retaining the narrower authority and obtaining an explicit contract review.

## Ownership and data flow

| Boundary | Authoritative owner | Data handed forward | Authority not transferred |
| --- | --- | --- | --- |
| Inherited connection | systemd connection service | bounded AF_UNIX stream | intent, consent, capability |
| Mechanism admission | peer attestation | live request custody | browser authorization |
| Wire admission | codec and AgentPort | canonical typed request, digest, deadline | handler-authored request identity |
| Semantic admission | BrowserActor/PageOwner | bound principal, current generation, retained reference | caller-injected runtime |
| Durable operation facts | session journal | requested/dispatched/terminal or indeterminate fact | execution or replay permission |
| Real engine action | exact-pin Servo owner thread | single-use command and typed completion | a second PageOwner or hidden browser |
| Response publication | AgentPort | original identity and durable outcome | success invented after a timeout |

The product path must traverse these boundaries through the installed daemon.
A mailbox between qualification processes remains qualification infrastructure;
it cannot stand in for the production process/IPC topology.

## Ordered admission and dispatch protocol

1. Validate the inherited descriptor and socket/service custody. Construct opaque
   attestation and retain the original process incarnation; refuse ambiguity.
2. Decode exactly one bounded canonical request. Bind its original identifiers,
   normalized digest, operation risk and one effective monotonic deadline.
3. BrowserActor checks principal binding, session and content generation, human
   lease/IME ownership, cancellation, queue capacity and supported operation.
   Rejected requests produce a bounded refusal, not a fabricated admitted fact.
4. Persist the requested/admission fact. Failure to obtain the required durable
   acknowledgement prevents engine dispatch and invalidates the writer as required.
5. Complete the journal durability barrier required before possible dispatch.
   Specify whether this fact records dispatch intent or observed execution; those
   are not interchangeable. A crash after durable intent may prevent execution,
   so the fact alone cannot prove that the engine performed the action.
6. After that barrier, on the engine-owning thread, recheck deadline, cancellation,
   custody, current generation and the retained semantic target immediately before
   action, within one reviewed engine task. Do not insert a persistence wait or
   asynchronous resolve-then-act gap after this final check. No coordinate click,
   JavaScript, selector or text-search substitution is allowed. Once the engine
   may have received the command, missing completion is indeterminate, not failed.
7. Consume exactly one completion. Persist the terminal or indeterminate fact
   before publishing a success response. Journal sync failure cannot be repaired
   by claiming the engine result is durably successful.
8. Bind the response to the original request and generation. Lost response delivery
   does not authorize reexecution. Subsequent inspection reads existing facts only.

The implementer must document the exact linearization points, locks and callbacks
in code. The journal and engine do not form an atomic distributed transaction;
this protocol intentionally preserves an indeterminate window rather than
promising exactly-once external effects.

## Current source composition

`apps/hepta-browserd/src/product_dispatch.rs` connects these boundaries using
the original attested Unix stream, a bounded connection queue, concrete
`ServoBrowserActor`, and managed `ReceiptLifecycleObserver`. AgentPort preflight
rejects stale/unsupported/cancelled requests before admission facts. Journal
append/sync acknowledges requested and dispatch-intent facts before the actor
submits the engine command, then acknowledges terminal facts before response
publication. Canonical request-ID deduplication reads the complete managed chain;
transport loss after a durable terminal result does not permit reexecution.

Connection admission and queue residence consume one original monotonic budget.
On Linux, `AcceptedProductConnection::from_received` now consumes the opaque
`ReceivedAcceptedStream` and its original absolute Instant through the same
one-shot callback. The shared private admission helper checks the ceiling before
and after kernel peer observation, live pidfd-backed attestation, interrupt
clone/liveness and local setup; it does not allocate a fresh 20-second budget at
receiver handoff. A read-only `deadline()` observation rechecks creator PID,
cancellation and expiry and grants no dispatch authority. Procfs syscalls remain
synchronous: a late result is refused, not represented as preemptively timed out.
Real Linux same-UID/SCM_RIGHTS host tests verify this receiver bridge; approved
principal/service custody, installed native startup and actual Servo execution
still require separate integration and qualification.
Revocation closes the same transport to wake blocking receive and cancels active
actor work. The native owner must still perform the final peer/control/retained
node check inside its reviewed engine action and withdraw stale pixels/input
before notifying a crash. The installed native embedder, process/service handoff,
trusted recovery UI/policy and approved cross-UID live-executable attestation
broker/authority remain missing. Default daemon activation stays closed; the
qualification mailbox and static attestation profile cannot fill these gaps.

Existing request/coordinator regressions use real Unix framing/pidfds with
explicitly synthetic procfs facts and controlled native completion callbacks. They test source ordering and
failure behavior; they are not installed product or renderer qualification.

The live coordinator/supervisor, queues, cancellation handles, journal/store
custody and sealed facts are scoped to their creating process. Checks precede
copied mutex/channel access and the requested/dispatch/terminal gates. Fork
children cannot reuse a copied permit, publish a fact, translate old sealed
facts, clear recovery or cancel/shutdown the parent's original stream. Child
journal Drop closes only child descriptors and preserves the parent lease.
Standalone single-thread actual-fork regressions exercise these boundaries;
they do not establish an installed native owner or trusted policy/UI.

## Fault matrix required for the real product path

| Fault/cutpoint | Expected result | Forbidden recovery |
| --- | --- | --- |
| Before durable admission | Refuse without engine command | Invent admitted success |
| Admission sync fails | Stop admission; retain diagnostic evidence | Dispatch anyway |
| Cancellation or peer revocation before action | No new action; typed refusal | Reuse cached identity |
| Crash after dispatch intent, before known completion | Indeterminate until reconciled | Assume no effect and retry |
| Engine completion received; terminal journal sync fails | Stop/indeterminate, no durable-success response | Report success from memory |
| Terminal fact committed; response transport fails | Preserve terminal fact for inspection | Execute the original request again |
| Duplicate/late callback | Reject and retire according to actor contract | Publish a second terminal outcome |
| Content process dies | Withdraw old pixels/input, invalidate generation, preserve trusted chrome | Preserve stale authority |
| Explicit reconstruction | New checked generation; old references fail | Translate old references automatically |
| Crash-loop threshold reached | Stable trusted recovery state | Unbounded restart loop |
| Corrupt complete record or missing segment | Preserve store; fail closed | Create a fresh empty history |
| Capacity exhausted | Stop admitting new work; support bounded diagnosis | Silently prune deduplication history |

Run normal, fault and recovery cases through the same product binary and install
map. Each test binds exact source/tree, binary/image digest, inputs, command,
request/receipt identities, fault cutpoint and result. Never infer a physical
power-cut result from SIGKILL, QEMU shutdown or injected exceptions.

## Operator reconciliation and recovery

Recovery is a separately authorized action, not an automatic request retry.
The trusted UI or operator tool must show a redacted state and explain whether
execution is known, unknown or not dispatched. It must not expose secrets,
unrestricted page payloads or raw process identity in ordinary logs.

Before mutation, stop new admission, retain the journal and identify the exact
service lifecycle, image, store and affected request. Inspect the complete
managed chain under its lock. Export a bounded redacted forensic copy through
the reviewed API; do not use unbounded log scraping. A forensic copy does not
become an authoritative shortened journal.

A recovery decision must identify its actor, scope, source facts and allowed
transition. Only an exact same-request durable reconciliation accepted by the
journal may clear an indeterminate latch. Clearing a latch does not reconstruct
an actor or repeat an operation. Reconstruction is a separate explicit step.

The current coordinator's `reconcile_request` checks the exact blocked ID and
canonical digest against a journal-issued terminal `DurableReceiptFact`.
Storage ambiguity cannot be cleared through it. Default startup refuses both
nonterminal history and terminal indeterminate/interrupted-after-dispatch facts
from all segments. `from_connection_after_reconciliation` requires the trusted
recovery caller to explicitly acknowledge every terminal uncertain identity and
digest; incomplete, duplicate or mismatched acknowledgments fail closed. No
receipt is rewritten, replayed or promoted to a known outcome. A persisted
operator-decision protocol remains unimplemented, so reopening requires this
explicit review again rather than inferring a decision from terminal syntax.

When no reliable outcome evidence exists, retain indeterminate and hand control
to the human. Do not offer a misleading "retry safely" button. Any intentional
new action requires fresh human intent, new identifiers and fresh authorization.

Managed store directories use `0700`; journal files use `0600`. Preserve the
service UID and descriptor/ancestor custody. Do not run recursive ownership or
permission repair, delete a damaged store, truncate complete records, or guess a
prior head. Archival/pruning and an externally protected anti-rollback anchor
remain separate designs and tests, not implied capabilities of a hash chain.

## Human input and Agent orchestration acceptance

One PageOwner arbitrates native and Agent input. The real compositor tests must
cover scaling and coordinate transforms, focus withdrawal, keyboard layouts,
clipboard provenance, modal transitions and Chinese IME preedit/commit/cancel.
During IME composition, an Agent mutation must be refused or explicitly queued
under the reviewed policy without changing the user's preedit text. Test both
human preemption immediately before dispatch and loss of ownership afterward.

TaskFlow must separately specify task creation, planning-to-typed-operation
conversion, explicit consent, restricted permits, cancellation, budget limits
and human handoff. Webpage/model/tool output is untrusted data. It cannot issue
capabilities, extend a deadline, change the trusted approval surface or raise
its own risk classification. Bind each proposed action to the current task,
principal, session/origin and permission scope; reject unrecognized fields.

## Measured integration, not assumed performance

Record trusted first-frame, input-to-presentation, observe/act, journal-sync and
reconstruction latency, plus RSS, FD/PID counts and queue depth. Separate normal,
cancelled, rejected and indeterminate operations. Store measurement environment,
sample count, percentiles and resource growth. Hardware thresholds are selected
only after the exact hardware and measurement method are approved; these source
requirements invent no performance result or numeric product SLO.

## Dependencies and change protocol

Read `S08_PRODUCT_SERVO_SUPERVISION.md`, `MANAGED_RECEIPT_STORE.md`,
`S11_UPDATE_RECOVERY.md`, and the active plan before implementation. For every
new transition, update the concrete API, domain/wire schemas where applicable,
state/fault tests, module documentation and installation checks together. A
source-level state model or passing validator is not closure of this matrix.
