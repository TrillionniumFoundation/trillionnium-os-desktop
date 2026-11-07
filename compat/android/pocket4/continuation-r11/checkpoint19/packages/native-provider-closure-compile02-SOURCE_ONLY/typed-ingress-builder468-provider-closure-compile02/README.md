# Native typed-ingress provider closure — compile candidate 02

**SOURCE_ONLY. UNRUN. No Rust, Soong, Java implementation JAR, Android JNI object/link or App readiness success is asserted.**

Frozen 2026-11-06 05:06:06 UTC from the actual 467 compile03 source map and the preserved strict normal-resume failure. Compile candidate 01 remains unexecuted and retained.

## What changes

The old normal build reached strict Soong and reported the real missing MotionTestDefaults and SystemUI_optimized_defaults providers. This candidate preserves both original consumers and both normal targets, framework-minus-apex and libandroid_runtime, with ALLOW_MISSING_DEPENDENCIES=false. It adds real fixed-commit providers and their observed dependencies, including the parametric runner, collector helpers, tracinglib, Robolectric, Clearcut listener and asuite proto. It adds no fake defaults, placeholder framework implementation or replacement host JNI artifact.

The source lock has 224 projects: the original 214 projects keep their order and metadata, six existing projects receive only exact monotonic sparse-path additions, and ten projects use actual gitlinks from the fixed Android 17 superproject. The original eight root links remain unchanged. SDK multidex comes from the actual existing SDK providers; no duplicate frameworks/multidex source project is added.

Twenty-four complete pinned upstream Blueprint files are test fixtures. The projection retains metadata and 59 original provider stanzas byte for byte after whole-file SHA checks. Newly selected asuite's unrelated atest parent is reduced to its original package metadata with an exact file pin. The two old failure consumers are unchanged. The original first three provider projections retain their exact output hashes.

The fixed Soong Robolectric DepsMutator was inspected: it adds ClearcutJunitListenerAar, Robolectric_all-target, mockito-robolectric-prebuilt, truth, junitxml and robolectric-android-all-prebuilts even when consumers do not spell out those edges. Their known source providers are included. The misc Robolectric runtime Blueprint was reconstructed from an official complete diff and its full Git blob SHA matches the actual locked tree's 7ca6747736de6dfe94e1043ba5b9dd0a8cd98137.

## Exact compilation scope

The candidate builder map contains 491 files: 464 original rows remain identical, two Rust files are replaced, and 25 new text files are added. The request compiles this isolated builder and requests 15 updater plus nine unchanged source-resume controls. The expected 62 commands and 24 gates have not run. The new compiler is byte identical to reviewed compile01 except eleven explicit root, source-list, hash and count replacements; its tool, owned-child, cleanup, original environment and resource gates remain.

The plain JSON stdin is 886381 bytes, below the verified 1 MiB tool cap. It carries 30 exact source/manifest/proof files and reuses eleven already-owned authority files only after the existing fixed-path, identity and full-hash checks. The stage creates only the new owned compile root. No gzip decoder, binary payload, private UI or raw crash packet is included.

## Retained failures and limits

The original materialization timeout, compile02 owned-child failure, and strict normal-resume Soong failure remain historical failures. The actual misc Git reader's two missing local blobs remain a failed collection; the ub-uiautomator and Robolectric runtime files were later recovered from exact upstream bytes without replaying that reader. The six-file Maven/SDK reader passed with full identities and hashes.

The locked misc/robolectric-native-prebuilt directory was observed in the actual tree and is selected unchanged, but its Blueprint body has not been read. Its module and variant qualification remains pending. Full global Soong variant/visibility resolution and both final Android outputs also remain pending.

The previously published source tree may be reused only after complete fresh verification against the exact previous typed lock. Dirty, unknown or mismatched state is rejected. The normal work/source locks, reconcile verifier and atomic manifest publication remain in place. This is not an authorization to run normal build, install, UI, change services or reuse the unavailable Main epoch.

## Review files

- production.patch compares both Rust files to the actual compiled 467 source.
- production01-to02.patch isolates this closure expansion from the unrun compile01.
- compiler01-to02.patch, stage01-to02.patch and transport01-to02.patch isolate request changes.
- provider-closure-proof.json contains exact source pins, actual read provenance and remaining unknowns.
- source-verification.json records 168 V8 binding checks, explicitly excluding Python/Rust execution.
- exact-request.json is the complete reviewable request; Root alone may dispatch it after current resource and epoch policy review.
