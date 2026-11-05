# Owned Bili QA r3: bounded complete trees and a fixed public query

This is source for the independent self-instrumentation package
`org.droidloom.qa.bili.r3`, protocol `pocket4-owned-bili-qa-v3`. The already
installed r1 and r2 packages are not replaced. Their claims, source, APKs,
signatures, UIDs and original failures remain separate. A successful r3 build
does not authorize installation or UI actions. Each later step must bind this
source manifest, the actual new build/APK/signer, the actual new installed UID,
and the held Main/recorder gates.

## Actual reason for this revision

The r2 search-entry run launched a fresh Bilibili task and successfully inspected
76 nodes. Its subsequent click request failed before `performAction` with
`TREE_NODE_OR_DEPTH_BOUND`; a fresh independent post-inspection failed the same
way. Both independent finally after-state commands completed, and exact-owned
task cleanup removed task 876 while retaining Home task 851. The aggregate run
remains FAIL. The old failure combined the node and depth limits without
counters; it cannot establish which one was exceeded, or the later tree size.
The original source and actual receipts are not rewritten.

The r3 traversal admits at most 512 nodes, depth 32 and 64 children per node.
The canonical result is at most 524288 bytes; the tree reserves 65536 bytes for
non-tree metadata. These are complete traversal limits: exceeding any limit
fails the operation, never returns a truncated tree as success. The traversal
still omits the contents and descendants of invisible or password nodes, as
declared in its existing `visible-non-password-subtrees` contract.

Each capture has a small counter record: capture purpose, attempted/emitted
nodes, maximum attempted depth, maximum children, serialized bytes, timestamps
and a completion flag. Distinct node, depth, child and result errors retain
these counters. No node titles or text enter this diagnostic record. Python
checks the exact bounds and counter schema, rejects incomplete success, and
matches a successful inspection's counters to its actual complete JSON.

The existing display-0 focused application-window gate, target package and UID,
host activity/window binding, pre-action whole-tree/window equality, refreshed
target hash, final whole-tree check, eight-second operation deadline and
twelve-second watchdog remain. No action is retried. A changed tree still
fails and requires new evidence; increasing the traversal budget does not
remove the freshness or focus gates.

## Bounded result transport

The helper stores its raw canonical result in its own nonce result file. Its
instrumentation Bundle carries one gzip member under the new
`owned_qa_result_gzip_base64` key. The raw result is at most 512 KiB, gzip at most
256 KiB, and base64 at most 349528 characters. Python bounds decompression to
512 KiB plus one sentinel byte and requires one complete member with a valid
checksum and no trailing or concatenated data. It does not accept the old r2
wire key. Actual command exit, unique successful finish code -1, request hash,
nonce, helper UID, Main/transport post-guard and restoration are still required.

This codec keeps a larger allowed tree from expanding unchecked into a Bundle
string. It is not a diagnosis of the original traversal failure and does not
guarantee Binder availability. Android documents that the Binder buffer is
shared by concurrent transactions. The original recorder saves full command
output without its own numeric read cap; this producer and the r3 parser supply
the explicit output bounds. The parser's stdout cap is 353624 bytes, including
4096 bytes for instrumentation framing. Future collectors must retain these
bounds and fail rather than truncate a result into success.

## Only one new action: a fixed public query

The existing exact-node click remains available. The new `set_text` operation
only accepts the literal public query `微积分`. Its plan must specify an observed
exact `tv.danmaku.bili:id/...` resource and class `android.widget.EditText`.
The current complete tree must contain exactly one matching enabled, visible,
non-password editable node that advertises `ACTION_SET_TEXT`. The helper checks
the same facts after refreshing that target, performs the action once with
`ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE`, then refreshes it and verifies the
actual text equals the fixed query. A returned action acknowledgment without
that readback is insufficient.

The capability does not itself authorize a particular search-field selector.
The actual workflow must first observe the real search page. It adds no IME
submission, clipboard, generic typing, global Back, seek, settings write,
permission adoption, permission grant or touch-exploration action. Later
navigation and playback controls remain bound to their own observed controls.

The Python sequence preserves the first error and independently attempts one
fresh after-state in `finally`, including after action failure. It never
replays a click or text action. A successful after-state cannot replace a
failed operation or qualify restoration by itself. The frozen R4 recorder
manifest remains `52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1`.
The adapter rejects known old helper UIDs 10164 and 10165 and has no v2 fallback.

## Build-only scope and actual remaining gates

Compile API is SDK31; min API is 31 and target API is 33. The same pinned JDK21,
SDK31 public android.jar, D8/R8, aapt, zipalign and apksigner inputs are checked
before and after the build. This is a non-debuggable, testOnly, no-backup,
Java-only self-instrumentation APK, with no Activity or Android permission and
only Bilibili package visibility. It never instruments Bilibili itself.

The create-only source and output roots are
`/home/alex/work/pocket4-owned-bili-qa-r3-source-01` and
`/home/alex/work/pocket4-owned-bili-qa-r3-build-01`. The generated request uses
one CPU, 512 MiB RAM, zero swap, TasksMax 128 and a 300-second deadline. Its
stable key is `pocket4-owned-bili-qa-r3-static-build-01-20261105`; the author has
not submitted it. Default builder, stage, adapter and generator entry modes
remain PLAN_ONLY.

Nine local control groups execute the actual Python contract and sequence
code. They cover old/new tree boundaries, bounded gzip decoding and corrupt or
concatenated members, strict finish/UID/wire gates, fixed-query restrictions,
exact editable selection, safe partial counters, and independent after-state.
The Session control explicitly substitutes Android-facing methods; these
controls are not Java compilation, Android behavior or accessibility tests.
The source package includes no private commercial UI or raw journal.

Actual r3 compilation, installation, focused-window behavior, fresh click,
search-field readback and playback are still unqualified. Playback continuation,
pause/resume, Back/reopen, cold start and app-attributed real audio remain
separate acceptance gates. No whole-App readiness conclusion follows from this
source freeze or the preceding launch/inspection successes.

## Primary API references

- Android ACTION_SET_TEXT, its Bundle argument, and editable-node contract:
  https://developer.android.com/reference/android/view/accessibility/AccessibilityNodeInfo.AccessibilityAction#ACTION_SET_TEXT
- Android Binder shared-buffer and ambiguous-failure semantics:
  https://developer.android.com/reference/android/os/TransactionTooLargeException
- The unchanged all-display window API:
  https://developer.android.com/reference/android/app/UiAutomation#getWindowsOnAllDisplays()

These API references explain the selected contracts. They are not asserted to
be byte-identical source for the installed Android framework. The exact pinned
SDK31 jar remains the compilation gate.
