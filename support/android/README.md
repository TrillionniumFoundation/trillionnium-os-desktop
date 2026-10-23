# A08 build and APK evidence

This is support/android/README.md. The repository ROOT README.md stays 0 bytes.

## Android device organ adapter

The separate [Digitalis/Droidloom device adapter](DEVICE_ORGAN.md) provides
bounded, pinned host observation of the existing `pocket4` Android 17 / SDK 37
cell, plus pure construction of exact semantic intents. Its CLI permits only
`qualify` and `observe`; effect dispatch and original production owner integration
remain `NOT_CONFIGURED`. It uses the original operator-selected host and helper,
keeps ADB disabled, and never treats a timeout as permission to replay.
The development contract, source pins, tests, and required receiver/owner work
are documented together. These capabilities are separate from the Android 15
AOSP/Cuttlefish and Android-on-Asterinas qualification below.

## Current checkpoint — 2026-10-17 commit-bound source audit

`generate_kernel_source_audit.py` now resolves `--project-ref` once and reads
the selected commit's immutable Git blobs for both content hashes and source
candidate scans. Dirty, untracked, or differently checked-out files cannot be
attributed to that commit. Reports contain the actual UTC observation time,
resolved commit/tree, per-input Git blob/SHA256/mode, and a digest of the entire
scanned Rust blob inventory. Schema 3 distinguishes the expected upstream pin
from the actual `support/upstream-lock.json` read from that same commit; the
lock blob is hashed, and missing, malformed or mismatched metadata adds a
`pinned_lock` blocker. A metadata match does not establish that imported kernel
files are identical to upstream. The previous tool read the worktree while labeling
it with the requested ref and hard-coded its observation date.

Eight regression additions cover commit/working-tree separation, observation
time and upstream-lock validation. The first five fail on the original tool;
the additional lock cases reject its successor's unverified fixed-pin claim.
The current complete suite is **184/184 in normal and optimized Python**, with
no skips. The complete host runner returned **host_passed_only**
and actually compiled/loaded the JNI library and Java harness using the same
isolated OpenJDK tools documented below. Binder device open remains
**BLOCKED / exit 77**. Exact tested source, commands, baseline failures and raw
output are in `tests/workloads/android/evidence/2026-10-17-commit-bound-audit/`.

The newly recorded main snapshot is fixed at
`18d9fca65381f0e84f130c76fa289d5186894d85`, tree
`d779baa329f7cc04fb2c2cdeb7822356d34af899`. Its 757 committed core Rust files
still contain no Binder, seccomp-install, or Android MAC candidate; the source
gate returns **exit 2**. This is a separate immutable-main source scan, while
the host regression runs the A08 branch recorded in its receipt. Neither
result qualifies a kernel build, Android boot or APK execution. GitHub Actions
execution remains a separately reported result; queued jobs are not passes.

## Source recovery checkpoint — 2026-10-17

This repair is based on A08 PR #7 commit
`41a8c32b435f2fa9dd750ded40bd4b37cb7606c6`. That checkout omitted 39 files,
contained three invalid UTF-8 source blobs, changed a historical test log,
and lost two shell executable modes. The complete 105-file A08 snapshot was
recovered from `37466a93823b9b10ace81759ec6decb59bb5a140` and verified against
every original Git blob and mode before further edits. The 62 shared file
contents were unchanged; there were no newer A08-only files to discard.
The restored historical suite ran **166/166**. Ten new source-integrity
regressions brought that recovery suite to **176/176 in both normal and optimized
Python**, with no skipped tests. Provenance, commands and raw output are in
`tests/workloads/android/evidence/2026-10-17-source-integrity/`.

`verify_source_integrity.py` maintains an explicit source/test inventory so
omitted tests cannot silently reduce discovery. It checks required files,
UTF-8, Python/JSON/XML syntax, shell syntax one script at a time, and shell
entry-point modes. `verify_host.py` runs this check before host regressions.
The initial complete host gate returned **host_failed_or_blocked** because
the host lacked Java/JNI development tools. A subsequent single rerun using
isolated official `javac`/JNI headers with the host's existing OpenJDK 17.0.20
runtime/compiler modules returned **host_passed_only / exit 0**. The actual
JNI library and Java harness compiled, and host JNI loading produced
`HOST_JNI_INTEGRATION_PASS`; this was not a newly installed full JDK.
Linux ABI, Binder UAPI layout and child-only seccomp probes passed. Opening
Binder remained **BLOCKED / exit 77** because there is no Binder device.
The Asterinas source scan still reports Binder, seccomp and MAC blockers.
Both initial and subsequent reports are retained in the evidence directory;
the JDK source, digest and composition are in `jdk-installation.json`.
Historical 2026-10-16 receipts remain historical.

The A00-coordinated `.github/workflows/a08-host.yml` runs the source guard
before discovery, installs actual JDK 17/JNI build inputs, and executes this
complete host gate plus the optimized Python suite on relevant PR changes.
It preserves raw reports even on failure. The workflow YAML and its shell
steps were parsed locally; execution on its GitHub runner must be reported
separately. A green host job still does not qualify Android guest execution.

The Android15 Cuttlefish source lock is preserved. The generic APK runner
requires an explicit disposable serial and
checks the pinned Cuttlefish device, x86_64 ABI, build ID and 4 KiB page size
before any install. Strict APK CLIs also require a hash-bound
`cuttlefish-launch-preflight.json` bundle with all five source/image/VINTF audit
files. An unverified AOSP checkout is refused before Soong. These checks are
host/reference gates; no Android build, guest boot, or Android on the Rust
kernel has been executed here. AOSP
repo sync, image build, Cuttlefish boot, Android APK execution and Android on
the Rust kernel have **NOT** been executed. Product validity and toolchain
are subject to actual reproducible build verification.

## AOSP reference product

- Tag: android-15.0.0_r36 (build BP1A.250505.005.D1).
- Repo manifest URL: https://android.googlesource.com/platform/manifest
- Manifest repository commit: a0601d2912a6cedcaf97e1372173f8704a2715b0.
- default.xml SHA256: 58aee921fa2aa15b97c3de8e1a06fa582da798973803a3da4c8af596a984719b.
- Product: aosp_cf_x86_64_phone-trunk_staging-userdebug (not a GSI alone).
- Architecture/page: x86_64, 4 KiB; software graphics candidate:
  guest_swiftshader; Cuttlefish reference guest kernel: **Linux**.
- Build tools: AOSP Soong and manifest-pinned prebuilts/Clang; exact binary
  hashes/compiler versions only obtainable after full source sync. PENDING.
- Images: system.img and vendor.img. SHA256 PENDING.
- VINTF vendor device manifest/framework matrix, AIDL HAL versions and
  instances: inventory derived from built partitions only. PENDING.
- Bionic, init, ART, Zygote and system_server binaries: paths audited after
  build, but file presence **does not equal service running**.

The immutable tag plus verified checked project commits are in aosp-lock.json.
Full repo manifest -r, partition hashes, compiler fingerprints and VINTF
inventory remain unset intentionally until measured.

## Reproduction commands

On a dedicated, empty disposable AOSP build workstation with the Android repo
launcher and all AOSP build prerequisites:

    export AOSP_ROOT=/scratch/a08-aosp-r36
    export A08_EVIDENCE=/scratch/a08-evidence
    bash support/android/prepare_aosp.sh init
    bash support/android/prepare_aosp.sh audit
    bash support/android/prepare_aosp.sh build
    bash support/android/build_smoke_apk.sh
On the same dedicated KVM-capable build host after source/image audit and APK
build, start only a NEW disposable guest with its own empty HOME:

    export A08_CVD_HOME=/scratch/a08-cvd-fresh-instance
    export A08_CVD_INSTANCE_ID=42  # reserve an unused slot on this isolated host
    bash support/android/run_reference_cuttlefish.sh

The APK/boot identity gates additionally check Android build ID
BP1A.250505.005.D1 and release 15 (not just SDK/product name).
The launcher checks audited manifest/source/system+vendor image hashes, KVM and
same-source host tooling, refusing existing CVD HOME. Exit 0 proves ONLY
launcher return, NOT guest boot. Collect actual boot_gates.py evidence using
an explicit isolated Cuttlefish ADB serial.


The first command refuses to overwrite an existing checkout and validates the
manifest commit and default.xml blob, then exports the fully resolved manifest and
hashes required Bionic/init/Binder/ART/Zygote/system_server/LMKD/SurfaceFlinger
source files. Missing required source/lock identity fails before any build.
The second records logs plus sys/vendor image inventory, VINTF and HAL data;
missing components produce failure, never success. The third uses only an
ephemeral Soong module copied to external/a08smoke in this disposable checkout.

Cuttlefish Linux reference guest must be booted **separately** with its actual
same-build host package and images; verify software renderer, 4096-byte page,
Linux kernel build ID, system/vendor hashes, complete launch/serial/logcat
before using ADB. Example once its serial is known:

    python3 tests/workloads/android/run_apk.py \
      --apk /scratch/a08-aosp-r36/out/path/to/A08Smoke.apk \
      --serial ACTUAL_DISPOSABLE_CUTTLEFISH_SERIAL \
      --preflight-evidence /scratch/a08-evidence/cuttlefish-launch-preflight.json \
      --out /scratch/a08-evidence/apk-smoke

Before the APK test, collect actual init, Binder, Zygote, system_server,
ART APEX, PackageManager, SurfaceFlinger and LMKD gates on the same
**Linux reference** guest (this uses real Binder service-manager IPC):

    python3 tests/workloads/android/boot_gates.py \
      --serial ACTUAL_DISPOSABLE_CUTTLEFISH_SERIAL \
      --out /scratch/a08-evidence/framework-boot

The APK runner enforces Android 15 SDK 35, precise Cuttlefish product/device,
Linux guest identity, x86_64/4KiB and optional --expected-sha256. It checks
PackageManager install, clears prior test-only app data and verifies the
initial EMPTY state before input. It installs unchanged
A08Smoke.apk (first-party, version 1.0, DEX-only, no network/permissions),
starts its Activity, types, saves SharedPreferences, backgrounds, foregrounds,
force-stops, restarts and reads the saved value. result.json and logcat capture
actual outcome. Never point ADB at a real phone.

To re-run only executable Linux host tests:

    python3 support/android/verify_source_integrity.py
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/workloads/android -p 'test_*.py' -v
    PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s tests/workloads/android -p 'test_*.py' -v
    PYTHONDONTWRITEBYTECODE=1 python3 support/android/verify_host.py --out /tmp/a08-host-gates.json
    cc -std=c11 -O2 -Wall -Wextra -Werror -pthread \
      tests/workloads/android/kernel_abi_probe.c -o /tmp/a08-abi-probe
    /tmp/a08-abi-probe
    cc -std=c11 -O2 -Wall -Wextra -Werror \
      tests/workloads/android/binder_abi_probe.c -o /tmp/a08-binder-probe
    /tmp/a08-binder-probe  # 77 means BLOCKED, not PASS
    cc -std=c11 -O2 -Wall -Wextra -Werror \
      tests/workloads/android/seccomp_abi_probe.c -o /tmp/a08-seccomp-probe
    /tmp/a08-seccomp-probe  # child-only sandbox; Linux host comparison, not Asterinas

Host evidence is under tests/workloads/android/evidence; it is **Linux**
evidence and not Android, QEMU, Asterinas or CTS evidence.

## Status / failure handling

Source lock: selected, resolved full manifest PENDING. Build: NOT RUN.
Cuttlefish reference boot: NOT RUN. Rust-kernel Android: NOT RUN.
APK: first-party source and automated scenario exist, APK build and execution
NOT RUN. Native ABI x86_64/ARM64/32-bit: NOT RUN; no translator assumed.
Current host Python suite: 184/184 passed in normal and optimized Python,
with no skips. The broader host gate passed with the documented isolated
Java/JNI tool configuration; its earlier missing-tools failure is retained.
Linux ABI probe: mmap, memfd,
SCM_RIGHTS, futex, signals PASS; Binder device missing ENOENT. This means only
the Linux host probe has passed. Binder protocol probe exits 77 with ENOENT; no
Binder transaction has run. Real framework boot and APK tests remain NOT
EXECUTED. The current rerun receipt is
tests/workloads/android/evidence/2026-10-17-commit-bound-audit/.

For actual failures preserve first stderr/errno, initiator, target kernel,
AOSP version, full SHA/manifest, host toolchain, raw serial/logcat, timing,
and stage: source_lock, build, image_inventory, init, binder, zygote, ART,
system_server, PackageManager, graphics/input, apk_install, apk_launch,
apk_input, apk_storage, seccomp/MAC, LMKD/freezer, unsupported_cpu_abi,
encryption/Keystore or external_service. Do not hide missing features with
dummy success returns; escalate minimized failures per compat/android/
INTERFACES.md ownership table.

Nothing here certifies Android CDD/CTS/VTS, Play Integrity, GPU acceleration,
hardware attestation, or a new native Rust kernel.

## A08 second APK: x86_64 JNI / ART / Bionic test workload

The selected Soong fixture now builds two distinct APKs:

- A08Smoke (org.trillionnium.a08smoke) is DEX-only.
- A08NativeSmoke (org.trillionnium.a08native) embeds a genuine x86_64 ELF64 JNI liba08jni.so. The Activity displays JNI:x86_64:PID_MATCH only after nativeIsa and nativePid match the Java process, and also supports UI input, persistent SharedPreferences, background, foreground and force-stop/relaunch.

Both APKs are built via support/android/build_smoke_apk.sh. The script invokes Soong for both modules, checks actual AAPT2 package/version, validates ABI and emits smoke-dex-apk-path.txt, smoke-native-apk-path.txt and smoke-apk-artifacts.json, with hashes. The AOSP image and both APKs have NOT been built on this host.

After full source build and REAL Linux Cuttlefish guest verification, execute:

    python3 tests/workloads/android/boot_gates.py --serial ACTUAL_DISPOSABLE_CVD_SERIAL --out "$A08_EVIDENCE/framework"
    python3 tests/workloads/android/run_apk.py --serial ACTUAL_DISPOSABLE_CVD_SERIAL --apk "$(cat "$A08_EVIDENCE/smoke-dex-apk-path.txt")" --preflight-evidence "$A08_EVIDENCE/cuttlefish-launch-preflight.json" --out "$A08_EVIDENCE/dex-only"
    python3 tests/workloads/android/run_native_apk.py --serial ACTUAL_DISPOSABLE_CVD_SERIAL --apk "$(cat "$A08_EVIDENCE/smoke-native-apk-path.txt")" --preflight-evidence "$A08_EVIDENCE/cuttlefish-launch-preflight.json" --out "$A08_EVIDENCE/x86_64-jni"

Linux HOST-ONLY reproduction:

    python3 support/android/verify_host.py --out /tmp/a08-host-verification.json

An earlier host wave passed 34 offline Python tests, C syscall probes and an
isolated Linux seccomp filter; Java loaded a real x86_64 shared library compiled
from the same A08 JNI C source and reported HOST_JNI_INTEGRATION_PASS. That
receipt is historical. A subsequent 166-test historical host run was blocked
by missing Java/JNI development tools. The current 184-test full host pass is
recorded at the checkpoint above; missing /dev/binder is still explicitly
binder_blocked_no_device (exit 77), not a Binder success. Evidence for the
earlier JNI wave is tests/workloads/android/evidence/host-jni-gate.json.

ADB TCP transport selectors (for example localhost:6520) can differ from the guest-reported serial number. The runner now requires online selected transport, records both identities and continues enforcing Cuttlefish product, build ID, ABI, 4KiB page and Linux reference kernel BEFORE installing any APK. The strict CLIs also require the same `cuttlefish-launch-preflight.json` bundle produced immediately before launch; they rehash all five audit files and refuse stale, missing or claimed-boot evidence. `preflight_only` remains a source/image integrity result, not a guest boot result.

Android ART/PackageManager runtime execution, complete AOSP build, Cuttlefish boot, Asterinas compatibility, ARM64 translation, 32-bit native ABI and Play Integrity/DRM remain NOT TESTED. No physical device firmware was modified.


## Current Asterinas source snapshot

Select the exact project commit to audit. The generator reads that commit's
Git objects even when the A08 tools are checked out on a different branch;
it does not inspect local working-tree edits. Generate the bound snapshot with:

    python3 support/android/generate_kernel_source_audit.py \
      --repo-root . \
      --project-ref origin/main \
      --output compat/android/source-audit-main-$(git rev-parse --short origin/main).json

The referenced commit must already exist locally; `origin/main` is the locally
available ref, not a network freshness guarantee. The command returns exit 2
while Binder, seccomp, or Android MAC evidence is
missing. That is intentional. The JSON records the exact project commit/tree,
Git blob and SHA256 for each inspected kernel file, and keeps runtime Android
and Android-on-Asterinas false. `kernel_contract.py` remains the fail-closed
live scanner; neither tool modifies kernel sources.

The checked-in `source-audit-main-18d9fca6.json` records the fixed main checkpoint
`18d9fca65381f0e84f130c76fa289d5186894d85` using immutable Git objects.
`source-audit-main-acd9ee30.json` and earlier files
`source-audit-main-e1b9d705.json`, `source-audit-main-bc294f75.json`,
`source-audit-main-5aeff7b6.json`,
`source-audit-main-0709ab5d.json`,
`source-audit-main-3b2d15bc.json` and `source-audit-main-e44c92ac.json` remain
historical A08 wave records. They predate the commit-binding repair and are not
substitutes for a fresh snapshot from the corrected tool.

## Fourth wave: Asterinas kernel ABI source gate and artifact-qualified APK runner

The historical A08 source audit recorded the imported Asterinas tree at
`e44c92ac885eb003665ff2e1e5c6fab1f104b2d6`; the immutable-main snapshot above
supersedes it for the recorded main checkpoint. Both audits agree that futex/mmap/
memfd/sendmsg/recvmsg entrypoints exist, while an Android Binder driver,
seccomp installation syscall/prctl, and Android MAC policy enforcement remain
unverified or missing. **No Android guest was booted or qualified.**

For a workspace that contains both A08 tooling and A01's imported kernel, run the fail-closed scanner:

    python3 support/android/kernel_contract.py --kernel-root kernel/asterinas --lock support/upstream-lock.json --out /tmp/a08-kernel-contract.json

Exit 2 means known Binder/seccomp/MAC gaps, exit 3 invalid lock/missing kernel sources. Exit 0 would mean *source candidates found only*, never Android runtime success. This scanner does not modify the kernel.

The AOSP pin now also records bionic commit 8d67ca893c1523eb926b9080dbe4e2ffd2a27ba1 and frameworks/native commit cdca1e2000347ce2f2b25ab5d0f2dffa81f30e01. Full resolved repo manifest, build tool binary hashes and partition image hashes remain unmeasured until sync/build.

With a fully built and audited AOSP Cuttlefish product and both APKs, verify source-built artifact SHA256, paths in the same AOSP out/, real APK ZIP/DEX, x86_64 ELF header and actual aapt2 package/version:

    python3 support/android/run_verified_apks.py --aosp-root "$AOSP_ROOT" --manifest "$A08_EVIDENCE/smoke-apk-artifacts.json" --aapt2 "$AOSP_ROOT/out/host/linux-x86/bin/aapt2" --out "$A08_EVIDENCE/apk-audit" --check-only

Only when an isolated Linux Cuttlefish reference guest has *actually* booted, remove --check-only, provide --serial ACTUAL_CUTTLEFISH_ADB_SERIAL and pass the same preflight bundle:

    python3 support/android/run_verified_apks.py --aosp-root "$AOSP_ROOT" --manifest "$A08_EVIDENCE/smoke-apk-artifacts.json" --aapt2 "$AOSP_ROOT/out/host/linux-x86/bin/aapt2" --out "$A08_EVIDENCE/apk-audit" --serial ACTUAL_CUTTLEFISH_ADB_SERIAL --preflight-evidence "$A08_EVIDENCE/cuttlefish-launch-preflight.json"

The runner stops on any first failing framework/DEX/JNI step and preserves classified JSON/logs. Even full Linux Cuttlefish reference acceptance is **NOT** Android-on-Asterinas acceptance.

This wave's measured *new* isolated Python tests: 17 passed, zero
failed/errors/skipped (8 kernel-source fixtures + 9 APK artifact fixtures); see
tests/workloads/android/evidence/a08-fourth-wave.json and .log. These are
synthetic/host tests, not a real AOSP/ART/Binder execution. The complete
166-test suite was the historical checkpoint; the current full suite is recorded
above. AOSP checkout, actual APK build and
Android runtime remain **NOT EXECUTED**.

## Fifth wave: x86_64 Binder UAPI wire layout (2026-10-16)

At the fifth-wave checkpoint, the A08 branch incorporated then-current `main` with A01's full pinned Asterinas kernel as a **merge parent**, without changing non-A08 source. Binder is still NOT implemented or qualified on the target kernel.

For a real Linux x86_64 header baseline, build and execute:

    cc -std=c11 -O2 -Wall -Wextra -Werror tests/workloads/android/binder_uapi_layout.c -o /tmp/a08-binder-layout
    /tmp/a08-binder-layout
    python3 -m unittest tests/workloads/android/test_binder_uapi_layout.py -v

The source contains compile-time checks for Binder protocol 8, ioctl numbers, transaction/UID offsets and 64-bit structure sizes. The `BINDER_IPC_32BIT` negative build must fail. It does **not** open a Binder device or send transactions. Real host result: **3/3 passed**, with hashes and C output at `tests/workloads/android/evidence/host-binder-uapi-layout.json` and `.log`. These values describe only the Debian host's Linux UAPI header; AOSP 15/Bionic headers and a future A05 driver must still be compared and run on an actual guest. `support/android/verify_host.py` now includes the layout probe and exposes a separate RED imported-kernel contract report, never a green Android qualification.

## Cuttlefish product source checkout integrity (fifth wave)

`support/android/prepare_aosp.sh init|audit|build` now runs
`support/android/verify_product_source.py` after the resolved-manifest and
platform-source checks. It compares the **actual Git HEADs** of
`device/google/cuttlefish`, `device/google/cuttlefish_prebuilts`, and
`device/google/cuttlefish_vmm` against the 40-character commit IDs in the
same `repo manifest -r`. It also hashes the exact product source and verifies
that AndroidProducts.mk registers the selected x86_64 phone product and
`trunk_staging-userdebug` lunch configuration. Results are captured as
`product-source-audit.json`; no product commit is guessed or fabricated before
actual repo sync. The Cuttlefish launcher repeats the check immediately before
launch to reject changed source trees.

Standalone source check:

    python3 support/android/verify_product_source.py \\
      --aosp-root "$AOSP_ROOT" \\
      --resolved-manifest "$A08_EVIDENCE/manifest-resolved.xml" \\
      --out "$A08_EVIDENCE/product-source-audit.json"

Eight unit tests execute disposable real Git checkouts with intentionally
mismatched commits, missing VMM project, wrong product/ISA, and symlink escape
cases. They passed 8/8 on an isolated Linux host, but these are **synthetic
repositories**, not full AOSP sources or images. Passing this gate verifies
source checkout consistency only; Android runtime and Asterinas remain untested.

## Cuttlefish preflight evidence revalidation

The launcher now delegates its read-only integrity checks to
`support/android/verify_launch_preflight.py`. It requires passing manifest,
platform source, current Cuttlefish product and built partition inventories,
then rehashes **all** files inventoried by those reports (not only system.img
and vendor.img): Bionic/ART files, VINTF manifests/matrices, product makefiles,
and the launcher binary. It also rechecks recorded platform/Cuttlefish Git HEADs.
A changed source, VINTF file, image hash, or escaped path **blocks launch**.
The only successful status is `preflight_only`; it never asserts an Android
or Asterinas boot. Ten synthetic host regressions passed, including hash and
source tampering negatives. The launcher retains its separate unused-instance
and KVM-access checks.

## Sixth wave: run actual checkvintf, not just XML inventory

The AOSP build path now calls the exact same-build `out/host/linux-x86/bin/checkvintf` with `--check-compat` and real `/system`, `/vendor`, `/odm`, `/product` and `/system_ext` partition directory mappings. Where AOSP supplies `APEX_INFO_FILE`, the verifier passes it through and preserves its SHA256. The command, exit code, unfiltered stdout/stderr, binary SHA256 and VINTF file hashes are recorded in `vintf-compatibility.json`. If the tool is unavailable, the metadata is incomplete, or the checker reports incompatible, the build gate **fails** rather than claiming a product image is ready.

`run_reference_cuttlefish.sh` also requires a passing `vintf-compatibility.json` and rehashes the same recorded VINTF inputs and checker executable before guest launch. Its success remains `preflight_only`; no running HAL, ART, Binder or Asterinas compatibility is inferred.

To rerun just the metadata check after an actual AOSP build:

    python3 support/android/verify_vintf.py --aosp-root "$AOSP_ROOT" --product-out "$AOSP_ROOT/out/target/product/vsoc_x86_64" --checkvintf "$AOSP_ROOT/out/host/linux-x86/bin/checkvintf" --out "$A08_EVIDENCE/vintf-compatibility.json"

This round locally executed **26/26** isolated fixture regressions for VINTF tool command/exits, source/image/APEX/SW symlinks and stale evidence; all submitted source/test blob SHAs were compared to the tested versions. These are **not** real AOSP device VINTF compliance results; the complete checkout/build and Cuttlefish boot remain unexecuted here.

## Seventh wave: Android 15 APEX VINTF CLI correction

The AOSP `checkvintf` tool no longer accepts `--apex-info-file` as a raw CLI argument. AOSP's checkvintf source migrated to reading `apex-info-list.xml` through a `/apex` directory map. The A08 **Python wrapper** retains its input option `--apex-info-file PATH` for build-script compatibility, but validates the exact `apex-info-list.xml` filename and same-AOSP-out provenance, records its SHA256, and passes **only** `--dirmap /apex:PATH_TO_PARENT_DIRECTORY` to the actual checker. The obsolete option is never forwarded. See AOSP libvintf change 76409e8245965a7b6b6c2945a60a4b31e3eb2281 and current checkvintf usage.

Passing `checkvintf` now requires **both** exit code 0 **and** a final nonblank stdout line equal to `COMPATIBLE`; a silent or wrong-verdict exit 0 is a failure, as is `INCOMPATIBLE` anywhere in stdout/stderr. `apex_metadata_included=false` is explicitly recorded when no APEX info was supplied; such a result covers mapped static partition metadata only, not the installed APEX HAL service set or Android-on-Asterinas.

`verify_launch_preflight.py` verifies the real APEX info bytes, mapped directory and recorded `--dirmap` before Cuttlefish launch. It rejects legacy CLI use, stale APEX input, or an inconsistent mapping even when a prior metadata check was marked passed.

Exact byte-identical A08 remote source unit tests, on an isolated Debian x86_64 host:

    python3 -m unittest discover -s tests/workloads/android -p 'test_*.py' -v

Executed APEX/VINTF and launch-preflight subset: **31/31 passed** (0 failures, 0 errors, 0 skips). Transcript SHA256: `3be9e824861544965ea1ce0420756292144e15343afe038b30394d7800eb9f5c`. Evidence under `tests/workloads/android/evidence/host-seventh-apex.{json,log}`. This is NOT a complete A08 full-suite run and used a synthetic checkvintf executable, **not** the actual AOSP 15 built binary.

**Still unexecuted:** AOSP full checkout/build and partition image, actual target checkvintf/ART/Binder/PackageManager, KVM Cuttlefish Linux guest boot, original APK lifecycle, Android on Asterinas. At that historical wave, the container lacked repo, adb, QEMU, KVM and the necessary AOSP build disk space.

## Seventh wave: mounted ART and framework readiness

The Linux-Cuttlefish `boot_gates.py` no longer attempts to read
`/apex/com.android.art/apex_manifest.json` in a mounted payload. The
APEX package manifest is not reliable as a mounted-runtime file. Instead
the reference guest must make `/apex/com.android.art/lib64/libart.so` readable;
the test runs a fixed shell `test -r` and requires the exact sentinel
`A08_ART_LIB_PRESENT`. This checks the runtime library *file* only, not ART/JIT
execution. The A08NativeSmoke APK separately checks real ART/JNI execution.
The Framework gate also requires `getprop sys.boot_completed` equal to `1`;
process/PID-only checks are insufficient to establish completed boot.

On a local test host, **five** mock-ADB unit tests passed, including two new
negative cases for missing ART library and unfinished boot. The test host used
a temporary local `run_apk.py` identity shim to stand in for the Android
transport dependency, so this result is explicitly *not* a complete GitHub
branch unit suite or an Android guest runtime test. Remote committed
`boot_gates.py` and `test_boot_gates.py` bytes were separately SHA-verified
against the local tested versions. Log:
`tests/workloads/android/evidence/host-seventh-boot-gates.log`.

The VINTF/APEX 31-case test evidence is independent and byte-identical to the
remote code, and is retained under `host-seventh-apex.{json,log}`.
Neither host test denominator qualifies Android-on-Asterinas.

## A08 target-kernel ABI guest rehearsal

A08 can now stage real x86_64 Linux ABI/Binder probes into the imported Asterinas kernel's initramfs and run them under the recorded A01 one-CPU QEMU/TCG profile without modifying any A01/A05/A06 source files.

On a disposable host with a verified static BusyBox, C compiler, and full A01 source/build:

    export A08_ABI_OUTPUT=/tmp/a08-abi-new
    export A08_BUSYBOX_STATIC=/usr/bin/busybox
    bash support/android/build_asterinas_abi.sh

This compiles both existing kernel_abi_probe.c and binder_abi_probe.c as static ELF64, uses A01's original deterministic CPIO packer and init script, and stores the image SHA256 plus a manifest; it does not run the guest.

After an actual A01 kernel.sh run_kernel and trusted fresh qemu.json, replay the same built ELF and its exact SHA256 with:

    python3 support/android/run_asterinas_abi.py \
      --a01-qemu-json /path/to/A01/boot/qemu.json \
      --kernel kernel/asterinas/target/osdk/asterinas/asterinas-osdk-bin.elf \
      --expected-kernel-sha256 EXACT_SHA256_FROM_A01_QEMU_JSON \
      --initramfs "$A08_ABI_OUTPUT/a08-initramfs.cpio.gz" \
      --manifest "$A08_ABI_OUTPUT/manifest.json" \
      --bios /usr/share/seabios/bios-256k.bin \
      --qemu /usr/bin/qemu-system-x86_64 \
      --outdir /tmp/a08-qemu-abi-fresh

QEMU is restricted to q35, TCG, 1 CPU, 512 MiB, no network/disk/host QMP and no KVM. The runner checks the recorded A01 kernel and SeaBIOS hashes and captures raw serial bytes, QEMU exit status and required A01/A08 markers. A Binder errno/no-device (77) remains a separate BLOCKED status even if Linux ABI probes pass. A primitive Binder ioctl/mmap pass does not prove Binder identity, transactions, MAC or Android APK functionality.

Local measured host regression: 13/13 passed (static ELF compilation, deterministic initramfs fixture packing, full one-command builder fixture, profile/sha/overwrite rejection). These were synthetic fixtures on an isolated Linux host, NOT an Asterinas guest. See tests/workloads/android/evidence/host-asterinas-abi-guest.{json,log}. No QEMU executable was present on that historical test host; A08 guest probes and Android-on-Asterinas remain NOT EXECUTED.

## A08 ninth wave: falsifiable guest ABI and Binder verdicts

The previous A08 QEMU result parser had a reproduced **false positive**: raw QEMU exit 33 plus shell-level success markers incorrectly reported Linux ABI PASS even when the same serial log said `mmap FAIL errno=38` and `memfd_create UNAVAILABLE_AT_COMPILE_TIME`. A marker-only Binder primitive claim could also be reported as PASS without ioctl/mmap evidence. This was verified with the old parser, then fixed.

Now every named ABI case (mmap, memfd_create, SCM_RIGHTS, futex_wait_wake, signal) must have exactly one `PASS errno=0` record between the proper A08 BEGIN and PASS markers. 4096-byte page size, chronological unique A01/A08 markers, QEMU exit 33, and absence of panic or guest ABI failures are also required. Binder requires actual `binder_protocol_version`, `binder_set_max_threads`, `binder_mmap`, and `binder_empty_write_read` PASS records; missing device errno/exit 77 remains separately blocked. Even Binder primitive success NEVER qualifies full Binder transactions, UID/security context, death/fd lifecycle, Android ART or APK runtime.

QEMU replay now restricts the kernel `-append` command line to A01's known safe values (no `init=` override), requires exact serial chardev parameters, exact same A01-verified QEMU binary SHA256 and successful source QEMU record, and refuses invalid timeouts. Raw byte hashes of serial/stdout/stderr are retained, including non-UTF-8 bytes.

Host kernel_abi_probe.c now treats unavailable compile-time syscalls as a failure and validates SCM_RIGHTS received file identity via fstat, with errno=0 on genuine PASS. One new host test actually compiled the unchanged guest-intended probe **statically** and exercised mmap, memfd, UNIX fd passing, futex and signals on the Linux host. `/dev/binder` was absent (ENOENT) and was not scored as supported.

**Measured test scope:** 40/40 passed, 0 failures/errors/skips, from the six byte-for-byte verified current A08 files enumerated in `tests/workloads/android/evidence/host-abi-false-pass-regression.json`. Includes real Linux C syscalls and an executable **fake QEMU** used solely for transport/evidence regression testing, NOT a real virtual machine. See `host-abi-false-pass-regression.log` (SHA256 `3b9644dfe7bf29895db07abb24c9baf646cd6b8a5cce99e5d484e8d51d6f2626`). The entire A08 suite was not rerun in this isolated container; this is the exact six-file subset.

**Remaining red gates:** no qemu-system-x86_64 installed here, no A08 Asterinas guest boot, no actual Binder ioctl/transactions on Asterinas, no AOSP 15 build/ART/dual-APK runtime. Reproduce on A01's already validated QEMU/TCG host using `build_asterinas_abi.sh` then `run_asterinas_abi.py`. PR intentionally stays Draft.

## A08 tenth wave: seccomp BPF probe in actual Asterinas guest

A08 now stages **three** independent static x86_64 userspace probes into the A01-derived Asterinas QEMU/TCG guest: basic Linux ABI, Binder UAPI primitives and seccomp BPF enforcement. All three compile from existing A08-owned C sources. A01 kernel sources and build configuration remain unmodified.

The standalone builder `support/android/build_asterinas_abi.sh` now compiles and fingerprints `a08-seccomp-abi`, places it in the A01-format deterministic initramfs and injects these guest markers after the Binder probe: `A08_GUEST_SECCOMP_BEGIN`, `A08_GUEST_SECCOMP_FILTER_PASS` or `A08_GUEST_SECCOMP_EXIT:<code>`, then `A08_GUEST_SECCOMP_END`.

The static seccomp test uses a short-lived forked child, verifies `PR_SET_NO_NEW_PRIVS`, installs `SECCOMP_SET_MODE_FILTER`, requires real EPERM from blocked `getpid`, confirms permitted `getppid`, waits for the child to exit normally and prints raw errno/exit evidence. **A seccomp syscall/installation error is an independently classified red gate**, not proof that mmap/futex/memfd failed.

The QEMU result parser now accepts seccomp FILTER primitive status **only** when the seccomp marker, unique complete syscall/BPF-denial result lines and `seccomp_child PASS exit=0` agree. ENOSYS=38 or EOPNOTSUPP=95 from filter installation is `filter_install_not_implemented`; error13 with missing errno evidence is never treated as such. If Binder and basic ABI succeed but seccomp is blocked, the runner exits **2**, not 0. It exits 0 only if Linux ABI, Binder primitives **and seccomp filter primitive enforcement** are all independently evidenced. Still **no Android CTS/ART/MAC/TSYNC qualification**.

To create the guest payload on a verified A01 build host:

    export A08_ABI_OUTPUT=/tmp/a08-abi-seccomp-new
    export A08_BUSYBOX_STATIC=/path/to/static-x86_64-busybox
    bash support/android/build_asterinas_abi.sh

Run `support/android/run_asterinas_abi.py` with the same fresh A01 kernel ELF/qemu.json/SeaBIOS/TCG command documented above. No additional kernel files, QEMU network devices or host-wide seccomp policies are changed. The host seccomp filter is installed only inside the probe's isolated child.

**Actual host evidence 2026-10-16:** 53/53 isolated A08 unit/integration cases passed with GCC static C compilation, actual Linux child-only seccomp installation/EPERM enforcement and synthetic serial/fake-QEMU negative tests. These are **NOT** target Asterinas, full Android or real ART/Binder guest results. Exact source blob SHAs and run SHA256: `tests/workloads/android/evidence/host-guest-seccomp.json`; real host filter stdout: `host-guest-seccomp.log`. Real QEMU was unavailable on that historical test host; A08 Asterinas/Binder/seccomp guest probes remain **NOT EXECUTED**.
