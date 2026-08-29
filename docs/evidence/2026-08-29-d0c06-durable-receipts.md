# D0C-06 durable receipt journal evidence

**Date:** 2026-08-29  
**Status:** `HOST_VALIDATED_NO_EXECUTION_OR_REPLAY_AUTHORITY`  
**Validated head:** `25d2d5882018b9974fc360aaf646128c6b6f175f`  
**Workflow run:** `33235926577`

The exact head passed the permanent read-only `receipt-journal` qualification,
repository/contract audits, Rust 1.93.0 formatting, Clippy with warnings denied,
the complete durable-journal fault corpus, and the full workspace regression.
The same head also passed desktop CI, Browser codec/reference regression, and
AgentPort custody regression in runs `33235926576`, `33235926596`, and
`33235926613`.

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
