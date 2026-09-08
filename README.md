# TrillionniumOS Desktop

> **Current maturity:** architecture and source-qualification prototype. This repository does **not** yet contain a production-qualified, physically tested, signed desktop operating-system release.

**Canonical plan:** `2026-08-29-d6`  
**Integrated implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`  
**Machine truth:** [`manifests/project-state.v1.json`](manifests/project-state.v1.json)

This repository develops the desktop runtime, trust boundaries, contracts, qualification tooling, packaging, and release controls for TrillionniumOS Desktop. The design centers on a trusted native shell, a separately controlled browser runtime, authenticated local AgentPort transport, explicit capabilities, durable receipts, and fail-closed recovery.

## Read project status before using the code

The following files separate facts that are often incorrectly conflated:

- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — facts integrated on the current `main` branch;
- [`docs/CANDIDATE_STATUS.md`](docs/CANDIDATE_STATUS.md) — unmerged candidates and their evidence rules;
- [`docs/NON_CLAIMS.md`](docs/NON_CLAIMS.md) — capabilities and qualification levels the project does not currently claim;
- [`docs/status-documents.v1.json`](docs/status-documents.v1.json) — closed structured source for integrated-state projection, candidate freeze, governance observations, and bounded next actions;
- [`contracts/status-documents.v1.schema.json`](contracts/status-documents.v1.schema.json) — closed JSON Schema enforced before the human-readable projection is accepted;
- [`docs/DESKTOP_PLAN-2026-08-29-d6.md`](docs/DESKTOP_PLAN-2026-08-29-d6.md) — active product plan;
- [`docs/plan/PR73_DECOMPOSITION.md`](docs/plan/PR73_DECOMPOSITION.md) — mandatory decomposition of the frozen convergence candidate.

`docs/CURRENT_STATE.md` is generated deterministically from the structured status record. Free-form edits, synonymous self-merge instructions, unknown action types, or unbound governance observations fail repository validation rather than silently becoming project truth.

The repository registry validator binds the exact reviewed schema `$id` set. Adding, removing, or substituting a schema therefore requires an explicit reviewed code change rather than changing a permissive count.

A source file, fixture, hosted CI run, QEMU result, or document is not evidence of a production installation unless the applicable gate explicitly binds the exact commit, build inputs, image digest, environment, review decision, and claim ceiling.

## What is present on `main`

`main` contains a ten-package Rust workspace covering the desktop daemon scaffold, AgentPort daemon, authenticated Unix-stream transport, canonical browser codec, AgentPort bridge, peer attestation, shared contracts, session/receipt state, and trusted-workspace composition model.

The product AgentPort remains default-disabled and fail-closed until a promoted BrowserActor/runtime binding exists. Current integrated status is deliberately narrower than the cumulative development branch.

## What is not yet established

The repository does not currently claim a complete installed desktop, production BrowserActor activation, unrestricted external navigation, real external-effect authority, signed A/B update and recovery qualification, fixed-hardware endurance, protected signing-key custody, or a production release. See [`docs/NON_CLAIMS.md`](docs/NON_CLAIMS.md) for the authoritative list.

## Local verification

Use the locked toolchain and dependencies:

```bash
make validate
make truth
make fmt
make check-rust
make clippy
make test
make self-check
```

Or run the aggregate target:

```bash
make check
```

A passing local run is development feedback only. It does not replace exact-head CI, installed-image evidence, independent review, hardware qualification, or release authorization.

## Development rules

- Keep one primary trust boundary per pull request.
- Do not transfer tests, artifacts, approvals, or evidence from an older head SHA.
- State explicit non-claims for every candidate.
- Keep fixture, qualification, development, and production dependency graphs physically separable.
- Never make a gate pass by deleting hostile tests, weakening admission checks, widening permissions, substituting a fixture, or editing generated evidence by hand.

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), and the pull-request template before proposing changes.
