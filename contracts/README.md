# Desktop contracts

The JSON files in this directory are machine-readable contract baselines.
Rust domain types live in `crates/trillionnium-contract-core` and
`crates/hepta-browser-contracts`.

- `browser-api.v1.schema.json` — typed Agent/browser requests
- `receipt.v1.schema.json` — operation evidence envelope
- `capability-permit.v1.schema.json` — short-lived typed permit
- `app-manifest.v1.schema.json` — signed trusted app metadata
- `error-codes.v1.json` — stable failure taxonomy
- `golden/` — canonical examples used by validation and future wire tests

D0 schemas are not yet a production wire implementation. D0C-02 must add strict
bounded decoding, duplicate-key rejection, authenticated UDS transport,
deadlines, cancellation, and response binding.
