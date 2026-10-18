# Hepta integration validation

This directory validates the A10 read-only host observer and the separately
enabled [ObjectiveStart transport](../../../services/hepta-os/OBJECTIVE_TRANSPORT.md). It does not
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
- `run_original_objective.py` and the `original_objective_*.rs` probe use the
  unchanged original Fleet/Supervisor/Agentd and an isolated enrolled test
  issuer. [ORIGINAL_OBJECTIVE.md](ORIGINAL_OBJECTIVE.md) defines ten core checks,
  seven explicit submission attempts and the optional three known-run Session
  phases. Two actual Linux host runs passed; the second also completed the
  three Session phases and one native Shell's three captured frames. Build,
  runtime and visual sources are bound separately in the
  [2026-10-18 result](../../../results/integration/2026-10-18-objective-desktop/README.md).
- The [original Objective Shell capture guide](../../ui/ORIGINAL_OBJECTIVE_SHELL.md)
  holds that same Shell across a current admitted run, retained stale history
  and an explicit replacement Session's missing projection. Its capture ACKs
  coordinate phases; the actual PNGs require independent visual review.
- `check_objective_wire.py` verifies fourteen exact original source files and
  emits a small original-declaration wire check with extraction/hash provenance.
  It compiles no Agentd crate, signs nothing and submits no actual objective.
  The optional transport's tests use the fixed original expired/all-zero wire
  fixture and scripted replies over real disposable UDS connections; those
  tests are not original-owner admission evidence.

The original-runtime results qualify test-issuer authentication and durable
admission, not production issuer assembly or an online reconciliation service.
Model turns, Operations dispatch, HOS2/device effects and Asterinas/mobile
execution remain separate gates; see [S1–S5](../../../docs/agents/R8_NEXT_SLICE.md).

The socket and parser regression tests live in
`services/hepta-os/tests/socket_contract.rs`; the timed-out metadata admission
test lives with the private transport helper. See the crate's
[RUN.md](../../../services/hepta-os/RUN.md) for complete commands.
