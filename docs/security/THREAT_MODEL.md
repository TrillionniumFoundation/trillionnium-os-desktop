# Desktop threat model

The active normative threat model is:

[`THREAT_MODEL_V2.md`](THREAT_MODEL_V2.md)

Revision `2026-08-29-d6` covers trusted UI, local Agent identity, semantic
principal binding, stale references, renderer compromise, controlled egress,
receipt/effect reconciliation, supply chain, updates, and mobile-authority
contamination.

The earlier D0 baseline is superseded because main now includes host-validated
transport, codec, connected bridge, default-disabled systemd custody, peer
attestation, durable receipts, and Servo compile compatibility. Runtime
enforcement remains limited to each demonstrated evidence tier; the V2
document lists residual risks and future gates explicitly.
