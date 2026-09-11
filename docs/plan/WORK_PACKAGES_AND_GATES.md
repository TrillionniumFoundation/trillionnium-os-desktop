# TrillionniumOS Desktop work packages and gates — d6 applicability

**Source revision:** `2026-08-28-d5`
**Applicable plan:** `2026-08-29-d6`
**Status:** inherited requirements; subordinate to d6; not current implementation status
**Repository mode:** `FULL_PRODUCT_REPOSITORY`

The original detailed decomposition is retained without alteration in
[WORK_PACKAGES_AND_GATES-d5.md](WORK_PACKAGES_AND_GATES-d5.md) as a historical
record. Its former active-plan header and IMPLEMENTED labels describe that
revision, not current main. Apply the [d6 applicability table](ANNEX_APPLICABILITY.md)
and the [active d6 plan](../DESKTOP_PLAN-2026-08-29-d6.md) before using a task.
The current machine gate registry and [PR73 decomposition](PR73_DECOMPOSITION.md)
are authoritative for dependency order, review and claim ceilings.

## Current execution map

| Product milestone | Bounded successor work | Required evidence, not a completion assertion |
| --- | --- | --- |
| D0T truth and governance | S01 and D0T-03 | Consistent structured state, actual protected-main settings, independent review and no-bypass readback. |
| D0C deterministic core | S02–S05 | Checked contracts, canonical codec, request custody, non-replaying durable receipts and hostile source/host tests. |
| D0A/D2 browser behavior | S07 | Exact-pin upstream behavior, retained-node resolution and exactly-one callback with explicit unsupported cases. |
| D3 product control | S06 and S08 | Attested AgentPort through product browserd, concrete BrowserActor/Servo, durable receipt and response on one exact object. |
| D4 human/Agent collaboration | S08 and S09 | Real focus, input, IME, preemption and stale-reference behavior, not only a pure model. |
| D1/D2I installed substrate | S10 | Current product path installed in an exact locked QEMU image; fixture and product inventories stay separate. |
| D5 trusted applications | Separate bounded application work | Verified bundles, distinct synthetic origins, storage/CSP/revocation and visible trust indicators. |
| D6 capabilities and egress | Separate bounded service work | Concrete permit, resolver, TLS, connected-peer and redirect enforcement, including browser bypass corpus. |
| D7 recovery and updates | S05, S08 and S11 | Durable reconciliation, actual image/slot/health/rollback bindings, no duplicate uncertain effect and installed fault corpus. |
| D8 hardware qualification | S12 external facilities | Fixed BOM, numeric measurements, real 24/72-hour endurance and non-graceful power interruption. |
| D9 release | S12 protected promotion | Independent builds, rooted evidence, offline/HSM custody, signer/promoter/publisher separation and protected publication. |

## Acceptance protocol

A work package needs implementation, executable positive/negative tests, exact
head and current prospective merge, bounded digest-bound evidence, independent
review, protected integration and the required exact-main rerun. Source,
qualification, development and production profiles remain distinct. A current
source test does not close an installed-image, hardware or release gate.

The documentation package is accepted only when the module index is generated,
module/contract/feature inventories agree, operations examples execute, inherited
annex applicability is explicit and no new status projection competes with the
machine registries. It is not a product-completeness percentage.

## Failure and resumption

Keep the failing exact source object and first failing command. Classify source
regressions, stale parent identity, unavailable administration, absent independent
review and missing external facilities separately. A failed or skipped check is
never promoted to success. Do not remove hostile tests, broaden default features,
use a fixture as product runtime, or merge around protection to resume progress.

The September 12 audit is tracked in repository issue #117. That issue is an
execution ledger only; checked boxes cannot override the machine gate registry
or exact-object evidence.
