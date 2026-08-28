# D0C-04 Rust AgentPort source checkpoint

**Date:** 2026-08-28  
**Plan:** `2026-08-28-d5`  
**Candidate branch:** `codex/d0c04-rust-product`  
**Claim level:** source/static/reference only

## Source implemented

The candidate adds `hepta-agent-port`, which composes the D0C-02 authenticated
carrier and D0C-03 canonical Browser API codec over one already-connected
`UnixStream`.

Implemented source invariants:

1. one request frame and at most one handler call per connection;
2. canonical request decoding before handler visibility;
3. immutable peer/sequence/digest/effect/deadline dispatch context;
4. response identity copied from the validated request;
5. canonical response SHA-256 computed before transport commit;
6. effective deadline is the earlier server/request deadline;
7. late handler output is discarded without response commit;
8. handler output has independent depth/item/key/string bounds;
9. the D0 handler denies every potential external effect;
10. no listener, BrowserActor, Servo call, capability grant or automatic retry.

The crate adds no new registry package. It reuses the existing exact
`sha2=0.10.9` closure.

## Executed evidence

Independent executable references already recorded on the stacked candidate:

```text
D0C-02 authenticated transport reference   15/15 PASS
D0C-03 canonical codec reference            27/27 PASS
D0C-04 connected bridge reference           13/13 PASS
```

The specialized Rust-source/contract/lock audit reports:

```text
172/172 static checks PASS
```

The audit verifies workspace and lock integration, no-new-registry-dependency,
transport/codec composition, exactly-one dispatch shape, response binding,
deadline and output bounds, D0 effect refusal and the absence of listener,
BrowserActor and Servo authority.

## Unexecuted hard gate

The following exact-head commands remain unexecuted because this session has no
trusted Rust 1.93.0 executor and hosted jobs have previously failed before
runner assignment:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo test --locked -p hepta-browser-codec
cargo test --locked -p hepta-agent-port
cargo run --locked -p hepta-browserd -- --self-check
```

The branch and PR must remain Draft/non-merge-ready until these commands pass
against the exact head and the machine-readable validation state is updated
atomically.

## Explicit non-claims

This checkpoint does not prove or enable:

- a filesystem, abstract or TCP listener;
- systemd socket activation or service identity custody;
- BrowserActor dispatch;
- Servo compilation, window creation or rendering;
- navigation or input delivery;
- a capability grant or external effect;
- a Debian image, beta or release.
