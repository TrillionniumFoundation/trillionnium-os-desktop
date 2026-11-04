# Independent Go4 / 9 GiB profile: local proposal

## Assessment

The normal builder can consume this configuration through its existing checked Go memory patch. It is a plausible smaller build attempt, with no successful compilation evidence for this size. It has not prepared remote source, submitted a job, compiled code, or changed Main.

The new profile lowers the Go soft setting from the original 6 GiB to 4 GiB and lowers the owned unit's memory cap from 11 GiB to 9 GiB. It requires at least 13 GiB of **current** `MemAvailable`, preserving the same four-GiB admission difference. This calculation does not reserve physical memory. Swap remains capped at 1 GiB, CPU at 200%, affinity at two allowed CPUs, normal builder jobs at one, and the controller deadline at 6400 seconds. Targets, locks, recovery and source/artifact checks are unchanged.

The latest root-reported fixed-file sample at 22:25:34 UTC was 15065321472 bytes of available memory, approximately 14.030674 GiB. That sample would have approximately 1.030674 GiB above the proposed 13 GiB threshold. It is historical evidence only. The new controller reads memory again in its own invocation; neither this sample nor a successful preparation admits a build.

## Material risk

The only actual completed build used Go6 / MemoryMax 11 GiB / swap 1 GiB. It reached both caps and recorded 27 `memory.max` events, with zero OOM-related events. The original candidate05 Go6 / 15 GiB admission attempt and the separate Go5 / 14 GiB admission attempt both stopped before compiler execution. Those failures do not measure either profile's compilation memory needs.

A lower Go soft setting does not prove that peak total memory falls by the same amount. The Go4 profile may spend longer collecting memory, hit its owned-unit cap or deadline, or fail to finish. The program records the first outcome, resource peaks, memory events and cleanup; it does not retry, lower a gate, alter an existing attempt, or raise Main's limits. A new resource profile would require a separate reviewed source and attempt again.

## Exact source change

The builder source always starts from the **original** 449-file manifest `e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017`, not from the Go5 output. The only builder-source change is the single byte `6` to `4` in:

`android/apex-compat/0008-soong-leaf-go-memory-budget.patch`

The new patch remains 583 bytes and has SHA-256 `0f51b488dfcb6200281d25d4b6d3da594870c6e747d2629f7b2e1bed8ae4ddbd`. Its complete diff from the original Go6 patch is `original-go6-to-go4.patch`.

The new controllers are derived from the immutable Go5 profile with an explicit pinned local generator. `controller-go5-to-go4.patch`, `fence-template-go5-to-go4.patch` and `request-generator-go5-to-go4.patch` contain all changes. Their source-tree verification, private-inode mutation checks, exact applied-patch-map check, engine 925-file contract and artifact scope are preserved. The only functional differences are the proposed soft/cgroup/admission budgets and their fresh identity/pin bindings.

The original 449-file manifest was recovered exactly from the verified Go5 preparation by reverting its one patch-hash value; the complete recovered JSON SHA matched the original `e7c225…` pin. The same actual manifest is used locally to derive `expected-copied-builder-source-manifest.json`. That file is an expected inventory, not proof that a Go4 remote tree exists. Preparation still validates and copies every original file, makes only the private Go6-to-Go4 mutation, and checks the complete resulting inventory. A future actual receipt must have the expected new manifest hash.

The 925 engine files, candidate05 manifest `4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba`, six signal fixes and feature-disabled default remain unchanged. The normal builder executable remains `16df26d88391c22c9f076917531f022907ec5608bd31e58e05c898605db9dcc4`.

## New identities and request boundary

The proposed new root is:

`/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined05-go4-01`

Its `builder-source`, `engine-working`, `android-out`, `attempt-01` and `build-fences-01` are independent. Preparation and build reject an existing target rather than overwriting it.

The stable preparation key is `pocket4-native-combined05-go4-full-source-preparation-01-20261104`; the stable build key is `pocket4-native-combined05-go4-fenced-full-engine-flag0-build-01-20261104`.

The preparation request is frozen locally under `prepare-request-01` and has not been submitted. No actual Go4 preparation or builder-manifest receipt exists yet. The build request can only be generated after those two actual files are received with explicit hashes and match the new frozen plan. The unbound fence template rejects execution before actions.

`main_snapshot.py` remains exactly `f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb`. Main's identity, epoch, activation, service-root cgroup identity and resource limits are still compared before and after, and Main's OOM deltas must be zero. This proposal does not broaden any process-identity parsing or guard tolerance.

## Local verification and remaining gates

The 22 bounded local controls passed against the new functions. They include actual local no-follow/hardlink rejection, precise patch bytes, budget boundaries, template refusal and default PLAN behavior. Their memory values and projection receipts are fixtures. The separate expected-manifest derivation uses the complete previously verified 449-entry manifest. Neither result is a new remote preparation or build.

Successful preparation would authorize no compilation by itself. A successful future build would still require actual input/final receipt equality, full artifact hashes, the complete host suite, binary review and owned runtime controls. Paired ART, enabled metadata generation, the factory service, Android adapters, NOFILE=0 semantics and whole-app qualification remain outside this proposal.

The original candidate05 admission failure `1a1a886d2c7-fc05-2ef4` and Go5 failure `1a1a8a8aed2-fc05-2f5f` remain preserved. Root reported the latter's authoritative failure and terminal SHA `4910a7b38b0ba5fbd927bf1f9b19c74f46c549f97a474798878579edcc903426`; this subagent has not replaced or reinterpreted that receipt.
