# Native13 original framework aconfig provider review

## Result

Native13 remains FAILED and retired. Its actual strict Soong error is:

frameworks/base/AconfigFlags.bp:15:1: "framework-minus-apex-aconfig-declarations" depends on undefined module "com.android.eyedropper.flags-aconfig-java".

The primary log is the original normal-full-native-engine-ART-pair.stdout, 79,951 bytes, SHA256 da410f775b63329dfacd474c58198007983318e0714305a04cb490a463583147. The exact error is line 361. The package retains a bounded excerpt and the original log reference; it does not call that excerpt a complete log. Full stderr is 533,535 bytes, SHA256 3d244bc30d310da4361233cc12a7adcc394db39d1c795174df03abb59e14c3a5, also retained at its original remote path.

Original inner, outer, fallback and independent-retirement receipts are preserved byte-for-byte. Fresh authoritative H status confirms full job 1a1c184f061-e62c-be failed/1 with complete, durable output; independent-retirement job 1a1c19dac00-e62c-df succeeded/0 with complete, durable output. The strict missing-dependency gate was not relaxed. Resource/source restoration and retirement success do not upgrade the failed build.

## Existing owner work; no competing implementation

Owner already created these ai395 records under /home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/qualification:

- eyedropper-original-provider-r1/RESULT.json: 8,739 bytes; SHA256 5864954d51aaf69d25caa6802d9bc0fc7b2bf1543f10063a51275c31b65d9645.
- framework-aconfig-complete-group-index-r2/RESULT.json: 60,769 bytes; SHA256 72b5aeb964b758e81ab780db7251bd0a7ee717f47b865df510e1efdb592aa60b.
- framework-aconfig-complete-group-closure-r1/RESULT.json: 404,965 bytes; SHA256 da746776ca99561ab9e26f021747765bcbfd651b078d499f277327dac67e58df.

The owner closure records 292 visited modules and 435 edges, including 140 direct Java libraries and two direct group entries, with missing/ambiguous/unknown counts all zero. It correctly labels itself metadata-only and source/full unqualified. This review preserves that result as valid in its stated scope.

The reviewed controller does not traverse aconfig_declarations.srcs or filegroup.srcs. Its zero unknown count therefore does not prove those source inputs or arbitrary Soong expressions. The two concrete nonliteral cases were independently checked below. No competing source patch, reconcile, full build or private control was launched. A point-in-time process/unit observation found no matching live Native job, but it is not launch admission and does not release the foreground owner's lease.

## Two source-input cases independently closed

### Security select

At frameworks/base commit 94b4c163b7dfe5ce3607f7bb8456f9573f7de57d, AconfigFlags.bp lines 555–571 defines android.security.flags-aconfig with three unconditional .aconfig files plus select(release_flag("RELEASE_CONSCRYPT_NSC")):

- core/java/android/security/flags.aconfig
- core/java/android/security/keychain_flags.aconfig
- core/java/android/security/responsible_apis_flags.aconfig
- true branch: core/java/android/security/conscrypt_nsc_on.aconfig
- default branch: core/java/android/security/conscrypt_nsc_off.aconfig

The owner's parser preserves this as an unresolved *parser.Operator. All five physical source files and AconfigFlags.bp were read without following the final symlink, and their Git blob IDs matched the exact pinned commit. Checking both branch inputs does not claim to evaluate the selected release flag.

### Telecomm filegroup

At packages/services/Telecomm commit 2353977dc28ff88d3cdc1ec636fa9c3251d2ff86, flags/Android.bp lines 23–53 defines telecom_flags -> :telecom_platform_flags_config_src. That filegroup names 17 literal .aconfig inputs. All 17 and the Blueprint file were read and matched exact fixed-commit Git blob IDs.

The combined observation verified 24 files: two Blueprint files and 22 source inputs. Git used --no-lazy-fetch, not merely an environment-variable hint. There was no fetch, repository/index write, source replacement or lock mutation. The materialized manifest before and after was byte-identical: 393,709 bytes, SHA256 eb7dd68de94ff82addda54fd98f93fe78075fd37770b1a10392cd39917679e51. H job 1a1c1b6c759-e62c-104 succeeded/0, complete and durable.

These branches are already physically present. They require no duplicate source addition. This is a targeted input proof, not a claim that every remaining Soong source or generated input was independently qualified.

## Exact EyeDropper provider cone

The owner authenticated superproject 28f0bbddc24d56c8ec5a8df5342ac7a292184039 -> packages/apps/EyeDropper gitlink 225af0c6253316198738699de9041d1f28d0df44 in platform/packages/apps/EyeDropper. The original unmodified provider inputs are included:

| Path | Bytes | SHA256 | Git blob |
| --- | ---: | --- | --- |
| Android.bp | 2,204 | 9ec427f67a6a645a847436f39ff26a7c15fa1f97fbe7f5e04a4c95b4fd9e3816 | d263e2e169683853f1eecebb5b73a4effd064316 |
| flags/eye_dropper_flags.aconfig | 279 | 71ab73bc32c2792955592a414cdeef3506d7faa6ab9cfbbab647032090677966 | 3467349407f6f9180ffed10b21d579783586627a |

The Java provider points to com.android.eyedropper.flags-aconfig and to the existing framework-minus-apex-aconfig-java-defaults. The declarations consume the one original flag file. The existing defaults reference fake_device_config; the owner's closure reaches that pre-existing provider.

These two files are the minimal original declaration/data cone for this observed missing flag provider. They do not establish a complete EyeDropper application or a successful full graph: the unmodified Blueprint also contains EyeDropperLib and EyeDropper app declarations. Preserve that original file and let normal reconciliation, effective input validation and the strict full resolve the resulting complete build graph. Do not synthesize a shortened Blueprint or claim application runtime readiness.

## Adoption conditions

The owner should retain the existing metadata closure and append this bounded source-input evidence. No re-addition of Security/Telecomm files is needed. The still-pending source change is the exact EyeDropper project/provider addition, with corresponding source-count/manifest/recipe invariants and normal source verification. Root alone may submit Native14 after its existing admission and locks.

No current default target, upstream commit, private grant, dependency gate or selected QPR1 policy changed. A future successful CP2A-source Native build would still need the separate selected CP3A/QPR1 coherence and runtime gates.

INDEX.json intentionally leaves source materialization of EyeDropper, full build, ART/engine qualification, QPR1 qualification, runtime and production readiness false. The previously frozen packages are unchanged.
