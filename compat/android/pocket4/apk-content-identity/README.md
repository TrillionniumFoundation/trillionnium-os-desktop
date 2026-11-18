# Content-bound APK identity verification

This small Python package verifies an APK for Android SDK 37 using an existing Android Build Tools directory. It reads package, version, split, and SDK declarations directly from binary XML, reads public certificate bytes from the APK signing block, and compares these identities with Android's APK tools.

Each inspection fixes the whole-file SHA-256 first, copies the APK into an exclusive temporary directory with its SHA-256 as filename, runs `aapt2` and `apksigner`, and checks the original and copied bytes again. Every external tool output is bound to that APK SHA and the tool's own file hash. Package and version mismatches fail closed. App signing certificates and distribution Source Stamp certificates are separate. For packages carrying different v2 and v3 certificates, the identity comes from the strongest scheme actually verified for SDK 37.

## Run

Python 3.11 or later, Java, and Android Build Tools 37 are required.

```sh
python3 verify_apk.py reference.apk --build-tools /opt/android-sdk/build-tools/37.0.0 --expected-package example.application
```

Add one `--expected-certificate-sha256` argument per expected app signer when an independently trusted signer pin is available.

## Pinned current candidate input

`../current-app-acceptance/firefox-candidate.json` records the official Firefox stable Android x86_64 input observed on **2026-11-18 at 08:50:14 UTC**: version `160.0.1`, version code `2016196678`, min SDK 26, target SDK 37, 140689915 bytes. Its APK SHA-256 is an observed whole-file digest, not a publisher-published checksum. The APK content signature was verified against the package-specific Mozilla certificate fingerprint published at the recorded official `assetlinks.json` URL. The observation date and official URLs remain in the candidate and generated receipt. They do not assert that this version remains latest in the future.

The optional candidate mode performs the existing real `aapt2`, binary XML, public signing-block and `apksigner` verification again. It then requires exact package, version name/code/major, whole-file size/SHA-256, signer and native ABI agreement with the independently pinned candidate. It also checks binary XML SDK declarations and the class/machine of every native ELF library. This mode currently accepts a standalone `base.apk` without split declarations; it does not convert an incomplete split set into a base-only input.

From the repository root, using an already acquired APK and a new absolute receipt filename:

```sh
python3 compat/android/pocket4/apk-content-identity/verify_apk.py \
  /absolute/downloads/fenix-160.0.1.multi.android-x86_64.apk \
  --build-tools /opt/android-sdk/build-tools/37.0.0 \
  --candidate compat/android/pocket4/current-app-acceptance/firefox-candidate.json \
  --expect-candidate-sha256 6374df29a903904b8e9793d59cc96221d573cab35047382f1ad182b0c0db34cb \
  --receipt-output /absolute/receipts/firefox-160.0.1-source.json \
  > firefox-native-input.json
```

All three candidate flags are required together, without the legacy expected-package/signer flags. The external candidate SHA must come from the reviewed source revision, not be accepted from the candidate itself. Invalid JSON, duplicate keys, a mismatched pin or identity, an existing receipt, and input changes fail before publishing a new receipt. The tool does not fetch the recorded URLs. Without the candidate flags, the original verification behavior remains unchanged.

On exit 0, stdout's `application` object has the exact existing `runtime/droidloom-applications/src/runtime_plan.rs` `ApplicationPlan` shape: `package` and `expected_input`, with `version_code`, the complete base APK `name`/`bytes`/`sha256`, and a `source_receipt` file pin (`path`/`bytes`/`sha256`). The receipt contains the new signature/identity verification, actual tool hashes, binary metadata and dated official-source observation. It is written exclusively, after verification, and is never an old receipt relabeled with a new version.

This fragment can be used as the Firefox entry when an authorized complete runtime plan is assembled and independently pinned. It supplies no Main qualification, cohort, UID, installed inventory, runtime observation or business PASS. No plan is constructed or executed here. Historical `CANDIDATE42.json` records remain unchanged. Moving the receipt requires a new file pin in a newly reviewed plan. The APK is acquired and retained separately; it is not stored in this source package or Git.

### Recorded local SDK 37 verification

At **2026-11-18T09:05:08.634295+00:00**, the candidate command above was run against the complete official 160.0.1 x86_64 APK with Google's Android Build Tools 37. Both `aapt2` commands and `apksigner verify` exited 0. The actual public signing block and the cryptographically verified scheme agreed on one v2 app signer. Binary XML matched package `org.mozilla.firefox`, version `160.0.1` / code `2016196678`, min SDK 26 and target SDK 37. All 18 native libraries had ELF64 little-endian x86_64 machine 62 headers.

| Recorded item | Value |
| --- | --- |
| Complete APK bytes | `140689915` |
| Observed complete APK SHA-256 | `283b19f8313e8ce6e8a913bb178ce4a79c5cecd82c49f821de7fafb068c73fcd` |
| Mozilla app signer certificate SHA-256 | `a78b62a5165b4494b2fead9e76a280d22d937fee6251aece599446b2ea319b04` |
| Independently pinned candidate SHA-256 | `6374df29a903904b8e9793d59cc96221d573cab35047382f1ad182b0c0db34cb` |
| New source receipt bytes / SHA-256 | `5959` / `f73f1d0b20c4066ee25eb786d55b324d24e6b99b2e3ad3d281cb40eda15ca293` |

Four real reruns with separately pinned but incorrect candidate version, whole-file hash, signer and ABI each exited 1, emitted no stdout and created no receipt. The existing real-APK controls also passed, including a modified signed DEX rejection and unchanged reference bytes. The new nine source controls passed separately. Temporary negative inputs were removed. These are local acquisition and input-verification observations: no Android device was accessed, and no app was installed, launched or runtime-qualified. The official stable-version observation remains dated 08:50:14 UTC; neither that observation nor these results promises future latest-version status or production readiness.

## Explicit shared-library layout (candidate v2)

`../current-app-acceptance/szzc-candidate.json` pins the **2026-11-18** observation of the current APK delivered by `https://static.zuchecdn.com/download/SZZC.apk`, whose observed redirect is `https://edfs.zuchecdn.com/android-package/SZZC.apk`: package `com.szzc`, version `9.6.3`, version code `329`, min SDK 23, target SDK 33, 220522994 bytes, whole-file SHA-256 `7af438808904dbd4457f8d5ea7e267e5779e8ad6ab4d6a9c156c1e8ea0285d96`. This is the observed publisher download, without a claim about future releases or every store channel.

Its signing identity matches the independently reviewed historical public candidate pin `d85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44` in the repository's immutable `6fd7efdcfa27da2015b7eb5b103dc399491aa18f` `CANDIDATE42.json`. That historical pin is not represented as a publisher-published certificate statement. Candidate v2 therefore uses explicit `signer_reference_kind: public_historical_candidate` and `signer_reference_url`, and records `version_metadata_kind: signed_apk_android_manifest`. The candidate's external SHA must still be reviewed independently.

The APK has 59 `.so` entries in each of its `arm64-v8a` and `armeabi-v7a` directories. Four are shared libraries for a different architecture:

| Exact APK entry | Bytes | Actual ELF class / machine | SONAME | Entry point |
| --- | ---: | --- | --- | ---: |
| `lib/arm64-v8a/libexec_x86.so` | 667144 | ELF64 / x86_64 (62) | `libexec.so` | 229328 |
| `lib/arm64-v8a/libexecmain_x86.so` | 211616 | ELF64 / x86_64 (62) | `libexecmain.so` | 0 |
| `lib/armeabi-v7a/libexec_x86.so` | 556824 | ELF32 / x86 (3) | `libexec.so` | 181168 |
| `lib/armeabi-v7a/libexecmain_x86.so` | 132520 | ELF32 / x86 (3) | `libexecmain.so` | 0 |

All four are `ET_DYN`, have no `PT_INTERP`, and have no `DF_1_PIE` flag. They are in-process shared-library inputs, not separately executable helpers. Static inspection of the signed `classes.dex` (13600 bytes, SHA-256 `3f426667005f72ee1123f7afa5e3d9eacb3c374d8b1d51b0b619a3088dd388f6`) with the official SDK 37 `dexdump` shows `s.h.e.l.l.N.<clinit>()` calling `System.loadLibrary("exec_x86")`, and conditionally `System.loadLibrary("execmain_x86")`. The selector `N.x()` reads the Android linker ELF machine byte, with `Build.SUPPORTED_ABIS` / `ro.product.cpu.abi` as fallback information; the alternate path loads `exec` / `execmain`. No part of that application code was executed for this inspection.

The distinction between APK directory grouping and actual ELF machine type also appears in the [official AOSP NativeLibraryHelper implementation](https://android.googlesource.com/platform/frameworks/base/+/HEAD/core/jni/com_android_internal_content_NativeLibraryHelper.cpp), observed blob `3108f1f2c7c52f718e65f8f138393cffcf059f37`: `iterateOverNativeFiles` and `findSupportedAbi` select the `lib/<abi>/` path component. This explains why a directory label alone cannot describe every payload's architecture. It is not evidence of selected-GSI source equivalence or successful native loading.

Candidate v2 requires exactly four explicit `cross_arch_shared_libraries` records. Each record pins its literal path, kind, uncompressed byte count, complete SHA-256, ELF class, machine, `ET_DYN` type, SONAME, entry point and absence of an interpreter. Paths must be distinct, sorted, and free of wildcard syntax. The verifier first repeats real SDK 37 APK signature and identity verification, then reads each complete pinned library and parses its bounded ELF program and dynamic tables. The string table must belong to one file-backed load segment; the dynamic table must be bounded and terminated, with unambiguous SONAME metadata. An executable type, interpreter, PIE flag, invalid entry, changed payload, missing declaration or extra foreign library fails before a receipt is created. All other libraries still have to match their declared directory ABI. The entire actual foreign-library set must equal the four pinned entries.

V1 retains its existing requirement that every native ELF match its directory ABI. It has no cross-architecture declarations or exceptions. The v2 output records the actual foreign architectures separately, with `native_compatibility_qualified: false` and `dispatch_runtime_observed: false`. Neither source model establishes that the app's library selection, namespace, Native Bridge, dependencies, or business flows work on the final Android runtime.

```sh
python3 compat/android/pocket4/apk-content-identity/verify_apk.py \
  /absolute/downloads/szzc-9.6.3-329-official.apk \
  --build-tools /opt/android-sdk/build-tools/37.0.0 \
  --candidate compat/android/pocket4/current-app-acceptance/szzc-candidate.json \
  --expect-candidate-sha256 863d679c1ef7d56719777b5d75592aa65d6725aa5cd91fd75424fd349a9980e5 \
  --receipt-output /absolute/receipts/szzc-9.6.3-source.json \
  > szzc-native-input.json
```

The native `ApplicationPlan` fragment has the same existing format as v1. The receipt is created only after all checks and still says `installed`, `runtime_qualified`, and `production_ready` are false. A new version, APK hash or shared-library layout requires a new reviewed candidate; the four recorded files are never skipped based on their names.

Both candidate schemas accept the neutral digest description `observed_whole_file_digest` as well as the original `observed_whole_file_digest_not_publisher_published_checksum`. This allows an observation to coexist with a separately published publisher checksum without claiming that one does not exist. Neither description changes verification or grants trust: actual whole-file recomputation and the external candidate pin remain mandatory, and unknown digest descriptions fail.

The actual signed 9.6.3 APK passed the complete v2 CLI on 2026-11-18. Independently repinned candidates with a wrong shared-library SHA-256 or a wrong ELF class/machine each failed after real APK verification, produced no stdout, and created no receipt. The positive receipt described all 118 native entries and the exact four foreign shared libraries. These are source identity observations; no app was installed or launched.

## Controls

Use a trusted, signed public reference APK and its independently verified SHA-256:

```sh
python3 controls.py --reference-apk reference.apk --reference-sha256 VERIFIED_SHA256 --build-tools /opt/android-sdk/build-tools/37.0.0
```

The controls verify the real APK, reject a wrong expected package, keep Source Stamp certificates separate, and reuse the same external input filename with altered signed DEX bytes to confirm that stale metadata cannot make the altered APK pass. All altered files are temporary. The reference remains unchanged.

`VALIDATION.json` and the `SOURCE_MANIFEST.json` historical control results retain their original reference SHA. Adding the current candidate does not retag those earlier observations as a new APK verification.

The candidate schema, native fragment and rejection controls run without an APK or Android tools:

```sh
python3 -I -B compat/android/pocket4/apk-content-identity/test_candidate.py
```

These 18 source tests use explicitly synthetic inputs and mocks around the existing verifier. The original nine controls cover wrong package/version/hash/signer/ABI, signature failure, split declarations, raw version/SDK and ELF mapping, strict candidate JSON and external SHA, changed inputs, receipt overwrite, and CLI flag grouping. One control verifies neutral digest wording and rejects an unknown kind. Eight additional controls exercise exact four-library binding, every payload hash and size, actual ELF class/machine/SONAME/entry agreement, missing and additional payloads, unchanged v1 rejection, executable/interpreter/PIE rejection, and bounded program/dynamic tables even when synthetic whole-file pins are updated. They are separate from real signed-APK verification and from application runtime acceptance.

This is an identity and signature gate. It does not establish delivery eligibility, split completeness for a particular device, runtime compatibility, or application business acceptance. It never installs or launches an app. APKs that require v3.2 signer selection are explicitly rejected until that mapping is implemented and qualified.

Binary XML attribute decoding follows the Android resource parser's fixed attribute layout, including the platform's handling of noncanonical `typedValue.size` fields. The complete attribute remains bounded by its declared record stride and the enclosing chunk. Source: https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/libs/androidfw/ResourceTypes.cpp (observed blob `de9991a8be5e2919b49f2fc4a307999972855bc9`).

The package includes no application APKs, installed-package inventories, account files, private signing material, or raw device logs.

## Current Fcitx input

`../current-app-acceptance/fcitx-candidate.json` pins the official GitHub
stable **release tag `0.1.3`** observed on 2026-11-18 at 09:25 UTC. Its actual
Android version name is **`0.1.3-0-g048f581c`**, version code 114, min SDK 23,
target SDK 36, x86_64, 46,106,936 bytes. The release tag is not substituted for
the actual Android version string. The independently reviewed candidate SHA is
`b1a52ea3223e996f4b2bd2d30fbf3e6983648f4f571a1d4b283acf4d17130e77`.

The observed APK SHA-256 is
`aaeb569fc3e9e8ec532b0ea33be39ce77b143c8add824d172f17356ddc3b9ed2`.
It independently matches the `digest` of official GitHub release asset
`490266211`. The official [release metadata](https://api.github.com/repos/fcitx5-android/fcitx5-android/releases/tags/0.1.3)
and [publisher signing information](https://github.com/fcitx5-android/fcitx5-android/blob/0.1.3/README.md)
were read before the download. The APK passed actual SDK 37 cryptographic
verification against the publisher's GitHub/F-Droid/Jenkins certificate:
`e4db1e9edff13629d07de4bbf8165fe9bd8557ab55092672da8e40dbe484ecd7`.
The publisher documents a different Google Play certificate; these channels
are not interchangeable for an in-place update.

At 2026-11-18T09:36:25.610283Z, the final verifier
`e52e538d4093c2ae6875716c72f888d8ec7bad44e57315e8fe7f2f9db2946e3e`
also completed the pinned v1 candidate path against the actual APK: all 24
native libraries matched x86_64, and a new 6,672-byte source receipt was
written with SHA
`9d35c6df2636c6afed732ccfc0d12d98cb010e568d5ad1ae61863c0c86601b5a`.
The exact package, build name, code, bytes, APK hash and signer match the
published 2026-11-09 historical candidate. This is a fresh source-input check,
not a current installed-package readback or input-method business test.

The same final verifier was run against Firefox 160.0.1 at
2026-11-18T09:36:29.625016Z: the original v1 candidate remained unchanged,
18 x86_64 libraries passed, and the new 5,973-byte receipt SHA was
`0cbbb1e10241d92e3abd498ffeb71f7c36faf47b188a6b007ebbf50eabfb2581`.
Both native fragments retain installed/runtime/production false. The optional
neutral `observed_whole_file_digest` description changes no package, digest,
signer, SDK, ELF or external-candidate-pin check.
