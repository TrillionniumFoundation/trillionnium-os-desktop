# Native600 Tradefed provider sparse-source closure

This capsule prepares a minimal source-lock delta for the four missing modules reported by the actual Native R7 build: `vts-tradefed`, `cts-tradefed-tests`, `cts-v-host-tradefed-tests`, and `chdts-tradefed-tests`. It preserves the latest observed owner lock and every existing project commit.

## Source chain

The existing repository baseline is `compat/android/pocket4/native600-rkpd-apex-r1/source-lock.json`, as read at commit `e123939aae9ffeec4e6a2bb928b28cadd44e7f1e`. Its 354,234 bytes have SHA-256 `09a020b99c5f9f1876c69450d01ac99907cd6dda97cb4f69601f70151ea43d2b`.

1. `owner-signature-team-prerequisite.patch` reproduces the owner's already observed `tests/signature/lib/common` addition. The result is exactly the 354,272-byte latest owner lock, SHA-256 `fb05fce28e2541cc1c791350ede62d36579ac459922b6f394680930cba9f6d9d`, read from the ai395 original in six version-bound binary chunks.
2. `native-provider-sparse-closure.patch` appends the nine paths below. The result is 354,573 bytes, SHA-256 `881bf0ef909da06da09fe976c84c4efc1e1eebc6182fd3792f236b5eec4cbdcd`.

The patches contain source-selection changes only. They retain all 600 projects, the order and commits of every project, existing sparse paths, superproject identity, and source policy. They introduce no module definitions, replacement sources, acceptance-gate changes, or missing-dependency allowances.

| Project | Added paths | Newly locked original files |
| --- | --- | ---: |
| cts | `tools/cts-tradefed/etc`, `tools/cts-tradefed/tests`, `tools/cts-v-host/etc`, `tools/cts-v-host/tests` | 13 |
| external/deqp | `android/cts/Android.bp`, `android/cts/AndroidTest.xml`, `android/cts/runner` | 7 |
| system/chre | `java/test/chdts` | 13 |
| test/vts | `tools/vts-core-tradefed` | 32 |

The CHDTS parent cone includes the already selected app subtree; those existing 596 app files are not counted as new inputs. The source lock keeps its original app selection as well.

## Dependency evidence

The original CTS test definition has a static dependency on `CtsDeqpRunnerTests`. That original provider depends on `CtsDeqpTestCases`, whose pinned parent definition selects `runner/src/**/*.java`. The Deqp runner and original test configuration therefore accompany the four reported providers.

The CTS parent binaries reference real `etc` wrappers that were absent from the materialized tree. CHDTS needs its original tests, resources and wrapper. The VTS cone contains its harness Java source, resources, binary wrapper and original tests; its tests consume `suite-loading-tests` supplied by the CTS tests cone.

`provider-inputs.json` records all 65 exact Git blob IDs, original modes, project commits, and the directly reviewed Blueprint declarations. The pinned CTS-V tests tree contains only its original Android.bp, and the CHDTS parent harness source glob has no local Java files in that upstream tree. No substitute source is created for those empty upstream globs.

## Offline reproduction

From a checkout containing the existing baseline and this capsule:

```sh
python3 -I -B compat/android/pocket4/native600-tradefed-provider-closure-r1/verify_source_delta.py --repo-root .
```

The verifier checks each patch SHA, runs `git apply --check` before each application in a temporary directory, checks both resulting full-file SHA values, and proves that only the four specified sparse arrays changed. It uses no network and leaves the repository input unchanged. Ordinary and optimized Python runs, plus a wrong-base negative control, are recorded in `verification.json`.

## Qualification boundary and execution custody

This is a source-lock replay qualification. It does not qualify materialization, the complete Soong graph, Android boot, applications or production readiness. No full build was started and no owner source tree, Git object database, account, service or live Android installation was modified.

Ten of the 65 newly locked files have observed byte sizes, totaling **41,251 bytes**. The other **55 sizes remain unknown**. The available Git trees establish their paths and exact blob identities; unknown byte counts are not zero.

A subsequent read-only size observer and its exact terminal-metadata reader returned `launch_unknown`. Their exact identities, same-key reconciliation and the absence of positive terminal evidence remain in `verification.json`; no result or terminal state was inferred. No further remote command was started for this capsule after that boundary. Normal owner source-materialization and graph qualification are still required before a new full-build generation.
