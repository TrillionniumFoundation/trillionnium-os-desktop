# D0C-04 execution checkpoint — 2026-08-28

This checkpoint records the Rust connected AgentPort product candidate built on
top of the D0C-02 transport and D0C-03 canonical codec stack.

## Implemented source path

```text
already-connected UnixStream
  -> authenticated bounded transport
  -> canonical typed Browser request
  -> immutable dispatch context
  -> at most one handler invocation
  -> request-bound canonical response
  -> at most one response frame
```

The bridge owns wire identity and timing. The handler owns only the typed result
or typed Browser error. A potential external effect is refused by the D0
fixture. There is no listener, TaskFlow authority mapping, BrowserActor, Servo
runtime or effect permission in this checkpoint.

## Candidate files

- `crates/hepta-agent-port/`
- `contracts/agent-port-bridge.v1.json`
- `manifests/d0c04-candidate.json`
- `tools/validate_d0c04_rust_product.py`
- `.github/workflows/d0c04-rust-product.yml`
- `docs/architecture/CONNECTED_AGENT_PORT_BRIDGE.md`
- `docs/evidence/2026-08-28-d0c04-rust-agent-port.md`

## Promotion gate

The source must remain on a Draft PR until all commands pass against the exact
candidate head:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo test --locked -p hepta-agent-port
cargo run --locked -p hepta-browserd -- --self-check
```

A source/static pass cannot promote the candidate to host-tested Rust. Before
merge, `CURRENT_STATE.md`, `docs/MANIFEST.json` and
`manifests/repository-state.json` must be updated atomically with exact-head
execution evidence.

## Next dependency

After D0C-04 promotion, the control-plane sequence is:

```text
D0C-05 default-disabled systemd socket custody
  -> TaskFlow principal mapping
  -> BrowserActor conversion
  -> explicit local AgentPort enable decision
```

The Servo sequence remains independent:

```text
D0A-01 exact-pin compile
  -> D0A-02 trusted chrome + one content surface
  -> local fixture first frame
```
