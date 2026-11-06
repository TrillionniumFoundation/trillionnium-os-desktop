# Independent review of Stage A's current identity checks

Reviewed source: `stage-a-candidate-r1/runtime_stage_a_once.py`, 49,806 bytes, SHA-256 `2a6dfffa73fa7698e6d59039d992c78a17ddaf07f0a01eab0973c327870c5c1e`. No runtime/core/stager/request bytes changed during this review.

## The earlier helper identity is not a later observer

The fixed earlier controller result is the actual `inspect-after-partial-commit-01` job `1a1b2f182c1-fc05-803d`: complete stdout 13,947 bytes / `23639dfd1822118c1379e306ba45bf2a1e0d5c8b30ee660c6b50125e8b7cdf84`, terminal 733 bytes / `8c1b239ea57641d497f59f8f417ec66c663d4290366bb4f2fa008f0460109037`. Its embedded child and original adapter outputs are hash/length checked against their actual bytes. The adapter output is 5,752 bytes / `612ed6e8b154843990feec5ad647727a747e46faa540896c1534f561bd8ebd7d`.

`prior_installed_identity` requires the original successful controller/child schemas, durable exit 0, normal held-pidfd retirement, no signals or timeout, empty stderr, released namespace authority, original read-only operation and stable installed-before/after records. It extracts only the complete installed-helper identity as an expectation. It verifies that this earlier adapter result ended before the newer failed case began. The public proof labels its usage `previously_qualified_installed_helper_identity_only` and `is_later_observer_for_failed_click=false`.

The helper identity includes the exact original package, UID 10157, installed base path, 37,008-byte APK hash, signer reference and held-file device/inode/mode/UID/GID/length/mtime/nlink. These are not newly observed values merely because they appear in the earlier receipt. Stage A must actually reacquire and rehash them using the unchanged Session method.

The newer failed step has no successful `case-00-operation.json`, so Stage A does not invent its missing installed-before or foreground-after fields. The original ten-command sequence proves the two actual UID/path command rounds and contains the full failed request's scope. The fresh foreground expectation comes from that actual request, not the earlier inspect result.

## Exactly six recorded commands and two private foreground reads

The sequence below runs twice under the original Flow/global locks and held-R5 binding.

| Original method | Exact Android argv | Bound |
|---|---|---|
| `Session.installed` | `/system/bin/cmd package list packages -U --user 0 org.droidloom.qa.successor.p8f89f253350ba2fa.r1` | 8 s |
| `Session.installed` | `/system/bin/cmd package path --user 0 org.droidloom.qa.successor.p8f89f253350ba2fa.r1` | 8 s |
| `Session.task` | `/system/bin/cmd activity stack list` | 20 s |
| `Session.foreground` | `/system/bin/dumpsys window displays` | 15 s; original private backend |

`Session.installed` performs more than those two command reads: it reads the returned APK through the held Android root, hashes the complete bytes against the originally verified build/signature, guards before and after, and returns the actual held-file metadata. Both fresh rounds must exactly equal the fixed earlier identity. Merely matching a package name, UID or version does not pass.

`Session.task` requires the original selected task, package, `prelaunch_absent=true`, `cleanup_allowed=true`, and an actual exact leaf task. The native launch scope is independently rechecked through the original `ui.launch_gate`; the original 64-bit native object ID is retained as a Python integer.

`Session.foreground` calls its unchanged package predicate and returns the complete typed activity/window/epoch/app scope. The original error label containing Bili remains unchanged; its predicate is not weakened. Both current rounds must exactly equal the actual failed action's complete scope, including the window token. Any difference stops the producer. There is no task activation or window manipulation.

`verify_six_commands` requires exactly 50 files: intent and held binding, six complete command intent/result/stdout/stderr quartets, and eight complete transport intent/command-result/verified-result triples. The inherited `OriginalSequence` checks actual argv, held seven-FD/environment route, single owner PID, command chronology, complete raw hashes, normal zero/joined command status, original post-guards and lease-release receipts. It consumes every file exactly once. Private dumpsys bytes remain unpersisted; their original length/hash receipts remain required.

No instrumentation command is issued in this current stage. Instrumentation argv appearing in the historical parser is an expected-value comparison against already saved old command bytes, not an execution path.

## Qualification remains layered

Fresh held-R5 authority, full source/build/file rechecks and the original two-round predicates must all pass. The worker closes Main authority and verifies only the exact library descriptor and two original lock descriptors remain. The candidate is nonauthorizing. Its parent must observe normal child death through its original held pidfd, complete output and restored descriptor identities, and root must independently obtain the actual durable terminal. Neither the earlier helper receipt nor the new candidate file bypasses those gates.

This review found no additional static incompatibility. It does not claim that Stage A has run or that the current foreground still matches. Source, task, helper or foreground changes must fail through the unchanged predicates. The review does not confer any permission on another app or on a future helper revision.
