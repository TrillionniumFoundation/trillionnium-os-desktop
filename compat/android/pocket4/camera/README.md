# Camera2 zero-device and hotplug repair

This delivery preserves a reviewed source increment for Pocket4 Android 17 in DroidLoom. **Camera business qualification and overall application readiness remain NO-GO.**

## Failure and change

A removable camera could disappear after enumeration. The Camera2 manager then passed an obsolete identifier into `getCameraCharacteristics()`, allowing `IllegalArgumentException` to escape. The preceding zero-device change also needed to keep unavailable-camera initialization and module teardown safe.

Apply the two patches in order:

1. `patches/0001-zero-camera-and-teardown.patch` covers six Camera2/frameworks-ex files. It checks missing cameras and invalid indices, guards partially initialized modules, detaches availability callbacks, cancels pending work and shuts down module executors during teardown.
2. `patches/0002-camera-hotplug.patch` converts device-removal metadata failures into the existing checked camera-access path, invalidates stale facing caches, validates cached identifiers and continues enumerating when one device disappears.

The complete final manager is in `source/packages/apps/Camera2/src/com/android/camera/one/v2/Camera2OneCameraManagerImpl.java`. Its SHA-256 is `2b112a02eadd4c2db0a642c3263207cfc55ad9930e1a4399c06c219c480e2bca`. The negative-control fixture is the zero-device predecessor, not a mock replacement for the manager.

## Source pins and patch verification

[source-lock.json](source-lock.json) pins every touched file before and after each stage, both patch hashes and the final snapshot. Upstream revisions:

- Camera2: [3adb5275b9791c2128e78969579a69f03fe1ac00](https://android.googlesource.com/platform/packages/apps/Camera2/+/3adb5275b9791c2128e78969579a69f03fe1ac00)
- frameworks/ex: [4080c2d3e5a6387e0d064ce5744d56fc6a7c9bb7](https://android.googlesource.com/platform/frameworks/ex/+/4080c2d3e5a6387e0d064ce5744d56fc6a7c9bb7)

Place those projects under an AOSP-style root and run:

```sh
python3 -I tools/verify_source_series.py --aosp-root /path/to/aosp
```

The verifier checks original hashes, applies both patches in a temporary copy of the six touched files, then checks the intermediate/final hashes and the published snapshot. It leaves the supplied source tree unchanged. After this succeeds, the patch files can be applied with `git apply` from the AOSP-style root.

The source receipt binds these upstream revisions to the runtime source lock. It did not establish source equivalence to the original system APK before the local replacement builds.

## Host regression

With a Java 8-compatible compiler/runtime (the recorded run uses the pinned JDK 21 inputs):

```sh
python3 -I tests/run_host_regression.py --javac /path/to/javac --java /path/to/java
```

The test compiles the complete manager source against isolated host bindings, exercises 15 cases, and repeats against the predecessor. The candidate must pass all 15 cases; the predecessor must fail when an enumerated device disappears. Cases include replacement selection, missing metadata, checked service failure, preservation of unrelated runtime failures, external-camera fallback and callback detachment. The bindings under `tests/bindings/` are test fixtures only. They must never be copied into an Android build.

Recorded and publication-time results live in `evidence/`. The publication run passed both patch stages, all 15 candidate cases and the expected negative control. Its unsigned rebuild reproduced the recorded manager class and complete program JAR from all 60 locked inputs. These Java tests do not emulate a real camera provider or establish preview, photo output or Android lifecycle correctness. The six-file prerequisite has exact patch/hash verification; the host suite specifically exercises the manager hotplug logic, not every teardown path.

## Conditional unsigned rebuild

[dependencies.lock.json](dependencies.lock.json) records 60 exact external inputs and the original compiler/D8/alignment command shapes. Supply a local JSON object mapping every input key to its existing file path. Keep that local path map outside source control. Verify inputs first:

```sh
python3 -I tools/build_hotplug_release_07.py --inputs-json /path/to/inputs.json --verify-inputs-only
python3 -I tools/build_hotplug_release_07.py --inputs-json /path/to/inputs.json --out /path/to/new-output-directory
```

The script compiles the single reviewed manager against genuine SDK inputs, verifies its byte-for-byte class hash, replaces exactly that class in the pinned complete program JAR, runs D8, checks the unchanged 9,682-class descriptor set, preserves all 1,045 non-dex payload entries byte-for-byte and verifies 16 KiB ZIP alignment. It creates an **unsigned** aligned APK. The original signed release07 artifact is identified only by its hash in [the recorded build summary](evidence/recorded-release07-build.json).

This is a rebuild of one increment on exact external baseline artifacts. It is **not a complete clean-checkout Camera2 build**. Missing inputs include the baseline Camera2 class/program JARs, the release06 payload APK, AndroidX/Kotlin/Guava/other dependency artifacts, the genuine SDK/compiler tools, and the complete toolchain/shared-library distribution. The original 641-source compile inventory is identified by hash, but its complete source-generation/resource/manifest recipes are not reproduced here. Executable hashes do not pin every file in a JDK distribution. The input lock enumerates these limits and rejects substituted artifact bytes.

The portable unsigned script is adapted from the recorded release07 script whose original hash is retained in `source-lock.json`. Signing and installation are separate release operations. This source delivery contains no APK/JAR payloads, signing keys, private account data, raw device UI dumps or raw Android crash captures.

## Current device result

Release07 was installed with its exact APK hash and application data preserved. The first missing-provider flow reached a handled error without a new uncaught exception. Later real sessions succeeded on the prior Main/R14 epoch: the first collected 130 physical/129 producer frames; the separate reopen collected 197/196 frames and closed normally with its capture process reaped. Negotiated format was MJPG 640×480 with 1/30 interval. Measured rates were approximately 16.8 and 16.5 fps, not measured 30 fps.

The parent directly inspected the second reopen's private PNG at 08:26:30.810 UTC and confirmed a real physical scene in the Camera UI, with Options and shutter visible. The metadata observer's original `preview_ui_verified_by_this_agent=false` remains unchanged; the parent confirmation is a separate hash-bound receipt. Only public metadata and image hashes are distributed. No photo was taken, and photo output/persistence remains unqualified. These results do not automatically transfer to the later presenter/R16 Main epoch. Earlier provider failures and the parser-rejected non-launch remain historical failures.

See `evidence/camera-preview-parent-observe-01/`, `evidence/camera-reopen-parent-observe-02/` and `evidence/parent-visual-preview-confirmation.json`.

## Licensing

AOSP source headers are preserved. [LICENSE](LICENSE) contains the Apache License 2.0 text. Original upstream code remains attributed to the Android Open Source Project; the patches and local verification scripts are provided under the same license. Synthetic host bindings are isolated under the test directory.
