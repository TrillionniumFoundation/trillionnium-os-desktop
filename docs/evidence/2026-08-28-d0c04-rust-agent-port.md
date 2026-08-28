# D0C-04 connected AgentPort Rust source evidence

**Date:** 2026-08-28  
**Claim level:** source candidate plus static and inherited reference evidence  
**Merge readiness:** not merge-ready

The candidate implements an already-connected AF_UNIX path, authenticated
transport composition, strict canonical decoding before dispatch, exactly-one
handler structure, request-owned response identity, response canonicalization,
independent result bounds, one monotonic deadline and late-result suppression.
The D0 fixture permits health only and refuses potential external effects.

Inherited independently executed reference results are:

```text
D0C-02 transport reference: 15/15 PASS
D0C-03 codec reference:     27/27 PASS
D0C-04 bridge reference:    13/13 PASS
```

These references do not prove the Rust candidate. The exact-head commands below
remain **UNEXECUTED** until a trusted Rust 1.93 runner records them:

```text
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo test --locked -p hepta-agent-port
cargo run --locked -p hepta-browserd -- --self-check
```

There is no product listener, TaskFlow mapping, BrowserActor, Servo call,
visible frame, external navigation authority, external effect, Debian image or
release claim.


## Host-validation promotion

Product tree `5abd71db79b75e400c1c1d7cb0eac85a68041cae` passed exact Rust 1.93.0 formatting, Clippy with
warnings denied, all 45 workspace tests, and the integrated 10-check browserd
self-check in workflow run `33179346462`. The five AgentPort tests
cover exactly-once request binding, pre-dispatch canonical rejection, default
denial of external navigation, late-result suppression, and handler depth
bounds. No listener, BrowserActor, Servo call, or external-effect authority was
introduced.

Machine evidence: `docs/evidence/generated/d0c04-rust193-host-result.json`.
