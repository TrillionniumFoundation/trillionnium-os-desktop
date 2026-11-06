# Original bounded-case contract and next Beike decisions

This is a local source review, not a new runtime qualification. The exact
generated `helper/run_case.py` is 9,595 bytes, SHA256
`cea31bd9afd0ddc147224a441fab277e0b5d55e034008dc49295ff198a046f2b`.
The actual generated `qa_adapter.py` is 29,378 bytes, SHA256
`ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c`.
Both remain unchanged in their signed/build-qualified source closure.

## Admission happens before the case

`run_case.execute` requires root and interactive-production admission, the
exact helper source manifest, the qualified actual build/APK/signer, a pinned
case file, a canonical flow and the frozen recorder manifest. It constructs
the original `Flow`, calls `Flow.begin` once with operation `owned-qa-case`,
then acquires the original global action lock. Any unresolved earlier
mutating step still causes the original `PRIOR_ACTION_OUTCOME_UNKNOWN_NO_REPLAY`
rejection. The cleanup exception is not used for a case.

The wrapper narrows the admitted operation set to Beike `inspect`, `click` and
`set_text`, although the original generic validator also lists media-specific
operations that the compiled Beike policy does not admit. It does not change
the original case execution algorithm or its permissions.

## A case is a declared sequence, not an adaptive agent

The top-level case has exactly `schema`, `name` and `steps`, with the schema
`pocket4-owned-scoped-qa-case-v1`. There are between one and eight steps. Each
has exactly:

- `plan`: one original adapter plan;
- `post_inspection`: a separate original plan whose operation must be
  `inspect`;
- `postcondition`: the explicit observable node predicate.

Every phase nonce across both plans and all steps must be distinct. Each
individual plan must also satisfy the original compiled operation, selector
and text policy. The case cannot choose another App, a new task, a new helper,
an alternate command, an unobserved adaptive next action or an arbitrary text
value. It contains all decisions before execution begins.

The original 180-second deadline is checked before each next declared step.
It is not a hard assertion that all final restoration and evidence operations
finish within 180 seconds. Per-command timeouts and restoration remain
unchanged. The outer owned-process deadline allows those existing bounded
operations to conclude and cannot turn a timeout into a successful case.

## What happens within each declared step

The original `Session.sequence(plan)` first revalidates the installed helper
UID and exact base APK bytes. It obtains the actual original owned task,
captures a before-state, checks the real current foreground, performs a fresh
helper inspection and requires the foreground/window to remain consistent.
For click or set_text it selects the unique eligible node from that fresh
inspection, binds the action to its inspection nonce/hash and window, and
requires the actual action acknowledgement.

The sequence then makes its independent after-state attempt, checks
UiAutomation/accessibility restoration, rechecks foreground, rechecks the
original owned task, and revalidates installed helper identity. Failure in any
required phase propagates; it does not produce a successful sequence. The
original implementation retains primary and secondary failures.

Only after that successful sequence does `run_case` run another complete
`Session.sequence(post_inspection)`. That is a separate three-nonce read-only
sequence with its own current task/helper/foreground/before-and-after checks.
The code reads the actual saved assessment and requires its wire hash, helper
nonce, operation `inspect`, `action_attempted=false` and restoration result to
match that independent sequence. The original instrumentation parser has
already checked actual command completion, joined subprocess, response
protocol, helper identity and nonce. No caller-supplied inspection tree is
accepted in place of this observation.

## The node gate before the next declared decision

The postcondition can use only `resource_id`, `text`, `content_desc`, `class`,
`enabled` and `clickable`. Boolean fields require actual booleans. String
values must be nonempty and at most 256 UTF-8 bytes. At least one nonempty
resource ID, text or content description is mandatory; a class-only or empty
predicate is insufficient.

`match_postcondition` parses the actual independent inspection with the
original QA contract. Exactly one node must have the target package, be
visible, be nonpassword, match every declared field, and have every matched
string field explicitly marked untruncated. No match, multiple matches,
missing state, wrong package or truncated evidence stops the case. Expected
postconditions are test assertions, not claims that a future page has already
been observed; success is established only by that real post-inspection.

The original action sequence is saved as `case-NN-operation.json`. A successful
independent node gate is saved as `case-NN-postcondition.json`, including the
post nonce/wire hash, node/tree/window hashes and predicate. The receipt says
`allows_next_declared_case_decision_only=true` and retains a mutation's
original outcome as `unknown_retained`. It does not create a `reconciliations`
entry or turn an old result into a different result.

## Failure and end-of-case meaning

If the action sequence, independent inspection or postcondition fails, the
loop stops. No later declared action runs. Already attempted input remains
UNKNOWN; there is no compensation, task removal, replay or fallback UI route.
The final original guard, binding close and global-lock release are still
attempted, and their failures are retained. Case success requires all declared
steps and postconditions to finish.

Even successful completion of a case with input has top-level
`outcome_unknown=true`, because that is the original action-accounting
contract. A later independent case or standalone mutation still passes the
original Flow UNKNOWN gate. The per-step receipts permit only decisions
already declared inside that one case; they do not automatically admit a
future case. The reusable outer wrapper preserves this distinction and does
not add a compatibility reconciliation envelope.

## Minimal next sequence after the actual new launch

1. Execute only the prepared `inspect-new-session-01` request and review its
   real current visible nodes. Verify helper UID/APK, task878, current
   foreground, before/after state, full response completion and owned-process
   retirement. A successful native launch alone is not a current-page proof.
2. Build selectors from that actual page. The compiled text policy permits
   only `北京` on an exact eligible Beike EditText. If an editor is not visible,
   do not fabricate its ID or place it in a multi-step plan as an observed
   control.
3. Where the required controls and a meaningful expected transition are
   known, prepare one bounded original case with an explicit independent
   inspection and node predicate after every action. This avoids rewriting the
   worker or treating each intermediate action as an automatic new-session
   authorization.
4. If an exploratory action reaches a page whose next selector was not yet
   observed, collect that page through a separate read-only inspection. Its
   successful observation does not by itself remove the preceding UNKNOWN.
   Continue only through a legitimate reviewed proof or the existing owned
   recovery contract; do not weaken `Session.foreground`, rewrite the old
   result or escape to another live flow.

This document supplies no selector or Chinese-input action for an unseen
current page. The prepared first request is read-only. Business search result
quality, network/storage/permission behavior, long-running stability, restart
and recovery are later independent acceptance items. No case result here
establishes production readiness or authorizes artifact cleanup.
