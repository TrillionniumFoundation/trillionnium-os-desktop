# Camera2 checked-disconnect enumeration repair

This increment repairs a concrete source-level camera-selection defect. A camera
that disappears between ID enumeration and its metadata query can report
`CameraAccessException(CAMERA_DISCONNECTED)`. Release07 handles the unchecked
`IllegalArgumentException` form inside the loop, but catches the checked form
outside the whole loop. Consequently, it stops before querying a later connected
camera with the requested facing.

The candidate catches the checked exception at the individual-device query. It
continues only for `CAMERA_DISCONNECTED`; all other reasons rethrow the original
exception to the existing outer handler. It does not retry the failed ID, open a
camera, change permissions, or extend the existing back/front and external-facing
fallback passes. Direct selected-device queries still return the existing checked
`OneCameraAccessException` with its original cause.

This is not a diagnosis of the earlier physical UVC Gain/USB-disconnect event.
The source repair and its host controls do not establish a successful physical
camera session, photo capture, persistence, Android lifecycle, or App release.

## Exact source increment

The parent delivery is commit
`9b8f4fb09e6c9d12f23f83ccd7a0071b699a7f54` in
`TrillionniumFoundation/trillionnium-os-desktop`, camera subtree
`70ceb2c379ec9650bd63f5f4a946a6037d064ec6`.

| Item | SHA-256 |
| --- | --- |
| Release07 manager preimage | `2b112a02eadd4c2db0a642c3263207cfc55ad9930e1a4399c06c219c480e2bca` |
| Candidate complete manager | `0f35f1675d8977aed5b80141b380bd29bf995c8c48db73d688eff46b879c39ad` |
| Third patch | `0b0fd6dea573a0978cbd605422193315cacb63e43becf5758b102ee5edf90f53` |

All 40 original camera-delivery files remain byte-identical. In particular,
release07's build scripts, dependency/class hashes, source lock and historical
device receipts remain their original records. The new manager, patch, fixtures,
test runner and source lock are contained in this separate increment.

The six release07 source preimages were verified against the original lock. Five
were read from the existing release06 source tree and matched release07's locked
final bytes; the sixth was the exact published release07 manager. Reversing the
two old patches reproduced all six locked upstream hashes. The original patch
verifier then reapplied both stages successfully. Applying the third patch changes
only the manager, and reversing it restores all six preimages exactly.

The complete candidate manager is under `source/`. To update an exact release07
source tree, first verify the six hashes in the parent lock and apply
`patches/0003-checked-camera-disconnect.patch`. To rebuild from the pinned upstream
sources, apply the parent's two patches before this third patch. Neither method
reuses release07's expected class hash as an expected result for the new code.

## Actual host validation

The original release07 runner was executed unchanged: its 15 manager cases passed,
and its old zero-device predecessor produced the required original failure.

The new differential runner compiled the complete old and new manager against the
same test-only bindings. The original `HotplugRegression.java` remained unchanged.

| Suite | Release07 preimage | Candidate |
| --- | --- | --- |
| Original 15 cases | 15 passed | 15 passed |
| Back camera after checked disconnect | Expected failure | Passed |
| Front camera after checked disconnect | Expected failure | Passed |
| External fallback after checked disconnect | Expected failure | Passed |
| Remaining eight checked-error controls | 8 passed | 8 passed |

The additional controls cover bounded all-disconnected enumeration, camera-list
service failure, policy-disabled/error/in-use/resource-limit reasons, exact cause
preservation in direct selected-device lookup, and an unmodified security failure.
The complete expected case order and process exit are checked for both arms. Input
hashes are rechecked after execution; compiled outputs are private host fixtures.

The recorded local toolchain is OpenJDK 17.0.20 with its installed `jdk.compiler`
module, Java 8 source/target mode, two active CPUs and a 256 MiB Java heap cap.
This environment lacks the standalone `javac` launcher. The module invocation is
recorded explicitly; the separately replayed original runner uses an exact local
launcher wrapper. These are new host results, not a replay of the historical JDK21
Android build. Compile warnings about the Java 8 bootstrap class path are retained.

To reproduce the differential from the camera-delivery directory:

```sh
python3 -I checked-disconnect/tests/run_regression.py \
  --java /path/to/java --javac /path/to/javac --out /path/to/new-results
```

When no `javac` launcher is available, omit `--javac`; the runner requires the
selected Java runtime's `jdk.compiler` module. It creates the output directory
exclusively and retains compile and test stdout/stderr for both arms. Every original
camera-delivery hash and each locked repair source must match before it compiles.

## Actual Pocket4 release08 build

The new source has now been compiled with Pocket4's genuine JDK21 and Android SDK.
The first compile derives the new class and complete program hashes. A separate
normal build compiles the source again and reproduces both hashes before D8 and
APK packaging. This proves repeatability of the class/program pair; it is not a
claim that the final APK was rebuilt twice or that the complete original Camera2
application can be reconstructed from a clean checkout.

| Artifact or check | Actual result |
| --- | --- |
| New manager class SHA-256 | `460b0ae8b949370e3a86ec2bae98cbb11900ecbe95732212958e1980b84bbe31` |
| New complete program SHA-256 | `c18e5862c53cb3d7f7cf13c8def3ec99f11de00d37936497bd43972733612ae8` |
| Signed release08 APK SHA-256 | `0218041bc46f49c0c9622196e2a3610c641e0cc8f12386f23cdd88dc3a3ce18e` |
| Signed APK size | 11,892,407 bytes |
| Real external inputs | 60 verified before and after build |
| Program delta from current release07 | Exactly the manager class |
| Dex descriptors | All 9,682 preserved; no host test bindings |
| Non-dex payload | All 1,045 entries byte-identical to current release07 |
| Signing identity | Existing certificate `a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc` |
| Signature and packaging | v3 signature, payload preservation and 16 KiB alignment verified |

The isolated normal build used CPU 20/21, a 2 GiB memory ceiling and no swap.
It finished in 30.36 seconds; systemd reported approximately 1 GiB peak memory
and zero swap. Main's observed pre/post status and init identity were identical.
The separate signing job finished in 1.43 seconds with approximately 102 MiB
peak memory and zero swap. These observations do not claim absence of every
transient effect on other workloads.

[The new input lock](dependencies.lock.json) retains 58 original input hashes
and replaces only the original program/APK with the exact current release07
artifacts. The normal builder is `tools/build_release08_unsigned_v2.py`; it
accepts the same external `--inputs-json` map and requires a fresh `--out`
directory. It also verifies that the lock, source and all 60 inputs remain
unchanged at completion. Signing remains a separate local step with the existing
identity. No key, APK, JAR or private device image is distributed here.

Exact completed coordinator and signing receipts are under `evidence/`.

## Actual update and current Camera failure

Release08 was installed once through the existing native daemon. The completed
coordinator job `1a1aa38d396-fc05-3f61` returned exit 0 and `INSTALLED_VERIFIED`.
The actual installed APK reads back as `0218041bc46f49c0c9622196e2a3610c641e0cc8f12386f23cdd88dc3a3ce18e`.
UID 10062, first-install time, runtime permissions and both CE/DE directory
identities remained equal. The exact previously installed release07 APK was
retained before dispatch. These are data identity checks, not a byte-level backup
of every application database. Main remained on the same R16 framework epoch.
See [installation evidence](evidence/camera-installed-verified.json).

The first current-epoch acceptance trial failed at 05:42:53 UTC on 2026-11-05.
Direct visual review and the scoped native UI tree show **Camera error — Can't
connect to the camera.** There was no ready shutter and no photo was taken. The
trial created one Camera task and normally removed exactly that owned task; no
unknown action remains. Its original failure is retained in
[acceptance evidence](evidence/camera-accept01-unready-shutter.json). The source
enumeration fix and successful update do not resolve or qualify this observed
connection failure. CameraService/provider diagnosis is continuing.

The reviewed [device transaction and acceptance sources](device/README.md)
preserve the exact epoch, scoped task ownership, one-shot installation and shutter
semantics, and separate unknown outcomes from success. Current-epoch physical
preview, photo persistence, normal reopen and provider-disconnect recovery remain
unqualified. Historical R14 preview evidence does not qualify those gates.

## API references

The checked-disconnect behavior is documented by Android's
[CameraManager API](https://developer.android.com/reference/android/hardware/camera2/CameraManager#getCameraCharacteristics(java.lang.String))
and the
[Android 17 CameraManager source](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android17-release/core/java/android/hardware/camera2/CameraManager.java).
The
[CameraAccessException API](https://developer.android.com/reference/android/hardware/camera2/CameraAccessException)
defines the distinct failure reasons and `getReason()`. The implementation also uses
`CAMERA_DISCONNECTED` when the camera service itself is unavailable, so this repair
does not infer a physical unplug from that reason alone.
