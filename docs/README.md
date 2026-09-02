# TrillionniumOS Desktop documentation

This directory is the normative documentation entry point for the desktop
product implemented by this repository. The repository itself—not a separate
local documentation tree—is the canonical source for plans, contracts,
implementation, tests, packaging, and release evidence.

## Canonical truth

- [`../manifests/project-state.v1.json`](../manifests/project-state.v1.json) —
  single machine project status
- [`../manifests/gates.v1.json`](../manifests/gates.v1.json) — work-package,
  evidence-tier, review, and invalidation registry
- [`../manifests/modules.v1.json`](../manifests/modules.v1.json) — exact Cargo
  module, documentation, feature, binary, owner, contract, test, and workflow
  inventory
- [`DESKTOP_PLAN.md`](DESKTOP_PLAN.md) — stable plan index
- [`DESKTOP_PLAN-2026-08-29-d6.md`](DESKTOP_PLAN-2026-08-29-d6.md) — active plan
- [`CURRENT_STATE.md`](CURRENT_STATE.md) — human-readable integrated state
- [`MANIFEST.json`](MANIFEST.json) — documentation status and evidence links

## d6 annexes

- [`plan/PROJECT_TRUTH_AND_EVIDENCE.md`](plan/PROJECT_TRUTH_AND_EVIDENCE.md)
- [`plan/GATE_CONTRACTS_AND_INVALIDATION.md`](plan/GATE_CONTRACTS_AND_INVALIDATION.md)
- [`plan/BLOCKER_CLOSURE_LEDGER-2026-08-29.md`](plan/BLOCKER_CLOSURE_LEDGER-2026-08-29.md)
- [`architecture/RUNTIME_TOPOLOGY_AND_FAILURE_MODEL.md`](architecture/RUNTIME_TOPOLOGY_AND_FAILURE_MODEL.md)
- [`architecture/D3_INTEGRATED_RUNTIME_QUALIFICATION.md`](architecture/D3_INTEGRATED_RUNTIME_QUALIFICATION.md)
- [`security/THREAT_MODEL_V2.md`](security/THREAT_MODEL_V2.md)
- [`security/SECURITY_CONTROL_MATRIX.md`](security/SECURITY_CONTROL_MATRIX.md)
- [`release/RELEASE_SECURITY_AND_QUALIFICATION.md`](release/RELEASE_SECURITY_AND_QUALIFICATION.md)

The previous d5 and d4 plans remain recoverable history. They must not override
d6 project, process, authority, evidence, revision, network, update, or release
decisions.

The Android/mobile company repository
`TrillionniumFoundation/trillionnium-os` is a sibling reference, not a source
directory, workspace member, submodule, or default build dependency. The exact
reviewed reference and rejected mobile authorities are recorded in
`manifests/upstream-reference-review.v1.json`.
