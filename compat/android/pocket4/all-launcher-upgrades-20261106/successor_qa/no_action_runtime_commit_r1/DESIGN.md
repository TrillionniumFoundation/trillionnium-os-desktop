# Beike task 878: explicit rejected-before-dispatch reconciliation

This revision concerns only `search-click-after-partial-commit-01` in the existing task-878 flow. It is separate from the earlier two-step partial-case proof. The original case, controller result, nonce claim, `FAILED` and outer `UNKNOWN` remain unchanged.

The actual single-step failure has 90 step files, 10 recorded commands, 13 transport receipts and one complete helper rejection wire. The frozen helper rejected `INSPECTED_TREE_OR_WINDOW_CHANGED` before setting `actionAttempted` or calling `performAction`. Its own result reports `action_attempted=false`, `outcome_unknown=false`, completed claim persistence and helper work, no secondary errors and verified service restoration. The independently invoked before/after state helpers returned normally and bracket the rejecting helper. The outer command was conservatively marked attempted when the instrumentation command was submitted; this new proof never rewrites that layer.

There is no later independent inspect or completed business postcondition for this failure. The old earlier inspection is used only as an explicitly identified, previously qualified installed-helper identity reference. Its complete public controller and adapter bytes and durable terminal are pinned. It is never described as a later observer. The current foreground expectation comes from this failure's actual action request, not an invented `foreground_after` or tree.

## Frozen consumer and new producer

`recorder.py:Flow.reconcile` only understands the old `operation='ui'` backend. It cannot accept this owned-QA protocol. We do not call it, relabel an operation, or change it.

`Flow.reconciled` accepts an append-only `pocket4-flow-explicit-reconciliation-v1` record with the original step, exact epoch/scope hash, `original_action_outcome=unknown_retained`, `allows_new_decisions_only=true`, and exact hashes of flow-relative evidence. It does not interpret a typed proof or validate controller completion. The new producer therefore has its own explicit rejected-before-dispatch schema and must establish the full evidence before writing a compatible envelope. Root must independently require the producer's complete, durable exit-0 terminal and normal held-pidfd child exit before another action. Merely writing an envelope is insufficient.

The proof claim is narrowly **this helper did not dispatch the requested click**. It does not claim that the whole command had no effects: the helper claim was persisted, a UiAutomation connection existed and was retired, and the application could change autonomously. It proves no business success and no current tree.

## Stage A

The new explicit `owned-qa-no-action-runtime-proof` step is read-only for Android. It rechecks the fixed 101-file private archive against every original host path and full file identity, reparses the original case/commands/transports/wire/state sequence using the frozen grammar, verifies the unchanged 26-file helper/recorder closures and qualified build, and preserves every original failure.

Under the original nonblocking flow/global locks it acquires a fresh R5 binding, compares the original process/start, namespaces, classpaths and app identities, and runs two rounds of the unchanged `Session.installed()`, `Session.task()` and `Session.foreground()`. Only the existing eight nsfs observation-time exceptions remain; ordinary file times and all identity fields stay exact. The installed helper must equal the explicitly pinned prior actual identity and the failed case's original UID/path. Foreground must equal the failed action's complete actual scope. There is no activation, resume, instrumentation or UI action.

Stage A writes a nonauthorizing candidate, then normally exits under the existing parent-held-pidfd/explicit-libffi protocol. Its full original stdout and actual durable terminal are required before Stage B can be sealed. Stage A has no publication function.

## Stage B

Stage B will be sealed only from Stage A's actual completed outputs. It will reparse the same history, recheck Stage A's full command/source/candidate/joint evidence, and repeat the same two original installed-helper/task/foreground rounds. It then writes a new typed proof and a no-replace compatibility envelope for this one failed step, after held Main authority has closed and all known resources meet their existing final checks.

The envelope does not use `matched_native_node`, does not manufacture a later observation or postcondition, and never sets the old result to success. The original link-without-replacement/fsync/readback protocol, lock lifetime, failure-UNKNOWN behavior and parent normal-exit gate are retained. Existing receipts cannot be overwritten. No new decision is allowed after an uncertain publication until that exact job and evidence are reconciled.

Any later UI operation still needs the original fresh foreground, helper, state, exact selector and complete tree/window checks. This work does not solve the helper's cross-connection instability; that separate helper revision remains independently reviewed and installed. It does not reuse this old nonce or clear its claim.

## Scope and privacy

The compiled Beike/actions app scope remains the original two-package scope. This producer does not borrow the old all-48 snapshot, authorize other apps or install a helper. ZBJ's separate upgrade cannot be relabeled as part of this proof. Bili Accept and Meituan location restrictions remain unchanged.

Private bundles and full UI bytes stay at their existing private locations. Public proof records contain hashes, identities, timing/restoration facts and explicit limitations. No UI tree or business text is copied into Git. Production and cleanup remain zero.
