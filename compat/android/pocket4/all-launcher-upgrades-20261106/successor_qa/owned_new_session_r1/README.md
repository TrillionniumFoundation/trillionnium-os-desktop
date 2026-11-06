# Independent Beike session after actual original cleanup

This is a local, reviewable candidate. It has not been submitted to Pocket4. The
only sealed process request initializes a new recorder flow. A native launch is
a separate future process and is not included in that request. Production-ready
apps remain zero; no obsolete build, source, App data or intermediate APK is
removed.

## Actual prerequisite

Original task 876 was removed by the unchanged recorder cleanup operation in
job `1a1b2307f12-fc05-7cdd`. Its complete, durable terminal has exit code 0. The
original sequence is one stack list, one `cmd activity stack remove 876`, and one
stack list. The result at `2026-11-06T18:48:11.546832+00:00` records task 876
absent and other tasks 875 and 877 preserved. The original worker exited
normally with its parent-held pidfd observed dead and closed; parent descriptor
identities were restored. All 177 original evidence files, totaling 888,207
bytes, retained their contents and identities. The old close result remains
UNKNOWN. This does not assert native object-registry retirement solely from
Android task absence.

The two `cleanup.*.original.*` files here are byte-identical copies of the
public actual stdout and terminal saved under `../owned_cleanup_r1/actual/`.
They contain source/task/process/FD metadata, not original UI node records or
window text. Their hashes are fixed in the candidate. The child also rereads
the original cleanup result and old 177-file archive on the host. It never
exports or copies the private archive into the new directory or Git.

## Original contract and unchanged implementations

The actual generated recorder is 39,563 bytes, SHA256
`0e50c67b1d5d251766fb58a69d9e62e119f0663ff2c4115ae326874cf95d6c09`,
under the existing source root
`/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder/`.
Its actual manifest remains
`646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4`.

The new wrapper loads that exact file and calls `recorder.main()` with a fixed
argv. It does not replace any method, modify module constants, monkeypatch the
recorder, switch namespaces directly, or implement an alternative launch or
cleanup. The original source contract, current runtime/App guards, MainBinding,
held R5 authority, classpaths, UID/data checks, transport, task parser and global
action lock remain in force.

The already deployed, actual-successful 22,233-byte cleanup wrapper supplies its
unchanged bounded no-follow reader, module loader, original-evidence recheck,
and `require_owned_exit` utility. Its `child`, `parent`, `originals` and
`verify_cleanup` action functions are never called. The actual 20,132-byte FFI
support and original 18,199-byte probe supply the same library bootstrap and
owned-child algorithm used by successful source generation and cleanup. No
new process-reaping algorithm is introduced.

The old original library initialization leaves one exact, pinned libffi backing
FD. Each new child explicitly initializes that resource, freezes the full FD
identity set, and admits only its one original recorder `flow.lock` afterward.
That lock is identified by the fixed new pathname, complete stat, access mode
and CLOEXEC flag; an unspecified extra FD is never accepted. Namespace and
action-lock FDs must have been released before the child result. Library and
flow lock are retired by the worker's normal process exit, verified through the
parent-held pidfd. No library/private or unknown FD is manually closed.

## Fixed new identity

Source stage:

`/home/alex/work/pocket4-beike-owned-new-session-20261106-r1`

New flow:

`/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe`

Old flow, retained:

`/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb`

The runtime epoch, framework epoch, baseline, App-version scope, package,
component, UID, recorder and source manifest are the same actual typed inputs
already qualified for Beike. The new scope may differ from the old scope only
in its actual new `created_utc`. This is not a claim that the Beike two-package
scope authorizes all 47 installed packages. QA helper runtime identity will be
rechecked by the existing QA adapter before a later inspection; this candidate
explicitly does not claim that check has already run.

## Step 1: init only

`init-process-request.review-only.json` stages exactly the new wrapper and the
two actual public cleanup receipts. The stager is derived from the
actual-successful cleanup stager with only fixed file pins, new root and init
entry substitutions. It retains root ownership, private mode, O_EXCL,
no-follow, exact source readback, fsync and descriptor identity checks. It then
invokes one parent/child pair for `--init-once`; it never invokes the launch
entry.

The original recorder receives:

```
recorder.py init
  --adapter-manifest-sha256 646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4
  --flow-dir /home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe
  --current-baseline /home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/baseline.private.json
  --baseline-sha256 7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8
  --package com.lianjia.beike
  --component com.lianjia.beike/com.lianjia.activity.MainActivity
```

The old flow is never reused. Existing new flow or joint-init artifact causes
rejection. The original init creates the root-only flow, lock, exact baseline
copies and scope. Verification requires exactly the original layout and empty
steps/reconciliations. There are no Android commands, native launches, helper
instrumentation, UI input or permission changes in this entry. Typed guard
reads of the live runtime are still performed by the original recorder.

Only after normal child exit, descriptor restoration and final source/runtime
file pins does the parent create `init-owned-lifetime.json` with O_EXCL and
fsync. It rereads that artifact and verifies the parent FD set again. The
artifact is not independently sufficient authorization: the complete original
stdout and an authoritative durable zero-exit job terminal must also be
accepted. A publication or post-publication failure retains all evidence and
must not qualify the artifact.

## Step 2: a separately sealed original native launch

There is deliberately no executable launch packet in this candidate. After
actual init succeeds, its original stdout provides the joint artifact's real
bytes and SHA256. Root must inspect those and the durable terminal before a
separate request can bind:

```
/usr/bin/sudo -n /usr/bin/python3 -I -B <staged>/new_session_once.py
  --launch-once --source-sha256 <same frozen source SHA>
  --source-bytes <same frozen source size>
  --init-proof-sha256 <actual successful init artifact SHA>
  --init-proof-bytes <actual successful init artifact size>
```

The entry rejects missing proof pins. It verifies the same new flow/source,
exact scope bytes and the init child's normal retirement. It requires the new
steps and reconciliations to be empty and no launch marker or launch scope.
The original recorder then performs its unchanged native launch contract:

1. Acquire the original global action lock and a fresh held R5 binding.
2. Query actual stacks. Reject any existing Beike task before launch.
3. Write the original O_EXCL launch-attempted marker.
4. Execute exactly one original UID1000 `droidloomctl launch` command with the
   fixed package/component. No retry, focus/resume route or substitute channel.
5. Require the real native success receipt, current native owner, identified
   Android display 0/task, exact package leaf and preservation of the other
   task set. Write the original launch scope and original result.

The outer verifier checks those three original command receipts, complete
output hashes, seven held authority FDs for the two stack reads, matching
transport release/post-guard receipts, current prelaunch absence and the
actual native-assigned task. It does not predetermine a new task number. A
numeric ID reused after fresh absence still requires the original real new
native ownership receipt; old task ownership is never transferred by this
wrapper. The old task must be absent in the fresh prelaunch stacks, not merely
in the earlier cleanup record.

Any failure after original launch entry stays conservatively UNKNOWN. No
second native launch is sent, no task is removed as compensation, and no
reconciliation is manufactured. A successful launch establishes ownership of
one new task; it does not establish business success, login, network health,
Chinese input, permission readiness or production readiness.

## Subsequent QA

After actual new launch qualification, construct a new independent inspect
step with new nonces using the existing helper and adapter. Its current
installed helper/APK/UID, task, foreground, before/after state, raw response and
normal command joins must all pass. The old search plan remains blocked and
cannot be carried into this new flow. Any later selector or Chinese search
input must be based on a fresh actual page inspection and the current fixed
text policy. No business UI action is included here.

All previous Bili UNKNOWN records, its independent-cell Accept boundary,
Meituan's prohibition on proactively granting location, and all App integrity
constraints remain unchanged. No historical postcondition producer is
implemented or published.

## Local checks and limits

`check_actual_predecessor.py` loads definitions only and verifies the actual
cleanup stdout/terminal pair. It rejects altered terminal bytes and incomplete
original stdout. This is evidence-parser validation under the real local
UID1000, not a simulated root/Android positive test. The unchanged owned-child
normal-zero/nonzero controls are retained in the earlier cleanup directory;
the new candidate does not rerun unrelated controls or claim new remote tests.

The Python sources are compiled locally. `prepare_init_packet.py` writes new
files once, records all exact pins and produces a diff against the frozen
actual cleanup stager. Neither program executes the packet, calls Git, opens a
Main namespace or changes an installed file.
