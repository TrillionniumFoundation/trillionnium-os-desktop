# Design only: reconciling this particular partial, failed case

No producer, compatibility receipt, new Flow operation, or runtime request is
implemented by this document. The existing helper, adapter, recorder, guard,
consumer and failed results remain frozen. The proposed read-only inspection
has been prepared separately and must actually complete before this design can
be turned into an executable candidate.

## Conclusion

A new producer can in principle record that a **new decision is based on a
later real observation**, while retaining the original case as FAILED and
UNKNOWN. It must describe the exact successful prefix and the exact rejected
no-action suffix. It cannot invoke or impersonate the old `Flow.reconcile`,
reuse a success-only case proof, or call the failed case complete.

This is consistent with the existing consumer's narrow purpose. `Flow.begin`
blocks a later mutation until each previous attempted action either explicitly
had no unknown outcome or has a separate accepted reconciliation. The original
case result is never overwritten. The compatibility record must retain
`original_action_outcome=unknown_retained` and `allows_new_decisions_only=true`.
It records a basis for a later decision; it is not a successful old click,
business result, current-page guarantee, or permission to bypass fresh UI
admission.

## Actual evidence and the unresolved parts

The failed case is exactly `close-and-observe-search-01`, SHA
`2049bd107278f39cab66fccf14a6d9dda5c66db40723761d8eb64b436ee4ae95`,
in the existing task-878 flow. Its controller job is
`1a1b272ec9d-fc05-7e0d`, durable failed/1. The normal owned child exited 1 after
the original case runner returned 2. The host evidence reader
`1a1b27f06b8-fc05-7e46` reparsed 268 original files, 1,509,462 bytes; its successful
collection does not change the original case outcome.

The private original-byte bundle is 2,155,722 bytes, SHA
`6e5288e45697a130fa404e7038905521c2f5f912ad24fd3bdff361153d3a7d90`.
It remains on the host at
`/home/alex/work/pocket4-beike-case-failure-evidence-20261106-r1/bundle.private.json`.
It must not be copied into Git.

| Case portion | What is actually available | What it does not establish |
| --- | --- | --- |
| Step 0 close | Successful helper action assessment, original action UNKNOWN, independent subsequent inspect, exact declared homepage search-node postcondition | The whole case succeeded, or that page remains current |
| Step 1 before/inspect | Independently completed state command 23 and inspection command 24 | That the UI remained identical until dispatch |
| Step 1 action | Command 25 joined normally; helper finish 0, explicit `INSPECTED_TREE_OR_WINDOW_CHANGED`, no action attempted, no helper outcome uncertainty | A successful click, a search page, or an unchanged app state |
| Step 1 after | Independently completed state command 26 | A successful original action or the missing final post-inspection |
| Final post-inspection | All three declared nonces absent | N/A, passed, or reconstructed observations |
| Whole case | FAILED, attempted earlier action, UNKNOWN retained; 29 command and 38 transport receipts available | A successful case producer's eligibility |

The public failure diagnostic intentionally omits some full helper fields.
Before any producer can qualify the failed suffix, it must inspect the already
saved complete raw failure wire in the private bundle. In particular it must
verify `secondary_errors`, the pre-connection accessibility state and the full
restoration record. Merely checking the public safe diagnostic is insufficient.

The case runner does not persist the failed `Session.sequence` result object:
the method raises with attached details, and the case runner saves only the
exception type/code. Therefore `restoration_qualified`, `foreground_after`,
`installed_after` and other missing sequence-level fields must **not** be
manufactured. The producer must state which facts it independently proves
from saved raw commands and which are established only by new live checks.
Private foreground dumps were deliberately discarded by the original backend;
their saved hashes are not a recoverable foreground package observation.

## Proposed exact typed producer boundary

The new operation would be explicitly named, for example
`owned-qa-partial-case-reconciliation`, with its own versioned typed proof.
It would accept only this exact case, flow, task 878, helper UID 10157 and
original source/build/APK/signer/runtime/App binding. No generic package,
arbitrary old failure, other nonce, other error code, or unbounded sequence is
admitted. A future different partial case would require its own reviewed
contract.

The frozen old `Flow.reconcile` accepts only old `operation=ui` click/set-text
and later old dump/observe records from the old Existing android-app CLI. It
cannot consume owned-qa-case evidence. None of the records in this proposal
would be relabeled as that old protocol.

### 1. Preserve and bind the complete historical evidence

Require the authoritative failed controller terminal and all original stdout,
with their actual byte hashes. Require the normal owned child retirement,
without a timeout, cancellation, signal or retry. Bind the exact original
request, case, intent, failed result, helper source closure, actual build and
task-878 native launch scope.

Re-read the original files with no-follow, bounded reads and complete stat/path
identity checks. Match the private bundle's original bytes to the actual files;
keep all original UNKNOWN, failure and absence evidence. Check every saved
command's exact argv/environment/seven authority FDs/parent process, raw stream
hashes, normal join, and transport lease-release/post-guard receipt. The fixed
case shape has the actual 29/38 completed prefix; do not treat the expected full
case counts of 38/50 as if they occurred.

### 2. Prove the successful prefix with the original strict parser

Use unchanged `qa.parse_completed` for each actual successful phase, and the
existing restoration predicates for the completed step-0 operation and its
independent post-inspection. Verify the exact original selected node, inspection
nonce and complete wire binding. Recompute its unique visible, nonpassword,
untruncated postcondition from the original complete inspection. This proves a
historical observation only. Retain the close action's original UNKNOWN.

### 3. Prove the suffix was a completed helper rejection before dispatch

First require that unchanged `qa.parse_completed` rejects the actual command-25
wire with the original strict error. Then use unchanged
`qa.failure_diagnostic` to bind the real finish-0 failure, not a success parser
with relaxed rules. Decode the complete original wire with the unchanged
bounded codec and additionally require:

- The exact request, nonce, operation, helper UID, actual source/APK identity,
  scope, and inspection-wire reference agree with command 24 and the original
  declared selector.
- The exact error is `INSPECTED_TREE_OR_WINDOW_CHANGED`, `ok=false`,
  `claim_persistence_completed=true`, `helper_work_completed=true`,
  `secondary_errors=[]`, `action_attempted=false`, `outcome_unknown=false`,
  and no click dispatch acknowledgement is present.
- The actual helper time bounds, complete bounded target capture, finish code,
  command join and lease/post-guard evidence are preserved.
- The failure's own-service restore readback has unchanged flags/capabilities;
  its pre-connection accessibility state equals the actual before-state and
  actual independent after-state. The after-state command is a complete
  no-automation probe. Any mismatch remains a rejection.

The last condition is a new explicitly typed **failed-helper retirement/state
check**, not a fabricated successful `qa.assess_restoration` return. Its meaning
is limited to the facts actually compared. The original helper declares no
dispatch because `ActionRunner.act` raises at the whole-tree/window comparison
before setting `actionAttempted=true` and calling `performAction`. This does not
claim that the app made no autonomous UI or network changes.

Require the final three post-inspection requests to remain absent and the
original case result to remain failed. Do not publish an invented final case
postcondition or delete the rejected operation.

### 4. Require a genuinely later independent observation

The new original-worker inspection must itself complete with authoritative
durable exit 0, complete raw output, normal owned-child exit, exact source,
helper APK/UID, epoch/App binding and same owned task. All its original state,
inspection, foreground, restoration and post-check requirements remain intact.
Use the original file bytes and raw helper protocol, not a summary or earlier
home-page observation.

Require chronological order of case end, observation start/end and proof, and
the corresponding actual helper elapsed-time order under the unchanged
runtime epoch. Choose an explicit meaningful postcondition **only after the
new complete inspection is observed**. It must match exactly one visible,
nonpassword, untruncated real node. A future text-input selector additionally
requires actual editable/capability evidence and the original subsequent helper
checks; this design supplies no speculative EditText identity.

### 5. Fresh authority and truthful publication

Before qualifying a candidate, reacquire the existing held R5 authority and
original locks. Recheck the actual runtime/App scope, original owned task as an
exact leaf, current full helper APK/UID/source, and current original foreground.
Do not make the foreground check optional because a historical observation
passed. Keep the proven namespace observation-time projection only at its
eight original nsfs records; no other identity field is relaxed.

The proof must contain a complete hash map of the original failed step and the
new independent observation, plus a precise typed account of the successful
prefix, rejected no-action suffix, actual later postcondition and fresh checks.
It must explicitly keep `case_ok=false`, `case_outcome_unknown=true`,
`original_results_rewritten=false`, `old_action_replayed=false`,
`business_success_verified=false` and `production_ready=false`.

Publication should use the already discussed two-stage boundary: first a
non-authorizing candidate with normal resource retirement and authoritative
controller completion, then a separately reviewed bounded commit. The commit
must bind that actual terminal, exact candidate bytes and actual evidence; it
must not turn an in-memory success or unjoined worker into a consumer record.
Both source/request closures and any final publication outcome require root
review. A partial write or late failure remains UNKNOWN, with no automatic
retry or subsequent UI step.

Only after the typed proof has actually qualified may an O_EXCL compatibility
record be created at the original consumer's expected reconciliation path.
That record must identify the **new producer and new typed schema**, the exact
unknown case step, current epoch, original scope SHA, preserved original
UNKNOWN and the evidence hashes. It must not claim that old `Flow.reconcile`
ran. Every evidence reference consumed by the frozen consumer must be a safe
relative path within the same flow, and all bytes must still match. The private
bundle outside that flow is a pinned archival input, not a forged relative path.

The compatibility record allows only a new decision under the original
`Flow.begin`, fresh foreground, task/helper, state, selector, complete tree and
window, target refresh and final-window gates. It cannot authorize replay of
the old click or accept the tree/window change that caused the failure.

## When this design must stop

Missing/malformed original failure wire, a secondary error, unjoined command,
state mismatch, incomplete post-guard evidence, modified source or original
files, a different task/epoch/helper, failed later observation, ambiguous
postcondition or wrong current foreground all block publication. If the
necessary factual proof cannot be obtained, the previously reviewed original
exact-owned-task cleanup remains the recovery route. No second live flow or
new key may be used to evade the existing UNKNOWN.

The immediate executable candidate remains the separate read-only inspection.
There is currently no implemented partial-case producer and no new mutation
authorization in this design.
