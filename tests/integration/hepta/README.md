# Hepta integration validation

This directory validates the A10 read-only host observer candidate. It does not
implement or claim A07's Hepta → HOS2 durable-effect gate.

- `check_upstream_contract.py` verifies exact source provenance and can emit a
  small Rust program using original upstream declarations and EventBuffer.
- `agentd_fixture.py` is a labelled external socket fixture for actual Session
  IPC/worker → observer → UDS projection and stale-state checks.
- `EVIDENCE.md` records the commands, results, limitations and remaining gates.

The socket and parser regression tests live in
`services/hepta-os/tests/socket_contract.rs`; the timed-out metadata admission
test lives with the private transport helper. See the crate's
[RUN.md](../../../services/hepta-os/RUN.md) for complete commands.
