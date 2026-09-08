# D0C-02 final gate trigger

> **HISTORICAL BASELINE / STALE_EVIDENCE:** This trigger marker belongs to
> the historical D0C-02 host result. The current candidate changed declared
> inputs; rerun the permanent Rust 1.93 gate on the exact current head before
> treating the result as current evidence.

**Date:** 2026-08-28
**Evidence lifecycle:** `STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN`

The historical host-validated Rust evidence and independently regenerated
deterministic reference evidence were committed at that checkpoint. This
marker triggered the permanent repository, Rust and independent-reference
workflows against that historical candidate head; it does not replace the
exact-head rerun required for the current candidate.

It changes no protocol, runtime authority or product behavior.
