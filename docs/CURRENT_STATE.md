# TrillionniumOS Desktop — integrated state

**Updated:** 2026-09-08  
**Canonical plan:** `2026-08-29-d6`  
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Integrated implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`  
**Machine truth:** [`manifests/project-state.v1.json`](../manifests/project-state.v1.json)  
**Status scope:** integrated `main` facts only

This document projects the structured integrated state. It intentionally excludes unmerged implementation and candidate-only qualification. Read [`CANDIDATE_STATUS.md`](CANDIDATE_STATUS.md) for unmerged work and [`NON_CLAIMS.md`](NON_CLAIMS.md) for the current claim ceiling.

## Machine-aligned integrated work-package identifiers

The following identifiers are projected from `integrated_completed_work_packages`; their detailed evidence tiers and invalidation paths remain in the gate registry:

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

An identifier being integrated does not widen its recorded claim ceiling.

## Integrated repository foundation

The integrated `main` state contains a ten-member Rust workspace:

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

- product-boundary and dependency locks;
- bounded shared identifiers, revisions, and browser contracts;
- authenticated framing over an already-connected Unix stream;
- canonical bounded Browser API parsing;
- an exactly-one request AgentPort bridge;
- local Linux peer identity mechanisms;
- durable non-replaying receipt foundations;
- a deterministic trusted-workspace composition model;
- default-disabled AgentPort service custody;
- exact-pin Servo compile-compatibility qualification at a bounded claim level.

## Integrated local control path

```text
already-connected AF_UNIX stream
  -> kernel peer credentials and bounded authenticated framing
  -> canonical Browser API codec
  -> exactly-one request-bound AgentPort core
  -> local process/service identity checks
  -> durable receipt facts
```

This path does not by itself establish semantic principal authority, production browser dispatch, user consent, capability issuance, or an external effect.

## Product fail-closed state

The production AgentPort is not enabled by default. Until a promoted BrowserActor and installed runtime are bound through the applicable gates, product activation must fail closed rather than substitute a fixture or broaden authority.

## Repository governance observation

**Observation source:** GitHub REST API  
**Observed at:** `2026-09-08T03:15:06Z`  
**Observed main SHA:** `addaf73a48bae65f19f6bfe91c6264fd2ddb85a1`  
**Observation validity:** snapshot only; it is not live authorization after the observed `main` ref or repository settings change

At this identity-bound observation, live GitHub readback reported `main` as unprotected with required-status enforcement disabled. CODEOWNERS source existed, but source files alone did not enforce approvals or no-bypass policy. Administrative branch protection, active rulesets, protected environments, and independent review separation therefore remained open controls under issue #76.

Operational merge and release decisions must read live GitHub state rather than infer it from this snapshot. A later `main` movement or settings change requires a dedicated exact-main status update before this section may describe the newer state.

## Unmerged work

PR #73 is a frozen Draft convergence branch. It is not part of the integrated state and must be decomposed rather than merged as one unit. Its cumulative evidence does not transfer to a later head or a successor PR.

The structured manifest still contains a committed candidate snapshot from an earlier repository state. That snapshot is rendered and qualified in `CANDIDATE_STATUS.md`; it is not silently promoted into this integrated projection.

## Next bounded work

1. enable and independently verify branch protection and rulesets;
2. decompose PR #73 into bounded successor PRs;
3. qualify every successor on its own exact final head;
4. complete a real AgentPort → BrowserActor → Servo → durable-receipt vertical slice;
5. prove that slice in an exact installed QEMU image before hardware or release claims.

## Interpretation

The narrower claim always wins. Historical evidence remains useful for diagnosis but does not substitute for a current exact-head or exact-main rerun after an invalidating change.
