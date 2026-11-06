# Stage B: pending actual Stage A, not sealed

There is no executable Stage B request in this revision. This note fixes the required adaptation of the earlier actually successful `partial_case_runtime_commit_r1/stage-b-candidate-r1` producer.

Before Stage B can be assembled, root must obtain the complete original Stage A stdout and authoritative durable exit-0 terminal. The required inputs are the actual stage receipt, source/request pins, actual child PID and complete output, normal parent-held-pidfd exit, restored parent descriptors, candidate, step result, joint artifact and all 57 Stage A files. None of these future values is filled from an expectation. A failed or incomplete Stage A cannot be used.

The new operation will be `owned-qa-no-action-commit`, in a new `no-action-commit-01` step. The only compatible-record destination is the existing flow's `reconciliations/search-click-after-partial-commit-01.json`, initially absent. The earlier `close-and-observe-search-01.json` reconciliation remains untouched.

## Minimal code differences from the actual earlier Stage B

1. Retain the exact `commit_envelope`, parent-held-pidfd owner, explicit libffi initialization, original two locks, all original Session checks, final descriptor checks and postpublication UNKNOWN behavior.
2. Use Stage A's new no-action history verifier and unchanged frozen original recorder/helper dependencies. Reparse all 101 originals and require exactly 90 files in the original failed step. Do not require or invent a later observer directory. The earlier installed-helper reference remains explicitly earlier.
3. Verify the actual completed new Stage A through its exact new schemas and actual source/job/bytes/terminal/candidate/joint pins. Reparse its six recorded commands and eight transport receipts. Its generated `no-action-history.json` must exactly equal the newly recomputed historical proof.
4. Fresh-bind the original failed case and the completed new Stage A to a new held-R5 identity, using only the existing eight nsfs observation-time projection. Run two unchanged installed-helper/task/full-foreground rounds, with the same full foreground from the original failed request and the pinned previous helper identity. Do not activate a task or run instrumentation.
5. Set the new typed reason to `exact_helper_refusal_before_performAction`. State `independent_later_observer_available=false`, `business_postcondition_observed=false` and `helper_requested_click_dispatch_attempted=false`. Preserve `original_case_ok=false`, `original_case_outcome_unknown=true`, `original_action_outcome=unknown_retained` and all original bytes.
6. The compatibility envelope still uses the frozen consumer schema and scope/hash contract, with `observation_step=null` and `postcondition=null`. It explicitly names the new producer and typed proof. It does not use `matched_native_node`, claim a successful case or masquerade as old `Flow.reconcile`.
7. Replace the old evidence cardinalities (257 failed-case files, 81 later-observer files) with this actual 90-file case and the actual 57-file Stage A. The complete new proof-step evidence is also included. The new total must be derived from these fixed sets, not relaxed to permit arbitrary missing inputs. Hash every original flow-relative input and every new prepublication proof/source/controller file. Never include a future postpublication result as self-referential success evidence.

## Publication and acceptance

All current checks and historical rechecks must pass; held Main authority must be closed; only the exact known library resource and original two locks may remain. Only then is one typed proof written and the original no-replace link/fsync/readback commit performed. The proof truthfully records a prepublication phase and the **already completed Stage A**; it cannot claim its own future exit.

Root must keep all later Main mutations frozen until the exact Stage B job's complete original stdout, normal held-pidfd exit, restored parent descriptors, successful final readbacks and durable exit-0 terminal are jointly verified. The frozen Flow consumer does not itself inspect that controller terminal. A postlink error therefore remains publication UNKNOWN; do not delete the envelope, change keys or retry blindly.

After legitimate completion, the old case still remains FAILED/UNKNOWN in place. The new record allows a new decision only. A new helper or search operation requires its separately verified source/APK/UID/scope, fresh foreground and the unchanged per-action safety checks. Neither the old click nonce nor its persisted claim is reused.
