# Remaining audit gaps: execution and acceptance ledger

Audit baseline: integrated `main` `854d0341eaba43408edc014297ea8af43ffcc87e`;
source candidate `8bc2ea084c2ce69ba83ad277418aa20a7865d69b`.
This is a requirements/ownership ledger, not a closure certificate. Live heads,
checks and settings must be reread; none of the rows below is self-certified.

| Audit finding | Existing work boundary | Required action | Evidence required to close |
| --- | --- | --- | --- |
| Unenforced main protection | #76 / D0T-03 / PR #110 | Apply reviewed administration policy through an authorized administration interface, read it back and perform independently rooted probes | Current-main-bound settings and independent signed positive/negative results; source files alone insufficient |
| Stale module index | #78 / module-documentation successor | Generate index from the existing module registry; fail on exact byte drift and hostile mutations | Final-head and prospective-merge documentation tests, independent review, protected integration and exact-main rerun |
| Incorrect journal directory mode | #83 / receipt documentation | Use 0700 directories and 0600 files; execute the example on a temporary filesystem | Documentation regression and execution result, not an installed-journal claim |
| Ambiguous d5 authority | #78 / documentation | Preserve d5 history, replace active entrypoints with explicit d6 inheritance and overrides | Header/precedence regression and review; no evidence or completed-package relabeling |
| Core product path absent | #86 / S08 | Wire product daemon, authenticated AgentPort, concrete Servo actor, durable receipt and typed response | Exact product execution plus crash/cancel/lost-completion/stale-reference/journal continuity tests |
| Desktop model versus real OS adapter gap | #87 / S09 | Implement real trusted surface/input/focus/IME, human preemption and display scaling contracts | Headed-host and installed-image input traces and hostile tests; pure models insufficient |
| Qualification image versus installed product gap | #88 / S10 | Install the same reviewed product binaries/units and run the vertical slice in a locked image | Exact image/input/source identities and product inventory; fixture replacement forbidden |
| Failure closure without complete recovery operations | #83, #86 and #89 | Define authorized reconciliation, read-only diagnostics, capacity/archival and boot recovery | Persistence cutpoint and installed restart tests; unresolved possible effects remain never-automatic |
| App/capability/egress/Agent product detail | d6 D3-D7 | Bind model proposals to typed task/consent budgets; implement signed apps and permit-bound actual I/O | Independent runtime/security review and complete origin/egress/rebinding/worker/consent corpus |
| Update source versus installed and signed update gap | #89 / S11 | Connect external trust-root signature verification, inactive-slot staging, boot health and rollback | Accepted S10 image lineage plus installed update/recovery matrix; source exception injection not raw power loss |
| Independent hardware/key/release facilities | #90 / S12 | Use two independent builders, fixed physical BOM, actual endurance/power and offline/HSM dual control | Externally rooted signed packet, separate promoter/publisher and protected release; no fabricated identities or elapsed time |

## Cross-module execution acceptance

An end-to-end trace must distinguish: mechanism admission; semantic
principal/consent decision; durable request admission; dispatch intent;
possible engine execution; durable terminal/indeterminate outcome; response
delivery. The owner of each transition, deadline, cancellation check and
persistence barrier must be named. No response-loss or process-loss branch may
implicitly retry a potentially dispatched effect.

The hostile matrix includes peer exit and PID reuse, queued cancellation,
IME/human preemption, navigation and stale semantic references, engine failure
before/after possible dispatch, receipt write/fsync failure, content crash,
reconstruction, transport disconnect, restart, disk-full and capacity limits.
Measurement records include frame/input/observe/act/receipt-sync/recovery
latency and RSS/FD/PID/queue growth under a declared environment.

## Stop and resume

When the required administration interface, independent reviewer, build
facility, installed system, physical device or protected key holder is not
available, record that specific blocker and exact resume input. Preserve
reviewable source changes and their actual test results. Do not change machine
truth, close the external issue, weaken a gate, merge the frozen cumulative
branch, or write `all_gaps_closed=true` to compensate for a missing facility.
