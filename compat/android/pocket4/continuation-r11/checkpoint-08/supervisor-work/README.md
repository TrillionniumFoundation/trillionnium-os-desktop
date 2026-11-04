# Pocket4 continuation: prefix02 source checkpoint

Parent lineage: checkpoint07 commit `1bd04519e0c8bff7721553a6e42bb8f5fca7efeb`, delivery manifest `8cd693e13f3f34394a7236967b8f7752ae276efad7b45dfbcd09ea1487620f71` (2530 payloads). Existing checkpoint07 files remain unchanged.

The original prefix01 read-only preflight failed before any namespace or runtime work. A separate exact-PID, held-pidfd diagnostic established that the 99-byte system_server command line had unchanged nonempty argv and trailing NUL padding; all other original identity fields matched. Prefix02 changes only MainFence.capture presentation to the already-pinned canonical argv parser. Generic actor identity, launch argv, FD, Main epoch and lifecycle gates remain unchanged.

The new source freeze preserves the original failure and actual diagnostic, initial test-harness postcondition error and source snapshot, final 27 local candidate tests, and two old-source controls. The actual padded argv case fails against old source and passes against new source; a real nonempty argv change remains rejected.

The separate matching-only packet stages six exact files to new source05-02 and runs 16+27 Python controls. It proposes reusing the original native probe only after exact prior receipt, held FD identity/full SHA, source and pathname verification. It does not claim a new native build or new native controls; the prior six are referenced separately. At this source-checkpoint freeze no prefix02 remote matching request has been submitted, no new plan preflight has run, and no normal/death/Android or installed-supervisor runtime qualification is granted. Later actual receipts must be additive.

The factory diagnostic03 runtime02 peer review is limited to exact controller/stage/request deltas and recorded host03 build binding. It is not execution or authorization of that runtime, does not change the original runtime01 failure, and does not independently recompile or rehash remote ELF/header closure.

This allowlist contains UTF-8 source and evidence only. Instantiated transport wrappers, ELF files, archives and caches are excluded. No Git operation is performed here.
