# Native601 original provider source chain

This capsule continues the producer source represented by the published `native600-rkpd-apex-r1` capsule at publication commit `e123939aae9ffeec4e6a2bb928b28cadd44e7f1e`. It contains four sequential ordinary source patches, the exact initial source preimages, the resulting 601-project lock, original-input identities, and a source-only replay checker. Apply the patches to the Droidloom producer repository. The publication repository stores this capsule; it is not the producer source root.

## Exact replay boundary

The starting producer is commit `c90b25bdc326cd35dc77698c83a4cf3671d73f47`, tree `65180728507f82ad58b48d7099c8ac702684cd95`. Its lock is 354234 bytes, SHA-256 `09a020b99c5f9f1876c69450d01ac99907cd6dda97cb4f69601f70151ea43d2b`.

The resulting normal producer is commit `f7e89c652141a1dcf2ca5edee04b0ea69de46863`, tree `41964997c1fa90ab2472ddb4da05e3687f2ec06c`. Its lock is 354822 bytes, SHA-256 `9375d2850e830e6213556ab87693fb54df456096f5c455c87afb76d681436ed2`. All five changed or added source files have an exact byte count and SHA-256 at every stage in SOURCE-PINS.json. The four included initial preimages were reconstructed by exact inverse patches from qualified final source bytes and independently matched against the original normal RKPD producer's recorded full-file hashes. No source hunk uses offset or fuzzy matching in that reconstruction.

Run `python3 verify_patch_series.py` from this capsule to check FILES.json and use ordinary `git apply --check` plus `git apply` in a fresh temporary directory. It verifies each complete intermediate source image and the final lock. It does not fetch code, build Android, or install anything. The normal Rust tests added by each producer patch remain in the actual Rust source.

## Four finite changes

1. **Signature and maintenance metadata.** Keep the original CTS `tests/signature/lib/common` cone. The separately reviewed VKMS conversion removes exactly the unresolved 49-byte `default_team` field from the pinned 1522-byte original Blueprint, yielding 1473 bytes. The ordinary projection journal preserves and restores the exact original; cc/java source, dependencies, license and visibility remain unchanged. The patch includes exact-preimage, changed-file, symlink/hardlink, normal restore and interrupted recovery controls.
2. **Tradefed providers.** Add five original cones from four existing projects: CTS `tools/cts-tradefed` and `tools/cts-v-host`, CHRE `java/test/chdts`, VTS `tools/vts-core-tradefed`, and dEQP `android/cts`. All project commits stay fixed. The original inventory records all 1228 Git objects, including the complete wrapper, Java, resources and test inputs; it is a source inventory, not a compilation result.
3. **RenderScript's original bcc_compat provider.** Add `frameworks/compile/libbcc/tools/bcc_compat` at the existing pinned revision. The original provider Blueprint, parent Blueprint and Main.cpp are included with their full-file hashes. The RenderScript consumer and strict targets are unchanged.
4. **Dexdeps and pyee.** Add the original Dalvik `tools/dexdeps` cone and the original `platform/external/python/pyee` project from the same frozen superproject. The inventory binds 12 Dexdeps and 11 Pyee files. Pyee uses the existing real `typing_extensions` provider. The project count becomes 601 while the existing maximum remains 608; the sparse-path maximum remains 336. All prior 600 revisions and prior selected paths stay intact.

The strict targets remain `libberberis_arm64` and `com.android.art`. Missing dependencies are not allowed. No consumer, target, runtime check, artifact verification or resource threshold is removed. Historical-lock negative tests reconstruct the preceding complete locks before rejecting their use for the new route.

## Actual validation and pending work

The latest normal producer build completed 23 ordinary commands, both CLI builds and loader checks, and the normal lock verifier. The actual Linux test filters passed 26 source tests, 30 ordinary-pair tests, and 20 native-generation-pair tests with zero failures or ignored tests. The filters overlap, so their counts are not added into a unique total. The observed tool-build memory cap was 4 GiB, peak 1041432576 bytes, with no OOM or swap. The previous full build remains failed and retired after strict Soong identified `dexdeps` and `pyee`; this capsule does not revise that result.

At this source checkpoint the new build-host import is running; Native601 materialized-source qualification and its next complete build are still pending. No compiled ART/translation artifact, crypto qualification, QPR1 runtime qualification or production readiness is claimed. Validation.json records this point-in-time scope and opaque evidence hashes without machine paths or process/job identities. Future actual results belong to a new explicit snapshot.

The capsule contains public source, source patches, hashes and compact validation facts. It contains no binaries, caches, signing material, account data, private logs or deployment authority.
