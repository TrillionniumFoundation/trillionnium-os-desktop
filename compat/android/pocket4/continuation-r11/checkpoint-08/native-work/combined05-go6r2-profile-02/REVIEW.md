# Independent Go6 / 11 GiB build profile, second attempt

This is a new preparation and output root. It does not modify or retry the original Go6, Go5 or Go4 attempts. Nothing in this package has been submitted remotely. Main deployment, ART pairing, factory activation and whole-app qualification remain outside this build.

## Evidence and decision

The actual Go4 attempt `1a1a8b5b235-fc05-2f88` reached its 9 GiB memory maximum and 1 GiB swap maximum. Its own cgroup recorded 4,344 `max` events, one `oom` and one `oom_kill`. It ended after 762.44 seconds with controller SIGTERM and builder return code -15. The SIGTERM sender is still unproven. The artifact gate did not run. Owned cleanup completed and the pinned Main before/after identity, limits and OOM fences passed. Its source projection journal remains present and must be recovered by the normal builder under its normal locks.

The prior signal engine build completed with the same pinned normal builder and Go6 source projection under 11 GiB RAM plus 1 GiB swap. That successful build also reached both hard limits, with 27 `max` events and zero OOM events. This is evidence for returning to that actual working resource package; it is not proof that the new combined 925-file engine will build successfully.

This profile therefore restores the original Go6/11 GiB package. It changes the fresh admission thresholds to MemAvailable at least 14 GiB and SwapFree at least 2 GiB. The RAM difference is **3 GiB**, compared with the earlier 4 GiB fixture choice. The swap difference is 1 GiB. Neither difference reserves physical memory or excludes later activity by other workloads. Root explicitly requested this independent profile after reviewing the actual 9+1 OOM and prior 11+1 success; no repository instruction is changed.

The 2026-11-04 23:00:32 UTC sample reported MemAvailable 15,560,728,576 bytes (14.492 GiB) and SwapFree 3,714,203,648 bytes (3.459 GiB). It is historical evidence only. The controller reads `/proc/meminfo` again at the actual new attempt and rejects either threshold failure without a lower-budget or alternate-key retry.

## Exact resource package

| Item | Value |
|---|---:|
| Owned MemoryMax | 11 GiB / 11,811,160,064 bytes |
| Owned MemorySwapMax | 1 GiB / 1,073,741,824 bytes |
| Fresh MemAvailable minimum | 14 GiB / 15,032,385,536 bytes |
| Fresh SwapFree minimum | 2 GiB / 2,147,483,648 bytes |
| RAM admission difference | 3 GiB / 3,221,225,472 bytes |
| Swap admission difference | 1 GiB / 1,073,741,824 bytes |
| CPU | 200%; last two CPUs in the existing allowed set |
| Builder parallel jobs | 1 |
| Inner builder timeout | 6,100 seconds |
| Outer managed task timeout | 6,400 seconds |
| Go soft memory budget | 6 GiB |

The controller, outer fence and source request remain UID 1000. Only the unchanged pinned helper uses sudo for read-only Main observations. The build never changes Main cgroup settings. A passing pre/post fence does not prove absence of transient pressure or causal independence throughout the interval.

## Source and recovery

The complete 449-file builder source copy is **unchanged**, including the 583-byte Go6 patch. Its manifest must remain `e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017`. There are zero source-row changes and no private Go-patch rewrite function in this controller. The patch hash is `6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e`.

Candidate05 remains its immutable 948-file freeze, with 925 engine files and the six previously verified signal source files. The raw metadata generation feature remains off. The pinned builder ELF remains `16df26d88391c22c9f076917531f022907ec5608bd31e58e05c898605db9dcc4`.

The new root is:

`/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined05-go6-02`

The copied builder, engine working tree, `android-out`, `attempt-01` and `build-fences-01` are all below that new root. Preparation and the actual build are separate exact-key requests. The build request cannot be generated without a new complete actual preparation receipt and copied-builder manifest, each explicitly SHA-bound. The original source clone is independent, without hardlinks or Git alternates.

The builder uses its existing lock and projection-journal recovery for the shared AOSP working tree. No script in this profile removes or edits the previous journal or bypasses recovery. The final artifact gate additionally requires the applied patch map and the actual projected `build/soong/ui/build/soong.go` hash to match the pinned earlier successful Go6 input receipt. A stale Go4 or Go5 projection fails this check.

## Retained qualification gates

The normal targets remain `libberberis_arm64` and `berberis_arm64_host_tests`, with tests requested but not executed by the build. Raw/effective source inventories, compiler and external input pins, native bridge exports, SONAME, disabled feature marker, host binary, loader libraries and three corpora remain checked. A new explicit final resource gate rejects missing, malformed or duplicate owned memory counters and any nonzero `oom_kill` or `oom_group_kill`, even if the builder returned zero and artifacts exist. The original failure and raw counters are retained. The complete 3,793-registration host suite and four owned Android signal cases are later separate gates against the actual outputs. This build does not establish the enabled generation/ART lifecycle, NOFILE follow-up delta, or all-app readiness.

## Local checks and limits

`local-controls.json` records 29 passing local checks. They execute the actual Python admission/request functions and default PLAN CLIs. Memory readings, projection receipts and new-preparation objects are explicitly synthetic fixtures. The prior full 449-file manifest and Go6 patch are actual pinned bytes. The controls exercise below-boundary memory and swap rejection, stale Go4/Go5 projection rejection, source/scope mismatch rejection, unchanged builder binding, and rejection of a missing new preparation before actions. The actual frozen Go4 terminal is also passed through the new resource gate and correctly rejected for its observed OOM kill.

`preserved-protocols.json` records byte equality for the existing preparation, verification, lock/recovery invocation and cleanup helpers. The Main snapshot helper remains byte-identical. These controls are not a remote preparation, fresh resource admission, completed build or runtime test.

Risks remain: the earlier successful package touched both hard limits; the new engine may require different peak memory; availability may change after admission; GC overhead may alter duration; and the interrupted old projection must be recovered correctly. Any failure stays attached to this exact new attempt. No automatic retry or source/qualification relaxation is authorized by this package.
