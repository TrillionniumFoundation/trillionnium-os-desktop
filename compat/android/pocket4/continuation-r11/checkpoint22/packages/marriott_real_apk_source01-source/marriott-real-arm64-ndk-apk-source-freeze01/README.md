# Genuine ARM64 NDK test APK: source candidate 01

This is a **SOURCE_ONLY** candidate. No build request is bound or dispatched. The new product-configuration actual receipt is required before the binder can produce an executable request.

## Intended result

Build the original `com.example.ndk_tests` Java/JNI APK with its original manifest (minSdk 14, targetSdk 23), genuine GTest/Shared/User/JNI code, and the shared ProcSelfMaps source that contains the nine added syscall/FD boundaries. The complete native registry has 23 tests; the ProcSelfMaps filter selects 12. Static symbol presence is checked after link; no test is executed by this builder.

## Input state and first observation

The old 13-input reader02 has unknown admission and is not reused or resubmitted. This build loads the exact original reader02 observation functions in process, without calling its main, and performs all 13 fixed two-read/hash/format observations itself before any compiler child. Missing archives, LLVM bitcode members, the wrong architecture, a missing SDK class, an alias, or an input change fails without fallback.

SDK22 actually failed only on its unsuffixed soong.variables path. Its complete original report and terminal remain embedded with terminal exit 1; 21 individual successful observations may be reused only with all their original predicates and fresh complete build-time rechecks. A separate successful product-configuration observation is mandatory. It binds the original product and coverage filename from one fixed Soong environment file, and reads one configuration. No default SDK value is fabricated.

## Real source and ABI path

The exact original Soong symbolfile and ndkstubgen generate the five standard **link-only** NDK interfaces for libc/libm/libdl/liblog/libz. None is copied into the APK. Bionic crtbegin_so/crtbrand/crtend_so are compiled from exact source. The brand macro is taken from the actual product configuration. Four genuine ARM64 archives are observed and checked before use: libc++_static, libc++abi, libunwind, and compiler builtins.

The original APK libraries keep sdk=current (10000). The original GTest sdk9 and cpufeatures minimum declarations normalize to ARM64 API21 according to the original Soong source. These module settings are separate from the unchanged manifest SDKs and the observed CRT brand.

GTest is compiled from its complete original gtest-all.cc and its source includes, not a harness replacement. The two real implementation DSOs are linked with --no-undefined, exact SONAME/NEEDED checks, real JNI exports, all 23 TestBody symbols, the actual CRT brand, and a native unwind program header on the test DSO. ARM64 code is never executed on the build host.

The original two Java files are compiled against the actual SDK31 class interfaces. D8, aapt, zipalign, keytool and apksigner use the previously observed tool entries. The new APK uses its own private signing key, keeps v1 for original min14 and v2/v3, and packages exactly the two real implementation DSOs. Signing material is retained only in the owned 0700 build directory and is never exported in a report.

## Commands, cleanup, and reporting

The fixed plan has 50 commands and 16 translation units. The full M04 OwnChildReaper is byte-identical, including nonreaping observation before group cleanup, bounded descendant adoption, pidfds, and final empty-child/subreaper restoration. Only the command environment adds the exact observed JDK bin/JAVA_HOME; HOME is inherited unchanged. The child-only regular-file ceiling becomes 32 MiB for real object/DSO/APK outputs, while each command output capture remains 256 KiB.

The existing resource guard remains 1 GiB, one CPU, nice 15, with a 600-second work bound and 660-second outer bound. Existing swap/pids observations are retained; stricter caps are not invented. All original inputs and emitted artifacts are completely re-read and compared before success. The full report is limited to 64 MiB; stdout contains its size/SHA and a summary.

## Binding

After Root retrieves the successful product-config original and its authoritative terminal, run the local binder with:

```text
bind_build.py --sdk_configuration <original.json> --sdk_configuration-sha256 <full-sha>
  --sdk_configuration-terminal <terminal.json> --sdk_configuration-terminal-sha256 <full-sha>
  --sdk_configuration-job <actual-job> --output <fresh-local-binding-directory>
```

The binder validates the six exact pure production binding functions, parses the actual-bound Python source, and writes the new request. It does not execute it. Root is the sole dispatcher.

Future Android instrumentation needs a separately reviewed install and fresh current framework/task scope. Its original VerifyTestList must receive the explicit nonempty 23-name registry; the Activity route that supplies an empty list is not admitted. Compilation cannot establish Marriott's current failure cause, translator feature activation, ART success, or any app acceptance.
