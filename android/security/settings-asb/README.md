# Settings AddAccount source repair

This recipe applies the official defensive AddAccount change for CVE-2026-58943 to the exact Settings source already selected by the complete production source lock. It also requests the normal Settings APK and binds that APK to its source provider and, on complete-image delivery, its system_ext image member.

## Original source and patch

The unchanged 651-project lock selects platform/packages/apps/Settings at commit 213829fb67f5e070029e0513a088f31bc8f5c1ed. Its original AddAccountSettings.java has Git blob 85e942b199058c68a9eaa025deec49b8d3190ea6 and SHA-256 6d72c50a8883676d20544d61301afb4998fd8ad7be428ceee9c4d41915d66a36.

The complete official patch is 9c7b03ebb0471c18b3d30a21873308d917570c8e. The b70d3754d990391f9f7bda92c9fbf659cd2e01f2 patch is byte-identical and is recorded as an alias, not applied a second time. The complete patch SHA-256 is 2ec497de1552ee5df5a3edb15d7ad68cb81e2e588edec8976352599dedb6a399. Applying it to the pinned original yields Git blob 34f87f1a3521eac075c8773db22da9d5296804d0 and SHA-256 7c46eb5b516eb2de1b669daebeb7656f061ef347f33f2a6f92f95d8836f4c7f0.

The patch tracks the activity's visible lifecycle, declines the callback's launch when it is not visible, and passes the official visibility-constrained ActivityOptions to the four-argument activity launch API. Both complete Java fixture bodies are retained for ordinary patch and restoration checks. They are source data; those checks do not execute Android code or reproduce the vulnerability.

## Four supplemental original inputs

The existing Settings sparse selection includes Android.bp and src, but omits the following root files required by the original build recipe. These are original files from the same selected Settings commit, not replacements for the source lock.

| Original path | Bytes | Git blob | SHA-256 |
| --- | ---: | --- | --- |
| AndroidManifest.xml | 340607 | c0cd7748c8f2b3cf0f280600cb023aa18257f78c | 04eae21c25f1b1525933d3b82b3e4643065d9f390cbc785971d61f1422aca998 |
| NOTICE | 10695 | c5b1efa7aac764ae6d8da63476a2d5cec02a6a5d | 38751245389e1e23f73e6f5384b5cbe7fa972cc4410c5adc9c04b082a0b9561a |
| proguard.flags | 3185 | b648707f6d659b1b000b7c711f9d221863cdbf59 | 987a4a8c3613db2e9776a96b1f6fda7c592677351bdb78cc4689ad69d72ba4fe |
| lint-baseline.xml | 19620 | 07f7a72a2b0840e5d81b2e72668374c85d1154fd | ccb3cd41693f1fc1df1eafa83049a0d630ec15b6602802fb18b8244691d965eb |

The original Android.bp is bound separately: 6448 bytes, Git blob 98415d7522acbc736c5bb9e09a2259c74503a49d, SHA-256 a2f9de37f38ce72b44adfff18e8553640e7255f80de3f00b248ec7c2f537e115. It connects src/**/*.java to Settings-core and Settings-core to the privileged platform-signed system_ext Settings module.

The official AOSP mirror preserves the exact project revision and complete file blobs:

- [Selected Settings source](https://github.com/aosp-mirror/platform_packages_apps_settings/tree/213829fb67f5e070029e0513a088f31bc8f5c1ed)
- [Official defensive patch](https://android.googlesource.com/platform/packages/apps/Settings/+/9c7b03ebb0471c18b3d30a21873308d917570c8e)
- [Same-fix patch alias](https://android.googlesource.com/platform/packages/apps/Settings/+/b70d3754d990391f9f7bda92c9fbf659cd2e01f2)

## Normal build and restoration

The Settings recipe requires strict complete-source selection, one Settings target and one module-info target. The default complete product also explicitly includes Settings in PRODUCT_PACKAGES. Missing-dependency and neverallow suppression remain disabled.

Before any of these five source paths changes, the existing Projection journal records the original AddAccount Java file and all four supplemental paths in one durable write. Existing supplemental files must match the original complete bodies. Originally absent files are supplied from the pinned recipe; foreign files and aliases fail validation. Restoration retains original bytes, mode and modification time, or original absence. It does not claim to preserve inode or ctime.

The normal build input receipt records the fixed Java body, unchanged source lock, complete patch, original and effective provider identities, request, and effective projection. After successful normal command completion and source restoration, the result requires the Settings module-info provider to be packages/apps/Settings and binds the complete installed system_ext/priv-app/Settings/Settings.apk bytes. Complete-image delivery additionally verifies the same APK against the actual system_ext image using the existing coherent-image consumer table.


## Already selected local dependencies

The original Settings sparse paths already include aconfig, assets, libs, protos, res, res-export, res-product and src. The src selection includes both Java/Kotlin sources and the settings-logtags input. Those directories are not supplied a second time. The explicit lint.baseline_filename in Settings-core refers to the additional original lint-baseline.xml above.

SettingsInterfaceLib is provided by frameworks/base at the lock's exact commit 94b4c163b7dfe5ce3607f7bb8456f9573f7de57d, under packages/SettingsLib/SettingsInterfaceLib. Its Android.bp (218 bytes, SHA-256 4e9d4bf8f0b518ae9848979f32d148377bd9e0de1e44309887a923079010c07b, Git blob 80b84efce93e0e0ad7b979b17b9ce18a5461d839) defines the named android_library with no static_libs and source globs src/**/*.kt and src/**/I*.aidl. The exact subtree 9c2b6aea780e8722619e8fc97d0446bbf5c52546 contains its AndroidManifest.xml and ITroubleshootingInfoProviderService.aidl. All are covered by the unchanged packages/SettingsLib sparse path. The similarly named Settings project settings-api-registry directory contains documentation and JSON lists; it is not this module's provider.

The required privapp_whitelist_com.android.settings module is defined in frameworks/base/data/etc/Android.bp at the same selected framework commit, with system_ext_specific and source com.android.settings.xml. The unchanged data sparse path covers both the module and its XML. No extra whitelist or permission is introduced.

- [Selected SettingsInterfaceLib provider](https://github.com/aosp-mirror/platform_frameworks_base/tree/94b4c163b7dfe5ce3607f7bb8456f9573f7de57d/packages/SettingsLib/SettingsInterfaceLib)
- [Selected permission-file build provider](https://github.com/aosp-mirror/platform_frameworks_base/blob/94b4c163b7dfe5ce3607f7bb8456f9573f7de57d/data/etc/Android.bp)

## Qualification boundary

Adding this recipe does not establish that every transitive Settings dependency in the sparse source closure has built successfully. The normal strict build remains responsible for rejecting missing dependencies.

Source preparation and ordinary Rust fixture tests do not qualify a resulting APK's complete DEX semantics, production signatures, Android startup, or application behavior. The normal receipts keep those qualifications false. The existing CP3A source and ART/APEX provenance gates are unchanged: the CP2A source lock cannot be relabeled as the selected CP3A image. A real complete build, final artifact checks, and the existing runtime gates are still required.
