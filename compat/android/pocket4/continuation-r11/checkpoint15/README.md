# Pocket4 continuation R11 — checkpoint 15

**Snapshot: 2026-11-05 13:39:25 UTC. Whole-App production readiness remains 0 / 45. No new engine or supervisor has been deployed to Main.**

This checkpoint closes one fixed evidence slice while repair and acceptance work continue. It contains the previously frozen **944 payloads** (801 source/review/request files and 143 actual-evidence files) and adds this README plus [status.json](status.json). It inherits all **7,352 CP14 payloads unchanged**, including the continuation root README. The combined delivery contains **8,298 payloads**, excluding the delivery manifest itself.

The 944-file checkpoint subtree is `bf7aac44eab4838d6322ef29b5fa19d0dc63a3ca`. The parent is CP14 commit `9e6bed241bcbf20986f505dbc0a5c70d211d6ab5`. [The delivery manifest](../delivery-manifest.json) preserves the older checkpoint records; `current_status_key` selects `checkpoint15`. New facts below are limited to records actually present in this slice. Results arriving after the cut are reserved for the next checkpoint.

## Scope at the cut

| Area | Included evidence | Qualification still open |
| --- | --- | --- |
| Owner13/14 | Diagnostic context and strict terminal-drain repair; original Owner13 ordinary failure; Owner14 matching compile, ordinary controls and prepared receipt | Actual new Owner lifecycle through ACTIVE/enrollment and original retirement; installed Main lifecycle |
| Native Registry | Ten owned authorization cases with 1,017 assertions | Production platform policy, factory service, Android/ART/engine integration |
| Native snapshots | Four owned ordinary-read sealed-snapshot cases with 355 assertions; NOFOLLOW matching build | NOFOLLOW runtime verdict in this cut and platform enablement |
| Bilibili | Three R5 fresh-before/after capture transactions with exact task cleanup; R6 frozen source and admitted build request | Sustained playback, pause/seek/reopen, attributable audio and R6 build/install/runtime outcomes in this cut |
| Amazon | Initial launch/inspection/cleanup; preserved search-entry01 readiness failure; search-entry02 frozen source | Public search/business success and whole-App qualification |
| 12306 | Current package/APK/launcher read-only evidence; frozen helper build source and request | Helper actual build/install outcomes in this cut and functional UI acceptance |

## Owner repair: ordinary controls pass, actual lifecycle remains a separate gate

The [diagnostic source](source/owner/pinned-io-cause-source-freeze-12/) retains the relative name, flags, held base identity and lifecycle role around a failed pinned open, while preserving its original errno. This makes a later real failure distinguishable without changing authority or admission.

The separately reviewable [producer13 terminal-drain change](source/owner/retirement-terminal-drain-source-freeze-13/retirement-only.diff) handles a broker that has already queued `AUDIT` and `RETIRED` and closed. It drains through the existing validator before attempting `RETIRE`. A close racing that send is accepted only with complete matching terminal evidence and the exact owned child's matching exit. Bare HUP, a dead child, missing audit, wrong nonce/scope or an unresolved send failure still fails. Retirement failures remain poisoned; cleanup and new-generation admission remain separate requirements.

[Producer13 compiled](evidence/owner13-compile01/compile-result.json), but its [ordinary run failed](evidence/owner13-ordinary01/run-result.json): 35 of 37 relay tests passed and two fixture assumptions failed. The supervisor and IPC stages were not executed after that failure. The record is preserved as FAIL.

[Producer14](source/owner/retirement-fixture-repair-source-freeze-14/README.md) changes only those two test fixtures. The faulted terminal fixture had `faulted=true` with `incomplete=false`; the unchanged codec correctly rejected it. The repaired fixture retains that negative control and uses a legal incomplete fault record. `stop_reason=0` was not the defect. The dead-proc fixture now compares the production contextual error against raw `SYS_openat` on the same held procdir, accepting the actual ENOENT or ESRCH value instead of assuming ENOENT. Production bytes before both test modules remain unchanged from producer13.

The [actual producer14 compile](evidence/owner14-compile01/compile-result.json) and [ordinary result](evidence/owner14-ordinary01/run-result.json) pass: **37 relay tests, 122 supervisor tests, seven IPC controls, worker-context and entry ABI3 checks**, plus two targeted public retirement controls, each with one pass and 36 filtered tests. These are ordinary host controls. They do not execute Android or certify a complete Owner generation. Their receipts record zero observed swap use and memory-event deltas; `memory.swap.max` is still `max`, and whole-invocation resource qualification remains false.

The [NORMAL14 prepared receipt](evidence/owner14-normal01-prepared-read01/prepared.json) is an actual PASS with `runtime_executed=false`, no errors and equal Main before/after/final fences. The original acknowledgement timeouts, read-only metadata reconciliation and subsequent exact stable-operation evidence are retained. A scan with no match proves only what was observed, not that the original operation could never have acted. **No NORMAL14 runtime outcome is included in this fixed cut.** Older Owner runtime failures and the distinction between original retirement and outer cleanup remain historical evidence.

## Native Registry and sealed-snapshot mechanisms

The [Registry positive run](evidence/factory-role-positive-run02-read01/result.json) passes **10 cases / 1,017 assertions**, with ten direct children and one nested child normally reaped, no forced cleanup and no unreaped children. It exercises owned kernel identity and authorization mechanics, including grant, suspend/attach, fork-token rejection, tombstones and duplicate approval rejection.

The [ordinary O_RDONLY snapshot run](evidence/factory-role-snapshot-run01-read01/result.json), bound to its [matching build](evidence/factory-role-snapshot-build01/result.json), passes **four cases / 355 assertions**. It produces real sealed snapshots using an owned fixture formatter and rejects wrong source, unsealed input and size mismatch. Its four children are normally reaped.

These are owned host mechanisms. Their receipts explicitly leave production platform policy, Android execution, factory service startup and Main identity observation false. They made zero Main actions. Observed resource counters are not a claim that an unlimited swap ceiling was zero.

The [NOFOLLOW matching build](evidence/factory-snapshot-nofollow-build01/result.json) completes 39 commands and reports `PASS_BUILD_ONLY`. The [runtime admission record](evidence/factory-snapshot-nofollow-run01/admission.tool-original.json) in this cut is an MCP acknowledgement timeout. The exact request and review are retained, but no runtime verdict is supplied here. A later result must be published with its own original binding.

## Bilibili: three bounded capture transactions, playback gates still open

The [R5 fresh-before run](evidence/bili-r5-player-fresh-before01-read01/originals/navigation.json) obtains a fresh inspection before each of three captures and independently inspects after each attempted capture. All three before/after absolute scopes match in this run. The [cleanup receipt](evidence/bili-r5-player-fresh-before01-read01/originals/cleanup.json) removes owned task 936 and preserves preexisting task 851; the [retained review](source/android/bili-r5-fresh-before-actual-review-01/report.json) verifies Main equality and the original source/evidence bindings.

The original geometry failure remains preserved. The new run does not exercise an actual inter-transaction movement branch, and these bounded observations do not establish sustained playback, pause/resume, seek, reopen, App-attributed audio, atomic screenshot ownership or renderer/producer attribution. The original business-outcome-unknown fields remain intact. Private image bytes and raw commercial UI trees are not added to this checkpoint.

R6 helper source, its [build review](evidence/bili-r6-build01/dispatch-review.json) and [build admission](evidence/bili-r6-build01/admission.tool-original.json) are included. The final R6 build receipt, installation and controls-reveal results are outside this fixed cut. No such later success or failure is imported into this snapshot.

## Amazon: preserve the readiness failure and freeze the next attempt

The [initial launch/inspection review](source/android/amazon-launch-inspect-actual-review-01/report.json) verifies one real launch, bounded inspection and exact cleanup: task 946 removed, task 851 preserved and Main fences unchanged. This establishes that limited flow, not public-search business success.

The [search-entry01 run](evidence/amazon-search-entry01-read01/coordinator.json) fails the existing requirement for two consecutive complete observations with matching full identity. Four successful observations contain **72 → 220 → 281 → 464 nodes**. A separate final observation matches the fourth, but it does not retrospectively pass the failed readiness gate or authorize a click. **Zero click commands ran.** The [failure review](source/android/amazon-search-entry01-actual-review-01/report.json) preserves the first error, exact removal of task 950, preservation of task 851, released resources and unchanged Main.

[Search-entry02 source](source/android/amazon-search-entry-02/search-entry01-to02.patch) raises the successful-observation allowance from four to five within the original 30-second budget. It retains the consecutive full-tree/window/target gate, a maximum of one public entry click and the original cleanup. Its fresh attempt has 22 helper nonces. The source and exact request are frozen; **this cut contains no search-entry02 actual runtime verdict**.

## 12306: current artifacts observed, helper build source frozen

The [read-only result](evidence/12306-artifact-launcher-readonly01/result.json) and [review](source/android/12306-artifact-launcher-actual-review-01/report.json) bind `com.MobileTicket`, UID 10121, version 275, its one 150,377,492-byte APK and current launcher `com.MobileTicket/.ui.activity.WelcomeGuideActivity`. Five fixed read commands complete with held artifact and Main identities unchanged. No App launch or UI action occurs, and the commercial signer is not independently qualified by this byte binding.

The [12306 helper build source and request](source/android/owned-12306-qa-r1-build01/) are frozen. The fixed cut has no final helper build or install receipt. A later launch must repeat current resolver and artifact/Main checks rather than treating this observation as permanent authority.

## Continuation and preservation

The baseline Main engine remains R16 (`c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d`) with framework epoch `48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f`. Individual included fence observations do not establish continuous absence of interference. None of the scoped passes supplies a whole-App production verdict, so the matrix stays **0 / 45**.

The immediate work continues on actual Owner lifecycle, matched native integration and the per-App functional queue. Later actual terminals, Owner diagnostics and repairs, NOFOLLOW runtime results, R6/Ticket results and new Native source are deliberately deferred to the next checkpoint. This closed slice does not reopen old failures or alter their original bytes.
