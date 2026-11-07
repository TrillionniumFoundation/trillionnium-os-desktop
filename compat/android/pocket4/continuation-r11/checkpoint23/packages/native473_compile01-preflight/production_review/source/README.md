# Builder 473 source checkpoint

SOURCE_ONLY. This checkpoint recovers the minimal Audiocontrol example projection from immutable builder 471 and the complete actual Normal08 consumer. No Rust control, compiler, Soong, Android, or device action has run for this candidate.

The exact two typed-ingress targets keep strict missing-dependency behavior. Only the observed standalone vendor example is projected to its unchanged package/license metadata; parent AIDL/provider files, sibling implementation, 225-project lock, and the builder 471 SystemUI projection remain unchanged. The original complete 1869-byte consumer is the regression fixture and the complete preimage remains journaled and restored by the existing Projection/recover code.

Three real Rust regression tests cover exact metadata and write scope, source drift rejected before any write/journal, and full preimage recovery after an interrupted projection. Sentinel files assert write scope only. Static source reasoning is not a complete generated Soong variant graph proof.

The prior memory-only WIP body was lost with V8 state and was never uploaded or run. Its advertised hash is retained in proof.json; this recovered candidate has a distinct pin. The compiler/request will be a later immutable package. No dispatchable request exists in this checkpoint.
