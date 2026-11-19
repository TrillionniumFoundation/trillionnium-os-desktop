# Pocket4 vendor sparse-cone source repair

The actual R12 offline vendor attempt passed its original 42 GiB memory and
144 GiB disk gates, then failed before source reconciliation or vendor compilation.
The normal 651-project source verifier returned successfully both before and after
the attempt. Its separate content observer incorrectly required the original
requested sparse-directory list to equal Git's normalized cone list.

## Scoped comparison repair

For CTS, the unchanged plan requests 534 paths. Git's actual cone list contains
261 paths because 273 descendants are already covered by selected ancestors.
The new helper removes only these redundant descendants from the expected
comparison. It preserves the original complete plan, actual cone list, Git
commit and remote, index, clean-worktree checks and every file-body comparison.

Thirteen disposable real-Git controls reproduce the original error and verify
the repair. They also reject missing cones, unplanned broader or unrelated
cones, changed bodies, changed index entries, changed HEAD/remote, duplicate
paths and noncanonical paths. The recorded controls used /usr/bin/git 2.47.3;
the operational read-only observation used /usr/bin/git 2.53.0. These distinct
observations are not interchangeable execution evidence.

## Real source gaps remain separate

The complete read-only cone survey checked 446 sparse projects within the
651-project plan. It found 444 matches and two actual mismatches: Clang lacked
clang-r547379 and clang-r563880c; Rust lacked 1.91.1 and 1.92.0. Those paths
exist in the original committed trees but were absent from the checkout and
sparse selection. The repaired helper continues to reject these missing paths.

The fixed normal source CLI supports same-plan reconciliation and re-applies
each existing project's exact planned sparse paths. Its successful completion
and any new manifest identity need their own actual execution evidence. The
allocation estimate is not a completed restoration, a disk measurement, or
evidence that every object body was read.

## Reproduction and evidence limits

Run `python3 -I -B source_replay.py`. This validates the complete packet, preserves
the original failed R12 outcome and the historical missing-source diagnosis,
and runs thirteen fresh real-Git controls in disposable local repositories.
It never invokes the operational source CLI or reads the host AOSP checkout.

R12's real original processes and service cgroups retired. Its normal source
commands returned successfully, but the whole-source observer failed in both
phases; successful whole-source recovery is not claimed. The original raw JSON
retains complete integer identities and is never replaced with a reconstructed
success record.

This packet does not build vendor, start Android, verify the new kernel ABI,
install apps, or satisfy business acceptance. Production ready remains false.
The only app exclusions remain TextNow, TextFree and Uber Rider.

Git's primary documentation describes cone-list semantics at
https://git-scm.com/docs/git-sparse-checkout.html#_internalscone_pattern_set.
