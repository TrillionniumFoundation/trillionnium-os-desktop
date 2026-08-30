# Desktop contracts

The JSON files in this directory are machine-readable contract baselines.
Rust domain types live in `crates/trillionnium-contract-core` and
`crates/hepta-browser-contracts`.

- `browser-api.v1.schema.json` — typed Agent/browser requests
- `receipt.v1.schema.json` — operation evidence envelope (the journal's
  `export_redacted_jsonl` output is validated against this schema after
  lifecycle aggregation)
- `capability-permit.v1.schema.json` — short-lived typed permit
- `app-manifest.v1.schema.json` — signed trusted app metadata
- `error-codes.v1.json` — stable failure taxonomy
- `golden/` — canonical examples used by validation and future wire tests

D0 schemas are machine-readable contracts, not a production listener. D0C-02
through D0C-04 now provide host-validated strict bounded decoding,
duplicate-key rejection, authenticated connected-stream transport, deadlines,
cancellation, and response binding. Product listener activation, principal
mapping, and BrowserActor dispatch remain later D3 claims.
