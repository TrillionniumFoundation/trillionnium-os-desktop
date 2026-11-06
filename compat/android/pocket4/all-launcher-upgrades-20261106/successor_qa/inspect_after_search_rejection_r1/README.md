# Read the current UI after the safely rejected search click

This candidate uses the **unchanged already staged owned worker**, original
adapter, helper, recorder and held R5 bindings. It declares only a new
`inspect` sequence, on existing flow
`pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe`, owned task **878**.
Its new step is `inspect-after-search-rejection-01`. There is no selector,
click, text input, focus transfer, launch, cleanup, installation, permission
change or reconciliation in this request. It has not been submitted by this
agent.

The frozen `Flow.begin` checks previous UNKNOWN actions when a **new mutation**
is requested. This candidate's operation is `owned-qa` with mutation false.
The original read-only path can therefore observe the current state while the
failed case remains unchanged. This is not a new flow, an alternative UI
channel, or a mutation allowed by another request key. Its key only identifies
one new read-only observation. The original worker still requires an unused
step and request marker, exact source/build/helper APK/UID, the same task and
fresh foreground, independent before/after state, final guards and normal
owned-child retirement. Failure or timeout must remain failed without replay.

## What the actual failure establishes

The case job `1a1b272ec9d-fc05-7e0d` ended failed/1. The new host reader
`1a1b27f06b8-fc05-7e46` completed successfully as an evidence collector, not as
UI acceptance. It retained 268 original files, 1,509,462 bytes, in a private
bundle. Its 29 recorded commands and 38 transports completed normally and
their original raw hashes and protocol receipts were checked.

The first close operation was acknowledged and retained UNKNOWN. Its separate
post-inspection found the exact declared homepage search node. The second
operation's before-state and fresh inspect succeeded. Its action nonce
`50e2673f0308c07c66e2b551f355bfae`, command 25, returned the helper's explicit
failure `INSPECTED_TREE_OR_WINDOW_CHANGED`, finish 0. The helper records
`action_attempted=false`, `outcome_unknown=false`; its claim and work completed
and its own service state restoration was verified. Command 26's independent
after-state succeeded. None of the three final post-inspection nonces was
created. The case's overall UNKNOWN remains, because the earlier close action
was actually attempted and the whole declared case did not complete.

## Source-level cause and its limits

In the unchanged `ActionRunner.act`, the prior inspection is verified by its
exact persisted wire hash, nonce, scope, success/restoration and age. A new
`action_target` capture is made. The failure occurs at the comparison of both
complete tree and stable window hashes, before target refresh, node-hash
validation, the final window capture, `actionAttempted=true`, or
`performAction(ACTION_CLICK)`. The search click was therefore not dispatched.
The strict host parser correctly rejects the helper's failure finish; the host
command returning zero does not convert that helper failure into success.

The failure's safe window observation shows one nonfocused window ID 39 first,
then a focused window ID 41 and the original nonfocused window. The target
capture completed with 245 nodes. This is evidence of a changing window census
inside that action connection. It is **not** enough to identify which tree
field or stable-window field changed: the error combines two hash predicates,
and the failure protocol does not publish the two captured structures or both
hashes. Connection-scoped window IDs are deliberately excluded from the
stable window hash, so an ID difference alone is not the explanation.

## Repair direction without weakening the current contract

First inspect the actual current UI through this original read-only sequence.
Use its complete raw evidence and restoration/foreground/task/helper checks
to determine whether the app has settled or presented a different page or
popup. Do not infer a search page, text field or eligible new selector from the
old homepage postcondition or from the failure's node count.

Keep the complete tree/window comparison, target refresh, exact node hash,
final-window check and current foreground guard unchanged. Do not add a retry,
ignore dynamic fields, accept a changed window, substitute an earlier tree,
or turn this helper's explicit no-action rejection into successful click
evidence. A later original action, if separately admitted, must make its own
fresh inspection and satisfy all of those checks again.

This fresh read cannot itself clear the failed case's UNKNOWN. A later
mutation still needs a reviewed proof appropriate to the **actual partial
failed case**, with complete evidence for the successful prefix and rejected
no-action suffix plus a genuinely later current postcondition; the existing
success-only case proposal cannot be reused or relabeled. No such producer is
implemented here. The already reviewed original exact-owned-task cleanup
remains the available failure-recovery alternative. Neither route may rewrite
the old failure, bypass Flow admission, or reuse the old click nonce.

Only request data and a local provenance check are new. The exact process
request inherits the existing read-only envelope: 480 seconds outer bound,
the worker's original 360-second owned-child bound, CPU 100%, memory 512 MiB.
It awaits root review and a coordinated Main window. No remote or Android
operation occurs during local preparation.
