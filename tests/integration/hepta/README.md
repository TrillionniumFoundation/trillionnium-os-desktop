# Hepta integration validation

This directory validates the A10 read-only host observer candidate. It does not
implement or claim A07's Hepta → HOS2 durable-effect gate.

- `check_upstream_contract.py` verifies exact source provenance and can emit a
  small Rust program using original upstream declarations, lifecycle transition
  methods/accepted-phase expression and EventBuffer.
- `agentd_fixture.py` is a labelled external socket fixture for actual Session
  IPC/worker → observer → UDS projection and stale-state checks.
- `EVIDENCE.md` records the commands, results, limitations and remaining gates.
- `run_original_agentd.py` and `original_agentd_probe.rs` are the separate
  original-source build/process gate. Default mode performs only preflight;
  [ORIGINAL_AGENTD.md](ORIGINAL_AGENTD.md) records commands, historical resource
  blockers and the [executed native ARM64 result](evidence/2026-10-17-original-agentd-arm/README.md).
  All eight original-process read checks passed on the fixed source; continuous
  Session/Shell integration and authenticated effects remain separate gates.
- `test_original_process_guard.py` exercises the original-process harness's
  Linux child identity and cleanup guard using disposable Python children,
  kernel WNOWAIT/ECHILD results and safe signal spies. It does not build or
  launch original Agentd.

The socket and parser regression tests live in
`services/hepta-os/tests/socket_contract.rs`; the timed-out metadata admission
test lives with the private transport helper. See the crate's
[RUN.md](../../../services/hepta-os/RUN.md) for complete commands.
