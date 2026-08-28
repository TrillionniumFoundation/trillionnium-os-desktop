# D0C-04 promotion gate

The `codex/d0c04-rust-product` candidate is promoted only when all checks below
pass against the exact pull-request head:

```bash
python3 tools/agent_port_bridge_reference.py
python3 tools/validate_rust_browser_codec.py
python3 tools/validate_rust_agent_port.py
python3 tools/validate_repository.py
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo test --locked -p hepta-browser-codec
cargo test --locked -p hepta-agent-port
cargo run --locked -p hepta-browserd -- --self-check
```

Promotion also requires the machine-readable contracts and manifests to retain
all of the following false values:

```text
listener
browser_actor
servo
capability_grant
external_effect_authorized
automatic_retry
```

A reference PASS, source audit, successful compile, or local socketpair test is
not evidence of a listener, browser runtime, visible page, navigation, input,
Debian image or release.
