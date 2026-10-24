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

Notes framing/correlation failures poison the effect stream. A timeout after a
possible write is indeterminate, not a safe retry. The separately inherited
recovery datagram channel supports bounded observation and exact receipt
acknowledgement after that stream has closed. Only the original owner may
acknowledge its retained result after durable reconciliation; observing an app
receipt does not itself establish a durable Hepta terminal. Bootstrap v2 requires
both descriptors and rejects the historical v1 handoff. See the
[Notes contract](../../support/ui/NOTES_ORGAN.md) for the finite outstanding
receipt and failure bounds; this channel is not a new grant or effect retry path.

## Development

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-ui-broker --locked
```

[tests](tests/) cover actual Session admission/identity and Notes targets within
their stated host scope. The complete setup and gate are in
[workspace setup](../README.md) and [RUN](../../support/ui/RUN.md).
Read [NOTES_ORGAN](../../support/ui/NOTES_ORGAN.md) and
[INTEGRATION_CONTRACTS](../../support/ui/INTEGRATION_CONTRACTS.md) before changing
bootstrap, cancellation, retained outcomes or the owner seam.
