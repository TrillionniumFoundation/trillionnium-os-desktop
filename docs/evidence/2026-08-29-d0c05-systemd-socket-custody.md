# D0C-05 default-disabled systemd socket custody

**Date:** 2026-08-29  
**Branch:** `codex/d0c05-systemd-custody-v2`  
**Validated source head:** `7be7121b1d2593a0e708ec9ade189ef84ab245da`  
**Status:** `HOST_VALIDATED_DEFAULT_DISABLED_NO_PRODUCT_LISTENER`

## Implemented source

- one filesystem AF_UNIX stream path owned by systemd;
- `Accept=yes`, backlog 8, maximum 8 simultaneous connection services;
- dedicated `hepta-agent` and `hepta-browserd` package identities;
- per-connection inherited-stream service with no bind/listen code;
- exact `SO_PEERCRED` plus pidfd/procfs/start-time/cgroup/unit attestation;
- one D0C-04 request per process;
- hard process lifetime and sandbox controls;
- default-disabled preset and an absent explicit enable marker;
- static contract/source/package audit and permanent CI.

## Exact-head validation

The source head passed the following independent GitHub Actions runs on
Ubuntu 24.04 using Rust 1.93.0:

| Gate | Run | Result |
| --- | ---: | --- |
| `agent-port-custody` | `33190387511` | PASS |
| repository-wide `desktop-ci` | `33190387553` | PASS |
| codec/reference and exact-head Rust regression | `33190387564` | PASS |

The custody workflow job `98914075761` passed every step:

```text
python3 tools/validate_repository.py
python3 tools/verify_systemd_socket_custody.py
systemd-sysusers account mapping
systemd-analyze verify
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
cargo run --locked -p hepta-agent-portd -- --self-check
claim-ceiling recheck
```

Machine evidence is
`docs/evidence/generated/d0c05-rust193-host-result.json`.

## What the host evidence proves

- checked-in unit syntax and account mappings are valid;
- the exact Rust graph compiles without warnings under the pinned toolchain;
- peer attestation, transport, codec, AgentPort and service self-check tests pass;
- the connection binary accepts only an inherited stream and contains no
  product bind/listen path;
- the preset remains disabled and the enable marker is not shipped;
- no TCP/WebDriver endpoint, BrowserActor, Servo call or effect authority was
  introduced.

## Explicit non-claims

- No product listener was started by this host gate.
- No QEMU PID 1 activation has yet been demonstrated.
- No TaskFlow principal is mapped.
- No BrowserActor or Servo call exists.
- No external navigation or effect is authorized.

Host validation does not authorize socket activation. The first live
socket-activation claim requires D1 QEMU evidence showing PID 1,
sysusers/tmpfiles application, socket ownership and mode, default-disabled
negative behavior, explicit test-marker positive activation, unauthorized-peer
refusal, one authorized fixture request, per-connection service teardown, and
recovery after process termination. The marker remains absent from the product
image after that test.
