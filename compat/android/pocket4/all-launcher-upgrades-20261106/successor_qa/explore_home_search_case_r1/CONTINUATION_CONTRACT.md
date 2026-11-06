# Original Flow reconciliation and this owned QA case

This is a source-level contract review. It does not publish a proof, change
the original consumer, reconcile an action or admit another mutation.

The exact reconstructed original recorder is 39,563 bytes, SHA-256
`0e50c67b1d5d251766fb58a69d9e62e119f0663ff2c4115ae326874cf95d6c09`.
The original case runner is 9,595 bytes, SHA-256
`cea31bd9afd0ddc147224a441fab277e0b5d55e034008dc49295ff198a046f2b`.

## There is a strict existing consumer and a narrower existing producer

`Flow.begin`, at the original recorder's `begin` definition, checks every prior
mutating step before a new mutation. Outside its explicit cleanup exception,
the prior result must have `outcome_unknown=false` **or** `Flow.reconciled` must
validate a separate reconciliation record. Missing/incomplete original steps
remain blocking. A new key or step name changes none of these requirements.

`Flow.reconciled` reads `reconciliations/<unknown_step>.json` and requires:

- schema `pocket4-flow-explicit-reconciliation-v1`;
- the exact unknown step name and current flow framework epoch;
- the exact SHA-256 of this flow's unchanged `scope.json`;
- `original_action_outcome=unknown_retained`;
- `allows_new_decisions_only=true`;
- every referenced evidence path to be relative and free of `..`, and every
  referenced current file's complete SHA-256 to match the record.

This consumer is a final evidence binding, not an API that makes arbitrary JSON
trustworthy. A valid producer must first establish the real postcondition and
all source, runtime, App, task, helper and command evidence. Writing an envelope
by hand merely to satisfy the consumer would bypass that effective contract
and is not permitted.

The original `Flow.reconcile` producer is narrower than its consumer. It accepts
only an original step with `operation=ui`, `mutation=true`, request `click` or
`set-text`, and a completed unknown action. The independent later observation
must also have `operation=ui`, request `dump` or `observe`, and a successful,
non-mutating result. It requires chronologically ordered timezone-aware times,
exact original `Existing android-app CLI` command identities, a spawned original
mutation, a successful real observation, one actual visible target node matching
the explicit predicate, current exact-leaf task identity and a successful guard.
It then creates the new reconciliation record without rewriting or replaying
the original action.

## The old producer cannot accept the new protocol

This candidate uses `operation=owned-qa-case`. Its helper responses, source pins,
raw instrumentation, nonces and postcondition files are the actual owned QA
protocol, not the old CLI dump/observe protocol. The original `Flow.reconcile`
correctly rejects them. Neither changing their labels to `ui` nor wrapping their
JSON to resemble an old CLI result is legitimate.

The original `run_case` gate is already a legitimate within-case postcondition
mechanism: each successful action is followed by a separate full read-only
sequence and a unique visible non-password untruncated node match. Its receipt
explicitly says `allows_next_declared_case_decision_only=true`. It is not read
by `Flow.reconciled` and does not unblock a later independent case.

The previously staged owned-postcondition producer is also not transferable:
it was bound to the old task 876, old flow, exact close action, exact observer
and its own original bundle. Its current-context publication failed before
publication on the real foreground gate. That failure remains. Its pure
`validate_step`/`validate_pair` code accepts a single owned-qa plan, not this
multi-step case. No old PASS or scope can be renamed to authorize task 878.

## Concrete next evidence, without pretending it already exists

After this exploration case actually settles, obtain its original result,
both `case-NN-operation.json` records, all nonce requests and assessments,
original command and transport receipts, the independent post-inspection raw
outputs, any `case-NN-postcondition.json` records, the exact held binding and
the authoritative owned-parent/controller termination evidence. If the terminal
postcondition fails, preserve the failure and independently inspect the live
page through the unchanged read-only helper; never promote the failed assertion.

If a real unique visible, non-password, untruncated EditText is observed, it can
provide a **proposed future input selector**. That does not itself clear the
case UNKNOWN. A separately reviewed owned-case proof producer would have to
validate the true owned protocol and full completed case evidence, then bind a
genuinely later successful independent observation and explicit postcondition.
It must recheck the same actual source/build/APK/signer/UID, runtime/App scope,
owned leaf task and current foreground with fresh held R5 authority, retain all
primary/secondary failures, close every resource and finally publish a new
typed proof plus a compatible consumer envelope with O_EXCL. The original
UNKNOWN bytes, source pins, Session foreground predicate and consumer stay
unchanged. Such a producer is not implemented or authorized by this document;
it requires a concrete source/evidence review after the actual case outcome.

The existing separate original cleanup path remains the known recovery option
if a truthful postcondition proof cannot be established. It may retire only
the exact current owned task under the original epoch/leaf/other-task guards.
Only actual successful removal and task absence can precede a separate new
session; a second live flow cannot be used to bypass the unresolved case.
