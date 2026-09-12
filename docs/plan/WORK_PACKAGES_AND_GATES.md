# TrillionniumOS Desktop work packages and gates

**Plan revision:** `2026-08-29-d6`
**Status:** active d6 index and precedence record
**Repository mode:** `FULL_PRODUCT_REPOSITORY`

## Plan inheritance and precedence

The active executive plan is [`../DESKTOP_PLAN-2026-08-29-d6.md`](../DESKTOP_PLAN-2026-08-29-d6.md).
Machine truth in `manifests/project-state.v1.json` and `manifests/gates.v1.json`
controls implementation stage, evidence tier and claim ceiling. The archived
[`WORK_PACKAGES_AND_GATES.d5-historical.md`](WORK_PACKAGES_AND_GATES.d5-historical.md)
contains historical scheduling detail only and cannot authorize activation or
promote evidence.

## Gate rule

Each work package must declare an exact source head, inputs, environment,
outputs, review authority and claim ceiling. A gate failure or changed input
invalidates dependent evidence. Candidate branches are rebased and rerun on
current `main`; their artifacts, approvals and claims do not transfer by name.

The detailed d6 execution sequence is maintained in the canonical plan and the
closure plan. This page is a stable entry point so old d5 links cannot be read
as active authority.
