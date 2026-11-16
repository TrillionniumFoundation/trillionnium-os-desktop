# Content-bound APK identity verification

This small Python package verifies an APK for Android SDK 37 using an existing Android Build Tools directory. It reads package, version, split, and SDK declarations directly from binary XML, reads public certificate bytes from the APK signing block, and compares these identities with Android's APK tools.

Each inspection fixes the whole-file SHA-256 first, copies the APK into an exclusive temporary directory with its SHA-256 as filename, runs `aapt2` and `apksigner`, and checks the original and copied bytes again. Every external tool output is bound to that APK SHA and the tool's own file hash. Package and version mismatches fail closed. App signing certificates and distribution Source Stamp certificates are separate. For packages carrying different v2 and v3 certificates, the identity comes from the strongest scheme actually verified for SDK 37.

## Run

Python 3.11 or later, Java, and Android Build Tools 37 are required.

```sh
python3 verify_apk.py reference.apk --build-tools /opt/android-sdk/build-tools/37.0.0 --expected-package example.application
```

Add one `--expected-certificate-sha256` argument per expected app signer when an independently trusted signer pin is available.

## Controls

Use a trusted, signed public reference APK and its independently verified SHA-256:

```sh
python3 controls.py --reference-apk reference.apk --reference-sha256 VERIFIED_SHA256 --build-tools /opt/android-sdk/build-tools/37.0.0
```

The controls verify the real APK, reject a wrong expected package, keep Source Stamp certificates separate, and reuse the same external input filename with altered signed DEX bytes to confirm that stale metadata cannot make the altered APK pass. All altered files are temporary. The reference remains unchanged.

This is an identity and signature gate. It does not establish delivery eligibility, split completeness for a particular device, runtime compatibility, or application business acceptance. It never installs or launches an app. APKs that require v3.2 signer selection are explicitly rejected until that mapping is implemented and qualified.

Binary XML attribute decoding follows the Android resource parser's fixed attribute layout, including the platform's handling of noncanonical `typedValue.size` fields. The complete attribute remains bounded by its declared record stride and the enclosing chunk. Source: https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/libs/androidfw/ResourceTypes.cpp (observed blob `de9991a8be5e2919b49f2fc4a307999972855bc9`).

The package includes no application APKs, installed-package inventories, account files, private signing material, or raw device logs.
