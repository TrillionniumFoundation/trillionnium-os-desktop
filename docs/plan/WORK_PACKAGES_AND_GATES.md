# TrillionniumOS Desktop work packages and gates

**Origin revision:** `2026-08-28-d5`
**Status:** inherited d5 design annex; subordinate to the active d6 plan
**Active plan:** [`2026-08-29-d6`](../DESKTOP_PLAN-2026-08-29-d6.md)
**Repository mode:** `FULL_PRODUCT_REPOSITORY`

The full historical work-package definitions and risk register remain in
[the original d5 snapshot](WORK_PACKAGES_AND_GATES.d5-historical.md).
Its IMPLEMENTED, NEXT and HOST VALIDATED labels and its old immediate execution
order are historical observations, not a current completion dashboard.

Current package state comes from `manifests/project-state.v1.json`; gate and
invalidation definitions come from `manifests/gates.v1.json`. Live PR, review,
check and administration state must be read from GitHub. Use the
[d6 precedence map](D6_ANNEX_PRECEDENCE.md) and
[PR #73 decomposition](PR73_DECOMPOSITION.md) rather than merging the frozen
cumulative candidate.

## Execution order and acceptance

| Priority | Deliverable | Completion test |
| --- | --- | --- |
| P0 | D0T-03 enforced governance | Live protection, required checks, reviewer/environment separation and independent positive/negative probes on the same main identity |
| P0/P1 | Current documentation and contract correspondence | Exact generated module index, explicit inherited annexes, executable operations examples, module/contract/repository/truth regressions |
| P1 | S02-S07 mechanism foundations | Bounded independently reviewed successors, exact-head and live prospective-merge checks; no inherited closure from frozen PR #73 |
| P1 | S08 product vertical slice | Attested AgentPort to browserd to real Servo to durable receipt and response; cancellation, crash, generation replacement, stale refusal and no automatic replay |
| P1 | S09 actual desktop adapters | Trusted chrome plus real window/focus/input/IME/preemption and fail-closed OS mechanism bindings; endpoint connectivity alone is insufficient |
| P2 | S10 installed product | Same reviewed product path in one locked Debian/QEMU image, production inventory audit, restart and receipt recovery, no fixture substitution |
| P2 | D5-D7 app/capability/egress/effect delivery | Signed local app isolation; actual permit-bound OS/network enforcement; explicit external-effect reconciliation before activation |
| P2 | S11 installed update and recovery | Verified production-rooted metadata, slot staging/boot-health/rollback, restart and interruption corpus on accepted S10 image lineage |
| P3 | S12 independent hardware and release | Independent builders, fixed BOM, actual endurance/power cuts, external key custody, protected independent promotion/publication |

This table expresses required work, not that it has passed. Source corrections
can be reviewed while external facilities are unavailable, but may not close
those external gates. A passing source verifier is not an installed system,
physical test or signed release.

## Promotion and rollback

Each successor has one primary trust boundary and a reversible source delta.
No self-approval, self-merge, administrator bypass or weakening of hostile tests
is permitted. A failed, pending, cancelled, skipped or stale check is not a
pass. Head/base/input changes invalidate the affected evidence and reviews.
After ordinary protected promotion, rerun the exact integrated object before
changing canonical integrated state.

## Unresolved work

The [remaining-gap execution ledger](REMAINING_GAP_EXECUTION.md) binds the audit
findings to existing issue owners and evidence requirements without declaring
new completion truth. Missing production entrypoints, external facilities,
independent reviewers or administrative capabilities remain explicit blockers.
