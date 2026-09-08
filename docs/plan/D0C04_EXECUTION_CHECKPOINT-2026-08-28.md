# D0C-04 execution checkpoint — 2026-08-28

> **SUPERSEDED_HISTORICAL:** This checkpoint predates the Rust 1.93 host
> validation and validator migration recorded in the current D0C-04 evidence.
> Its source and claim ceiling remain historical; consult
> `docs/architecture/CONNECTED_AGENT_PORT_BRIDGE.md` and
> `manifests/project-state.v1.json` for current truth.

The candidate connects the authenticated bounded transport and canonical Browser
codec to an exactly-one typed handler boundary. It does not create or activate
a listener.

## Implemented source path

```text
already-connected UnixStream
  -> authenticated transport
  -> canonical typed Browser request
  -> immutable dispatch context
  -> at most one handler invocation
  -> request-owned canonical response
  -> at most one response frame
```

## Promotion gate

The PR remains Draft until exact Rust 1.93 execution passes:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo test --locked -p hepta-agent-port
cargo run --locked -p hepta-browserd -- --self-check
```

The legacy repository validator still contains a pre-D0C-03 fixed workspace
list. `tools/validate_repository_v2.py` is the compositional successor for this
candidate; before merge, the stable `tools/validate_repository.py` entry point
must be migrated atomically with `CURRENT_STATE.md`, `docs/MANIFEST.json` and
`manifests/repository-state.json`.

## Closed authority

- no filesystem, abstract or TCP listener;
- no TaskFlow principal mapping;
- no BrowserActor or Servo call;
- no external navigation/effect authority;
- no Debian image or release claim.
