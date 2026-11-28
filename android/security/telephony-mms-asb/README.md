# MmsProvider subscription-ownership production repair

This candidate follows the accepted af0 complete-source producer. It addresses the source integration gap for CVE-2026-59005 / A-517376786; the selected CP3A binary component remains UNREVIEWED in the unchanged R24 map.

## Exact production input and change

The 651-project lock remains byte-for-byte unchanged. Its TelephonyProvider project is packages/providers/TelephonyProvider at 013b803626164c026025897b7dec45521c2cccab. The complete original MmsProvider.java is 75,335 bytes, SHA-256 c4c7c49f08c538a320e76e2a4e6c8e485d7a9806cab1a46104f8098a90298ddc. The fixed body is 75,313 bytes, SHA-256 5e3488a4809e49611ef63c3fa5397f82c0c9358132e2710ca131817211f767bc.

The sole production hunk comes from official AOSP TelephonyProvider change 95af247d92b5c0b5d02dfa5ca2a62310e4cedbd6, also represented by branch change 70b9404db328f3f3d4b1ba3c0ec76637d3bdf88e. Its edits are unchanged; only the file preimage/index and hunk line are adapted to the exact original. It performs the existing subscription-ownership check before the table-specific branch. ProviderUtil.java and its policy are unchanged, including its existing invalid-subscription handling.

Original complete diffs are retained in the pre-existing first-party capture, with respective SHA-256 63612d5552bed832f45a5c5d60610967276fa232bb3d0e0c4f98507885a14f9e and 06e153c73aee1c8c5524629cf3f7bf872277ad01926660a4e567ee6ff8a3d70d. This repository patch deliberately includes only the production hunk. It does not include, port, or run the official provider-request tests. The original test source has a different footer from the official test patch; no test compatibility is inferred.

## Existing normal producer

The new module joins the existing complete strict user build, with the exact TelephonyProvider and module-info targets. It uses the existing Projection journal to save the one Java original before patching, validates complete before/after bytes, and checks restoration of bytes, permissions and mtime. Android.bp, both manifest bodies, and ProviderUtil.java remain exact read-only dependencies.

The inherited generic_system.mk reaches handheld_system.mk, whose actual source selects TelephonyProviderHsum only when PRODUCT_USE_HSUM is true and TelephonyProvider otherwise. This candidate does not change that configuration or force an HSUM value. It accepts only the normal TelephonyProvider source row and exact system/priv-app/TelephonyProvider/TelephonyProvider.apk output; a different variant or missing artifact fails closed. coherent_images also requires that module and binds the same APK to its final system-image inventory. No Hsum qualification is claimed.

No source lock, Cargo lock, release identity, signing key, resource limit, dependency exception, SELinux neverallow control, image selection, CURRENT value, or C/D input is changed. The normal caller still restores the projection before evaluating the build result and producing component completion records.

## Validation scope

Six ordinary Rust cases are prepared for static production-hunk placement, exact dependency/patch identity and prewrite rejection, journal recovery/failure, strict request/651-lock checks, exact APK metadata and alias rejection, and restoration-bound completion records. Test files use private source fixtures and synthetic artifact bytes. They do not issue Android provider calls or use real MMS data.

This source-only candidate has not been formatted, compiled or run. A future isolated ordinary qualification must materialize the exact candidate, format the changed Rust files, execute the six cases and affected existing producer cases, then perform the normal Rust release build. It does not authorize an Android build. Any later Android, DEX semantic, signing, runtime, whole-CVE and production qualifications require their own actual evidence.
