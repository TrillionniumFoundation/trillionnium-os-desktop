# Profiling official source correction

This candidate applies the complete upstream correction for CVE-2026-59016
(A-546680461), commit a7abbb79d9a30d6efe687c84407dae7a8d6dae67, to the
existing pinned Profiling source. It is a source-only successor to the actual
f733276e866388548b9995c8040d24f1799057fe producer. It has not been formatted,
compiled, tested, published, or used to build Android.

## Exact source identity

The unchanged 651-project source lock is
android/manifest/production-full-source-lock.json,
400363 bytes, SHA-256
30dcc1b5b090530b3fc06aeb3e489a961b0fc7c6368ed9d19eb0a1b2054e3eb4.
Its Profiling row is index 530:
platform/packages/modules/Profiling, path packages/modules/Profiling,
commit 8b3abe8eebc0e97890977d9658038f4966aa7df6. The existing sparse selection
already includes both service and apex; no additional project or file provider
is supplied.

The complete official patch is 2107 bytes, SHA-256
574e027a0f580a4e6f629c22c45eff1a6ba2a00c00757e04aa243a93ed484407.
It applies exactly to service/java/com/android/os/profiling/ProfilingService.java:
189294 bytes, SHA-256
3ff227876f069da4b56b778b4d54d96e296115c9931409eab56faed90095caf7,
Git blob 503e67870c33d5869d9a41a357d76d8c586221a0.
The resulting full source is 190650 bytes, SHA-256
7b896a55aeed2ccba7b5bd9cc9abff5b516a51b53d87df907096f298aa027dca,
Git blob 411433836a84dc9a0c957581b8df0ac5a1340683.
The fixtures preserve both complete bodies. The official two hunks add the
filename-validation call before handler dispatch and its validator.

## Existing normal builder integration

The implementation uses android.rs::build_targets_with_fixed_request and the
existing complete-product FixedProductionRequest. It introduces no alternate
build command. The complete target set now explicitly contains
com.android.profiling and service-profiling, and the journaled normal product
configuration installs com.android.profiling.

profiling_asb_security.rs validates the exact source lock, Java preimage,
unchanged service/apex Blueprint providers, and official patch. It registers
the Java original in Projection::save_many before applying the patch through
Projection::patch. It records original/effective identities in the normal
input receipt. After the existing normal build command and Projection::restore,
it verifies restoration of complete source bytes, mode, owner, link count,
length and mtime. Inode and ctime restoration are not claimed.

The module-info rows must name the actual Profiling service and APEX source
providers. The normal installed APEX/cAPEX is bound to its full file identity.
coherent_images::complete_normal then uses its existing complete_apex path for
Profiling as the fifth required APEX, independently reads the full payload,
requires both classpath records and the complete framework/service Profiling
JARs, closes scratch, and binds the container to the normal system partition
inventory. The later cohort validator requires the same module and members.

No release feature flag, source release, dependency exception, signing input,
execution deadline, resource limit or source lock is changed. If the selected
release does not enable the normal Profiling provider, or a real dependency is
missing, the normal build must fail. This candidate supplies no fallback APEX.

## Evidence boundaries and next use

The selected CP3A binary capture established only that the observed
sendAnomalyProfile method lacks the official required pre-handler filename
validation. It did not demonstrate exploitability, inspect all downstream
classes, or qualify a whole CVE. The capture's 11 MB dexdump stdout was streamed
and hashed; only the complete selected class and bounded command metadata were
retained. R24 coverage counts are not edited by this candidate.

The six new Rust tests are unexecuted source. They cover the exact official
patch and original recovery; preimage, provider and alias rejection; journal
failure before source writes; complete-product/lock gates; artifact metadata
rejection; and restoration/input-receipt binding. Their synthetic APEX bytes
exercise metadata only and provide no Android, DEX, signing or runtime result.

A future qualification must use a new isolated builder worktree/target. It
must consume the complete candidate source map, run the affected ordinary Rust
tests and the existing normal release build, then perform the unchanged
complete Android builder with its real source and resource gates. A successful
Rust qualification alone does not repair the already captured image. The
normal Profiling APEX/JAR/DEX must subsequently be read back and the corrected
method reviewed before updating any binary coverage claim.

Current C/D sealed source, authenticated source597, CURRENT, the accepted
Android image, user data and existing evidence are not modified by preparing
this candidate.
