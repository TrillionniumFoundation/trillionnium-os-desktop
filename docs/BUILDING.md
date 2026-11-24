# Build the pacman packages

The Rust package builder compiles Droidloom's host programs and modified Android
components, assembles the Android image, and produces a matching runtime/image
pacman package pair. It uses pinned upstream Android base and toolchain inputs;
it does not rebuild every upstream Android component from source.

## Shipping with GitHub Actions

`.github/workflows/ship.yml` runs on pushes to `main` or a manual dispatch of
`main`. It builds the matching package pair, runs the disposable-container package
checks, uploads archives to the `packages` GitHub Release, then deploys the pacman
database and `install.sh` to GitHub Pages. There is one job, with no promotion or
provenance pipeline. Pull requests do not run on this machine.

Before publishing changed packages, increment `packaging/arch/version.json`'s
`release` (or update `version` and reset `release` to 1). Published filenames are
never overwritten. A publication retry accepts existing assets only when their
bytes match. If a rebuilt package differs, increment the release. Old archives
stay available for users with cached pacman databases. Each package release also
includes a matching Git source snapshot; pinned upstream sources and licenses
are documented in that snapshot. Optional Google apps are not published.

### Manually controlled local worker

The runner and all its build state live under `/mnt/puck/logix/droidloom`:

- `runner/`: official GitHub runner, credentials and diagnostic logs.
- `work/`: Actions checkouts and temporary files, cleaned by checkout each run.
- `cache/arch/`: rootless Podman storage, downloaded inputs, AOSP sources and
  incremental compiler output.
- `cache/host-target/`: host Rust tooling build cache.
- `cache/cargo-home/`: host Cargo downloads.

The machine needs the usual build prerequisites plus `gh` (authenticated with
repository administration access for runner registration), `curl`, `tar`,
`sha256sum`, `cmp`, `jq`, `repo-add` (Arch's `pacman` package), and a working systemd
user manager. Configure GitHub Pages once with **Source: GitHub Actions**.
No host sudo is used by the runner or package builds.

Install or refresh the official runner while stopped:

```console
cargo run --locked -j 1 -p droidloom-package -- runner setup
```

Before pushing `main`, arm one job, then push:

```console
cargo run --locked -j 1 -p droidloom-package -- runner start
git push origin main
```

The ephemeral runner exits and unregisters after one job. It has no boot service.
It also stops after 24 hours if unused or stuck. Each queued run needs a new
`runner start`; concurrency prevents simultaneous publication. Start it only for
trusted changes. This runner uses the local user's account and is not a security
boundary around workflow code.

```console
cargo run --locked -j 1 -p droidloom-package -- runner status
journalctl --user -fu droidloom-actions-runner
cargo run --locked -j 1 -p droidloom-package -- runner stop
```

`stop` also removes a leftover GitHub registration, stops remaining build
containers, and preserves caches. The workflow calls `runner cleanup` after each
job to stop leftover containers in its package workspace. Cancel
an active workflow in GitHub before stopping its worker. Re-arm and rerun a failed
workflow after fixing its cause. A Pages failure can leave uploaded archives, but
the previous database remains live until deployment succeeds.

`DROIDLOOM_PACKAGE_WORK` overrides the default `.work/arch` directory for builds
and package checks; it must be an absolute path. The Rust runner tool sets it to the persistent
cache above, outside checkout cleanup; machine paths stay out of the workflow. Do not use `--clean` for normal releases.
The first build needs the full download/compile; later builds reuse the cache.
The builder leaves two logical CPUs free and the host Cargo build uses one job.

To prepare the Pages tree locally after building, without publishing:

```console
cargo run --locked -j 1 -p droidloom-package -- ship prepare
```

This writes `dist/pages`. `ship publish` uploads to GitHub and is normally run
only by Actions with its scoped token. Pages stores only metadata and the
installer because Android packages approach its 1 GB site limit. Pacman's
`CacheServer` fetches the archives from Releases without requesting databases
there. Packages are currently unsigned; see [INSTALL.md](INSTALL.md) for the
repository's explicit signing policy.

## 1. Prepare an x86_64 build machine

The supported package workflow uses rootless Podman with an Arch build container.
Install Rust/Cargo with a C linker, Git, Podman and rsync. On Arch / Omarchy:

```console
sudo pacman -S --needed rustup gcc git podman rsync
```

Sudo is needed only to install those host tools and dependencies under `/usr` and
update pacman's database. If you already have a working Rust installation, keep
it; you do not need to replace it with rustup. The checkout pins Rust 1.93.0.

Allow **120 GiB free** for a fresh build, including sources, toolchains, compiler
outputs, downloads and temporary package staging. The workflow has been exercised
on a machine with 32 GiB RAM and 16 logical CPUs. Retained build files are smaller
than peak space requirements: keep free space for staging and compression even
when rebuilding from cache.

Verify rootless Podman works as your ordinary user:

```console
podman info
```

Resolve any rootless Podman setup error before building; do not switch to a sudo
build. Internet access is required for the initial container and pinned inputs.

## 2. Get the source

```console
git clone https://github.com/denialwm/droidloom.git
cd droidloom
```

For a published preview, check out its corresponding source tag or commit before
building. The `main` branch may contain changes beyond that preview. Package
version and release are defined in `packaging/arch/version.json`.

## 3. Build binaries and packages together

```console
cargo run --locked -j 1 -p droidloom-package -- build
```

Run as your ordinary user, without sudo. The Rust tool performs compilation and
invokes makepkg inside the rootless container; no manual binary build or separate
packaging script is required. Shell is used only at required upstream interfaces
and in PKGBUILD functions.

The builder limits jobs to the available logical CPU count minus two. To limit compilation further:

```console
cargo run --locked -j 1 -p droidloom-package -- build --jobs 4
```

Container CPU pinning is opt-in, so the default build works without rootless
`cpuset` delegation. To restrict the container to a CPU subset as well:

```console
cargo run --locked -j 1 -p droidloom-package -- build --cpuset
```

This requires the host to delegate the `cpuset` controller to rootless Podman.
Without it, the job limit still leaves capacity for two logical CPUs and nested
Android builds retain their own CPU affinity control.

Outputs are written to `dist/arch/<version-release>/`. For revision 0.1.0-7:

```text
dist/arch/0.1.0-7/droidloom-runtime-0.1.0-7-x86_64.pkg.tar.zst
dist/arch/0.1.0-7/droidloom-image-0.1.0-7-x86_64.pkg.tar.zst
```

The command prints the exact installation command when finished. Install both
packages by following [INSTALL.md](INSTALL.md).

Normal builds fetch [Teto](https://github.com/denialwm/teto), the Translation
Engine with Target Optimization, at exact commit
`917021cf3ecd077eb1581146a79d2265011755b8`, pinned in
`android/manifest/native-bridge-lock.json`. It includes the memory-reservation,
FPCR rounding, breakpoint/ptrace and JNI-table isolation fixes. No local
development checkout is needed for these fixes.

For further Teto development, use a separate Git checkout whose `origin`
matches the repository URL in that lock and whose history contains the pinned commit.
Commits on top of that base and uncommitted edits are both supported:

```console
cargo run --locked -j 1 -p droidloom-package -- build --jobs 8 \
  --native-bridge-source /absolute/path/to/digitalis
```

The checkout is mounted read-only and copied into the generated AOSP workspace.
The installed `/system/etc/droidloom-native-bridge.json` records its base, actual
commit and hashes of all working source files. Keep any unpublished development
edits needed to reproduce such a package. Omit the option for the locked Teto
source. Existing caches with an old origin URL, an older revision, or
development edits deliberately fail verification instead of silently discarding
them. Use a fresh build workspace when switching to the new pin. For an existing
development clone, preserve the DigitalisX64 remote as `upstream`, set `origin`
to the lock's Teto URL, and fetch the pinned commit before building.

Teto's `droidloom` branch includes `android-mmap-noreserve`,
enabled by Droidloom's `ro.berberis.flags`.
It gives private anonymous guest mappings Android's expected
overcommit behavior without modifying the desktop's global memory policy. Strict
host overcommit policy still applies. The pin adds branding, licensing documents
and change notices to the previously validated translator code (3743 host tests
passed, three skipped; Brawl Stars
startup confirmed by the user). Pinning source does not publish new packages or
replace existing installed images and local library overrides. Teto derives from
Digitalis/AOSP Berberis; upstream history and notices remain intact. Existing
`berberis_*` ABI names, build targets, source paths, and the local
`.work/translation/digitalis` directory remain unchanged for compatibility.

### Translation stress and performance benchmarks

`droidloom-translation-bench` is a Rust command-line runner for Digitalis's
existing `berberis_arm64_host_tests`. Run it on an **x86_64 Linux host** as an
ordinary user. It does not install packages, start Android or restart a session.
An ARM64 phone runs ARM64 natively and cannot measure this translation path.

For an engine-only candidate, use the separate prepared-workspace command:

```console
DROIDLOOM_NATIVE_BRIDGE_SOURCE=/absolute/path/to/digitalis \
  cargo run --locked -j 2 -p droidloom-update -- \
  native-engine-build --work /absolute/path/to/prepared-build --tests
```

This selects only the installed Android `libberberis_arm64.so` and the real
`linux_glibc_x86_64` ARM64-guest host-test install target. It writes to
`android-native-engine-out` and records the working source snapshot (including
untracked files), effective compatibility projections, link references and
artifact identities in `droidloom-native-engine-source.json`. Its native Soong
route preserves selected missing-dependency errors and applies the qualified
defaults-propagation and Go memory-budget patches. Builds sharing the prepared
source remain serialized by the existing locks. It builds the tests without
running them; it does not assemble an image or install the engine. Runtime ABI
checks against preserved libraries and the real host-test run remain required.
The inherited common source projections still apply, including baseline
minigbm compatibility changes. The dedicated allocator/YV12 candidate patch
`0017` and audio PCM patches `0015`/`0016` are outside this mode. The provenance
records all applied common patches and their effective projected files.
Each attempt clears only its previous engine receipts and saves a separate
`droidloom-native-engine-inputs.json` before compilation; a failed build cannot
leave its previous success receipt in place.

Local translator snapshots compare file contents and preserve destination times
only for identical contents; a changed file receives its import time even when
the developer copy has an older timestamp. The older archive-style import
preserved source times and could leave Ninja objects stale. When migrating an
output tree produced by that policy, select a fresh absolute directory with
`native-engine-build --work /absolute/path/to/prepared-build --out
/absolute/path/to/new-engine-out --tests`. The default output directory is
unchanged. The selected directory controls compilation, engine receipts, host
test binary, corpora and shared libraries; it is also recorded in both receipts.
Keep the old output tree as evidence and verify the complete test registration
before running the rebuilt suite.

Before measuring a translator edit, rebuild **the host test binary**, not just
`libberberis_arm64.so`: the host tests statically link the translator. In the
already prepared Android build environment, use the updater's focused target:

```console
DROIDLOOM_NATIVE_BRIDGE_SOURCE=/absolute/path/to/digitalis \
  cargo run --locked -j 1 -p droidloom-update -- \
  native-bridge-build --work /absolute/path/to/prepared-build --tests
```

Use the paths visible inside the rootless builder when running there (`/build`
for the prepared build and the mounted Digitalis source path). This is the
existing source build workflow and requires its prepared dependencies. A package
build alone does not request the host tests. Keep the test executable in its
Soong output tree, alongside its test data and `../../lib64` support libraries.
Each benchmark run makes and verifies a private copy of these inputs under its
output directory, so a later rebuild cannot mix executables within a run. It
also retains the benchmark source and writes `inputs.json` before testing;
only `result.json` denotes a completed run. Avoid concurrent builds anyway,
because their CPU and memory traffic can distort the measurements.

From the Droidloom checkout, save a baseline (choose an available, idle logical
CPU and keep it the same for subsequent runs):

```console
cargo run --locked -j 1 -p droidloom-translation-bench -- run \
  --cpu 6 --label before --output .work/translation/bench-before
```

The default paths match this checkout's `.work/arch/build/android-out` host
test executable and `.work/translation/digitalis` benchmark source. Override
`--binary` and `--benchmark-source` for another build. The supplied benchmark
source must be the file used to build that binary; hashing it cannot prove that
a stale executable was rebuilt. Optional `--build-manifest` records the same
build's `target/product/droidloom_x86_64/droidloom-native-bridge-source.json`.
The executable hash identifies exactly what ran; the optional manifest is
supporting provenance, not independently verified linkage to that executable.

The runner first executes the complete non-benchmark correctness suite twice
in fresh processes, in its normal `two-gear` mode. These tests directly exercise
the interpreter, lite translator, heavy optimizer, decoder, guest ABI and kernel
emulation, including upstream differential fuzz cases. `--stress-repeats 10`
increases repeated stress; it does not generate new fuzz seeds or establish a
code-coverage percentage. Disabled and skipped tests remain visible in the logs
and correctness summaries. A failed test or timeout aborts the run before it can
publish `result.json`. Some upstream seccomp/ptrace tests require an ordinary
unsandboxed host process; an agent/container sandbox can cause failures. Do not
filter those failures away to manufacture a passing baseline.

After correctness passes, the runner measures each of these workload families
in `interpret-only`, `lite-translate-or-interpret`, and `two-gear` modes:

| Workload | What it exercises | Loop iterations per timed run |
| --- | --- | --- |
| Integer | Mixed integer arithmetic, bitwise operations and shifts | 3,000,000 |
| Branch | Comparisons and conditional branches | 3,000,000 |
| Call | Guest calls, returns and dispatch | 3,000,000 |
| NEON | Vector arithmetic | 3,000,000 |
| FP | Scalar double-precision arithmetic | 3,000,000 |
| Memory | Repeated loads/stores over a small hot buffer | 3,000,000 |
| Syscall | Guest `clock_gettime` emulation | 1,000,000 |

`--mode two-gear` selects a shorter, production-mode timing sweep.
`--samples 9` (the default) collects nine fresh-process results per case; each
result is the upstream median of five internal timings. Case order rotates
between sweeps. `--timeout-seconds 120` bounds each child process and preserves
logs on failure. All test processes inherit the selected CPU affinity and a
clean environment. Set translator flags explicitly with `--flags` when needed;
ambient `BERBERIS_*`, tracing and dynamic-loader overrides are removed.
The workload uses one logical CPU, leaving at least two physical cores outside
its affinity on this eight-core development host. To pin the runner's own
snapshotting/reporting work as well, first build it with
`cargo build --locked -j 1 -p droidloom-translation-bench`, then invoke
`taskset --cpu-list 6 target/debug/droidloom-translation-bench run --cpu 6 ...`.

After changing and rebuilding Digitalis, repeat with a fresh output directory:

```console
cargo run --locked -j 1 -p droidloom-translation-bench -- run \
  --cpu 6 --label after --output .work/translation/bench-after
cargo run --locked -j 1 -p droidloom-translation-bench -- compare \
  .work/translation/bench-before/result.json \
  .work/translation/bench-after/result.json --fail-on-regression
```

Comparison reports milliseconds, percentage time change and relative
interquartile range (IQR) for each mode/case. **Positive time change means
slower.** Changes beyond 5% are flagged by default; a row with more than 10%
IQR in either run is inconclusive. `--threshold` and `--noise-limit` adjust these
screening thresholds. These are heuristics, not statistical significance tests;
IQR is calculated over the saved process medians and does not expose variation
hidden inside each upstream median. With `--fail-on-regression`, exit code 2
means at least one non-noisy regression, 3 means noisy data without a detected
regression, and 1 means invalid input or execution failure. Without that flag,
performance findings are informational.

The comparison rejects changed machines, CPUs, kernel versions, recorded power
settings, mode/flag selections, benchmark source, work counts, support libraries
or test data and correctness summaries. It allows a changed test binary, which is the subject
of the comparison. Use the same build configuration, an idle host and consistent
power/thermal conditions. Pinning a CPU does not isolate it from other tasks or
its SMT sibling. Repeat unchanged builds to establish normal noise, then repeat
A/B or ABBA runs before accepting small gains. Reports and logs belong under
`.work/`, outside Git; existing result directories are never overwritten.

Scope: this stresses many paths but does **not** cover every ARM instruction or
every translator path. The timed kernels themselves use upstream `SUCCEED()`
rather than answer checks; correctness comes from the separate test gate, not
from their speed. The upstream warmup is only one loop iteration, so optimization
tier promotion can still occur inside the timed interval. These are guest-loop
elapsed times, not isolated translation-compilation costs or proven steady-state
heavy-JIT timings. The reported instruction counts are workload labels (the
branch case counts skipped instructions); the runner deliberately compares time
rather than treating the upstream MIPS number as an exact instruction rate.
Iteration counts are fixed in upstream source, not controlled by `--samples`.
Changing those kernels requires rebuilding the host tests and starting a new
baseline. Memory bandwidth, atomics under contention, Android API proxies,
graphics, app startup and cold translation need additional dedicated workloads
and app-level measurements. An optimizing-mode result can include fallback;
selecting that mode does not prove every instruction used the heavy optimizer.

## 4. Exercise package installation

```console
cargo run --locked -j 1 -p droidloom-package -- check --packages dist/arch/0.1.0-7
```

Use your build's output directory if its version differs. This runs actual pacman
dependency installation, setup, reinstall, removal and data-retention checks in
a disposable rootless Arch container. It needs no host sudo and does not restart
your desktop. It uses a simulated GPU entry for setup checks; app rendering must
be tested separately on a real Wayland desktop.

Add `--previous dist/arch/<older-version-release>` to include upgrade and downgrade
transactions against an older pair.

## Rebuilds and troubleshooting

For a change confined to host components, increase the release in
`packaging/arch/version.json`, then select the component instead of compiling
Android again:

```console
cargo run --locked -j 1 -p droidloom-package -- build --component droidloom-supervisor
```

This compiles the selected Cargo package and its Rust dependencies. Selecting
`droidloom-supervisor` updates `droidloomctl`, `droidloomd`, the supervisor and
`droidloom-host-mac` together, including the fixed executable copies under
`/usr/lib/droidloom/production/current`. Other supported components are `droidloom-wayland`,
`droidloom-applications`, `droidloom-doctor`, and `droidloom-package-support`.
Repeat `--component` to select more than one. Without it, the command builds
the complete runtime and Android components as before.

Full builds also stage the matching production unit templates under
`/usr/share/droidloom/production`. These are package data: staging does not install
them into `/etc/systemd/system`, enable a service, write a production selection,
load host policy or qualify Android. The production installer must still bind
the selected image/runtime cohort and complete the actual kernel and runtime
qualification before activation.

A component build reuses unchanged files from the newest completed older package
pair with the same version and architecture in `dist/arch`. It produces a new
matching pair and records its baseline and selections in `build-summary.json`.
It does not use installed binaries or rebuild Android, Mesa or SurfaceFlinger;
extracting and repackaging the image still takes some time.

Use a full build for Android changes, changes spanning the host/Android protocol,
or changes to dependencies and package integration. Component builds reject
changed Cargo lockfiles, pinned Android inputs, runtime contracts, production
unit templates and packaging recipes. They also reject `--clean` and `--source-cache`. A completed full build
provides the baseline; builds made before component support need a full rebuild
to record their inputs. Keep that baseline's archives, summary and
`component-inputs.json` together. Unselected source edits are not included.

Rerun the same build command to reuse caches. Downloads, sparse AOSP sources and
outputs live under `.work/arch`; build attempts save `build-*.log` there.
`build --clean` removes this workflow's compiler outputs while retaining downloads.
An existing sparse AOSP source checkout can seed a build with
`build --source-cache /path/to/checkout`; installed binaries are not build inputs.

If staging fails with `No space left on device`, free disposable outputs and rerun
the builder. Do not distribute partial archives from a failed attempt. APKs,
packages, caches and local test artifacts must stay out of Git.

The fully empty-cache source-download path has not yet been rehearsed; see
[KNOWN_ISSUES.md](KNOWN_ISSUES.md). Build logs should accompany reports of failures.

### Complete-source ownership metadata

The full production source route, including the two official GSI vendor phases,
applies one exact compatibility projection to
`device/google/cuttlefish/guest/commands/vkms_controller/Android.bp`.
The pinned Cuttlefish commit
`283645aacf6cdb56cc31a9362f54d412dbc132a1`
references `trendy_team_desktop_display`, which has no definition in the
pinned public build commit `5ce6f787337d0223710bf7d4a16dbe6d2a35f777`.
The public Android 17 security branches retain the same consumer and team-table
Git blobs. No team ID is inferred or synthesized.

The adapter accepts only the original 1,522-byte file with SHA-256
`fad92f331030a22d22d989e4df4f7b6fdd90f2d11b702f90fd1d26304783b45d`
and removes its single 49-byte `default_team` line. The resulting 1,473-byte
file must hash to
`bd556a4385b92f6808a8d9df94f118a8b2f93e35a0598fef636fe0f91c075b7f`.
The original `vkms_controller` and `CfVkmsControllerTest` declarations,
licenses, source lists, compile flags, dependencies and install settings remain
byte-for-byte intact. Other team references are not changed.

The pinned Soong `android/package.go` checks `Default_team` only when the
optional pointer is set. `android/team.go` publishes a metadata provider;
`android/all_teams.go` uses it for `ownership/all_teams.pb` and explicitly
supports an absent `TrendyTeamId`. This adaptation does not change Soong's
missing-dependency checks, the production `user` variant, neverallow enforcement,
the full651 lock, or the requested build targets.

The existing projection journal records the exact preimage and effective hash.
Normal completion and interrupted recovery restore the original bytes, mode
and modification time before full source verification. Reapplying after recovery
works; a second application to an active projected file is rejected. The ordinary
native-pair path keeps its existing independent invocation of the same fixed
adapter. Full source and runtime acceptance still require their normal gates.

## Desktop image policy

The Android 17 x86_64 package omits legacy VNDK 31–34 APEXes from its derived
`system_ext.img`. The pinned upstream inputs remain unchanged. The policy rejects
other vendor products, SDK versions, or an explicit legacy VNDK selection. `adbd`
is retained. Image derivation runs in one fakeroot session to preserve Android
ownership and security xattrs. Before staging, it re-extracts the rebuilt image
and compares every retained file’s contents, permissions, ownership, timestamps,
symlink target and extended attributes. Missing expected VNDK files or any other
content/metadata change fails the build. A full package build is required.

## Optional Google apps

`droidloom-gapps` builds an optional add-on from a **locally supplied LiteGapps
regular lite archive for Android 17/API 37**. The guest architecture comes from
the APK payload and base build properties, independently of the build host.
Both raw ext4 developer partitions and the standard desktop EROFS partitions
are supported. Every selected APK must contain the guest's native ABI or be
Java-only; Google apps do not depend on ARM translation on x86_64.

Host tools are `bsdtar`, `xz`, `e2fsprogs`, Android SDK `aapt2` and `apksigner`,
and a Java runtime. EROFS derivation also requires `erofs-utils`, `fakeroot` and
`attr`. Pacman archives use the existing rootless Podman Arch builder
and its `makepkg`/`fakeroot` tools. Build as an ordinary user; assembly uses `debugfs` on private image
copies and does not mount images, install software or start services.
EROFS assembly runs extraction and rebuilding in one fakeroot session to retain
Android ownership and security attributes without administrator access.

Inspect the selected archive, then pass its reviewed SHA-256 to the builder:

```console
cargo run --locked -j 1 -p droidloom-gapps -- inspect /path/to/LiteGapps-arm64-17.0.zip
cargo run --locked -j 1 -p droidloom-gapps -- build \
  --archive /path/to/LiteGapps-arm64-17.0.zip --sha256 <archive-sha256> \
  --base /path/to/active-image-set --output .work/gapps-arm64 \
  --aapt2 /path/to/aapt2 --apksigner /path/to/apksigner
```

`--base` contains `images/system.img`, `images/system_ext.img` and
`images/product.img`. Use the actual activated images, including previous
Droidloom derivations. `--system-ext /path/to/system_ext.img` selects a separately
derived input without modifying the base directory. APK signatures, package IDs,
SDK and native ABI are checked. The importer does not execute upstream installer
scripts or resign APKs. A supplied archive checksum establishes input identity;
it is not an independent endorsement of its publisher.

For x86_64, an Android 17 ARM64 archive can supply the Java-only Services
Framework and Android 17 configuration when native Play APKs are provided:

```console
cargo run --locked -j 1 -p droidloom-gapps -- build \
  --archive /path/to/LiteGapps-arm64-17.0.zip --sha256 <archive-sha256> \
  --base /usr/lib/droidloom/images --output .work/gapps-x86_64 \
  --play-services-apk /path/to/x86_64/GmsCore.apk \
  --play-store-apk /path/to/x86_64/Phonesky.apk \
  --aapt2 /path/to/aapt2 --apksigner /path/to/apksigner
```

Replacement APKs must have the same package ID and signing certificate as the
archive's APK, or a verified ancestor in its signed certificate rotation lineage.
Their actual minimum SDK and native ABI are checked and their hashes are recorded
in the manifest and import report. Older archive release labels alone do not
establish APK compatibility: only the two native APKs are selected, never older
Services Framework, platform libraries or permission XML. Configuration is
filtered against the replacement APKs' requested permissions. Validate the result
on Android 17 before relying on sign-in or other Google APIs.

On the development desktop, native Play Services 24.23.37 and Play Store 41.3.25
from the Android 15 x86_64 archive completed account sign-in with the Android 17
framework and configuration. This older Play Services build also starts a
hotspot listener that crashes when Android has no Wi-Fi service. The local
workaround disables only that component for Android user 0, from inside the
Android cell:

```console
/system/bin/pm disable --user 0 com.google.android.gms/com.google.android.gms.magictether.host.TetherListenerService
```

This is a desktop workaround, not a general default for devices with Wi-Fi.
Google subsequently updated Play Services to 26.33.32 and Play Store to 53.0.27,
both targeting API 37. The user confirmed NTE launches successfully after an
official **Update from Play**, following permission repair and a local catalog
compatibility experiment; see the
[app-service limitations](KNOWN_ISSUES.md#application-compatibility).

The default selects Google Services Framework, Play Services and Play Store.
`--sync-adapters` also selects Google Contacts and Calendar sync. Configuration
is filtered to selected applications and their requested permissions, with
privileged allowlists on the apps' own partitions. Pixel feature declarations,
phone setup wizard configuration and unrelated applications are excluded.
`import-report.json` lists selected files and excluded upstream files. Original
license comments and the archive's license notice are retained.

Only `product` and `system_ext` are derived. Assembly checks every retained
file's contents, symlink target, UID/GID, mode, mtime and xattrs and checks filesystem
integrity. The manifest binds the outputs to all three exact base image hashes,
the source archive, SDK, architecture and verified APK signers. A failed build
does not publish the destination. Keep images, APKs and packages outside Git.

For a separately maintained ARM developer runtime:

```console
cargo run --locked -j 1 -p droidloom-gapps -- package \
  --addon .work/gapps-arm64 --version 4.9.20260513 --standalone \
  --output dist/droidloom-gapps-4.9.20260513-1-aarch64.pkg.tar.zst
```

For pacman-managed deployments, replace `--standalone` with
`--base-package-version <version-release>` to require the exact matching
`droidloom-runtime` and `droidloom-image` packages and include the lifecycle hook.
Standalone packages require manually stopping Droidloom before every install,
upgrade or removal. They contain images and notices, not an updated supervisor.

The runtime must include `gapps_dir` support before activation. Install the
package with pacman only when ready; administrator access is needed to write
the package-owned directory and update the package database. While Droidloom is
stopped, add `"gapps_dir": "/usr/lib/droidloom/addons/gapps"` to its root-owned
cell specification. Package installation alone does not activate Google apps.
The supervisor verifies root ownership and every base/output hash before boot.
An incompatible or missing selected add-on fails startup without falling back.

**First activation requires fresh Android data.** Configure a separately
provisioned fresh `data_dir` (with its `data.img` and `metadata.img`), or enable
GApps before the installation's first Android boot. Existing data is never wiped.
The runtime records Google-app selection and signers in the cell's data image;
updates with the same selection/signers refresh only Google parser caches.
Changing selection or signers requires fresh data or a separately validated
migration. To disable GApps, stop Droidloom, remove `gapps_dir` and select fresh
data or restore a pre-GApps backup. Merely removing the package cannot undo
Google updates and account state in `/data`; startup rejects that mixed state.

A separately validated migration must also reconcile existing applications'
permission state. An app installed before GApps may request Google-defined
normal permissions yet retain `granted=false` after those permissions appear.
On the desktop, reinstalling NTE's unchanged base APK with
`pm install -r -p com.hottagames.nte --user 0 <installed-base-apk-path>` retained
its existing splits and data and restored `CHECK_LICENSE`, allowing it to bind
to Play's licensing service. This does not establish a Play license or repair
catalog incompatibility. Do not substitute a blanket runtime-permission grant
or reset application data.

Offline checks do not prove account sign-in, Play Store installation, push
delivery or Play Integrity behavior. Validate those on the intended device,
including repeat boots and package changes, before considering the integration
ready for use. Google certification and redistribution rights are separate from
successful image assembly; see [third-party scope](../THIRD_PARTY.md).

Play Store also filters its catalog using Android's reported capabilities.
The vendor product declares touch and distinct multitouch provided by Droidloom's
input bridge, which preserves independent contact IDs in Android MotionEvents.
The framework includes that routed input when computing display
configuration, since physical input devices remain private to Denial. The Mesa
products advertise OpenGL ES 3.2 (`ro.opengles.version=196610`), matching the
verified Moto and x86_64 AMD rendering paths. Both window orientations are
declared for freeform Android tasks. When validating another graphics backend, compare
the advertised version with SurfaceFlinger's actual GLES implementation.

From inside the Android cell, `cmd package list features` should include the
touch features and a nonzero `reqGlEsVersion`; `cmd activity get-config` should
report `finger` for a touch-enabled Droidloom product. A feature XML alone does
not correct the display's input configuration. After updating these boot-time
capabilities, restart the cell and refresh Play Store's cache. Successful account
sign-in does not guarantee that Google has refreshed its device profile or that
every app is compatible. Only declare capabilities the runtime implements;
Google certification and missing camera, microphone or sensor integration are
not repaired by adding feature names.

## Audio target SDK prerequisites

The Audio APEX source lock includes the original released Java SDK inputs
referenced by its retained discovery graph. In particular, the original
android-support-test-nodep provider uses SDK 23, while its companion support
libraries use SDK 15. Preserve those API levels: changing them to current
does not repair the missing build inputs.

Select the official android.jar and public framework.aidl from the pinned
platform/prebuilts/sdk revision. API 30 and newer also require the original
core-for-system-modules.jar; system SDK consumers require their original
system-scoped android.jar and the corresponding public AIDL/system modules.
The source admission guard rejects incomplete SDK selections before Soong.
These are build inputs, not additional Android installations.

The source-lock checks establish input completeness only. A successful complete
Audio APEX build, compiled-artifact checks, and runtime playback/capture remain
separate release requirements.

## Audio and vendor policy test-tool providers

The retained Soong discovery graph also includes host test tools even when the
selected target is `vendor_sepolicy.cil`. The Audio source profile contains 444
exact projects from its original Android superproject. It includes the original
`dexdeps`, Atest certificate locator, Mobly result uploader and converter, Scapy,
and their Python providers. The Google API client needs its OAuth, URI template,
API core, auth, cache, RSA and ASN.1 dependencies; selecting only its top-level
module leaves the normal graph incomplete.

Keep the original complete source cones and provider Blueprints. The admission
checks bind the current lock and original provider bytes before invoking Soong;
they reject the previous 431-project profile, partial library selections,
changed provider files and symlink substitutions. The previous lock remains a
regression fixture, and `audio-test-tool-provider-origins.json` records the
original project commits and Git blobs. These source checks do not establish a
successful vendor policy build or combined CP3A policy compatibility. Build the
fixed production `user` target with missing-dependency and neverallow checks
enabled, then verify the generated policy with the selected original platform
inputs before runtime adoption.


### Original bcc_compat input within Audio444

The fixed user vendor-policy run on the first Audio444 source reached the
original `development/build` consumer and reported missing `bcc_compat`.
The successor retains all 444 project identities and adds only
`frameworks/compile/libbcc/tools/bcc_compat` to the pinned libbcc sparse cone.
Git cone mode also retains the original parent `tools/Android.bp`.
The original `libbcc`, `libbcinfo`, `libLLVM_android`, `slang_headers` and inherited
defaults remain in their existing pinned source projects. No substitute module,
provider deletion or relaxed missing-dependency switch is used.

`android/manifest/audio-bcc-provider-origins.json` records ten original provider
and consumer inputs, including the complete `bcc_compat/Main.cpp` bytes. The
normal Audio guard rejects a pre-expansion lock or missing, changed and symlinked
provider files before Soong. Focused tests preserve the old Audio444 lock as a
historical fixture and require a monotonic cone expansion without repinning.
The fixed policy receipt profile is `exact-audio444-bcc-source-policy-target`.
This is an independent Audio recipe; no global Native602 project limit changes.
Source tests and materialization do not qualify the vendor CIL, selected cohort
policy composition, complete Audio APEX, or device runtime.


### Original CHRE Pigweed providers within Audio445

The subsequent strict user vendor-policy run reached the original `chre_linux`
and `chre_linux_nanoapp_unit_test` consumers and reported seven missing Pigweed
and Emboss providers. Audio445 preserves all prior 444 project identities and
adds the original `external/emboss` project at the same Android superproject
gitlink, with its complete `compiler` and `runtime` cones. Git cone mode also
retains the root `embossc` script and original license and Blueprint files.

The existing Pigweed revision gains `pw_async2`, `pw_bluetooth`,
`pw_bluetooth_proxy`, `pw_checksum`, `pw_intrusive_ptr`, `pw_multibuf` and
`third_party/emboss`. This supplies the original providers and all modules
newly exposed by these cones, including the `gatt`, `command_multiplexer`,
`sniff_offload`, `rfcomm` and multibuf adapter modules. Existing original
allocator, common backends, threading, logging and Fuchsia header providers
retain their revisions and selected paths.

`android/manifest/audio-chre-provider-origins.json` records the exact provider
and consumer files, original Emboss root tree and generator inputs. The normal
Audio path checks the complete original bytes before projection. Focused tests
reject the failed Audio444 lock, missing cones or projects, changed revisions,
and missing, modified or symlinked provider files. Historical BCC and test-tool
source tests retain their exact previous lock fixtures. No source provider or
consumer is replaced, and strict Soong dependency and neverallow checks remain.

The source profile is `exact-audio445-chre-source-policy-target`; the isolated
Audio project capacity remains 448 and does not change global Native602 support.
Source tests and materialization do not qualify vendor CIL, selected-cohort
policy composition, Audio APEX, device runtime or production readiness. Those
require new successful runs with their own inputs and execution evidence.


### Original VINTF VTS provider within Audio446

The subsequent strict user vendor-policy run reached the original
`libassemblevintf` consumer and reported the absent
`libvts_vintf_test_common` provider. Audio446 preserves all 445 previous project
identities and adds `platform/test/vts-testcase/hal` at the same Android
superproject gitlink. Its complete `treble/vintf` cone retains the library,
parent test defaults, all three AIDL files, original test sources and configs.
Git cone mode also retains the ancestor `treble/Android.bp`. Existing `libbase`
and `libvintf` projects and the parent defaults' provider cones retain their
original revisions and selected source paths.

`android/manifest/audio-vintf-vts-provider-origins.json` records the exact
consumer and provider inputs. The normal Audio path checks all 30 original
files before projection. Focused tests reject the failed Audio445 lock, a
missing project, a library-only cone, changed revision, and missing, modified
or symlinked original files. Historical CHRE, BCC and test-tool source tests
retain their previous exact lock fixtures. Strict Soong dependency and
neverallow checks remain enabled.

The source profile is `exact-audio446-vintf-vts-source-policy-target`; the
isolated Audio capacity remains 448 and does not change global Native support.
Source tests and materialization do not qualify vendor CIL, selected-cohort
policy composition, Audio APEX, device runtime or production readiness. Those
require successful subsequent runs with their own complete execution evidence.


### Original ADB and WebRTC provider closure within Audio453

The Audio446 strict user vendor-policy run reached the original `libadb_host`
and `libaudiopreprocessing` consumers. Their original OpenScreen, libusb and
WebRTC providers were absent. WebRTC's unmodified defaults additionally require
pffft, rnnoise and libsrtp2. The original libsrtp2 fuzzer, the original Soong
device-fuzzer dependency rule and the actual unsanitized production user
configuration also require the original libFuzzer MTE crash-handler provider.

Audio453 preserves every prior project revision and every existing consumer.
It adds seven projects at the same superproject's original gitlinks, and
monotonically fills the required libevent and ADB physical source cones.
Parent Blueprint, license, visibility, original architecture branches, source
files, exported headers and transitive dependency declarations remain intact.
The provenance record explains each provider/consumer edge and binds the
original Git blobs. Normal Audio qualification rejects a missing, changed or
symlinked guarded input, a missing or repinned provider, and a narrowed source
cone. The previous 446 lock remains an exact historical fixture.

The preceding profile was `exact-audio453-adb-webrtc-source-policy-target`,
with an isolated source limit of exactly 453 projects. Global Native source support and
other build modes are unchanged. Missing-dependency and neverallow checks stay
enabled. Source tests, source materialization, vendor CIL, selected-cohort policy
composition, full Audio APEX and actual device runtime remain separate gates.


### Original edit_monitor dependency within Audio454

The strict Audio453 user build completed bootstrap and reached the unchanged
`edit_monitor_lib`, whose original Blueprint requires `watchdog`. Audio454
adds `external/python/watchdog` at the same pinned Android superproject's
original gitlink and selects its complete `src` cone, retaining all root files.
The original parent license and Python provider Blueprints are byte-pinned.
The provider declares no libraries or defaults; the other explicit
`edit_monitor_lib` dependencies remain in the already selected asuite and
protobuf projects. This does not add unrelated atest default dependencies.

All 453 preceding project records, revisions and source cones remain identical.
The historical 453 lock is retained as an exact fixture. The current isolated
profile is `exact-audio454-watchdog-source-policy-target`, bounded to exactly
454 projects. Ordinary source validation rejects a missing or repinned
watchdog project, an incomplete source cone and missing, modified or symlinked
original guarded Blueprints. Global Native support and the other build modes
remain unchanged. Source qualification, strict vendor CIL composition, full
Audio APEX and enforcing device runtime require their separate actual results.

### Complete production source: local APK and APEX signing providers

The complete production provider entry now applies the same pinned local signer
selection already used by the normal native pair build. It accepts only the
original 5,010-byte tools/apksig/Android.bp with SHA-256
22f86ab11f2470d9e34861f7273dd92c0ba4e9b914710a71c22dc374ebbac2fb.
The complete original apksig, apksigner-defaults, and apksigner modules,
including their local cryptographic dependencies, remain byte for byte intact.

The product selects local signing. Its upstream Soong APK and APEX packaging
rules use signapk; the remaining local tooling uses apksigner. The separately
declared AWS and GCP KMS backends, apksigner-kms, and the aggregate apksig test
that imports both cloud SDKs are not selected for this product. Those four
declarations alone are omitted from the effective Blueprint. This is explicit
provider selection, not a substitute implementation of a cloud SDK. No source
Java class, signing algorithm, local signer dependency, product target,
neverallow setting, or source lock is changed.

This projection uses the original journal. Both successful completion and
normal interrupted recovery restore the whole upstream Blueprint and its
recorded metadata. The full 651-project verification remains in force before
and after the build, and ALLOW_MISSING_DEPENDENCIES=false remains mandatory.
No private discovery exclusion is enabled by this change. Focused regressions
exercise the actual complete provider entry, whole upstream module retention,
wrong preimages, interrupted recovery, and the unchanged complete target
contract. These source tests do not constitute a completed vendor build or
Android runtime qualification.

## Software KeyMint and existing KMR keys

The x86_64 product selects the process-local Rust KeyMint service. Its patched
constructor reports SOFTWARE with the exact provider name
"Droidloom software KeyMint (KMR legacy v1)". The permission XML suppresses
hardware keystore, StrongBox, device-unique attestation and hardware usage-limit
features. This provider supplies software protection; it does not provide a TEE,
hardware attestation or verified-boot evidence.

The file android/keymint-software-compat/SOURCE.json records the pinned original
and projected hashes for the generic KMR hook, TA, nonsecure constructor, test
module and exact executable context. The updater applies these through its
existing source journal for complete product builds and both vendor-image
routes. The executable context selects the existing hal_keymint_default_exec
domain; no policy allow rules are added. Source drift or an existing injected
source file aborts the projection. Recovery restores the original source bytes
and removes added files.

The new generic hook defaults to Ok(false) and is consulted only when the
current TA actually reports Software. Only the selected nonsecure handler
overrides it. A historical blob must have the original V1 structure, one
TrustedEnvironment characteristic bucket, an empty KEK context and no secure
deletion slot. Its original characteristics, application ID/data and boot root
are authenticated with the original software provider before
KEY_REQUIRES_UPGRADE is returned. Unknown profiles and authentication failures
are errors. The normal upgrade operation authenticates again, changes only the
characteristic bucket to Software, retains authorizations and key material,
checks version monotonicity and encrypts a replacement with a fresh derivation
nonce. No caller key material is exported and the input blob is not deleted.

### Complete-system metadata and build entry

Stock Keystore2 does not replace stored authorizations when upgradeKey returns
a new encrypted blob. For the exact software provider above,
metadata/service.after.rs changes only the authorization security levels
returned by getKeyEntry, after its original permission checks. It preserves
the stored parameters, usage counts, UUID routing, certificates and certificate
chain bytes. It uses cached hardware information and keeps pure certificate
queries independent of KeyMint. Historical certificate attestations remain
historical signed statements; the migration does not turn them into hardware
evidence.

This metadata change is projected only by the complete normal system build:
android::build uses strict TARGETS, then coherent_images::run_normal builds
systemimage, system_extimage, productimage and vendorimage. With a prepared
ordinary-user workspace, the existing build-only staging entry is:

~~~console
droidloom-update --source /absolute/integrated-source package-stage \
  --work /absolute/prepared-work \
  --destination /absolute/prepared-work/package-candidate \
  --jobs 6
~~~

This uses /absolute/prepared-work/aosp-source and
/absolute/prepared-work/android-out. The four images are under
android-out/target/product/droidloom_x86_64/; the normal result is
android-out/droidloom-coherent-product-normal-result.json. The destination
must be a child of the workspace. The command stages a complete payload and
does not install it. Its complete-source, source/runtime identity and image
verification requirements must actually pass before any candidate exists.

The official-gsi-vendor-build and vendor-image-build commands do not rebuild
Keystore2. An existing official GSI therefore does not acquire this metadata
change. A vendor-only candidate can test fresh boot and keyblob continuity on an
isolated userdata copy, but cannot establish the complete metadata migration.
Never patch or relabel an old system image to imply that it contains the
matching source changes. Select and verify all four normal images as one cohort
when adopting the complete system.

### Focused compatibility validation

The exact-source projection tests can run against a directory containing the
five pinned original source files listed in SOURCE.json:

~~~console
DROIDLOOM_KEYMINT_PINNED_SOURCE=/absolute/pinned-source \
cargo test --locked -j 1 -p droidloom-update --bin droidloom-update \
  keymint_software::tests -- --include-ignored --test-threads=1
~~~

The integration test copies its inputs to a private temporary directory,
exercises the real projection and journal restoration, verifies that vendor
projection leaves system metadata unchanged, and checks that late source drift
fails before earlier files are mutated.

The projected Soong host test is droidloom_keymint_software_compat_test. It uses
the actual KMR TA and BoringSSL implementation with synthetic keys. It checks
new-key SOFTWARE reporting, authenticated old-blob upgrade, matching HMAC results
before and after upgrade and TA restart, idempotence, wrong root/hidden
parameters, ciphertext/nonce/characteristic corruption, unsupported contexts and
profiles, opt-in isolation, TEE isolation, version downgrade refusal and
preserved purpose/auth restrictions. The five system metadata tests are in the
existing keystore2_test module. Their Android build and execution remain
separate from source projection checks.

The official-GSI normal vendor producer includes this host test in its real
vendor Soong target list. Before packaging the paired system extension or
publishing its normal result, it checks the built x86_64 test ELF and resolves
its actual dynamic dependencies without inherited loader variables. BoringSSL
must resolve to libcrypto-host.so (and libssl-host.so when used) from the same
vendor output's host/linux-x86/lib64 directory. The producer checks the exact
ten-case inventory and then runs every case without a filter. It retains the
binary and runtime-library hashes, raw command logs, and exit statuses under
keymint-soong-host-test; a failed, missing, empty, ignored or filtered test run
blocks normal publication. Packaging an existing normal vendor also requires
this successful test result. This gate exercises synthetic KMR keys; device
boot, existing userdata continuity and application metadata still require their
own runtime qualification.

For host development, Cargo.host.toml, Cargo.host.lock and host_test_crypto.rs
record the standalone Cargo test configuration. It uses sibling aosp-keymint and
default-keymint directories containing the pinned sources with the exact
production changes. Only in that private test copy, the constructor's crypto
factory call is connected to host_test_crypto. Cargo uses the pinned KMR OpenSSL
backend; CMAC and ML-DSA return unsupported errors in that adapter. The normal
Android projection never installs this adapter and continues to use BoringSSL.
A Cargo pass is not a Soong build, Android boot, application KeyInfo result or
existing-userdata compatibility result.

Before adoption, use an isolated, reversible copy of the existing data and
metadata images. Verify keystore and vold startup, representative existing key
operations and app data, new keys, honest KeyInfo security levels, and restart
continuity. Do not reset credentials, change the original boot root, write the
original userdata, export keys or delete the rollback copy to force a pass.

### Offline Keystore metadata audit and clone experiments

The host tool in tools/droidloom-keystore-metadata is an independent Rust
workspace with its own committed Cargo.lock. Its bundled SQLite dependency
does not change the normal image builder's workspace dependency graph. Build
and test it explicitly:

~~~console
cargo test --locked -j 1 \
  --manifest-path tools/droidloom-keystore-metadata/Cargo.toml \
  -- --test-threads=1
cargo build --locked --release -j 1 \
  --manifest-path tools/droidloom-keystore-metadata/Cargo.toml
~~~

Use a stopped, detached, independently verified copy of the userdata filesystem
to obtain persistent.sqlite in a new private directory. Preserve the cold image,
its copy receipt, the database extraction receipt and the original userdata.
A database hash alone does not prove that a live SQLite database was quiescent.
This tool refuses any -wal, -shm or -journal file, including an empty file; it
does not attempt a blind multi-file snapshot or checkpoint an input database.
See SQLite's [WAL file semantics](https://www.sqlite.org/wal.html#the_wal_file)
and [online backup interface](https://www.sqlite.org/backup.html) for the
separate consistency requirements of a live database.

~~~console
droidloom-keystore-metadata audit \
  --input /absolute/private-cold-copy/input/persistent.sqlite \
  --workspace /absolute/private-cold-copy/audit-work
~~~

The input must be a regular, singly linked file with absolute, unaliased
ancestors. The workspace must already exist outside the input directory.
The tool opens the input only for ordinary read-only, no-follow, no-atime I/O;
it checks its identity and complete SHA-256 before and after copying and again
after analysis. SQLite only opens a new mode-0700 private child with an
independent mode-0600 database. Audits discard that child. There is no
in-place/output-database option, and existing output directories are never
selected for mutation.

The supported schema is the exact version-2 persistent schema in
system/security commit cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb.
Unknown versions, tables, indexes, triggers, views and changed table constraints
are refused. Reports contain counts, schema identity and logical table hashes;
they contain no aliases, key IDs, authorization values, certificates or blobs.
The certificate summary locates the X.509 extension with Android attestation
OID 1.3.6.1.4.1.11129.2.1.17 and counts its two historical security-level
declarations. It validates the enclosing DER structure and reports malformed
or unsupported data separately. It does not validate certificate signatures or
equate an old signed declaration with the current HAL's protection level.
The [official attestation schema](https://source.android.com/docs/security/features/keystore/attestation)
defines those public fields. Existing certificates are preserved byte for byte.

Candidate selection is deliberately separate from backend identity. Only live
client keys in APP/SELINUX domains, routed through the default UUID, with one
current nonempty key blob and consistent optional blob UUID can be considered.
Pure certificate entries, super keys, unreferenced entries, other UUIDs and
ambiguous StrongBox/unknown authorization buckets are excluded. Only existing
TrustedEnvironment authorization cells are candidates for Software; parameter
values, existing Software/Keystore rows and their order remain intact. A UUID
is only the big-endian integer form of the routing security level in the
[pinned database source](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/database.rs#319).
It is neither a provider identity nor proof that a key blob authenticates.

A separate prepare-clone command can retain a new private experiment:

~~~console
droidloom-keystore-metadata prepare-clone \
  --input /absolute/private-cold-copy/input/persistent.sqlite \
  --workspace /absolute/private-cold-copy/clone-work \
  --evidence /absolute/reviewed-evidence/envelope.json
~~~

The exact version-1 evidence structures are in src/evidence.rs. The envelope
contains schema, input_sha256 and three objects named snapshot_receipt,
legacy_provenance and replacement_observation. Each object is an absolute
regular file path plus its SHA-256. The snapshot receipt must bind the same
database to an isolated-offline-filesystem-copy receipt with no SQLite
sidecars. Legacy provenance must name aosp-rust-keymint-nonsecure, the exact
pinned KeyMint/interface source commits, its actual default-service executable
and its custody receipt. Replacement observation must identify the real
IKeyMintDevice/default Binder getHardwareInfo call, security_level 0, exact
implementation name "Droidloom software KeyMint (KMR legacy v1)", source commit,
actual executable, vendor image and runtime receipt. Those artifact paths and
digests are checked. Decoded JSON and its digest come from the same read buffer.
These are externally reviewed observations: matching file bytes is not an
independent attestation of their assertions. Never manufacture a replacement
runtime observation from a source selection or from the default UUID.

Preparation updates only the selected security_level cells within one private
SQLite transaction. Before commit, it verifies the exact expected row count,
integrity_check and a typed, rowid-ordered hash of every value in all seven
persistent tables plus sqlite_schema. Its expected hash differs only at those
selected cells. Alias, namespace, UUID, grants, usage counts, key metadata,
blob metadata, encrypted key blobs and certificates must all remain identical.
A failed postcondition rolls back the whole transaction. Successful output is
a fresh private directory containing persistent.sqlite and CLONE-EXPERIMENT.json;
the input remains untouched. Repeating the correction with properly rebound
snapshot evidence changes zero cells. The tool does not install that clone.

#### Authorization-consumer review and runtime boundary

The following review is scoped to the pinned source, not an assertion that a
different prebuilt system has already been runtime-qualified.

| Concern | Pinned implementation and implication |
| --- | --- |
| Stored security level | [KeyParameter](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/key_parameter.rs#1058) keeps the field private. Its accessor is used for DB storage; into_authorization exposes it to clients, while into_key_parameter returns the original parameter value. |
| Authentication, purpose and lock state | [authorize_create](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/enforcements.rs#488) inspects parameter values, including USER_SECURE_ID, auth type, timeout, purpose and unlocked-device requirements. HAT matching does not branch on the stored security-level column. |
| Super encryption | [super_encryption_required](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/enforcements.rs#743) uses parameter values, domain and flags; [unwrap and begin](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/security_level.rs#342) still require the actual super key and KeyMint operation. |
| Persistent usage count | [check_and_update_key_usage_count](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/database.rs#2299) selects and decrements data by key/tag and deletes an exhausted key. The level column does not select or reset the counter. |
| Permissions and grants | [check_key_permission](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/permission.rs#340) uses caller UID, descriptor domain/namespace, grant access vector and SELinux. These values are preserved. |
| Credential invalidation | [auth-bound deletion](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/database.rs#2748) and [SID-dependent app selection](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/database.rs#3095) inspect USER_SECURE_ID values, not the level column. |
| Blob upgrade | [store_upgraded_keyblob](https://android.googlesource.com/platform/system/security/+/cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb/keystore2/src/security_level.rs#1003) re-super-encrypts when required and replaces the encrypted blob, without refreshing SQL authorizations. |

The production-consumer scan also covered the parameter type's derived Eq/Ord
and serialization uses. The DB-loaded enforcement paths inspect tags/values;
changing this column does not replace those parameter values or relax those
checks. This source review and the clone's content invariants do not constitute
an actual CP3A permission or authentication test.

MaxUsesPerBoot is checked by the actual KMR
[operation begin path](https://android.googlesource.com/platform/system/keymint/+/cfeefc94bf8c4f19d19dca193d376a1fc05e8e3e/ta/src/operation/begin.rs).
The upstream TA derives its per-boot counter key ID from the entire encrypted
blob in [key_id/update_use_count](https://android.googlesource.com/platform/system/keymint/+/cfeefc94bf8c4f19d19dca193d376a1fc05e8e3e/ta/src/lib.rs).
An ordinary re-encryption upgrade therefore changes that identity. This
migration targets a cold-start data-copy qualification and makes no claim of
preserving a prior count identity across upgrade in one already-running TA.
The metadata tool itself preserves every blob byte and existing SQL count.
The hardware usage-limit feature remains disabled for the software provider.

No offline blob authentication is performed, even for apparently unwrapped
blobs. In particular, outer super encryption cannot be authenticated without
the proper live Keystore context. Existing keys must still authenticate their
original KMR blob through the actual HAL upgrade; the metadata operation cannot
make a bad key usable. Before any adoption, a separate isolated Android run must
verify stock Keystore/vold startup, honest KeyInfo, representative existing key
operations, credential/lock-state and HAT refusals, purpose and usage/max-use
refusals, caller/grant refusals, app data continuity and restart/idempotence.
The tool always reports production_approved=false and never writes the original
userdata or turns source/host tests into runtime evidence.

## Export the normal Ubuntu host release

Use the normal host-stage producer with --archive-output to preserve the empty
var/lib/droidloom-mac-calibration StateDirectory as well as regular payload files.
The flag requires --board-policy-inputs and names a fresh direct child of --work.

The producer checks the clean source identity before and after normal compilation,
rejects linked or writable payload members, and requires the original state
directory to be empty with mode 0700. It exports a reproducible archive with root
ownership, then extracts it privately and checks every file, permission and the
empty directory. HOST-STAGE.json records both files and directories; RELEASE.json
binds the final archive and manifest hashes. An existing output is never replaced.

The normal container-host build also compiles the Wayland presenter, application
catalog and doctor with the same locked source as the production supervisor. The
archive owns fresh `/usr/bin/droidloomctl`, `droidloom-wayland`,
`droidloom-applications` and `droidloom-doctor` files, so existing XDG launcher
commands cannot silently retain an earlier binary. The public and production
control clients have identical bytes. This stage does not install the legacy
user service that starts and stops `droidloomd.service`; production desktop
lifecycle and authenticated presenter registration require their own qualification.

A file-only archive drops the empty StateDirectory and is not a valid input to
the original Ubuntu calibration qualifier. Packaging success does not establish
boot, calibration, Android readiness or application acceptance.
