# Bilibili r3 search-entry interaction 01

This fresh, once-only flow uses actual installed package `org.droidloom.qa.bili.r3`,
UID 10166, and its verified source/build/APK/signer/installed-file chain. It opens
Bilibili through the original native launch and permits at most one `ACTION_CLICK`
on a unique eligible node matching all three fixed fields:

- resource ID `tv.danmaku.bili:id/expand_search`
- class `android.widget.LinearLayout`
- description `Search bar, button`

The fixed selector came from a previously observed private tree. No old node path,
node hash, window or nonce authorizes a new action. The new helper captures a fresh
complete tree and rechecks tree/window/target immediately before its single click.
There is no retry, coordinate fallback, text entry, login, messaging, purchase,
media control, installation or settings change in this request. The r3 helper has
a separately constrained set-text capability, but this plan never invokes it.

## Actual identity and source

The admission consumes original r3 install/state receipts, actual UID 10166,
signed APK a32348c8d4615872aa2ec04b9253cd89826aca31d92d6c208365745ff522d3c8,
and signer 2850f7ce24d73314634e48e187643c97436cecb9d96e54e771b62686e12fdf6f.
It reparses the actual compressed no-UiAutomation state command and checks exact
installed base APK metadata before/after. The live session rechecks installed APK
and current state; historical state never substitutes for a current baseline.
R1, R2 and the old v2 helper stay untouched.

The original R4 recorder and R5 held namespace transport, original action lock,
Main epoch and exact task ownership remain mandatory. The host foreground parser
does not independently establish display identity; Java separately requires the
focused Bilibili application window on display 0. Source/manifest and actual build
receipt pins are checked before and after the operation.

## Result and failure semantics

The click sequence includes an independent after-state. One additional read-only
state/inspect/state sequence uses three further fresh nonces, including on click
failure. Primary and secondary errors remain separate. A later successful read
cannot turn the first failure into success. A poisoned transport can refuse a new
read; no uncertain action is replayed.

An acknowledged click and a complete post-inspection prove only this scoped
dispatch/observation/restoration result. The business result deliberately remains
unknown until the privately retained post-tree is reviewed. No subsequent mutation
is included. Exact search-page selection and public query entry are the next
separate functional step. Whole-App readiness remains open.

The original coordinator finally block remains unchanged: it retires only this
flow's positively owned new task and preserves preexisting tasks. It does not
force-stop the package or prove a cold process start. Original r2 node/depth-bound
failures are preserved; their combined error did not distinguish node from depth.
The new r3 helper's finite complete-tree limits and safe counters are consumed
without accepting partial trees. No r3 runtime success is presumed by this freeze.

## Resources and privacy

Default PLAN is inert. Init, launch, navigation and exact cleanup are separate
joined CLI processes. The navigation worker limit stays 240 seconds; outer 600
seconds, CPU 100 percent, 512 MiB RAM, swap 0 and TasksMax 128 stay unchanged. No
stress or audio capture is introduced. All eight nonces are distinct and new.

Raw commercial UI assessments/stdout remain in the new root-private flow. Public
summaries expose only hashes, scope/window metadata, safe tree counters and the
fixed public selector. Recommendation/account text, raw trees and private journals
must never be published. Local controls consume actual receipt bytes with explicit
local-path routing and label non-device sequence seams; they are not Android
execution or a guarantee of a future successful click.
