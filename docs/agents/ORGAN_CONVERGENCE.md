# Desktop / Hepta convergence work

The 2026-10-25 implementation continues the Asterinas derivative. Its starting
pair is Desktop `38227d33fd3ed668f0424bc153e0d3d811731597` and original Hepta
`6d6097da843f5831dfaf9cee3530da512d072a15`. Selected later owner fixes are
reviewed as small source patches; unrelated candidate evidence is not imported
as current qualification.

## Implementation tracks

| Track | Ownership | Required behavior |
| --- | --- | --- |
| Source pair | `support/release` | One Hepta commit, original history, exact lockfiles, clean final source receipts |
| Kernel safety | Asterinas capability/Unix/cgroup/VM code | Correct target capability bound, immutable credentials, honest resource-setting semantics and actual page-budget enforcement |
| Session | `ui/session` | Bounded nonblocking IPC, whole-frame deadlines, fair progress and child reaping under slow peers |
| Durable Notes | `ui/core`, `ui/app-window`, private target | Stable document identity, atomic durable document/receipt, exclusive writer and read-only old-operation recovery |
| Original owner | Hepta Agentd/memory/contracts | Original authorization, outbox/SQLite terminal state and unknown-preserving recovery |

The new named anonymous/COW page budget is a limited native resource boundary.
It must not be advertised as Linux `memory.max` or as complete accounting of
page cache, shared VMO, page tables, kernel allocations and DMA. Recovery of a
sibling domain under anonymous-page exhaustion is separately testable; full
recovery-resource protection remains a broader requirement.

## Authority and recovery

Hepta remains the only operation and authorization owner. A durable Notes
document receipt is evidence about an application effect, not a second task
ledger. New process incarnations never inherit an old target's effect grant.
The original writer may query retained receipts through a read-only recovery
path and retain `unknown` when neither authoritative history nor independent
effect evidence is available. Unknown actions are not retried as new operations.

Production composition requires independently configured issuer transport,
protected clock, durable external frontier, trusted issuer keys, authenticated
revocation state, recovered original writer and current-cut authorization.
Discovery of an installed service does not authorize a different destination;
expired or `qualification.no-effect` policies cannot authorize Notes.

## Acceptance

Retain final source identities and raw logs for each lane. The host-pair runner
proves build/test compatibility; a separate real Session/App run must prove
document bytes and revisions survive a killed application and lost response.
The original owner must reconcile to its durable terminal state without a
second effect. Explicitly run root/GUI tests when their platform is provisioned;
ignored tests remain unqualified.

The [source and build runbook](../../support/release/README.md),
[UI runbook](../../support/ui/RUN.md),
[Notes contract](../../support/ui/NOTES_ORGAN.md) and
[native security contract](../SECURITY_AND_RECOVERY.md) are the development
entry points. Final execution results belong in the integration receipt, rather
than being inferred from this plan.
