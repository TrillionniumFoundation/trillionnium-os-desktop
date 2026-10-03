# TrillionniumOS Desktop documentation

This directory is the normative documentation entry point for the desktop product implemented by this repository. The repository itself—not a separate local tree—is the canonical source for plans, contracts, implementation, tests, packaging, and evidence definitions.

## Project truth

- [`CURRENT_STATE.md`](CURRENT_STATE.md) — recorded integrated qualification baseline;
- [`source-state.v1.json`](source-state.v1.json) — current Cargo source inventory, without qualification promotion;
- [`CANDIDATE_STATUS.md`](CANDIDATE_STATUS.md) — unmerged candidate state and evidence freshness rules;
- [`NON_CLAIMS.md`](NON_CLAIMS.md) — authoritative current limits;
- [`../manifests/project-state.v1.json`](../manifests/project-state.v1.json) — machine project-state registry;
- [`../manifests/gates.v1.json`](../manifests/gates.v1.json) — work-package, evidence-tier, review, and invalidation registry;
- [`DESKTOP_PLAN-2026-08-29-d6.md`](DESKTOP_PLAN-2026-08-29-d6.md) — active product plan;
- [`MANIFEST.json`](MANIFEST.json) — documentation and evidence-definition metadata.
- [`modules/README.md`](modules/README.md) — one-to-one technical development contracts for every Cargo workspace member.
- [`DEVELOPMENT_GUIDE.md`](DEVELOPMENT_GUIDE.md) — actual implementation entry points, verification and product-wide documentation gaps.

When machine state, prose, a PR description, or a historical artifact disagree, no broader claim is allowed automatically. Resolve the conflict and apply the narrower claim until exact evidence is regenerated.

## Execution and governance

- [`plan/PROJECT_TRUTH_AND_EVIDENCE.md`](plan/PROJECT_TRUTH_AND_EVIDENCE.md)
- [`plan/GATE_CONTRACTS_AND_INVALIDATION.md`](plan/GATE_CONTRACTS_AND_INVALIDATION.md)
- [`plan/PR73_DECOMPOSITION.md`](plan/PR73_DECOMPOSITION.md)
- [`governance/BRANCH_PROTECTION_REQUIRED.md`](governance/BRANCH_PROTECTION_REQUIRED.md)
- [`security/SECURITY_CONTROL_MATRIX.md`](security/SECURITY_CONTROL_MATRIX.md)

Historical plans and evidence remain useful for archaeology, but they must not override current `main`, current exact-head evidence, active policy, or a narrower claim ceiling.

The [2026-10-02 source audit](audit/PROJECT_AUDIT-2026-10-02.md) records reproduced
defects, local regression validation and the remaining product acceptance gaps.
It does not promote the historical qualification baseline or release authority.


## Authenticated update readback

[Authenticated update journal and readback](architecture/AUTHENTICATED_UPDATE_READBACK.md) describes the additive G6 / D7 / S11 exact-signature capsule and actual read-only OpenSSL/file readback candidate, preserving the v1 profile and installed qualification limits.

[G6a installed immutable A/B fixture](architecture/G6A_IMMUTABLE_AB_FIXTURE.md)
describes the separate executable Debian/QEMU guest selector, real signed
dm-verity roots and persistent attempt/fault matrix. Its test fixture does not
qualify desktop health, firmware trust, production floor or release activation.
