# Task 878: one explicit partial-case proof

This candidate verifies historical evidence for `close-and-observe-search-01`
and the genuinely later `inspect-after-search-rejection-01`. It never changes
the original failed result, its UNKNOWN outcome, the frozen recorder consumer,
the helper, the adapter, foreground checks, or the whole-tree/window checks.

The first submitted package is **host-only**. It does not enter Android, take a
Main action lock, call a runtime guard, inspect the live foreground, invoke
instrumentation, install anything, send a signal, or create a reconciliation
envelope. A successful historical report alone cannot admit a new UI action.

## Exact evidence

The original case's authoritative job is `1a1b272ec9d-fc05-7e0d`, durable failed
with exit 1. Its owned child exited normally with code 1 after the unchanged
case runner returned 2. These outcomes remain failures. The already collected
private archive contains 268 original files, 1,509,462 original bytes: 257
files inside the failed step plus 11 original source/input files. Its exact
2,155,722-byte body is pinned; the verifier rechecks every member against its
original file and complete stat.

Step 0 has a successful close acknowledgement and a separate complete
inspection proving the unique visible, nonpassword, untruncated homepage
search control. Step 1's actual helper returns finish 0 and
`INSPECTED_TREE_OR_WINDOW_CHANGED`, explicitly without an attempted action.
The frozen Java source raises this error before setting `actionAttempted` and
calling `performAction`. The new verifier checks the **complete original
failure wire**, including secondary errors and pre-connection state, rather
than treating the public failure diagnostic as a success assessment.

The failed suffix is given its own typed retirement/state result. It must
have no acknowledgement fields, one complete action-target capture, no final
action capture, the original exact request and wire hash, unchanged own-service
flags/capabilities, and actual independent before/after state probes. The
existing success parser must still reject it. The code never passes this
failure to the success-only `qa.assess_restoration` function. This says nothing
about autonomous app activity or business success.

All three final post-inspection nonces declared by the failed case remain
absent. No sequence summary or final postcondition is invented for that failed
step.

The later observation is tied to actual job `1a1b285c279-fc05-7e67`, durable
complete exit 0, its normal held-pidfd child retirement, original stdout,
original step result, and original plan. The verifier reads exactly its full
81-file step: 9 commands, 12 transport receipts, and three independent helper
nonces. Its complete inspection must reproduce the already observed homepage
search control and the exact actual tree/window hashes. Its UTC and Android
elapsed times must follow the failed case.

## Source and identity checks

`partial_case_core.py` is a new pure verifier. It uses the unchanged common
command/environment predicates, helper wire parser, plan validator and task
parser from pinned actual sources. The full 26-file helper/recorder source
closure and both actual manifests are re-read. The original task-876
`fixed_launch` and success-only `validate_step` are not repurposed; task 878 has
an explicit new boundary and exact native receipt.

The only namespace cross-observation projection is the previously reviewed
eight nsfs `mtime_ns` fields in the frozen R5 comparison function. Namespace
device/inode/type provenance, process identity, APK/data/classpath identity and
all other fields remain exact. Raw bindings are retained unchanged.

The real build ran as UID 1000. The host packet carries the already retrieved
33,691-byte original build receipt, byte-for-byte, as an archival input. It does
not describe the original file as root-owned or claim to have performed a new
live build validation. A future runtime candidate must still use the unchanged
adapter's actual build and helper checks.

`verify_partial_case_host.py` uses the previously executed bounded no-follow
file reader, complete stat/path rechecks, and whole-process FD identity census.
Only two new root-private host files can be written: a hash-only public proof
and a private archive of the later observation. Both are O_EXCL, synced and
read back. The private archive and any private UI raw must remain outside Git.
Unknown descriptors are never closed or tolerated by count.

## Entry and acceptance

`candidate-r1/process-request.review-only.json` is the exact root-reviewable
process request. Its stable key is
`pocket4-beike-task878-partial-case-host-verifier-r1-20261106`. The stager is a
minimal derivative of the already executed inspection stager: seven fixed
files, root 0400, O_EXCL/fsync/readback, unchanged FD identity, then the real
staged Python source with `--verify-host-once`. Timeout is 300 seconds, one
CPU, 512 MiB. No target request is submitted by the preparation program.

Local boundary controls use actual public controller originals. They test
failed/incomplete observer rejection, preservation of the original failed
case, wrong task/authority rejection, duplicate/nonfinite JSON rejection and
the exact sealed byte closure. They do not simulate a root run or claim the
complete private archive has been validated locally. The next meaningful gate
is the actual fixed host verification with complete stdout and authoritative
durable terminal.

## Subsequent stages remain separately gated

After the host-only verifier actually succeeds, a separately reviewed runtime
candidate will reacquire the original Flow and action locks, fresh held R5
authority, exact task 878, the complete current installed helper APK/UID and
the unchanged `Session.foreground` predicate. It will recheck this historical
proof and originals and produce a non-authorizing candidate. Normal owned
child retirement and the real durable controller terminal must be recorded.

Only a subsequent explicitly reviewed bounded commit may publish a new typed
proof and compatibility envelope at the frozen consumer's expected relative
path. The new producer must identify itself; it cannot impersonate old
`operation=ui` or old `Flow.reconcile`. Original FAILED/UNKNOWN remains intact.
Any new UI action still needs the original fresh state, foreground, selector,
complete-tree/window, node refresh and final-window gates. Neither the runtime
candidate nor this commit is executed or implemented by the host packet.

Bilibili's original unknown history and authorized independent-cell boundary,
Meituan's location restriction, integrity checks and every other original
security constraint remain unchanged. Production-ready count remains zero.
