# Owned native semantics qualification

The final private three-arm run passed its **owned native semantics** contract. It does not qualify Marriott, Bilibili or another publisher application. Its original aggregate predates Main activation and correctly records that it did not deploy Main.

| Engine | Split-file mapping controls | Default alarm |
| --- | --- | --- |
| R14 baseline | Expected failures `[32, 32, 0, 0]` | Ignored alarm returned and process survived |
| R15 | Same expected mapping failures | Actual exact-UID SIG14 exit |
| R16 | `[0, 0, 0, 0]` | Actual exact-UID SIG14 exit |

All three final arms used the same frozen v5 runner, assessors and V8 APK `dc1777871e32681a823253c36dba0a553ef596a464a3c4d7a282d3f9a6bafa67`. Handler and V4–V6 controls passed. V4's openat2 `-904` remained **observe-only**, not a repaired API claim. R15 and R16 each observed one framework relaunch that the durable nonce claim refused; there was still only one native executor per arm.

Each arm preserved the complete 143-package inventory and exact 143-name UID registry, removed four owned packages/UIDs, verified all 16 code/data paths absent in the host and actual guest namespace, and retained zero OOM events across five owned resources. Owned units were empty and adbd stopped. The independent reviewer rejected six incomplete-evidence negative controls. The parent separately rehashed 22/23/23 aggregate inputs before Main activation.

See [three-arm summary](evidence/three-arm-summary.json), [independent cleanup reviews](evidence/independent-cleanup-reviews.json), [parent rehash](evidence/parent-rehash-summary.json) and [retained failures](evidence/retained-failed-attempts.json).

## Public source adaptations

The full owned C/Java probe, manifest, build/preparation programs, runner, assessors, qualifier and independent reviewer are under `source/`. [Source provenance](source-provenance.json) distinguishes original executed hashes from the public copy hashes. Private roots were mapped to documented `/srv/pocket4-*` inputs. Original Main PID literals became explicit `DROIDLOOM_RECORDED_MAIN_*` environment inputs; historical framework and other guards remain strict. The literal owned test signing password was removed and replaced by `DROIDLOOM_OWNED_TEST_KEY_PASSWORD`. No signing material is distributed.

These adapted runtime programs were not executed. Their original source manifests are historical records and cannot authorize edited copies or a new epoch. The full historical Java/build patch is identified by hash in the recorded manifest; the delivered final source is complete for the listed files, while that original patch and the local parent builders are not distributed. The original build-time `actual_Android_executed=false` field remains historically correct; separate final runtime evidence supplies later execution.

The relocated `default_once_parser_test.py` runs beside the two unchanged assessors in a fresh temporary directory. Its synthetic positive/rejection/incomplete cases are not Android proof. Publication verification and its exact source hashes are recorded separately.

# Recorded source and input boundary

This transfer records the owned native canary used to compare the frozen R14, R15, and R16 bridge candidates. The completed v5 runs established the tested signal and maps semantics in private Android cells. They do not establish publisher application compatibility or a complete production readiness verdict.

## Source identity

The JSON index lists exact digests of the original repair artifacts. Cached content was restored in scratch and checked against previously observed remote digests wherever a digest was available. The parser test source was restored from the exact creation payload; its remote digest was not separately read.

The original runner, preparer, and builder contain host-specific paths or identity checks. They are historical execution sources. A sanitized publication copy must have its own digest and a documented transformation. The historical execution manifest does not authorize an edited copy, a different machine, or a new Android generation.

## What can be reproduced from the source

The unchanged native probe C body covers file-backed mapping offsets, anonymous and unsplit mappings, signal handler/mask controls, and the default alarm action. The revised Java code adds a durable exclusive-create claim before the default test. A system-created Activity can report that execution was refused; it cannot call the native test again. The native ELF digest remained unchanged across this Java-only revision.

The v5 runner saves raw observations before checking attribution. It accounts for every matching process record, requires one native executor, and binds the default exit to the fresh launch and persisted claim. The completed private cells preserved their package inventories and removed all owned probe code and data.

## Inputs still required outside this transfer

- The builder imports the earlier V6 builder definitions and V7 ELF/DEX helpers at the recorded digests.
- That builder also depends on frozen Clang, JDK, Android SDK jar, R8/D8, aapt, alignment/signing tools, and an ARM64 Bionic libc provider. The complete tool digest map is in the original build receipt; it is not available in this offline transfer and is not reconstructed by inference.
- The V4, V5, and V6 controls are existing hash-pinned APK inputs. This transfer does not close their complete source and build preparation chain.
- The private runtime uses an existing 86-record frozen image/HAL/runtime fixture and a fixed presenter. The index pins that manifest and candidate binaries; it does not provide a complete Android operating-system source rebuild.
- Owned test signing material is not included. ZIP/signing metadata was not normalized for cross-machine byte reproducibility. A rebuilt APK must not be claimed to match the observed APK digest without independently checking its bytes.

These dependencies mean a clean checkout of this PR is not a directly runnable three-arm canary environment. A new run needs a newly reviewed host inventory, identities, paths, package baseline, nonces, and resource limits.

## Evidence limits

The final three-arm qualification receipt is pinned by digest. The R14 baseline retains the expected maps failures and ignored default alarm. R15 fixes the default alarm while retaining the maps negative controls. R16 passes the tested maps cases and default alarm behavior. All three used the same final runner, assessors, and owned APK.

For the immediately terminating R15/R16 default executors, start ticks were recorded by the application in the durable claim; the host did not independently sample those processes' start ticks or engine mappings before death. Actual candidate-engine mappings were independently observed in the preceding live controls of each arm. Refusing lifecycle processes were independently sampled where reported. The evidence must not be described as an independent engine-map sample for every default executor.

The parser-unit stdout summary reports one synthetic positive, ten rejected cases, and two incomplete cases. This is attribution-parser testing, not Android execution. Its full original receipt is not present here and has not been regenerated or fabricated.

## Preserved failed attempts

Earlier CPU-inventory and asynchronous Home-bootstrap fixture failures remain failed. The original v3 R15 arm failed its multiple-process attribution check. A separate diagnostic established Activity re-entry after actual default-alarm termination; it was not promoted to a full qualification. The first once-APK compile failed because the pinned public SDK lacked one constant. A later launch preflight failed before Android execution because a non-root reader could not read the frozen manifest. Only the final v5 three-arm runs supply the final qualification.

No APK bytes, signing key contents, raw logs, actual nonces, process IDs, or private Main identities are included in this index or README.
