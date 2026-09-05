# D0A-01 exact-pin Servo qualification

> **HISTORICAL BASELINE / STALE_EVIDENCE:** This qualification is bound to
> candidate head `01d02d692c573ccde7a99d990f2a63235d9bc69f`. D0A-01 declared
> inputs changed after that run; rerun the exact-pin workflow on the current
> candidate head before using this result for a current qualification claim.

**Date:** 2026-08-29  
**Servo commit:** `670ae8a70801b162e186f81cbb5bdd2d59c39108`  
**Candidate head:** `01d02d692c573ccde7a99d990f2a63235d9bc69f`  
**Workflow run:** `33230713426`  
**Job:** `99042937091`  
**Artifact:** `9708505752`  
**Artifact digest:** `sha256:aad3c47a4151b0ecaf96c4e0dd16680cc498667e155391c53b4a6e489a57501b`  
**Status:** `PASS_COMPILE_COMPATIBILITY_ONLY`

**Evidence lifecycle:** `STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN`
**Evidence freshness:** `STALE_EVIDENCE`
**Merge-ready:** `false`
**Stale reason:** The compile result is bound to historical source head
`01d02d692c573ccde7a99d990f2a63235d9bc69f`; rerun `servo-exact-pin` on the
exact candidate head before promotion.

## Exact-head gate

The historical successful workflow checked out the exact upstream Servo commit into a clean
working tree, enforced the zero-delta patch ledger, used Servo's declared Rust
`1.97.1` channel and locked Cargo graph, and compiled all four qualification
steps:

| Check | Status | Machine log SHA-256 |
| --- | --- | --- |
| locked Cargo metadata | `PASS` | `7e1ff3dde6cb6545795aa274a8d3e0e4eff2834c210bd2810a365883d855d70c` |
| official `winit_minimal` embedder | `PASS` | `1309ebea3901926df0d3bcc0171cb5e85be628b2ff9e1257951a9f059b910dcc` |
| Trillionnium public embedder API probe | `PASS` | `17349dd4493a32d846f108fa4854528d84b3b818e29dca96cdff26ab3642e7d1` |
| official `servoshell` | `PASS` | `22f72bc26ab455b00faf1194d256936044c38feeded604b8d76977c02418900d` |

The public probe source digest is
`d0da792e14b439ab781ad8a1c00b51af7c3c97544492d928b9d9b54d342d833c`.
The workflow additionally validated the repository from a tracked-only archive,
so the external Servo checkout and generated qualification files could not
silently change repository validation scope.

Machine evidence is committed at
`docs/evidence/generated/d0a01-servo-qualification-result.json`.
It remains a historical baseline and is stale for the current candidate until
the exact-pin workflow is rerun at the current head.

## Qualified source surface for D0A-02

The exact pin exposes and compiled the product-required builder, one-WebView,
event-loop wake/spin, render/present, screenshot, input, composition/IME,
navigation refusal, popup refusal, crash, and accessibility callback surfaces.
This is sufficient to start the headed local-fixture implementation gate; it is
not runtime evidence.

## Enforced claim ceiling

Every runtime/product claim in the generated result remains `false`:

- Servo was not started by this checkpoint;
- no window or visible frame was created;
- no native pointer, keyboard, wheel, or IME event was delivered;
- no network navigation or WebDriver listener was used;
- no Debian image or product readiness was claimed.

The next gate is `D0A-02 product-owned headed local-fixture runtime`.
