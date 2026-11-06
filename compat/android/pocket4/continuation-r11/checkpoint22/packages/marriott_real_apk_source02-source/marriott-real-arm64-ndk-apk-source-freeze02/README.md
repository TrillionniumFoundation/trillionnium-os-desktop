# Original ARM64 NDK tests APK: input correction 02

This is a fresh, unexecuted build candidate for the original `com.example.ndk_tests` fixture. Build01 failed before any compiler command. Its full result, terminal and stdout are retained under `references/` without changes. The previous standalone APK13 reader02 admission remains unknown and is not retried or borrowed.

## Exact changes

The controller changes only its fixed kind and fresh root to build02. The binder changes only its request-key prefix. All observer functions are unchanged; its fixed INPUTS literal and kind are updated.

The three missing shared-tree cpufeatures inputs are the original public Android.bp, cpu-features.c and cpu-features.h from immutable upstream commit e0e58e67cd11713799cdf6b50ba5843d62881660. Their bytes and SHA256 match the original planned inputs exactly. The normal create-only inline-source loop stages these originals beneath the new root's source/prebuilts/ndk directory. Nothing writes to shared AOSP. The observer then performs the same complete double reads, identity checks and UTF8 checks on these exact files before any compiler command. Original source layout and provider semantics are preserved.

The required InstrumentationTestCase class moves from android.test.runner.jar to android.test.base.jar; InstrumentationTestRunner remains required in runner. The complete required class set is unchanged. The fixed framework API sources provide the module mapping, while build02 must still observe the actual SDK31 base JAR member. Current framework source is not proof that the actual SDK31 JAR contains that class. All seven complete archive/JAR bytes and SHA256 values observed during build01 are now explicit expected pins, including the runner JAR whose old class gate failed after both reads.

## Retained execution contract

The exact ProductSDK observation remains bound. Source SDK37, native current target10000, original GTest/cpufeatures ARM64 floor21, manifest min14 and target23 are unchanged. The build expects 50 commands, 16 real ARM64 REL objects and 7 linked outputs, including the two original real JNI DSOs. The 23-name original registry, exact 12 ProcSelfMaps tests, 9 new FD cases, real JNI exports, no-undefined links, package/signature/readback gates, disabled translator feature, child subreaper, source before/after checks, resource guard and final bounded full receipt are unchanged.

No Python parse, compilation, installation, Android execution, namespace entry or Main operation was performed while freezing this package. Static byte transformations and hashes were checked in V8. Build02 has no actual result yet. The independent fixture installation/run route remains source-only and has no executable runtime request.

## Review files

`controller01-to02.diff`, `observer01-to02.diff` and `binder01-to02.diff` cover the executable differences. `config01-to02.diff` is the full byte-preserving configuration patch; `config-normalized01-to02.diff` omits only encoded bodies for readable comparison. Each encoded body is still present with full size and SHA256 in the actual config. `SOURCE_PINS.json` is the original three-file binder contract.
