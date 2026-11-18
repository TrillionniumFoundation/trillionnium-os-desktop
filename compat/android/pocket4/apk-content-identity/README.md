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

All candidate schemas accept the neutral digest description `observed_whole_file_digest` as well as the original `observed_whole_file_digest_not_publisher_published_checksum`. This allows an observation to coexist with a separately published publisher checksum without claiming that one does not exist. Neither description changes verification or grants trust: actual whole-file recomputation and the external candidate pin remain mandatory, and unknown digest descriptions fail.

The actual signed 9.6.3 APK passed the complete v2 CLI on 2026-11-18. Independently repinned candidates with a wrong shared-library SHA-256 or a wrong ELF class/machine each failed after real APK verification, produced no stdout, and created no receipt. The positive receipt described all 118 native entries and the exact four foreign shared libraries. These are source identity observations; no app was installed or launched.

## Exact native input layouts (candidate v3)

V3 adds a distinct `native_layout_exceptions` list containing zero through eight records. V1 retains its original directory-to-ELF requirement, and v2 still requires exactly four `cross_arch_shared_libraries`. Adding v3 does not reinterpret either earlier schema.

Every v3 exception has a literal, sorted, unique `lib/<abi>/lib*.so` path, an exact uncompressed byte count, and a complete SHA-256. The list must describe the entire actual exception set. Missing entries, additional foreign or empty payloads, wildcard paths, unknown kinds, and changed bytes fail before receipt publication. All unlisted `.so` entries still have to match their directory's ELF class and machine. No filename or path grants a general exemption.

- `cross_arch_shared_library` requires the same explicit class, machine, `ET_DYN`, SONAME, entry point and no-interpreter pins as v2. It uses the unchanged bounded `_shared_elf_metadata` parser. A new APK or payload hash cannot make invalid program/dynamic/string tables, an executable type, an interpreter or a PIE flag pass that parser.
- `empty_placeholder` requires `bytes: 0` and the actual empty-file SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. The ZIP member's declared and read content must both be empty. These entries appear only in `empty_placeholders`; they never enter `native_libraries` and cannot establish that an ABI has a native ELF library. The model does not assume that the app avoids loading the placeholder.
- `dual_dynamic_shared_library` explicitly describes an `ET_DYN` payload whose declared dynamic-table file range differs from its unique `PT_LOAD` mapping. The separate `dual_dynamic_elf.py` parser requires one `PT_DYNAMIC`, one matching `SHT_DYNAMIC`, a linked string table identifying the same complete bytes as the mapped string table, matching SONAME and ordered NEEDED identities, and bounded tables and pointers. Both complete dynamic views and their consumed prefixes are hashed. Consumed entries cannot overlap each other, the ELF/program/section headers, or the string table. Unconsumed tails, tag differences, section-name-index type, section/segment address differences, and 4 KiB versus 16 KiB load congruence remain explicit observations. The original shared-library parser still rejects this layout when the ordinary kind is selected.
- `embedded_7z_archive` describes a 7z 0.3 resource, between 33 bytes and 64 MiB, with the complete signature header, valid start-header and next-header CRCs, and a next header of at most 64 KiB ending exactly at payload EOF. `native_resource_payloads.py` records the packed range without decompressing or verifying its contained streams. These entries appear in `embedded_archives`, never in `native_libraries`, and cannot supply a native-ELF ABI witness.
- `interpreter_tagged_et_dyn` is limited to the observed ARM32, zero-entry `ET_DYN` form with exactly one literal `/system/bin/linker` interpreter, including its terminating NUL, before loadable segments. The interpreter is explicitly pinned. Program and dynamic table bounds, a unique file-backed mapping, bounded SONAME/NEEDED identities, and the no-PIE check remain enforced by the separate resource parser. These actual ELF entries appear separately in `interpreter_tagged_et_dyn`; the record does not establish that they serve as standalone executables. The ordinary shared-library kind continues to reject `PT_INTERP`.

The last three kinds additionally require an independently pinned `layout_sha256`. Each helper returns its complete structural `layout`. The consumer serializes that object again using UTF-8 JSON with sorted keys, compact separators, `ensure_ascii=False`, `allow_nan=False`, and no trailing newline; it enforces a 64 KiB bound and compares the computed digest both to the helper's digest and the external candidate pin. Any helper-supplied kind, byte count or payload SHA must also equal the already verified payload pin before its metadata is recorded. A new kind never provides a generic opaque-payload allowance.

An empty exception list can describe a conventional ELF layout while accurately recording a historical signer reference. V3 uses the same explicit `public_historical_candidate` signer reference and `signed_apk_android_manifest` version metadata distinction as v2. Neither a historical signer pin nor signed manifest metadata is relabeled as a publisher-published certificate statement or a global latest-release guarantee. The complete APK, actual signature verification, binary manifest, and independently reviewed external candidate SHA remain mandatory even when the exception list is empty.

Every v3 binary-metadata result records `native_compatibility_qualified: false` and `dispatch_runtime_observed: false`. The source receipt and unchanged native `ApplicationPlan` fragment retain `installed: false`, `runtime_qualified: false`, and `production_ready: false`. A source identity result supplies no evidence that Android loads the libraries, that architecture selection works, or that application business flows pass.

### Current publisher observations

The complete publisher APKs below were acquired and verified with SDK 37 on 2026-11-18. Their package signers match the public historical candidate at immutable commit `6fd7efdcfa27da2015b7eb5b103dc399491aa18f`; the signer-reference URL is preserved in each new candidate. The source package contains candidate definitions and verification code, never the APK payloads.

| Candidate | Signed APK version / code | Complete bytes / SHA-256 | Actual native entries |
| --- | --- | --- | --- |
| `../current-app-acceptance/ctrip-candidate.json` | `ctrip.android.view` `8.97.6` / `2136` | `104927037` / `d22e5db066d8d2fd7c1bd53e5c62cc108fc9d89d42169cbdaf3b2ddfc04ac68c` | 57 ELF64 ARM64 libraries; zero exceptions |
| `../current-app-acceptance/beike-candidate.json` | `com.lianjia.beike` `3.06.71` / `3067100` | `228991122` / `6984af4bbeda2818ad0a35183dd59af798eceebb9e441ef869b32dcc5095f728` | 71 ELF64 ARM64 libraries and one explicitly pinned ELF64 x86_64 shared library |
| `../current-app-acceptance/ceair-candidate.json` | `com.rytong.ceair` `9.5.16` / `239` | `220804847` / `a6da8d746f98cae884f6b0137b5c7e8412836adf75530b763dae1536c75522ce` | 46 ELF64 ARM64 entries, one dual-view ELF64 x86_64 entry, and two empty placeholders |
| `../current-app-acceptance/12306-candidate.json` | `com.MobileTicket` `5.9.4.5` / `275` | `150377492` / `c7e56101e5753002bba220ce40d07b00d4bc822e1eeef12bbe36ec9e2f8e272d` | 59 ELF64 ARM64 entries, one dual-view ELF64 x86_64 entry, one interpreter-tagged ARM32 ELF, and one 7z resource |

Ctrip's [official download page](https://m.ctrip.com/html5/mkt/centerpage/download/) requests the publisher's `getConfigUrl` endpoint with `config: versionInfo`; the observed response reported `8.97.6` and an update date of `2026-11-16`. The current [publisher QR image](https://pages.c-ctrip.com/market/union/adPlatform/ios_and_6_more.png), 11427 bytes with SHA-256 `5cc9d0bf75ac84166f9b71602e05f1d11640de92ec9f52e664a19a700bbe25b2`, decodes to `http://m.ctrip.com/m/c1052`. Its Android download selection returned the exact HTTPS publisher APK URL recorded in the candidate. The [HTTPS form of the same route](https://m.ctrip.com/m/c1052) was independently checked and returned that identical APK URL, byte count and ETag. The separate `c1051` route returned an older `8.94.6` filename and was not used. The actual new APK is `8.97.6` / code `2136`, min SDK 24, target SDK 30, with signer `8155dc0644fed517e8ef6bef9718c363d0eb3eb2c22c06455044d88268bdcf0a`. The candidate SHA is `df96be23ff2026e5d7296de32874f4adb7e19cf874f5d896d32edf9722145f08`.

Beike's [publisher page](https://m.ke.com/client/) supplies the [current Android route](https://m.ke.com/download/lianjia?scheme=&direct=1), which redirected to the `file.ljcdn.com` APK URL recorded in the candidate. This observation delivered the same complete APK SHA-256 as the public historical candidate; it is a fresh official-channel observation, not an inferred version upgrade. Binary XML reports min SDK 23 and target SDK 31. Its signer is `0b66624117621bb9bc3e7d12a1fe5436794cf8999b0253d9ff9bec71e0932178`. The candidate SHA is `409a2304f11371604429e10d83a1f859372ea38ad01c6086819722c8274e7080`.

Beike's one foreign entry is `lib/arm64-v8a/libjgclb_x86.so`: 992840 bytes, SHA-256 `7341951a925105ba15263c0f90943f41c740754a52821750d1317c23a1ae4676`, ELF64 little-endian machine 62, `ET_DYN`, SONAME `libjiagu.so`, entry point zero, no `PT_INTERP`, and seven program headers. The unchanged shared-library parser accepted its actual bounded structure. Static inspection of the signed `classes.dex` (63576 bytes, SHA-256 `ec759739e2aa7926d76ff7ebe2613e10cca9748432b0652ac02d0086133701a2`) with Google's SDK 37 `dexdump` shows `ekieb.aijnail.moc.StubApp` selecting `jgclb_x86` using Android ABI information and calling `System.loadLibrary` through its `a(String)` method, with a `System.load` file-path fallback. This is an in-process shared-library layout, not a separately executed helper. Neither the DEX nor native payload was executed during inspection.

The existing candidate CLI accepts these v3 definitions with their reviewed external SHA and a new absolute receipt path. Only the stdout `application` object is a native `ApplicationPlan` entry; the wrapper is not a complete runtime plan.

### China Eastern Airlines and 12306 structural observations

The [China Eastern publisher page](https://app.ceair.com/) reported `V9.5.16`, updated `2026-11-05`, and supplied the exact HTTPS APK URL in `ceair-candidate.json`. The actual package has min SDK 24, target SDK 33, and signer `b48f75514e956be6bd7d56f1701136c8d76f19459bd724ac52390a572bc0ecbf`. Its candidate SHA is `f51645ff56426e595cfe5e12ab6383ab6c84e0260414bb2ee9a3ffe8b9c05910`. The two empty members are `lib/arm64-v8a/liblocSDK7a.so` and `lib/arm64-v8a/liblocSDK8b.so`; neither is counted as an ELF library.

Its `lib/arm64-v8a/libDexHelper-x86.so` is 1146781 bytes with payload SHA-256 `37b0cc1dd6a8a23f700a2c20aa3c20668e74dde6ce405a7f63a61830dd6c2b1b`. The declared dynamic table is at file offset 1145072 with 608 bytes; the virtual-address mapping identifies a different 608-byte table at offset 1115240. The declared table's consumed prefix contains dependency and SONAME identities, while the mapped table carries additional tags. The exact layout pin is `f3b7232ec5c5d871f8f1116c502af4f8d3890de4e4e99e1cb01aa06f87ae6ee9`. The full declared range overlaps section-header bytes after its consumed prefix, the section-name index identifies `NOBITS`, and several other noncanonical facts remain in the layout. They are not normalized away or represented as loader compatibility.

The separate paths have a concrete counterpart in official AOSP source: [`ElfReader::ReadDynamicSection`](https://android.googlesource.com/platform/bionic/+/refs/heads/main/linker/linker_phdr.cpp), observed blob `5967e2d48a29cbbaca8f87a2be42361ab43decd5`, checks section file offset/size against `PT_DYNAMIC` and reads the linked string table. `phdr_table_get_dynamic_section` uses the segment virtual address, and [`soinfo::prelink_image`](https://android.googlesource.com/platform/bionic/+/refs/heads/main/linker/linker.cpp), observed blob `4cf93b9badb616b892a2b063234abd72fb7c71e8`, consumes that mapped dynamic address. This supports recording both views. These observations do not identify the selected GSI's source revision or qualify its linker, relocations, namespaces, dependencies or Native Bridge behavior.

The [12306 publisher page](https://mobile.12306.cn/otsmobile/h5/otsbussiness/downloadapp/downloadapp.html) supplied its published JavaScript and the `appDown` API; the observed `appAndroidDownUrl` selected the exact `12306v5.9.4.5.apk` HTTPS URL in `12306-candidate.json`. Binary XML reports min SDK 23 and target SDK 34. The signer is `53a2508d2efcef95deadf8ff74ef41eadcd1e96fbcc49b53d741787806c01904`; the candidate SHA is `c77e4c3ddd303b5417aeef9170f61e7f32e6a1563037979bb7c9ad88783ff112`. The three declared resources are:

| Exact member under `lib/arm64-v8a/` | Actual bytes | Explicit kind | Canonical layout SHA-256 |
| --- | ---: | --- | --- |
| `libDexHelper-x86.so` | 1237645 | `dual_dynamic_shared_library` | `d6687be7878f15be3d24622a109b2015363175f31f3e11e1931247fdc8a6b9a0` |
| `libWebViewCore_3.22.2.72.240709175818_7z_uc.so` | 13999047 | `embedded_7z_archive` | `6f45cd40d70c111d1be7002ba05f4362931a1eba30f7ee98d9b68f17bedc2b3c` |
| `libwb.so` | 2208920 | `interpreter_tagged_et_dyn` | `63587c3383ae55b1becb76c792e6560290d55d580e144a15b5e326445a18aff8` |

The full payload SHAs are in the candidate. The archive's start-header CRC is `ec19ea22`, and its 37-byte next header ends at EOF with CRC `a250b709`. No stream was decompressed. `libwb.so` is ELF32 ARM, `ET_DYN`, entry zero, SONAME `libwb.so`, with the exact interpreter string and no `DF_1_PIE`; an interpreter tag alone is not treated as evidence of a standalone executable role. Its existing ordinary shared-library rejection remains unchanged.

### Final verification with one source revision

From **2026-11-18T10:24:30.672214+00:00** through **2026-11-18T10:25:02.642998+00:00**, the same final `verify_apk.py` (39174 bytes, SHA-256 `e464907dc5cffdfe4a2b104eb1e7febfd8b6aebfe876b1a5c69647fab739ff0d`) and the frozen helper bytes repeated the complete SDK 37 candidate CLI for all seven listed APKs. All seven exited zero and produced new source receipts and exact `ApplicationPlan.expected_input` fragments. The original three candidate files remained unchanged; their schemas remain v1, v1 and v2 respectively.

| Application / signed version | Candidate schema | Actual ELF entries | New source receipt bytes / SHA-256 |
| --- | --- | ---: | --- |
| Firefox `160.0.1` | v1 | 18 | `5958` / `84d555dd4920e8600f59b11cf939063501c54b2584361f3b1282912337bbccfb` |
| Fcitx `0.1.3-0-g048f581c` | v1 | 24 | `6657` / `756889ed192b3848d37bd9171aad2bc96accdbe3c7c9002ef870a81ef778793c` |
| SZZC `9.6.3` | v2 | 118 | `20844` / `4945bdbc416c76b995d51fcf787a444f80000a7f4e943efbb13358f46cd5b562` |
| Ctrip `8.97.6` | v3 | 57 | `11318` / `01103603d36893d00e7b9e1005df3e906ba61903a43e517e798ae7d1ad439fba` |
| Beike `3.06.71` | v3 | 72 | `13551` / `ba8d0c8a408b1353b990d1827b588403cc1b3f684068b1522999e2480c6ad4c0` |
| China Eastern `9.5.16` | v3 | 47 | `29387` / `5aa4a7916b2b42a2f61c4a402ceb4ec56409e30d6b10fef92ddd95f9cf29d793` |
| 12306 `5.9.4.5` | v3 | 61 | `43549` / `93cd90cf7a3f4d9d6677b4e319f4e0e86f2147ed834df743e8e1b61c73914011` |

The counts include recorded actual foreign-architecture ELF entries. China Eastern's two empty placeholders and 12306's one 7z resource are excluded from ELF counts. Every original APK's full SHA and file-identity bookends stayed unchanged; their total size was 1112420343 bytes. All executed source-code files were checked against the same frozen hashes before and after verification.

Four additional complete-APK candidate invocations deliberately used a wrong payload SHA, a wrong canonical layout SHA, a missing exception, or a 7z resource mislabeled as empty. Each exited one, emitted no stdout and created no receipt. The APKs remained unchanged, and the temporary incorrect candidate files were removed. The unified local `ACTUAL_INPUTS.json` index (33913 bytes, SHA-256 `0804c247f530acfb4ec00bdb00ecec8cee1b8430fd5f9712d43754ed1290887a`) binds all seven new receipts, native fragments, actual command records, candidate pins, code pins and four negative results. It is retained with the separately acquired current APK artifacts, not embedded in this source package.

These results cover the seven listed source inputs only. Their receipts and fragments retain installed, runtime and production false; native loading, architecture dispatch, input delivery to an Android owner, and application business acceptance remain separate gates.

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

V3 adds sixteen source controls without changing those initial 18 test bodies. Nine cover a normal zero-exception layout, separation of empty placeholders from actual ELF libraries, missing and additional payloads, false empty declarations and ABI witnesses, strict kinds and legacy-schema isolation, the eight-record upper bound, per-payload identity, the unchanged strict ELF parser after complete synthetic repinning, and external-pin/signature/manifest gates. Seven more cover the three explicit structural kinds, canonical digest agreement, changed helper summaries, strict original-kind rejection, and archive-versus-ELF accounting. All 34 candidate controls use inert synthetic inputs; successful unit controls do not stand in for SDK 37 verification of the complete real APKs.

The two helper suites have independent isolated entry points:

```sh
python3 -I -B compat/android/pocket4/apk-content-identity/test_dual_dynamic_elf.py
python3 -I -B compat/android/pocket4/apk-content-identity/test_native_resource_payloads.py
```

They contribute nine and twenty synthetic cases respectively, for 63 ordinary source controls across the three commands. The dual parser's real China Eastern payload was also observed separately with three modified-byte rejection cases. The resource helper's two optional actual 12306 payload cases are additional local byte-parser checks; the ordinary CI command neither reads those APKs nor counts them as two extra synthetic passes. The real payloads and modified copies are never included in the source package.

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
