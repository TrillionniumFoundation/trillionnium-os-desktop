# TrillionniumOS Desktop — integrated state

**Updated:** 2026-09-08  
**Canonical plan:** `2026-08-29-d6`  
**Canonical subject:** `main` at `addaf73a48bae65f19f6bfe91c6264fd2ddb85a1`  
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Integrated implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`  
**Status scope:** integrated `main` facts only

This file intentionally excludes unmerged candidate implementation and candidate-only qualification. Candidate work is tracked separately in [`CANDIDATE_STATUS.md`](CANDIDATE_STATUS.md).

## Integrated repository foundation

The current `main` branch contains a ten-member Rust workspace:

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

This path does not itself establish semantic principal authority, production browser dispatch, user consent, capability issuance, or an external effect.

## Product fail-closed state

The production AgentPort is not enabled by default. Until a promoted BrowserActor and installed runtime are bound through the applicable gates, product activation must fail closed rather than substitute a fixture or broaden authority.

## Repository governance state

At this snapshot, GitHub reports `main` as unprotected, with required status-check enforcement disabled. CODEOWNERS source exists, but source files alone do not enforce approvals or no-bypass policy. Administrative branch protection, active rulesets, protected environments, and independent review separation remain open controls.

## Unmerged candidate

PR #73 is a frozen Draft convergence branch. It is not part of the integrated state and is not merge-ready. Its former cumulative evidence cannot be transferred to a later head or to successor PRs.

Historical candidate references **PR #23** and **PR #27** are retained only as repository archaeology required by the current validation baseline. They are not active candidates, current evidence, or authorization to widen an integrated claim.

## Immediate integrated-state priorities

1. merge the repository-truth bootstrap through ordinary review;
2. enable and independently verify branch protection and rulesets;
3. decompose PR #73 into bounded successor PRs;
4. qualify each successor on its exact final head;
5. complete a real AgentPort → BrowserActor → Servo → durable-receipt vertical slice;
6. prove that slice in an exact installed QEMU image before hardware or release claims.

## Explicit limits

The authoritative non-claims are maintained in [`NON_CLAIMS.md`](NON_CLAIMS.md). In case of conflict, the narrower claim wins.
