# Beike owned-helper postcondition proof candidate

This is a new, explicitly named proof producer for one existing Beike flow. It is
not a new Android automation framework and it does not change any frozen helper,
recorder, transport or guard source. No reconciliation has been published by this
candidate. The default entry prints `PLAN_ONLY`.

## Why a separate producer is needed

The frozen `qa_adapter.py` correctly leaves a dispatched click or input with
`outcome_unknown=true`, including when Android acknowledges the action and the
helper finishes normally. The frozen `Flow.begin` then refuses a later mutation
until it has an explicit postcondition reconciliation. This is an effective
constraint and remains in force.

The frozen `Flow.reconcile` producer supports only the older `operation='ui'`
and `Existing android-app CLI` receipt format. Its parser cannot accept the new
owned-helper instrumentation protocol. We neither call that branch with
mislabelled data nor edit its checks.

`Flow.begin` consumes reconciliation through the separate, generic
`Flow.reconciled` envelope verifier. That verifier checks the exact flow scope,
epoch, retained UNKNOWN declaration and every relative evidence hash. This
candidate is an explicitly reviewed **new producer** for that existing envelope.
The new envelope names its new typed proof, producer source hash and verifier
source hash and says `original_Flow_reconcile_called=false`. The old action
result is not edited and is never renamed to PASS.

This relationship is material: the frozen generic envelope consumer does not
itself reimplement the new instrumentation parser. Only a fully reviewed,
externally pinned producer and request may create the envelope. Merely writing
the few fields accepted by `Flow.reconciled` would be insufficient. This source
does not provide an unpinned receipt-writing interface.

## Exact present scope

| Item | Bound value |
|---|---|
| App | `com.lianjia.beike`, UID 10143 |
| Owned QA helper | `org.droidloom.qa.successor.p8f89f253350ba2fa.r1`, UID 10157 |
| Existing flow | `pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb` |
| Native task | 876, original successful native launch scope |
| Original action | `close-entry-popup-01`, job `1a1b1bceb2f-fc05-7a8f` |
| Later independent observation | `inspect-after-close-02`, job `1a1b1caee35-fc05-7ad5` |
| Original action outcome | UNKNOWN, retained unchanged |
| Framework epoch | `7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c` |
| Runtime epoch | `a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9` |

The separate `inspect-after-close-01` launch-unknown attempt is not an observation
input and is not changed or reclassified. The original click selected the exact
observed `iv_close_icon` / `android.widget.ImageView`; its purpose is not inferred
from an absent label.

The root coordinator observed and explicitly selected this postcondition from
the real later complete inspection:

```json
{"resource_id":"com.lianjia.beike:id/tv_home_tab_selected","text":"首页","class":"android.widget.TextView","enabled":true,"clickable":false}
```

The proof requires exactly one matching visible, non-password, non-redacted node
and an explicit false truncation flag for each selected string field. It also
binds the observed node path, node hash, tree hash, window hash and inspection
nonce. It does not infer absence of a popup from this node, authenticate an
account, or assert a business transaction or production readiness.

The first candidate accepts only a complete single `owned-qa` click/set-text
sequence and an independent later single `owned-qa` inspect. It rejects legacy
`ui`, `owned-qa-case`, launch and cleanup records. A case producer would have to
verify every internal action and post-inspection sequence before being added;
the current code does not silently treat a case as a single action.

## Evidence verification before any Main access

The host reader has already collected only the two fixed steps, their two plans,
and four identity documents. Its original private bundle is 1,218,042 bytes with
SHA-256 `3c72bc43b2a32950a576405049b12cf6984ef790978638122ef2a7d4602941c8`.
It contains 177 files and 888,207 original bytes. The bundle, its full raw UI
contents, and the reader's node-summary stdout are **not approved for Git**.

`--verify-host-only` reads that exact bundle on Pocket4, preserves each file's
original bytes, and verifies all individual hashes. It loads only exact frozen
host source/parser definitions and the actual build receipt. It creates no Flow,
loads no Main guard, acquires no Main or flow lock, enters no namespace, executes
no child and publishes no reconciliation. It compares the full process FD
identity set before and after its host verification.

The core recomputes each instrumentation request and exact Android argv from the
original plan and prior inspection. It then reparses actual raw stdout/stderr
with the unchanged `qa_contract.parse_completed`, compares the full saved
assessment, and checks the actual recorder command result. Every command must
have spawned, returned 0, joined, timed out false and have no errors. Every held
transport sequence must include its successful command result and a matching
`verified-result`, which the frozen transport emits only after lease release
and its post-command guard.

The original sequence has 13 transport operations and 10 recorder-owned command
records; the later inspect has 12 and 9 respectively. Each sequence also has
three private foreground queries. The original backend intentionally does not
persist their raw window dumps. Their synchronous successful transport result,
command identity and output length/hash are checked; they are not represented
as invented raw records or as recorder-owned commands.

The actual process requests use two exact reviewed plan-publication sources,
not a direct `qa_adapter.py` argv. Their complete code hashes are fixed. AST
literal evaluation only recovers their already fixed adapter argv; none of
their code is executed by this verifier. The two original stdout lines must be
the exact plan-publication record followed by the same final Flow result.
Each start, idempotency key, terminal and complete durable stdout/stderr is
bound. A launch-unknown, reused start, error, timeout, truncated stream, missing
assessment or failed helper sequence is rejected.

Both sequences must preserve the same actual helper APK/source/signing identity,
UID, task, runtime/App binding and independent before/after accessibility state.
Their phase nonces must be distinct; host UTC and Android monotonic observations
must order the original action before the later inspect. The action UNKNOWN
remains present in the exact original bytes.

## Explicit publication after independent review

`--publish-once` first runs the same complete host verification. It then performs
the previously qualified, exact libffi bootstrap: actual Python, `_ctypes`,
library bytes/file identity and the sole library-owned FD must match the real
host probe. It does not ignore an unknown extra FD or close libffi's private FD.

The new producer uses the unmodified `Flow`, `MainBinding`, `Session.installed`,
`Session.task` and `Session.foreground` under the original flow/global locks.
It independently revalidates the typed current runtime/App scope, held R5
namespace/root/classpaths, original native task 876, installed helper UID/APK,
and later observed foreground context. It runs exactly six recorded read-only
identity/task commands and two private foreground queries. There is no new
instrumentation, UI action, install, permission grant, task cleanup or replay.

The original evidence is re-read under its individual pins. The exact frozen
source closure and typed epoch guards are rechecked. All held binding and owned
directory FDs are released and the remaining full descriptor set must equal the
explicit bootstrap set plus the two original locks. Those locks stay held until
the producer process exits, which also reclaims the proved library resource.

The new proof step keeps a copy of the reviewed producer/verifier, exact request,
and both original execution metadata sets. Only then does the producer commit a
new compatibility envelope with no overwrite. Its evidence map binds all 177
original files and all newly created proof evidence. The original UNKNOWN file
and every old action/inspection record remain unchanged.

Any failure before the final commit leaves no accepted envelope. An I/O failure
or interruption in the final no-replace publication transaction is reported as
UNKNOWN and is never automatically retried. The coordinator must reconcile that
exact publication state from original evidence before any further decision. A
partial result file or a preview of the proof is not permission to continue.
The original stdout plus durable successful process termination are required
before the coordinator uses a newly committed envelope.

The next owned-helper mutation still performs its own original fresh inspection,
selector checks, held binding, task check and restoration. This postcondition is
an observation at one time, not a promise that the UI remains unchanged.

## Local controls and remaining status

The local suite checks complete-tree hashes, duplicate/hidden/password/truncated
nodes, failed/timed-out/unjoined/mismatched command observations, wrong legacy or
case operation types, malformed JSON, non-independent timing, the actual two
reviewed entry source shapes, real host no-replace publication with collision,
and real nonroot private-directory rejection with FD closure. Synthetic controls
are labelled fixtures and never become Android receipts.

These are host source checks. A successful `--verify-host-only` run would still
leave live runtime/task qualification and Flow admission false. At authoring,
the producer has not run and has not published an envelope. Production-ready
App count and cleanup count remain zero. Bili Accept, Meituan location and all
integrity/permission constraints are unchanged.
