# NORMAL02: fixed snapshot lifecycle before strict framework build

State: **SOURCE_ONLY / UNRUN**. No Hepta call, Python execution, Soong command, Android action, installation, branch update or PR update was made by this package's author. Whole-app readiness remains **0/45**.

This is the independently reviewable successor to NORMAL01 tree a45cd4f09ad8247ce0f621021357808a58e16a23. NORMAL01 was never admitted and remains preserved. Its direct sudo timeout lacked proof that every owned monitor/helper descendant had ended.

## Change and unchanged authorities

The new fixed root supervisor creates only its snapshot child or one of three fixed lifecycle-control children. It runs as real/effective/saved UID0, disables dumps and establishes its own subreaper before forking. Root retires its own root-UID descendants. The original operator remains UID1000 and uses the original sudo/Python policy with inherited environment. No HOME value is assigned.

The outer owner establishes its own subreaper and a fresh sudo session. Both layers preserve the leader PID until group signalling has finished, then reap it and retire any adopted descendants through bounded own-child/pidfd authority. Numeric fallback following pidfd allocation failure is restricted to a kernel-proven unreaped direct/adopted child with a single waiter. Every original failure and later cleanup error stays in the receipt.

Signals may target only this invocation's children and descendants. The seven fixed Main PIDs are explicitly excluded. There is no all-/proc scan, arbitrary privileged command interface, Main signal or service operation.

The entire 14,294-byte Main snapshot and original 40 pure controls are byte-identical to NORMAL01. The framework controller differs only in the fresh ROOT literal. Its actual builder468 ELF, 491-source manifest, prior failed terminals, published 214-project manifest, source locks, two strict targets and existing builder cleanup are unchanged. The original fence compare function is also unchanged.

The two normal Rust locks are acquired before recover and the typed build call. The actual old typed lock is verified in full before its monotonic extension to 224 projects. Reconciliation verifies existing/new projects and publishes the new full manifest atomically. This package does not pre-qualify source reuse or fabricate a manifest.

## Timing and retirement

The operator installs a watchdog before Popen. Its observation deadline is start+25 seconds and final retirement deadline is start+30 seconds. An early pidfd error does not create a false five-second cross-UID cleanup promise; the operator may wait within the same absolute limit for the fixed root supervisor to end.

The root bootstrap imports os, signal and time, captures its entry time, then installs the entry+15-second watchdog before the remaining hash/parse/compile/import work. Interpreter startup and those first three imports precede the root timer and are covered by the operator's timer. The supervisor checks its own absolute deadline independently of the original child snapshot alarm.

Root retirement has at most five seconds and never extends past entry+20 seconds. Signal-handler restoration, subreaper restoration, nonreaping wait authority, final ECHILD, all acquired pidfd/memfd closures and both output reads participate in qualification. A missing or unreadable root report cannot stand in for cleanup: retirement uses kernel child authority first, then the report is checked only for semantic qualification.

Inputs use a sealed anonymous memfd, bounded at 196,608 bytes. Root-child stdout/stderr are each bounded at 65,536 bytes; outer output streams are each bounded at 131,072 bytes. The original snapshot raw stdout and stderr are preserved alongside each root-envelope and operator lifecycle receipt. No App private UI or account data is involved.

## Real controls required before the build

The original 40 pure controls still run during staging, before ROOT creation or Main reads. Four additional process controls are mandatory before the normal build:

1. A root child and grandchild remain alive until observation timeout, then are killed and reaped with the original TimeoutError preserved.
2. A root descendant creates its own session while its leader exits zero; orphaned success is refused and the escaped child is independently retired.
3. A pidfd EMFILE seam is triggered only after a real root fork/session handshake; the owned child is still retired and the original errno remains.
4. A separate operator-side EMFILE seam follows actual sudo Popen and a live unreaped leader observation. All actual sudo/root descendants must be retired; this control does not assume that root startup happened. The three separate root cases require actual UID0.

Expected failure of a controlled child is not a successful snapshot. Root-control qualification rejects unrelated secondary errors. The operator case permits only explicit cross-UID signal EPERM or recorded, independently reaped adopted descendants; finalization errors prevent the build. The four cases must finish inside a cumulative 30-second qualification window. This is not claimed as a hard 30-second execution kill.

These new controls have **not been run**. The static peer read the 25,216-byte lifecycle core and found no definite blocker within its stated scope. The final core changes only a misleading fixed-five-second metadata label to describe the caller-supplied absolute deadline. The root supervisor and complete packet still require Root's review and actual execution.

## Exact request and resources

Fresh owned root: /home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-provider-build-02-20261106

Fresh key: pocket4-native-typed-ingress-framework-strict-provider-two-target-build-02-20261106

The reviewed request is exact-request.json: 780257 bytes, SHA-256 b11c431457ece570e2548c8188f92b48480e9da57b70d61aeaf1bea0ec4bd775.
Its plain UTF-8 stdin is 707866 bytes, SHA-256 b73c8211f9f23e343e2e1aded5ee951755885fa851f575a02346a30178836593, below the tool's 1 MiB stdin cap.
make_request.js reconstructs both exact byte strings from the 15 runtime members and stage.py and checks every source pin.

Original resources remain: CPU 200%, memory 10 GiB, owned swap 1 GiB, one build job, nice 10, 6,100-second builder wait and 6,400-second request timeout. Fresh admission still requires MemAvailable >=13 GiB and SwapFree >=2 GiB. This leaves 3 GiB over the job's memory budget and 1 GiB over its swap budget in those specific admission counters. Main's five limits remain unchanged, including pids.max=12288. Pressure or transient effects are not ruled out.

## Evidence and acceptance boundary

The actual builder468 compile03 remains PASS: 62 command results, 15 exact updater controls and nine exact source controls. Its 205/20 registered tests are not counted as executions. Original source/config/tool closure and complete non-forced child cleanup are bound to that real report.

The original first materialization timeout and 296 reaped children remain historical FAIL evidence. The later strict Soong graph failure and its one reaped child remain FAIL evidence. Their full pinned original terminals are included.

Even a later normal command PASS will need separate actual implementation-JAR and Android JNI object/header/link qualification. Header JARs and host-only native libraries are insufficient. This host build grants no new QA epoch, runtime authorization or whole-app acceptance.

Review SOURCE_REVIEW.json for exact startup/retirement scope, normal01-independent-risk-review.json for findings, the four patches for precise changes and FROZEN.json for the complete payload map. Only Root may dispatch the request, once, after review and its resource window.
