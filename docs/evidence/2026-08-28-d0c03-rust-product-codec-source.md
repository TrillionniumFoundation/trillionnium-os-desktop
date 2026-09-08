# D0C-03 Rust product codec source checkpoint

> **HISTORICAL BASELINE / STALE_EVIDENCE:** The recorded Rust host result is
> bound to `4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb`. Current source/reference
> checks remain green, but exact-head CI must rerun before promotion.

> **SUPERSEDED_HISTORICAL:** The source-only snapshot below predates the exact-head
> Rust 1.93 host validation. Current status is recorded in
> `docs/architecture/RUST_BROWSER_CODEC.md` and
> `generated/d0c03-rust-source-audit-result.json`; the historical claims are
> retained for auditability.

**Date:** 2026-08-28
**Evidence level:** source/static plus independent executable reference
**Merge-ready:** no
**Evidence lifecycle:** `STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN`
**Evidence freshness:** `STALE_EVIDENCE`
**Merge-ready machine flag:** `false`
**Stale reason:** Host result `4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb` was
recorded before the current candidate tree; run
`browser-codec-reference-and-rust-gate` on the exact candidate head before
promotion.


## Implemented

- product `hepta-browser-codec` Rust crate;
- custom bounded JSON parser with no new registry dependency beyond locked
  `sha2=0.10.9`;
- duplicate-key, float, BOM, depth, item and byte refusal;
- signed-64-bit integer domain shared with the reference implementation;
- sorted-key compact UTF-8 canonical encoding;
- current D5 request/response envelope and typed operations;
- paired session ID/generation and layered element references;
- typed navigation targets and loopback-only fixture URL policy;
- normative error-code/retry binding;
- byte-exact golden-vector tests;
- browserd self-check source integration.

## Executed evidence

The Python reference was rerun after the signed-64-bit numeric lock:

```text
27/27 PASS
py_compile PASS
golden request/response vectors byte-identical
```

`tools/validate_rust_browser_codec.py` was executed against the complete
candidate tree:

```text
96/96 static contract/source/lock/golden checks PASS
```

The generated machine-readable outputs are:

- `docs/evidence/generated/d0c03-browser-codec-reference-result.json`;
- `docs/evidence/generated/d0c03-rust-source-audit-result.json`.

## Unexecuted evidence

No trusted Rust 1.93 executor is available in the current environment, and the
repository's hosted jobs have previously failed before runner assignment.
Therefore the following remain explicitly `UNEXECUTED`:

```text
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```

The source checkpoint does not claim a listener, BrowserActor dispatch, Servo,
navigation, rendering or external-effect authority.


## Exact-head Rust 1.93 host validation

Validated source commit: `4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb`
Workflow run: `33176689873`
Result: repository validation, rustfmt, Clippy `-D warnings`, full workspace tests and `hepta-browserd --self-check` all passed. Machine evidence: `generated/d0c03-rust193-host-result.json`. This remains a no-listener, no-BrowserActor, no-Servo and no-effect checkpoint.
