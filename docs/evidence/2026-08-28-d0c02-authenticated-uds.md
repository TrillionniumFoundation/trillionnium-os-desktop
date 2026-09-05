# D0C-02 authenticated UDS carrier evidence

> **HISTORICAL BASELINE / STALE_EVIDENCE:** This checkpoint records the D0C-02
> host result at its bound source head. The current candidate changed declared
> invalidation inputs after that run; perform a fresh exact-head Rust 1.93 run
> before any merge-readiness or integrated-main claim.

**Date:** 2026-08-28  
**Claim level:** exact-head Rust 1.93 host validation  
**Evidence lifecycle:** `STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN`
**Evidence freshness:** `STALE_EVIDENCE`
**Merge-ready:** `false`
**Stale reason:** Host result `786debc12aa8d790b231397c1a3341fbf89de080` was
recorded before the current candidate tree; run `agent-transport-reference` on
the exact candidate head, then update the bound evidence before promotion.

**Candidate head:** `786debc12aa8d790b231397c1a3341fbf89de080`  
**Workflow run:** `33167838644`  
**Merge readiness:** historical host result only; exact-head evidence is
required for current promotion.

## Implemented boundary

The candidate contains Linux/Android `SO_PEERCRED` peer identity, an explicit
PID/UID/GID policy, a fresh 256-bit connection nonce, fixed 88-byte framing,
a 256 KiB pre-allocation payload bound, SHA-256 binding, strict sequences,
and one absolute monotonic deadline. It starts no listener, socket path, TCP
endpoint, WebDriver endpoint, or external network operation.

The registry closure is exact-name/version/checksum allowlisted in
`manifests/cargo-external-allowlist.json` and represented in `Cargo.lock`.

## Exact-head execution

GitHub-hosted Ubuntu 24.04 installed:

```text
rustc 1.93.0 (254b59607 2026-01-19)
host x86_64-unknown-linux-gnu
runner image ubuntu-24.04@20260823.283.1
```

The historical candidate head recorded above passed:

```text
python3 tools/validate_repository.py
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo run -p hepta-browserd -- --self-check
```

Rust tests: 25 passed, 0 failed. Browserd returned an `ok=true` D0 self-check
with eight checks and final revisions `2/3/3/3`. Machine evidence is
`docs/evidence/generated/d0c02-rust193-host-result.json`.

Those results remain a bounded historical baseline. Because the current
candidate changed D0C-02 invalidation inputs, they are stale for promotion;
rerun the permanent gate on the exact current candidate head before treating
the carrier as current evidence.

## Independent implementation

The standard-library Python reference remains an independent protocol oracle.
Its 15/15 fault and round-trip checks passed.

## Remaining closed gates

This work package does **not** implement or claim a product Unix listener,
systemd custody, service UID/cgroup identity, canonical Browser API decoding,
BrowserActor dispatch, Servo, a visible WebView, a Debian image, external
navigation, capability use, or external effects.
