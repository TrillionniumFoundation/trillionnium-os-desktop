# Native601 original aconfig provider repair

This capsule fixes the source selection that stopped the actual strict Native r12 build. It preserves all 601 project revisions, the two full targets (`libberberis_arm64` and `com.android.art`), strict dependency handling, and the enabled paired engine/ART protocol. It does not qualify a complete build, an Android boot, an application, or the selected QPR1 cohort.

## Actual failure and exact inputs

The unique Native r12 job `ai395:1a1c132120b-e62c-27` failed with exit 1. Its original stdout reports undefined `telecom_flags` and `update_engine_aconfig_declarations`. The source projection was restored and the owner retired that attempt. The original outer/inner receipts and full stdout are retained in `evidence/`; the still-running label in the earlier CURRENT r32 is not accepted as current job state.

| Original project | Frozen revision | Complete input | Change |
| --- | --- | --- | --- |
| `packages/services/Telecomm` | `2353977dc28ff88d3cdc1ec636fa9c3251d2ff86` | `flags/`: original BP and all 17 aconfig files | Add the full cone |
| `system/update_engine` | `4591637f51644f5429f9e2fe589ab22b92f61842` | `flags/`: original BP and its aconfig file | Add the full cone |
| `build/make` | `5ce6f787337d0223710bf7d4a16dbe6d2a35f777` | `tools/aconfig/fake_device_config/`: original BP and all 7 Java files | Retain the existing full project |

The original update-engine Java aconfig modules require `fake_device_config`. This dependency is already present in the full, frozen `build/make` project. All eight files were independently read and checked against that exact commit's Git tree. The regression rejects changing it to a BP-only, Java-only, narrowed, or different-revision selection. It does not synthesize a provider or import the unrelated `StrictMode.java` seen in other revisions.

All 20 flags files and all 8 transitive-provider files are included under `upstream/` with their exact SHA256, byte counts and Git blob identities. Two original project-root blueprints are also retained as dependency context. `preparation.json` and `original-flags-inputs.json` pin these reads. The owner origin receipt is 508206 bytes, SHA256 `c4587747432732445ace5977fe6bfe0f5d82954b01c852cb707c694606ca823c`, at the original `qualification/full-ai395-r12-retirement-flags-origin-r2/result.json`; its exact local copy remains in the sibling `r12-followup` directory.

## Three-file patch and replay

Base recipe: `456504027867f3a8c31c27459b9a8d9f29eb84f2`.

Isolated commit: `c0522b7877485d786b58b67b02e8297e41d53c8c`.

Tree: `a3a2813d61764f4b536087e5eb93f0aad74b0f18`.

The patch changes only the native source lock, its frozen validation in `native_generation_pair_build.rs`, and the lock identity comment in `droidloom-source`. The new lock is 354910 bytes, SHA256 `74372a62836ec16c30a6f24c6e13725831f90e13f2bbc4c9f9f56c74895b163d`. Its only project-selection differences are the two complete flags cones. All project paths, names, revisions, policies and eight root links remain unchanged.

`source-pins.json` supplies exact full preimages and postimages for all three files. Both full byte sets are included under `preimage/` and `source/`. Check those preimage pins before applying `original-flags-provider.patch`; a different current recipe requires an explicit rebase and a new validation result. Historical failed-lock fixtures remove later cones only within tests, preserving their original expected hashes. Production validation still requires the new exact lock.

Normal replay commands, from the exact patched repository, are:

```sh
cargo test --locked --offline -j 1 -p droidloom-update --bin droidloom-update ordinary_pair_ -- --test-threads=1
cargo test --locked --offline -j 1 -p droidloom-source --lib tests::project_bound_admits_superproject_gitlink_extensions_but_not_unbounded_sync -- --exact
cargo test --locked --offline -j 1 -p droidloom-source --lib tests::bounded_native_source_plan_keeps_duplicate_and_escape_rejections -- --exact
cargo build --locked --offline -j 1 -p droidloom-source -p droidloom-update
target/debug/droidloom-source verify-lock --lock android/native-generation-pair/source-lock.json
```

The actual run used its own Cargo target, CPU 1, MemoryMax 4 GiB and MemorySwapMax 0. It compiled from the exact isolated source path. The patch preserves the generated file's existing formatting; this capsule does not claim a whole-repository rustfmt pass.

## Actual normal validation and retained wrapper failures

There are **35 unique passed normal tests**: 22 `native_generation_pair_build` tests, 11 existing `android::tests::ordinary_pair_*` tests, and 2 source-plan tests. The two new regressions reject the exact failed r12 lock and incomplete or changed original-provider selections. Both normal tools compiled successfully. The CLI verified 601 exact projects and 8 root links at superproject `28f0bbddc24d56c8ec5a8df5342ac7a292184039`.

The first apply job (`1a1c15c2f93-e62c-79`) successfully applied and pinned the three files, then failed before any test unit started because its non-login PATH did not contain Cargo. Its failure and stderr are retained. The next job (`1a1c15e3e96-e62c-82`) used the verified absolute Cargo path and ran all 33 selected tests successfully. Its wrapper expected 22 and rejected the actual 33 count; that wrapper's original FAILED result is retained unchanged. The full stdout lists the 22 intended module tests and 11 existing Android controls, including both new regressions.

The continuation (`1a1c160824a-e62c-86`) checked that exact stdout hash and test-name set, then ran only the two remaining source tests, tool build and CLI. It did not repeat the 33 passed tests. It ended succeeded/0 with complete, durable output. Final source pins match the inputs of the actual compilation. The separate commit/retirement job (`1a1c1647c75-e62c-8e`) verified both normal units were collected, inactive with MainPID 0 and absent cgroups, and recorded the clean private commit and actual normal binary hashes.

No wrapper failure has been relabeled successful. `INDEX.json` combines only the individually observed passing test/build/CLI facts with the independent source and retirement checks. All original stdout/stderr and relevant H terminal receipts remain available.

## Mainline adoption boundary

Remote isolated root: `/home/qq/work/pocket4-native601-flags-20261109-2840-r1` on ai395. The tested recipe is its `source/` directory; the exact patch is `original-flags-provider.patch`. Mainline must first reconcile the complete cones using the normal materializer and shared owner locks, then independently reverify all 28 physical provider inputs and run its one admitted strict full generation. No such reconcile or full was started by this candidate.

A successful CP2A engine/modified-ART full build would still not qualify the selected official CP3A QPR1 image. Retaining official QPR1 ART/APEX and satisfying the engine's credential, namespace, worker-lifetime and private grant contracts remain separate unresolved requirements. `runtime_qualified`, `production_ready`, full pair qualification and QPR1 qualification remain false throughout this capsule.
