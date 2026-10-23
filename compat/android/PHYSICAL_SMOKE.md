# A08 physical Android application smoke

This profile checks the original `org.trillionnium.a08smoke` Java/DEX application
on an explicitly selected existing Android device. The device may run a custom
Android product. Its Linux kernel, vendor BSP, firmware, ART and framework are
the existing device's software. A pass qualifies only the measured application
install, UI, SharedPreferences commit and app process restart on that exact
fingerprint. It does not qualify Android on Asterinas, a new ARM BSP, JNI on ARM,
Hepta production ownership, mobile organ control or general APK compatibility.
Those three qualification flags remain false in every generated report.

The original x86_64 Cuttlefish reference profile, source/image/VINTF gates,
Soong builder and APK runners are unchanged. Do not supply physical device
facts to a fabricated Cuttlefish preflight report. The original JNI fixture
intentionally rejects compilation outside x86_64; it is not used here.

## Development and reproducible source boundary

`support/android/build_physical_smoke_apk.py` reads seven immutable Git blobs
from an explicit full commit SHA. Their sorted name-to-SHA256 inventory must
hash to `d5a8498ef5e36c9817d52fecb11b1b2aff36d29731b6aedce27831bdf0a59619`.
This binds the original Java, manifest, resources and original build recipes;
dirty or untracked checkout contents are not build inputs. Changing this fixture
requires reviewing the source contract and updating the pin deliberately.

The builder uses an already installed Android SDK platform 35, build tools
35.0.1 and a JDK. It runs AAPT2, javac targeting Java 8, D8 with min API 28,
zipalign, keytool and apksigner. It does not download tools, use Gradle or claim
the pinned AOSP/Soong build was executed. The app keeps minSdk 28/targetSdk 35,
version 1/1.0, no declared permissions, no network use and no native library.
DEX is architecture independent; device execution remains a separate result.

    python3 support/android/build_physical_smoke_apk.py \
      --source-commit FULL_REVIEWED_SOURCE_SHA \
      --sdk-root /absolute/installed/android-sdk --out /new/build-directory

The output must be a new directory. It contains the immutable source snapshot,
generated resources/classes/DEX, signed APK, build.json, exact tool paths and
hashes (including wrapper JARs), command arguments, return codes and raw output
hashes. The local test certificate is generated per build, so APK/certificate
digests are newly measured, not promised deterministic across builds. The
task-local test key has a public fixture password and is never a production
signing identity. Do not redistribute it as a release key.

## Technical execution contract

`support/android/run_physical_smoke.py` defaults to host validation only. It
requires separately supplied expected build-manifest, source, APK, signer and
ADB executable SHA256 values, an existing `tcp:127.0.0.1:PORT` endpoint, exact
USB serial, full Android build fingerprint and numeric target user. It verifies
the source blobs and compiled manifest/DEX/signature before producing a private
hash-checked install copy. Host-only mode never constructs an ADB connection.

Only `--execute` permits the device workflow. An existing-server smart-socket
handshake and client/server protocol comparison precede commands. Every ADB
command uses the explicit host, port and serial; there is no server start/kill,
connect, disconnect, global logcat clear, reboot or unlock operation.

Before the first write the runner requires the exact serial/fingerprint,
completed boot, SDK >= 28, current target user and positively confirmed unlocked
keyguard state. It enumerates Android users and checks the exact package with
`-u` for each, including retained data. A package present anywhere or an unreadable
user inventory fails before install. The new install uses no replace, downgrade,
grant-all or clear-data option. There is no `pm clear` path. A second invocation
must refuse a preexisting test installation rather than adopt its authority.

Every input action checks current user, installed APK SHA/UID, resumed original
MainActivity, owned input focus and lock state. Focus comes from the per-display
`dumpsys window displays` state; the Android 17 individual-windows subsection
omits `mCurrentFocus` and cannot prove input ownership. Missing or ambiguous
focus still rejects the action. It uses a fresh unique UI dump
path, matches the original resource IDs and validates owned enabled nodes and
screen bounds. Coordinates are computed from that current hierarchy. The input
must become focused before the fixed text `A08Persist42` is entered. Only the
original SAVE button commits SharedPreferences. No other app UI is targeted.

The workload observes `SAVED:EMPTY`, types and saves, observes the new value,
force-stops only this package, proves its process is absent, relaunches the
original Activity and observes persistence in a fresh hierarchy. Actual PIDs,
new installation UID and UTC step/command timestamps are retained. No log marker
is accepted as success, and no global logcat is read or cleared. “Restart” here
means application process restart, not device reboot or Android Direct Boot.

The finally path rechecks the same APK bytes and UID before stopping and
uninstalling only this new package for the explicit user. A concurrent package
replacement, user switch or ambiguous install identity refuses cleanup and
leaves a failed report for manual review. After removal the all-user absence
gate runs again; retained package state is a cleanup failure, not a pass.
Unique temporary hierarchy files are removed separately. Commands, raw outputs,
failure phase information and cleanup errors are preserved in a new evidence
directory. Reports never overwrite an earlier attempt.

ADB/UI observations cannot provide atomic exclusion against an unrelated
concurrent operator. Run with one authorized device operator, as the local
POCKET4 session does. A focus/package change detected between checks fails;
the runner is a bounded test harness, not a new production authorization owner.

    python3 support/android/run_physical_smoke.py \
      --build-manifest /absolute/build/build.json --apk /absolute/build/A08Smoke.apk \
      --expected-manifest-sha256 MEASURED_MANIFEST_SHA256 \
      --expected-source-sha256 d5a8498ef5e36c9817d52fecb11b1b2aff36d29731b6aedce27831bdf0a59619 \
      --expected-apk-sha256 MEASURED_APK_SHA256 \
      --expected-certificate-sha256 MEASURED_SIGNER_SHA256 \
      --adb /absolute/existing/adb --expected-adb-sha256 MEASURED_ADB_SHA256 \
      --adb-endpoint tcp:127.0.0.1:EXISTING_PORT --serial EXACT_USB_SERIAL \
      --expected-fingerprint EXACT_BUILD_FINGERPRINT --user EXACT_CURRENT_USER \
      --out /new/evidence-directory

Review that host-only report, then use a new evidence directory and explicitly
append `--execute` for the authorized device run. The same expected identities
must be used. A passing local build or offline fake transport test is not a
device execution result.

## Verification

`test_physical_smoke.py` exercises the lifecycle using an explicit fake transport
and tests wrong device/user, locked device, preexisting package/retained data,
foreign focus, concurrent APK replacement, stale UI output, out-of-bounds and
foreign nodes, default no-ADB behavior, manifest tampering and incompatible ADB
protocol rejection. It is included in the existing complete host test discovery
and source inventory. These tests never contact the physical device.

    python3 support/android/verify_source_integrity.py
    python3 support/android/verify_host.py --out /new/host-gates.json
    python3 -O -m unittest discover -s tests/workloads/android -p 'test_*.py' -v
