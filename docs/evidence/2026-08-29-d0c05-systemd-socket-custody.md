# D0C-05 default-disabled systemd socket custody

**Date:** 2026-08-29  
**Candidate branch:** `codex/d0c05-systemd-custody-v2`  
**Status:** `SOURCE_CANDIDATE_VALIDATION_PENDING`

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

## Validation required before promotion

The following results must be attached to the exact candidate head before this
checkpoint may be changed to host-validated:

```text
python3 tools/validate_repository.py
python3 tools/verify_systemd_socket_custody.py
systemd-analyze verify ...
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
cargo run --locked -p hepta-agent-portd -- --self-check
```

## Explicit non-claims

At this candidate checkpoint:

- the package does not ship `/etc/hepta/enable-agent-port`;
- the preset does not enable the socket;
- no product listener is demonstrated;
- no QEMU PID 1 activation is demonstrated;
- no TaskFlow principal is mapped;
- no BrowserActor or Servo call exists;
- no external effect is authorized.

Host validation of source and unit syntax will not by itself authorize socket
activation. The first enabled-listener claim requires D1 QEMU evidence showing
PID 1, sysusers/tmpfiles application, socket ownership, unauthorized-peer
refusal, one successful authorized fixture request, service teardown, and
recovery after process termination.
