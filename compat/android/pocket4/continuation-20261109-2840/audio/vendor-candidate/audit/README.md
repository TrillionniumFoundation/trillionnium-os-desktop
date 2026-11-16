# QPR1 Audio vendor boundary

This directory contains a read-only audit of the selected official GSI and the Rust implementation of a narrow candidate staging command in the existing updater. The Python files are a temporary prototype, not the supported packaging entry point. It does **not** establish a completed Audio APEX build, a signed release, VINTF compatibility, working audio, or production readiness.

## Findings from the selected image

The image examined was the exact CP3A.260905.010 / build 16176746 system image selected for Pocket4. Its complete 2,294,853,632-byte SHA256 was recomputed before extraction:

`dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4`

The original remained unchanged. Extraction used read-only `debugfs`; no mount, cell start, image write, or user-data access occurred. The immutable remote audit is:

`pocket4:/home/alex/work/pocket4-audio-qpr1-compat-20261109-2840-r1/evidence-r1/RESULT.json`

It is 42,949 bytes, SHA256 `ee18708bf0dd88ff1928b55e90ddcb08c8e7930ee98f4c1698a5e9b97b680e73`. The full raw receipt is included here as `RESULT.json`. Durable H job `1a1c0ef0346-336d-38` exited successfully at `2026-11-09T15:31:02.535Z`, with complete durable output and no stderr. Source image verification receipt SHA256 was `bd867013617453a04ddc753a9ee811d604efe0c195be78f3590c78037cadcb58`.

| Actual input | Observed constraint | Consequence |
| --- | --- | --- |
| `system/etc/vintf/compatibility_matrix.202604.xml` | Framework level 202604; `android.hardware.audio.core` and `android.hardware.audio.effect` contain version `1-4`; `IConfig/default`, `IModule/default`, and `IFactory/default` appear in the corresponding interfaces | The source recipe's V4 declarations fit the observed Audio interface ranges. This is only a component comparison; complete framework/device matching has not run. |
| Matrix file identity | 23,111 bytes; SHA256 `2ce785af96e3a04b7b06f74c5a8461618a01dae15588d84db47119fccd67fb13` | Later qualification must use this actual selected GSI, not a matrix reconstructed from the CP2A build tree. |
| `system/etc/llndk.libraries.txt` | Includes `libbinder_ndk.so`, `libc.so`, `libdl.so`, `liblog.so`, `libm.so`, and other listed stable vendor interfaces | The native vendor HAL can use the official stable providers. Every actual external dependency and symbol version still needs checking. |
| `system/lib64/libbinder_ndk.so` | 189,112 bytes; SHA256 `1c750ec879fb1473eb2e083bd9fd56a287616b3d45d32dc9e950318223b2977a`; dynamic table and dynamic symbols were extracted | This is the actual QPR1 provider to compare with the compiled HAL's imports. Its presence alone does not prove an arbitrary compiled consumer is compatible. |
| `system/lib64/liblog.so` | 102,368 bytes; SHA256 `9f8d804b28b075302e14f7ce2c5f997a8bf2749fa6a5180b2282f8ef3ae55c5c`; dynamic table and dynamic symbols were extracted | Preserve the official provider and verify actual consumer imports. |
| `system/apex/com.android.art.capex` | Compressed stock ART, not a `.apex` pathname; manifest package `com.android.art`, version 371899999 | A consumer hardcoded to stock `com.android.art.apex` does not implement this selected base's storage contract. |
| Inner ART `original_apex` | 49,065,984 bytes; SHA256 `5ace9ff8a8ab73aa64b63901fe18782028d5c61c452a35b8ad07fb0b711247d0` | Native's independent audit can inspect this exact original without modifying the official CAPEX. |
| ART payload public key | 1,032 bytes; SHA256 `8dc1b7157b0b16dd8ec0240dd8b3e65ce2f91c6bb0933dc048decb91917b465d` | This is key identity, not a completed APEX signature verification. |
| `system/apex/com.android.runtime.apex` | Present as an uncompressed APEX, manifest package `com.android.runtime`, version 1 | Keep official bionic/runtime. APEX manifest version 1 is a package version field, not an Android release or patch-level claim. |

The selected GSI's build properties report SDK 37, full SDK 37.1, and SPL 2026-09-05. No result here establishes November security coverage.

## Actual Audio producer and the stable boundary

The latest observed source recipe is `4caa694f25b3da022651a1078600a0eb1a5334fc`, tree `6c5a2f66cac52ebe4a9689252d80e591e1953319`, with 430-project source-lock SHA256 `db5187942e23ef535cfc53ebe47e98ef3e258a9f79d225a621f8fd20cded9a91`. Its normal source continuation succeeded under durable job `1a1c100e9c8-336d-44` at `2026-11-09T16:05:53.088Z`; the original RESULT is 917,973 bytes, SHA256 `ca309c277d3bcc962abbaadb1054b334ff2d0eb603bb091a991f60f4896e04ec`. The observed source service was physically absent after exit. The continuation verifies 58 original SDK files; the three added files are API36 public android.jar, framework.aidl and core-for-system-modules.jar at the unchanged upstream SDK commit. The owner label SDK35 denotes 35 added selectors, not an API35 change. The earlier independent recipe `de1534f4146f3aefc56c6d777545177be62b6029` and its 55-file source result are retained predecessor evidence; the unstarted full draft using those older inputs must not be reused as the latest build. The official upstream inputs remain pinned, including hardware/interfaces `0162af698935100a590b7359581ac8b1b80693e5` and build/make `5ce6f787337d0223710bf7d4a16dbe6d2a35f777`. This is the existing CP2A producer; it is not relabeled QPR1.

`android/device/droidloom_arm64/audio-apex/Android.bp` defines the separate vendor package `com.android.hardware.audio.droidloom`, manifest version 1, `vendor: true`, `updatable: false`. The `apex_available_name` value `com.android.hardware.audio` is a build availability alias; it is not the installed package identity.

Its actual services are the Droidloom AIDL Audio core service and the example AIDL effect service. The bundled VINTF fragment declares core V4 `IModule/default` and `IConfig/default`, plus effect V4 `IFactory/default`. Init runs both from this vendor APEX; the core receives `DROIDLOOM_AUDIO_SOCKET=/dev/socket/droidloom/audio`. The source includes the real PCM projection patches; older comments and the integration proposal still describing silent streams are not runtime evidence.

The pinned upstream interfaces use VINTF-stable, frozen AIDL and the NDK backend. Core/effect are V4; imported common interface versions remain separately versioned. The official QPR1 system supplies `libbinder_ndk`, which uses official system `libbinder`. Private native dependencies must remain inside the vendor APEX or use a separately verified stable external interface. An Audio vendor APEX does not require replacing official `com.android.art`, `com.android.runtime`, AudioFlinger, `services.jar`, or the framework.

This conclusion does not transfer to the current enabled Native601 generation route. That route requires paired custom ART/libnativebridge/engine markers and private callbacks, and its stage path can replace the whole ART APEX. Native's independent lifecycle and stock-ART audit owns that different blocker. The custom Audio package neither has nor needs the ART signing identity.

## CP2A outputs excluded from the QPR1 Audio candidate

The old `tools/droidloom-update/src/assemble.rs::assemble_artifacts` stages a complete old product. It must not be used to assemble this Audio component into the selected QPR1 base. The following actual old paths are outside this component's permitted payload:

| CP2A source or derived output | Old destination family | QPR1 Audio disposition |
| --- | --- | --- |
| `system/bin/init` | Runtime `bin/droidloom-android-init` | Excluded. Preserve the selected official system; host isolation work is a separate qualified change. |
| `system/bin/netd`, `servicemanager`, `surfaceflinger`, `vold` | Runtime service overrides and storage helper | Excluded from Audio staging; do not mix old system service implementations into the new base. |
| `system/framework/services.jar` | Runtime `framework/services.jar` | Excluded. The official framework must remain. |
| `system/lib64/libbinder.so`, `libmeminfo.so`, `libinputflinger.so` | Runtime `lib64` overrides | Excluded. In particular, vendor AIDL must not substitute an old private C++ binder provider. |
| `libandroid_net_connectivity_com_android_net_module_util_jni.so`, built `netbpfload`, `libnetd_updatable`, `libservice-connectivity` | `compat/classpath-compat` | Excluded. These are separate Connectivity changes, not Audio dependencies to overlay globally. |
| Extracted old virt `bootclasspath.pb`, `systemserverclasspath.pb`, `framework-virtualization.jar`, `service-virtualization.jar` | `compat/classpath-compat/apex/com.android.virt` | Excluded. Preserve the selected official classpaths/APEX. |
| Old `product.img`, derived old `system.img`, pruned old `system_ext.img` | Full images payload | Excluded. The selected GSI is `gsi_system_as_root`; the old product/system_ext recipe is not its input contract. |
| Native paired `com.android.art.apex` replacement | Whole ART APEX replacement | Excluded from Audio. Native must independently resolve the current official-ART constraint. |
| Old framework apps, IME/home/SystemUI projections, vendor properties, other vendor HALs, init/classpath/VINTF overrides | Other runtime destinations | Not selected by this component. Their individual current-build and runtime qualifications remain separate work; exclusion here does not assert they are universally incompatible. |

The only staged payload path is `vendor/apex/com.android.hardware.audio.droidloom.apex`. The external host PCM service/socket still needs its own current implementation, identity, permissions, and live qualification; it is not fabricated or silently included by this tool.

## Candidate staging tool

`droidloom-update audio-apex-stage-candidate`, implemented in Rust in `audio_vendor_candidate.rs` and `audio_vendor_zip.rs`, takes an explicit SHA256 of a normal full-build terminal. It checks the successful normal build record and exact recorded whole-APEX file identity, copies the actual bytes, independently reads them back, checks bounded ZIP metadata and the installed APEX name, and writes one new private candidate directory. It refuses reused destinations, old source-only terminals, failed compiler results, non-boolean success flags, replaced files, symlinks/hardlinks, duplicate JSON/ZIP entries, noncanonical ZIP names, oversized central directories, and the wrong APEX package.

It does not call `assemble_artifacts`, extract files into an image, read or write user data, deploy the candidate, or accept arbitrary destination mappings. Output uses held directory descriptors opened without following symlinks, relative exclusive creation and directory identity checks before and after manifest publication. The immediate parent must exist, belong to the invoking user and not be writable by group or others; an ancestor symlink is rejected. ZIP entries permit only the normal APEX stored/deflated compression methods, with central-directory bounds checked before allocating the directory or decoding metadata. Raw DEFLATE uses the already locked workspace flate2 dependency and a fixed declared-size-plus-one buffer; exact consumption, stream completion, decoded length and metadata CRC are checked. A recorded normal full-build success is not treated as a signature or runtime pass. Its `CANDIDATE.json` always sets `complete_apex_qualified`, `compiled_elf_qualified`, `apex_signatures_qualified`, `vintf_qualified`, `runtime_qualified`, and `production_ready` to false. The official base identity is a target binding; the staging tool explicitly does not claim to reverify that remote base or the H job itself.

After the normal full build has actually succeeded and its durable terminal, physical retirement and retained source state have been independently checked, invocation is:

```sh
droidloom-update audio-apex-stage-candidate \
  --terminal /path/to/verified/full-terminal.json \
  --terminal-sha256 <exact-independent-terminal-sha256> \
  --destination /path/to/new/private/audio-candidate
```

Do not run this against the source r2 success: it is deliberately rejected. No real Audio candidate was staged during this audit. On error, a partial new private directory may remain, including a manifest written before a final synchronization or identity check failed. Consume a candidate only after a successful command exit; failed attempts must not enter a release workflow. Both files are synchronized after chmod, all new directories are synchronized from deepest child through the stage root, the existing parent is synchronized, and held directory/file identities are checked again before successful return.

The Rust tests use synthetic, explicitly unqualified ZIP fixtures for 18 packaging controls plus three ZIP/DEFLATE/protobuf controls. A separate normal executable check is configured to consume the actual frozen latest 58-file source terminal (SHA256 `ca309c277d3bcc962abbaadb1054b334ff2d0eb603bb091a991f60f4896e04ec`) and require rejection before destination creation. The final Rust source commit is `207cb626934534e0c4600312d1afa8552c835df1`, on the latest observed 430-project recipe. Its normal locked/offline updater tests, normal build and actual latest-source CLI rejection all passed under durable job `1a1c1333f88-e62c-2a` at 2026-11-09T16:45:29.108Z. The final RESULT is 8,514 bytes, SHA256 `da7b0a7c59cec09d438aa7bbb1fc14fd18d1619c89ce75fbdc5d7c0e46c587ff`. The same three Rust module/test files also passed 21 controls through the portable Linux CI harness under job `1a1c13d1477-e62c-40` at 2026-11-09T16:56:11.248Z; that RESULT is 10,045 bytes, SHA256 `0becea3581be096b2dc685ed6dba46281a9da068a9da182db15a30457078df9a`. These checks qualify the scoped tool controls only. The prototype's earlier 18 Python controls remain prototype evidence only. No synthetic fixture or source receipt qualifies real Audio bytes.

## Remaining qualification sequence

1. Complete the normal strict Audio full build under the existing ownership/lock contract; independently verify durable H exit, original source restoration, retained actual compile/input evidence, and complete APEX bytes. The completed 55-file predecessor, 251-test result and latest 58-file source continuation are prerequisites, not this full-build result.
2. Verify both APEX signing layers against the intended release identity, the packaged payload filesystem, ownership/labels/modes, binaries, VINTF/init/config members, and full transitive library closure. The source currently names `com.android.hardware.key` and `com.android.hardware.certificate`; merely using these module names or observing stock `release-keys` is not evidence of a production signing decision. No private key was read or copied in this audit.
3. Check every compiled ELF's architecture, `DT_NEEDED`, undefined symbol and symbol-version requirements against the bundled libraries and actual QPR1 stable providers. Inspect actual APEX `requireNativeLibs` and generated linker namespaces; do not copy old global system libraries to make a failed check pass.
4. Run the complete framework/device VINTF check against the selected image, actual candidate vendor target-level/manifest and activated APEX fragment. Check frozen interface versions/hashes and duplicate service instances. The V4 component comparison does not establish compatibility of the complete device manifest.
5. With the preserved official QPR1 system, observe actual APEX activation, service registration, core/effect interface identities, AudioFlinger/AudioPolicy connection, and the host PCM endpoint. Then qualify output, capture, mute/volume, routing, permission denial, disconnect/reconnect, flush/cancellation, concurrent Linux/Android audio and the relevant official VTS tests. These are pending, not inferred from compilation or local tests.

## Official primary references checked on 2026-11-09

- [AIDL Audio HAL](https://source.android.com/docs/core/audio/aidl-implement), page updated 2026-10-09: the supported framework/HAL boundary and official VTS entry point.
- [AIDL for HALs](https://source.android.com/docs/core/architecture/aidl/aidl-hals): stable VINTF interfaces, NDK vendor linkage and the `vts_treble_vintf_vendor_test` gate.
- [Vendor APEX](https://source.android.com/docs/core/ota/vendor-apex): vendor installation, native dependency packaging, VINTF fragments and service init scripts.
- [Stable AIDL](https://source.android.com/docs/core/architecture/aidl/stable-aidl): frozen interface evolution; it does not provide compatibility for private C++ platform interfaces.
- [VINTF matching rules](https://source.android.com/docs/core/architecture/vintf/match-rules): full framework/device matching is separate from reading one Audio version range.
- [APEX file format](https://source.android.com/docs/core/ota/apex) and [release signing](https://source.android.com/docs/core/ota/sign_builds): distinct payload/container signing and release key handling.
- [PKWARE ZIP format specification](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT), version 6.3.10: ZIP local/central headers, descriptor layout and bounded supported methods.
- [ApexManifest protobuf](https://android.googlesource.com/platform/system/apex/+/refs/heads/main/proto/apex_manifest.proto), observed blob `09bbf38d0738032db1430e2a127ee0792a4b8889`: field interpretation for the extracted manifests.

The technical conclusion is deliberately narrow: the observed official QPR1 Audio interface boundary supports pursuing this independent vendor AIDL implementation. The actual compiled package and complete runtime still have to satisfy the listed gates.
