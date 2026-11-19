# Current CP3A system-app source adapter

This is an isolated **source-only review candidate**. It implements the deterministic identity changes required by the current CP3A GSI and explicitly retires the old Gallery modified-candidate entrypoints in its postimages. It does not activate or install anything. No Android runner is imported, no APK/image body is opened, and no user data or credentials are accessed.

The fixed source state is the Beike successor, 157891 bytes, SHA-256 `4d25fc0aafd5668cc3f0c31be157bc617732902976aad821333a02de84ff9bf7`. The coherent system image is 2294853632 bytes, SHA-256 `dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4`, build `CP3A.260905.010` / `16176746`, SDK 37, security patch 2026-09-05. Exact original GSI manifest and Gallery source receipt bytes are included under `inputs/`, with full source-host pins and F9 observations in `METADATA-CUSTODY.json`. These are source facts; their existing runtime and production fields remain false.

## Implemented changes

`adapt_cp3a.py` reads ten fixed, SHA-pinned metadata/source inputs, then the fixed original-source manifest and all 224 bounded source files from eleven preparations. These files include Python, Java, XML and JSON; none is imported or executed. Each file must be a single-link regular file, opened without following any local path component. Full byte hashes and F9 metadata are checked before and after generation. Embedded origin paths are never traversed by this program.

The adapter makes **42 explicit edits in 23 Python postimages**:

- Eighteen files receive exact current target APK SHA/size constants. The Calendar, Contacts and DocumentsUI profiles also gain the actual per-package signer constraint; DocumentsUI gains its previously omitted exact byte-size constraint. Existing v3 requirements are unchanged. The complete AST must equal the original AST with only those approved constants/fields changed.
- Five Gallery files receive six unconditional entry rejections before any existing function action. This covers the old top-level verifier/installer entry, its direct install executor and ART-receipt admission function, its modified-candidate verifier executor, and the rotation/video top-level entries. The original function bodies remain behind the rejection for review; their install or runtime paths cannot be entered through these postimages. They are not relabelled as current official Gallery implementations.

| Target | Historical APK bytes | Current official APK bytes | Current APK SHA-256 |
|---|---:|---:|---|
| Calendar | 2635213 | 2520846 | `726241395b485794badd1a1fdcef4298ebb284f67826d73a7e2648f2b7a5382e` |
| Camera | 11892407 | 7709134 | `24632b0e1a1c22741177583b0dfd4a3fa71ff9b1d1b72af60a3d7cf373c7e61f` |
| Contacts | 11839391 | 11896473 | `f91e45e89b3a302198c9269a60bb07387150c0f40def95feb873b765520ae028` |
| Clock | 7597225 | 7665498 | `9f24ea5fa57bca4a453556ab7cb44fbad1813cb3d15292a8e572cfb40fff7a77` |
| DocumentsUI | Old profile omitted size | 8923434 | `f7db1705178644333d5c9d291afd1170e71fcddfd1f73021381e1224be824899` |

The Contacts signer is `28bbfe4a7b97e74681dc55c2fbb6ccb8d6c74963733f6af6ae74d8c3a6e879fd`; DocumentsUI uses `c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8`. Calendar, Camera, Clock and Gallery use `a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc`. A uniform signer assumption is explicitly rejected.

`CURRENT-CP3A-COHORT.json` is the executable metadata adapter's output. `describe_source` exposes only one of the six source records; install, runtime verification and execution are not accepted modes. `require_provider_cohort` fails with the precise unresolved provider name. It will also reject an injected replacement record: this revision accepts no new provider receipt schema or guessed APK identity.

## The Gallery mismatch is separate

| Gallery artifact | Bytes | SHA-256 |
|---|---:|---|
| Historical official baseline and selected current official APK | 7390425 | `835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439` |
| Actual historical modified runtime candidate | 7493022 | `6677d382076f10f0502c813c7614c32127ccf3cd8f02756b75a8c3574980e87e` |
| Current official `classes.dex` | 1857660 | `725ac7153e9ab4a9742672c238fc140bda311e6c940daf9e1d10a2b26c33e829` |
| Historical modified `classes.dex` | 1886696 | `6a994fabd3494dcbf071d727922351f72ff8fdbee0d3d3c1a46b6ed30ca034ee` |

The official baseline equality is real. It does not make the modified candidate or its ART proof applicable to the official APK. The existing source verifier checks 2144 classes and these two modified methods:

- `ExifInterface.rewriteExif(Ljava/lang/String;Ljava/util/Collection;)Z`
- `MenuExecutor$MediaOperation.run(Lcom/android/gallery3d/util/ThreadPool$JobContext;)Ljava/lang/Void;`

The new evidence records the complete original candidate/DEX pins, the exact original build receipt, and each target class's preimage, patched source and patched IR hashes associated with the named replaced method. Those class/source/IR hashes are described with their actual scope, not presented as a newly measured method-body hash. The current official DEX metadata comes from the complete SHA-pinned current source receipt, whose all-member CRC/SHA verification was performed by its original owner. This adapter does not rehash the APK body or rerun that SDK qualification.

The original `gallery_current_install.execute` requires the modified candidate ART receipt and performs one `pm install`; `gallery_rotation_case.verify_install` requires that same custom-installed state and one install attempt. That receipt cannot be reinterpreted as an image-installed receipt with zero attempts. The postimages therefore retire those old entrypoints while the new metadata route admits only the official full-GSI source. **Fresh image generation custody, official-DEX ART/class-set verification, official edit/rotation behavior and business execution remain pending.** No old ART, method repair, rotation, video, album or audio credit transfers.

## Contracts deliberately still blocking execution

| Dependency or contract | Exact existing source location | Current requirement |
|---|---|---|
| Calendar repaired APK custody | Both Calendar preparations, `system_plan.inputs` and `system_factory.CalendarPrerequisites.verify` | A reviewed coherent-GSI custody successor is required. The old one-install receipt, CE/DE inode/UID/gid continuity and firstInstallTime checks were not bypassed or rewritten. Official Calendar UI behavior must be reviewed, because the older case expects its repaired local-calendar workflow. |
| CalendarProvider | `system_profiles.CALENDAR_PROVIDER`, `calendar_core.PROVIDER_SHA`, atomic-delete review | Current provider APK/source/signer and the exact empty-calendar cleanup semantic contract are pending. |
| ContactsProvider | `system_profiles.CONTACTS_PROVIDER`, `contacts_model.PINS` | Current provider source and cleanup semantics are pending. |
| ExternalStorageProvider | Both `documents_profiles.PROVIDER`, SAF/search-sort identity checks | Current provider APK and helper/provider semantic qualification are pending. |
| MediaProvider | `camera_profiles.MEDIA_PROVIDER_*`, `camera_session`, `owned_media.PROVIDER_*` | The old `MediaProvider@CP2A.260605.016` APK binding is retained as historical evidence. The CP3A CAPEX container pin does not identify its inner provider APK. Current inner APK path/SHA/size/signer and ownership/cleanup semantics are pending. |
| Source preparations | Each old bootstrap's exact preparation/source packet pins and host controls | The new postimages are not accepted by the old frozen preparation. A reviewed successor preparation and fresh host boundary qualification are required; no historical host-control pass is asserted for changed code. |
| Runtime identities | Original `app_common.validate_identity`, baseline/Main/data-continuity checks | UIDs in old code remain **historical expected constraints**, not observed current UIDs. Every actual Main, UID, framework epoch, installed identity, selector and helper binding is null in the new configuration. |

The bounded metadata lookup found the ten required system-app receipts, but no qualified current APK receipts for these four providers in the inspected receipt directories. It does not assert whole-host absence. No provider was inferred from an unrelated receipt or a same-version string.

All old data-preservation, permission, account, selector, owned-task, cleanup, timeout and action-count gates remain. All IHG code/profile/limits remain byte-semantically unchanged; only the Clock constants in the shared IHG preparation are changed. Clock's original timer/alarm/expiry limits and v3 check remain. Camera still allows one shutter dispatch and its original finite photo scope; this adapter does not create video coverage. Dialer, Messaging, QuickSearchBox and Settings still have no selected finite business executor in the historical selector.

## Exact preflight correction

The original preflight r1/r2 files and inputs are unchanged. The materialized `PLAN.json` is an explicitly named CP3A source-adapter successor of the pinned r2 plan. `PREFLIGHT-CORRECTIONS.json` contains all 25 exact JSON-field or README-sentence changes with before/after values.

The original five `target_profile_mismatch` definitions remain intact. A separate `gallery_candidate_mismatch` is added. The seven-package finite-source count is explicitly historical, and the count of current business/runtime-compatible packages qualified by this adapter is zero. The 13 preparation references are unchanged, and the 32 rows without a selected executor are byte-for-byte structurally unchanged. The whole original `required_before_installation` map, Meituan's pending official-signer/userdata migration, all three retained Play restrictions/expiry, the three exemptions, canonical gates and the Firefox public-page checklist remain unchanged.

The two corrected r2 README sentences distinguish the matching official Gallery baseline from its mismatching modified candidate, and clarify that historical finite source for seven packages does not establish seven compatible current runtimes. The Gallery row's old “current ART/source verification” wording is replaced by an explicitly historical modified-candidate scope.

## Local verification and use

The nine test methods exercise actual fixed metadata, distinct signer constraints, the full-image chain, old-candidate and ART-credit rejection, provider/CAPEX rejection, preservation of old UIDs/limits/provider/helper/IHG contracts, unconditional Gallery entry rejection, refusal of runtime modes or invented bindings, preservation of all 39 planning gates, changed-input and symlink rejection, and exclusive output creation. Tests operate on temporary host-only metadata copies. They do not execute an original app runner.

```sh
python3 -B -m unittest -v test_adapt_cp3a
python3 -B adapt_cp3a.py materialize --out successor-r1
python3 -B adapt_cp3a.py describe_source --package com.android.gallery3d
```

`successor-r1` must not already exist. The validation wrapper records real command stdout/stderr and exit codes; it does not count comments or catalogue entries as passes. A successful generator result means only `SOURCE_ADAPTER_PREPARED_RUNTIME_BLOCKED`.

No source packet was published to Pocket4 or AI395 by this task. No Android, SDK, installation, VM or kernel action was performed. Root review and source/preparation qualification precede any later deployment.
