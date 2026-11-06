# Beike: one observed search-entry click, then the shortest useful core test

## Prepared single action

The proposed step is `open-home-search-01`. It only clicks a unique node matching all three observed fields:

```json
{"resource_id":"com.lianjia.beike:id/tv_nav_right_search_text","class":"android.widget.TextView","text":"搜索"}
```

Root observed this visible, nonpassword, clickable node in the complete successful `inspect-after-close-02` tree. That observation supports preparing this selector. It does not authorize reusing a stale node instance: the unchanged `qa_adapter.py` performs its own new `before` state, foreground check and fresh inspection, selects a unique currently visible clickable node, and binds the click to the new inspection nonce/wire and current window. A changed, missing, ambiguous, password or unclickable node is rejected by the existing helper contract.

The plan has four new unique nonces, disjoint from the existing locally retained plans. The actual frozen plan validator accepted the plan locally. No Android action was executed during this preparation. `publish_open_home_search_01.py` is a narrow data revision of the actually successful close-entry wrapper: new plan/nonce/hash, new step, exact observed selector and descriptive labels. It retains the same adapter/build/APK/signer/UID/recorder/flow pins and the same O_EXCL/fsync/readback/descriptor checks. The exact request remains `review-only`.

**Submission order:** root must first accept the actual host-only r2 verification and actual durable successful `--publish-once` result for `close-entry-popup-01`. The original Flow consumer must validate that new envelope and its evidence hashes. Only then may root submit the new search-click request once. Its completion is still an action acknowledgment with UNKNOWN outcome, requiring a distinct later readonly inspect and a new explicit postcondition proof before another mutation.

## Minimum useful sequence

1. Publish the already observed home postcondition for the existing close action using the staged r2 publisher. Do not repeat the close click or repeat its two inspections.
2. Execute the one search-entry click above. Run exactly one independent readonly inspection afterwards. Review that tree to identify the actual unique visible nonpassword editable search field. Use that same observation as the postcondition evidence for the search-entry action and as the basis for proposing the next selector; the next action still performs its own fresh inspection internally.
3. Once that action's new explicit proof is qualified, perform one `set_text` with the already compiled public query `北京`, using the actually observed `android.widget.EditText` resource ID. Do not invent the resource ID or type into an unobserved field. Run one later independent readonly inspect to prove the displayed query and observe the resulting state.
4. Submit an additional search-button click only if the actual page needs it. If entering the query already produces the intended real results, omit that click. If a submit action is necessary, its selector and postcondition must come from the new observed tree, followed by the same independent observation/proof gate.

The actual result must distinguish query entry, suggestions and completed results. A restored accessibility state, input acknowledgment or visible home page is not evidence that network search succeeded. An account requirement, integrity rejection, network failure or unavailable capability remains an explicit blocker; it is not converted to a guest success or N/A. This sequence does not touch Bili, location permissions, payments, bookings or private messages.

## Necessary proof cost per mutation

Counts below follow the frozen `helper/qa_adapter.py` sequence and the new publisher's reviewed implementation; they are operation counts, not measured wall times.

| Phase | R5 transport calls | Recorder command records | UIAutomator instrumentation calls | Purpose |
| --- | ---: | ---: | ---: | --- |
| One click or set_text sequence | 13 | 10 | 4 | Installed helper/task checks, before/inspect/action/after, foreground checks and state restoration |
| One independent later inspect | 12 | 9 | 3 | New nonces, independent observation and before/after restoration |
| Fresh explicit proof publication | 8 | 6 | 0 | Two installed-helper/task/foreground checks, original evidence reparse, held identity and final publication gates |
| Total for a mutation and its explicit proof | 33 | 25 | 7 | Includes 8 private foreground observations whose raw window dumps are intentionally not persisted |

The bounded private-bundle reader and host-only verifier add host file work, with zero Android commands. The current pair has 177 original files / 888,207 bytes; a later pair's exact byte count and hashes must be measured from its actual outputs and cannot be copied from this pair.

The current r2 publisher is **fixed to the close action and observer02**: it pins that bundle, original entry sources/jobs, plans, wire and home node. It cannot simply be rerun for search or text input. The reusable pieces are the unchanged pure verifier contract, held runtime checks, original recorder/helper, exact library bootstrap and no-replace publication mechanism. For each later pair, create a new explicitly reviewed evidence binding with its actual raw pins and observed postcondition, then use the same checks. A future narrow configuration-only producer revision could remove repeated source-data editing after a separate review; no such generic producer or automatic loop is being introduced by this preparation.

To reduce unnecessary work while preserving this contract:

- Keep the working helper build/install and current guarded source closure; do not rebuild or reinstall them for every node action.
- Reuse the already qualified bootstrap source and actual library provenance. Each new worker still performs its required exact resource check and retires its own process; no repeated standalone library research or namespace controls are needed.
- Let each required independent post-inspection serve both as the prior action's postcondition evidence and the basis for selecting the next proposed action. The next adapter's internal fresh inspection remains mandatory.
- Avoid speculative navigation, repeated popup clicks, redundant inspectors and unobserved selectors. Stop after the smallest actual search path establishes the intended core operation.

The broader per-App login/guest, permissions, network/storage, long-run, restart and failure-recovery acceptance remains separate. The existing 60-minute / three-restart / three-recovery proposal is not claimed as historical evidence or satisfied by this short sequence. Current production-ready and cleanup counts remain zero.
