# D0C Rust product source checkpoint

This checkpoint adds source for `hepta-browser-codec` and `hepta-agent-port` on
top of the D0C reference stack.

Performed in the current environment:

- parsed every JSON and TOML document;
- ran the independent D0C-02, D0C-03 and D0C-04 references;
- validated source topology and forbidden-authority markers;
- checked Rust lexical delimiter balance and unsafe/listener absence;
- verified effect-class, domain-conversion and response-binding markers;
- executed 54 independent transport/codec/bridge conformance checks;
- executed 3 fail-closed overlay-application checks;
- executed 17 offline Rust/toolchain/Cargo-lock checks.

Not performed because no Rust toolchain was available and hosted jobs received
no runner:

```text
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```

The source must remain non-merge-ready until those commands pass against an
exact candidate head. Reference execution is supporting evidence, not a
replacement for Rust execution.

Additional source delivered in this checkpoint:

- recursive raw-shape validation for every nested operation variant;
- explicit lexicographic canonicalization independent of `serde_json::Map` features;
- byte-exact reuse of all six reference golden vectors in Rust tests;
- conversion into `hepta-browser-contracts::BrowserOperation`;
- acceptance-anchored monotonic deadline conversion;
- an honest D0 fixture that succeeds only for health;
- connected transport → codec → AgentPort self-check source;
- fail-closed, idempotent checkout application tooling;
- verified-offline Rust component verifier and isolated-prefix installer.
