# trill-ui-broker

Bounded host admission and the trusted-owner/target boundary. This is not an
issuer, signer, A05 CapSpace implementation or replacement effect ledger.

## Code map and contracts

[lib.rs](src/lib.rs) defines peer admission, finite sessions, generation
fences, operation requests and owner receipts. The same-UID authenticator is
a host prototype boundary, not production authorization.
[notes.rs](src/notes.rs) implements the private Linux Notes target exchange.

Keep global/per-peer session bounds, idle expiry and reaping together.
Evicting local presentation state cannot retire original owner history.
An opaque handle does not grant authority; original operation identity,
authorization and durable outcome remain owned by Hepta.

Notes framing/correlation failures poison the channel. A timeout after a
possible write is indeterminate, not a safe retry. Independent readback and
original-owner reconciliation are distinct from transport success.

## Development

```sh
RUSTUP_TOOLCHAIN=1.88.0 cargo test --manifest-path ui/Cargo.toml -p trill-ui-broker --locked
```

[tests](tests/) cover actual Session admission/identity and Notes targets within
their stated host scope. The complete setup and gate are in
[workspace setup](../README.md) and [RUN](../../support/ui/RUN.md).
Read [NOTES_ORGAN](../../support/ui/NOTES_ORGAN.md) and
[INTEGRATION_CONTRACTS](../../support/ui/INTEGRATION_CONTRACTS.md) before changing
bootstrap, cancellation, retained outcomes or the owner seam.
