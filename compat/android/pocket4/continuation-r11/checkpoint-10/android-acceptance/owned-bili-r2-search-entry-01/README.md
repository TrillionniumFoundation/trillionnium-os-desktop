# Bilibili r2 search-entry interaction 01

This fresh, once-only flow opens Bilibili with the original native launch,
uses the exact installed owned r2 helper (UID 10165), and permits one
`ACTION_CLICK` on the unique eligible node matching all three fixed fields:

- resource ID `tv.danmaku.bili:id/expand_search`
- class `android.widget.LinearLayout`
- description `Search bar, button`

The selector was identified in the actual, privately retained 76-node tree
from the retired prior flow. No old node path, node hash, window identity,
or helper nonce authorizes this action. `Session.sequence(click)` takes a
fresh state and inspection, verifies original foreground/task/Main and
installed APK, chooses a unique eligible node, and the actual Java helper
re-reads tree/window/target before a single action. There is no click retry,
coordinate fallback, text entry, login, messaging, purchase, or media control.

## Actual source and identity

The source consumes the r2 build/install/state receipts, actual UID 10165,
base APK hash/held file identity and actual signing certificate carried by
that APK. R1 and the old v2 helper remain untouched. It uses the unchanged
R4 recorder manifest and R5 held namespace entry through the already
qualified installed source. Main epoch and the original action lock remain
mandatory. The host foreground parser does not prove display identity;
Java separately requires focused Bilibili application window on display 0.

## Result and failure semantics

The click sequence includes an independent after-state in the unchanged
r2 adapter. The controller then attempts one additional read-only
state/inspect/state sequence with three different nonces, even when the
click sequence fails. Both primary and secondary errors are retained; a
successful later read cannot turn the first failure into success. A poisoned
transport can still refuse this read. No automatic replay is performed.

A successful scoped result proves acknowledged click dispatch, complete
post-inspection, actual restoration, unchanged helper/Main, and original
exact-task retirement. It **does not classify the resulting screen as a
successful search or playback**. The action result deliberately retains
`outcome_unknown=true` and `business_outcome_unknown=true`. No later business
mutation is made in this flow. Root will inspect the private post-tree to
choose a separately admitted fresh next flow. Whole-App readiness stays open.

The original coordinator's exact owned task cleanup remains in `finally`.
Cleanup is independently authorized despite an unknown action; it removes
only this flow's new task and preserves preexisting tasks. It is not a
force-stop and does not prove a cold process start.

## Resources, execution and privacy

Default PLAN performs no remote actions. Each CLI phase is a separate joined
process so the original flow lock is not accidentally held across phases.
There is one init, one launch, one navigation worker, and one original cleanup.
The navigation worker bound is 240 seconds for seven distinct instrumentation
commands plus identity/foreground reads; outer 600 seconds, CPU 100 percent,
RAM 512 MiB, swap 0 and TasksMax 128 stay unchanged. No pressure is generated.

Raw commercial UI assessments/stdout stay in the fresh root-private flow.
Public results contain hashes, safe scope/window metadata, restoration and
fixed public control selector only. They must never include raw UI nodes,
recommendation text, account details or private journal content. Audio capture
is absent. This package has not been executed on Android; host seam controls
are clearly labelled and do not replace actual device execution.
