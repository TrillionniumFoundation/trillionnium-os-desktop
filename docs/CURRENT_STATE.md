<!-- generated from docs/status-documents.v1.json; do not edit by hand -->
# TrillionniumOS Desktop — integrated state

**Updated:** 2026-09-08
**Canonical plan:** `2026-08-29-d6`
**Repository mode:** `FULL_PRODUCT_REPOSITORY`
**Integrated implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`
**Machine truth:** [`manifests/project-state.v1.json`](../manifests/project-state.v1.json)
**Structured projection record:** [`docs/status-documents.v1.json`](status-documents.v1.json)
**Status scope:** integrated `main` facts only

This file is a deterministic projection of closed structured data. Read [`CANDIDATE_STATUS.md`](CANDIDATE_STATUS.md) for unmerged work and [`NON_CLAIMS.md`](NON_CLAIMS.md) for the claim ceiling.

## Integrated work packages

- `D0T-01`
- `D0T-02`
- `D0R-01`
- `D0R-02`
- `D0R-03`
- `D0C-01`
- `D0C-02`
- `D0C-03`
- `D0C-04`
- `D0C-05`
- `D0C-06`
- `D0A-00`
- `D0A-01`

An integrated identifier does not widen its recorded claim ceiling.

## Integrated workspace

```text
apps/hepta-browserd
apps/hepta-agent-portd
crates/hepta-agent-transport
crates/hepta-browser-codec
crates/hepta-agent-port
crates/hepta-peer-attestation
crates/trillionnium-contract-core
crates/hepta-browser-contracts
crates/hepta-session-core
crates/hepta-workspace-composition
```

The integrated foundation includes:

- product-boundary and dependency locks
- bounded shared identifiers, revisions, and browser contracts
- authenticated framing over an already-connected Unix stream
- canonical bounded Browser API parsing
- an exactly-one request AgentPort bridge
- local Linux peer identity mechanisms
- durable non-replaying receipt foundations
- a deterministic trusted-workspace composition model
- default-disabled AgentPort service custody
- exact-pin Servo compile-compatibility qualification at a bounded claim level

## Local control path

```text
already-connected AF_UNIX stream
  -> kernel peer credentials and bounded authenticated framing
  -> canonical Browser API codec
  -> exactly-one request-bound AgentPort core
  -> local process/service identity checks
  -> durable receipt facts
```

This path does not establish semantic principal authority, production browser dispatch, user consent, capability issuance, or an external effect.

## Product fail-closed state

Production AgentPort remains disabled by default until a promoted BrowserActor and installed runtime satisfy their gates.

## Repository governance observation

**Observation kind:** `github_repository_settings_snapshot`
**Observation source:** `github_rest_api`
**Observed repository:** `TrillionniumFoundation/trillionnium-os-desktop`
**Observed branch:** `main`
**Observed at:** `2026-09-08T03:15:06Z`
**Observed main SHA:** `addaf73a48bae65f19f6bfe91c6264fd2ddb85a1`
**Observation validity:** `snapshot_only`
**Invalidated by:** `main_ref_change`, `repository_settings_change`

At this identity-bound snapshot, GitHub REST reported `main` as unprotected and required status checks as disabled. Source CODEOWNERS files do not enforce approvals or no-bypass policy. Administrative controls remain tracked by issue #76.

Operational decisions must read live GitHub state; either declared invalidation event makes this snapshot historical.

## Unmerged work

PR #73 is a `draft_frozen` candidate governed by issue #78 and policy `never_merge_as_one_unit`. It is not integrated, and its evidence does not transfer to successors.

The committed candidate snapshot remains in `CANDIDATE_STATUS.md` and is not silently promoted.

## Next bounded work

1. enable and independently verify branch protection and rulesets on `main` under issue #76;
2. decompose frozen PR #73 into bounded successor pull requests under issue #78;
3. qualify every member of `bounded_successor_pull_requests` on its own exact final head under issue #78;
4. complete the `agentport_browseractor_servo_receipts` vertical slice under issue #86;
5. prove the slice in an `exact_installed_qemu_image` before hardware or release claims under issue #88.

## Interpretation

The narrower claim wins. Historical evidence cannot replace a current exact-head or exact-main rerun after invalidation.
