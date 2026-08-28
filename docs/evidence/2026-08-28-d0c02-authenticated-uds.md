# D0C-02 authenticated UDS carrier evidence

**Date:** 2026-08-28  
**Claim level:** source candidate plus static repository validation  
**Merge readiness:** not merge-ready

## Source present

The candidate contains:

- Linux/Android kernel peer-credential extraction through `SO_PEERCRED`;
- explicit PID/UID/GID peer policy;
- a fresh 256-bit server challenge nonce from `/dev/urandom`;
- fixed, versioned, pre-allocation length-bounded binary framing;
- SHA-256 payload binding;
- strictly increasing request sequences and replay rejection;
- one absolute monotonic operation deadline across header and payload;
- browserd self-check integration using only `UnixStream::pair()`;
- no listener, socket path, TCP endpoint, WebDriver endpoint, or external
  network operation.

The registry dependency closure is exact-name/version/checksum allowlisted in
`manifests/cargo-external-allowlist.json` and represented in `Cargo.lock`.

## Executed in this development environment

- JSON and TOML construction/parsing for the candidate metadata;
- dependency-closure and checksum cross-check while constructing the lock;
- static review of the transport source and product listener boundary.

## UNEXECUTED exact-head checks

The environment had no Rust toolchain, and GitHub hosted jobs were observed
failing before runner assignment. The following are therefore **UNEXECUTED**:

```text
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```

No host-validation or merge-ready claim may be made until those commands pass
against the exact candidate head and the resulting evidence records the
toolchain identity and commit SHA.

## Remaining gates

Dedicated service identities, socket custody, systemd unit/cgroup binding,
strict canonical Browser API decoding, TaskFlow principal mapping,
BrowserActor dispatch, crash/reconnect handling, and explicit product listener
activation remain closed.
