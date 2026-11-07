# Combined candidate04: exact full build handoff

This frozen controller prepares a new independent source copy and then invokes the previously successful normal builder. Neither mode has been submitted by this agent. Root owns admission, actual build execution and subsequent runtime qualification.

## Executable requests

`exact-preparation-request.json` is the complete, hash-checked, create-only preparation request. It verifies all source inputs before creating `/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined04-01`. It uses one CPU, 1 GiB and a 300-second outer limit. It does not start an engine build, Android process or service.

After preparation succeeds and the actual `preparation.json` SHA is observed, `make_build_request.py --preparation-sha256 ACTUAL_SHA --output NEW_REQUEST.json` produces the complete build request. The builder itself rechecks that receipt and every source input before starting. There is no prefilled or invented preparation hash, and the request generator does not submit anything.

The build request has CPUQuota 200%, MemoryMax 11 GiB, a 6,400-second controller limit, and the original normal builder's `--jobs 1`. The controller sets and reads back only its own current unit's 1 GiB MemorySwapMax. It requires at least 15 GiB MemAvailable and 1 GiB SwapFree before admission. The latter is an explicit additional admission guard; the prior successful controller recorded a 1 GiB swap limit but did not test free swap. Neither guard causes an automatic lower-budget retry.

## Source and import closure

The candidate04 manifest binds 948 files, of which 925 belong to the engine. All six signal-mask-r1 outputs are verified before preparation, before build and in actual raw/effective build receipts. The candidate, original R16 tree, old successful output and original builder-source remain unchanged.

The normal builder's local source override requires a Git checkout with the locked origin and base ancestry. Candidate04 is a content freeze without that checkout. Preparation therefore performs a separate local Git clone with no checkout, no hardlinks and no alternates, pins the R16 HEAD, and writes exactly the 925 candidate bytes into the new working tree. It restores executable intent only from the exact original R16 file modes. It does not use a name-based executable heuristic or change frozen candidate modes. The builder receives this new tree through `DROIDLOOM_NATIVE_BRIDGE_SOURCE`.

The old R16 receipt identifies 22 normal projector changes. Every corresponding candidate input must still equal its R16 source input. Preparation records the exact expected 925-file effective projection by replacing those 22 hashes. An unexpected projector input or output is a failed gate.

The complete 449-entry builder-source manifest is copied and checked as files, symlinks and modes. The executable remains the original successful `16df26d8…` binary. Original `native-engine-build --tests` package/source locks, normal source-projection recovery, compiler setup and selected-target dependency checks remain in force.

## Actual artifact gates

The normal builder constructs `libberberis_arm64` and `berberis_arm64_host_tests` in a fresh `android-out`. It does not build ART or the factory and does not install anything. The actual input receipt must match the prior successful pinned signal build's external compiler, source locks and libandroid reference, the exact copied builder inputs, all 925 raw source hashes and all 925 projected hashes. The final receipt may differ only by the expected status and new artifact records.

Actual ELF checks require the original SONAME and `NativeBridgeItf`, the private `DroidloomBerberisGenerationV1` export, the disabled PROCMET2 marker, and absence of the enabled marker. A missing export or marker is a failed build qualification, even if compilation succeeded. The host executable, all three corpus files and all three matching shared libraries must have their recorded hashes under the fresh output paths.

The feature remains **default disabled**. This full link is useful for combined source/link regression and retaining the already repaired signal behavior. It does not repair or qualify the enabled metadata production path by itself. An enabled flavor requires a separate explicit source/flag manifest and paired ART lifecycle proof; it must not silently alter candidate04 or this build's scope.

## Failure and retirement behavior

The new controller becomes a subreaper for its own children. It binds its resource unit to its current process, admits only the expected host proc view, and requires actual owned-child enumeration before launching the builder. An interrupted or timed out direct builder is stopped through its newly created process group while the direct PID is still owned and unreaped. Adopted descendants are stopped through pidfds and reaped with exact waitpid calls. Enumeration or one child failure is recorded and does not become a cleanup pass. Bounded retirement runs before terminal-resource reporting, so a resource-read error cannot skip child cleanup.

The local executor exposes a different proc PID view and lacks the task children file. This was a real failed initial control and is retained in `pre-freeze-control-findings.json`. The final local real-pidfd test therefore substitutes only an exact known owned child enumeration, explicitly reported as a seam. One direct child and one nested child were actually stopped/reaped; remote proc enumeration is still a mandatory, unrun admission gate. The remaining offline controls cover default no-action behavior, mutually exclusive modes, missing preparation receipt, path rejection, enumeration failure and continuing after one child failure. These are controller checks, not a remote build result.

## Gates after successful linking

Root must run the complete matching host suite using the established wrapper, loader, data and libraries. Its prior contract is 3,793 registrations; the eight adapter controls are not a substitute. The new combined engine must also pass the four owned signal cases in the matching isolated Android environment.

Still separate: enabled engine and paired ART, V2 factory runtime and trusted Android positive, outer ARM64 guest metadata adapter, ordinary NOFILE=0 semantics, host-native credential/root/mount/final-thread lifecycle, and full application acceptance. Whole-app readiness remains false.
