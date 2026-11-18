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

These nine source tests use explicitly synthetic inputs and mocks around the existing verifier. They cover wrong package/version/hash/signer/ABI, signature failure, split declarations, raw version/SDK and ELF mapping, strict candidate JSON and external SHA, changed inputs, receipt overwrite, and CLI flag grouping. They are separate from real signed-APK verification and from application runtime acceptance.

This is an identity and signature gate. It does not establish delivery eligibility, split completeness for a particular device, runtime compatibility, or application business acceptance. It never installs or launches an app. APKs that require v3.2 signer selection are explicitly rejected until that mapping is implemented and qualified.

Binary XML attribute decoding follows the Android resource parser's fixed attribute layout, including the platform's handling of noncanonical `typedValue.size` fields. The complete attribute remains bounded by its declared record stride and the enclosing chunk. Source: https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/libs/androidfw/ResourceTypes.cpp (observed blob `de9991a8be5e2919b49f2fc4a307999972855bc9`).

The package includes no application APKs, installed-package inventories, account files, private signing material, or raw device logs.
