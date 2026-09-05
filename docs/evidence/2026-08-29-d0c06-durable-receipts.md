# D0C-06 durable receipt journal evidence

> **HISTORICAL BASELINE / STALE_EVIDENCE:** The recorded D0C-06 host result
> is bound to source head `25d2d5882018b9974fc360aaf646128c6b6f175f`.
> Receipt-journal invalidation inputs changed after that run; rerun the
> permanent exact-head gate before treating the result as current evidence.

**Date:** 2026-08-29  
**Status:** `HOST_VALIDATED_NO_EXECUTION_OR_REPLAY_AUTHORITY`  
**Validated source head:** `25d2d5882018b9974fc360aaf646128c6b6f175f`  
**Workflow run:** `33235926577`

**Evidence lifecycle:** `STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN`
**Evidence freshness:** `STALE_EVIDENCE`
**Merge-ready:** `false`
**Stale reason:** Host result `25d2d5882018b9974fc360aaf646128c6b6f175f` was
recorded before the current candidate tree; rerun `receipt-journal` on the exact
candidate head before promotion.

The historical source head passed the permanent read-only `receipt-journal`
qualification, repository/contract audits, Rust 1.93.0 formatting, Clippy with
warnings denied, the complete durable-journal fault corpus, and the full
workspace regression. The same head also passed desktop CI, Browser
codec/reference regression, and AgentPort custody regression in runs
`33235926576`, `33235926596`, and `33235926613`.

The demonstrated implementation provides:

- append-only, bounded and versioned segment/record framing;
- SHA-256 record chaining and cross-segment chaining;
- strict requested → dispatched → completed/indeterminate/interrupted lifecycle;
- a crash-recoverable single-writer lease bound to boot ID, PID and proc start
  time;
- durable append before in-memory sequence advancement;
- writer poisoning after an uncertain append until reopen/recovery;
- fail-closed distinction between a repairable torn tail and hard mid-log
  corruption;
- explicit repair only to the last verified record;
- typed storage-exhaustion handling;
- redacted export, quiescent rotation, and retention-candidate selection that
  never chooses an unexported segment;
- `never_automatic` recovery for unresolved potential external effects.

The journal contains no execution, dispatch, retry, or replay API. It records
facts only. No BrowserActor dispatch, Servo call, listener activation, external
effect, automatic replay, Debian/QEMU runtime, or product-readiness claim is
made by this evidence.

The synchronized promotion head must rerun the same permanent qualification
after updating `CURRENT_STATE.md`, the document manifest, and repository-state
data. The historical result is retained for provenance and does not substitute
for that exact-head rerun or widen the journal's authority boundary.
