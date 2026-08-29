# D0C-06 durable receipt journal evidence

**Date:** 2026-08-29
**Status:** `EXACT_HEAD_VALIDATION_PENDING`

The candidate implements an append-only, SHA-256-chained receipt journal in
`hepta-session-core`, with strict lifecycle transitions, a crash-recoverable
single-writer lease, typed torn-tail/storage-full/corruption states, redacted
export, quiescent rotation, and retention planning that never selects an
unexported segment.

Promotion requires a successful exact-head `receipt-journal` workflow and an
atomically committed machine result. Until then this is source candidate
evidence only.

No BrowserActor dispatch, Servo call, listener activation, external effect,
automatic replay, or product-readiness claim is made.
