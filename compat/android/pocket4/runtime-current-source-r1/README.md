# Complete current producer source and fresh CI

This directory reconstructs the complete 2,271-file producer source from its verified committed parent and the cumulative Launch, MAC, task-control observation, selected-lock identity, Settings AddAccount, Profiling, Telephony SMS and Telephony MMS overlay. The MMS source has passed the isolated normal component qualification described below. Fresh full CI, Android and runtime qualifications remain separate. The ordinary Linux CI workflow reconstructs source and builds fresh artifacts; it does not reuse private caches, old ELF files, APK collections or a production Android image.

| Identity | Value |
| --- | --- |
| Parent source commit recorded inside the baseline capsule | `61a38baa745483fbfb757466a1cf352febc20552` |
| Parent Git tree | `db6249e80209abeda8000eeced6d045a1d57e0a2` |
| Complete current source Git tree | `84d74983ea2c6f3ad131272efb0ac939d9ddcf55` |
| Current source files / bytes | 2,271 / 42,004,577 |
| Baseline archive members | 2,224: parent source files, portable manifest and original commit body |
| Baseline archive SHA256 | `7ab244365184ef670c244b6a0ed75857c6f942897f3fc59c00e6375e76f51816` |
| Formatted cumulative overlay | 71 complete path bodies / 593,640 compressed bytes |
| Overlay SHA256 | `a611c9ecf1f1d26b167920d5b5e25b5090a5a293020871e5d8fab835249d43c0` |

The Git commit containing this public wrapper is a different identity from the parent source commit above. `verify.py` first checks all 2,222 parent bodies, modes, Git blobs, the parent tree and original commit object. It then verifies the complete pinned overlay, requires all 71 before-rows to match that parent, verifies every replacement or added body and mode, and reconstructs the exact 2,271-file current Git tree. The output is a self-contained source directory. The source report records `source_parent_commit` and leaves `source_commit` null because this overlay has no newly created producer commit. The compressed overlay and external capsule inventory are pinned separately; neither transfers historical execution credit into a new CI result.

The XZ overlay must remain one complete frame with no trailing data and expand to at most 5 MiB under the unchanged 64 MiB decoder memory limit. The final MMS expanded overlay is 4,582,781 bytes, leaving 660,099 bytes below the existing cap. Its complete SHA256 is `f3783b943e5586465c33161fb662dce0991eecf9a433781b256926478cf57c4c`. The compressed overlay is 593,640 bytes, SHA256 `a611c9ecf1f1d26b167920d5b5e25b5090a5a293020871e5d8fab835249d43c0`. Undeclared members, missing bodies, unsafe paths, changed parent rows, wrong modes, sizes, digests, Git objects or complete tree identities remain rejected. The repository source-integrity check verifies the exact compressed size and SHA256.

The current increment changes exactly 13 producer paths relative to the accepted Telephony SMS source tree `af0ab8e0dd5e6d7ead400962dc86f2f4831de653`: `android.rs`, `coherent_images.rs`, `coherent_images_tests.rs`, and ten new Telephony MMS repair inputs. All three modified paths already occur in the previous 61-file overlay, so its exact union is 71 paths: 58 unchanged bodies, three replacements and ten additions. The other 2,258 producer files remain unchanged. The defensive production hunk is from [official AOSP MmsProvider change 95af247d92b5c0b5d02dfa5ca2a62310e4cedbd6](https://android.googlesource.com/platform/packages/providers/TelephonyProvider/+/95af247d92b5c0b5d02dfa5ca2a62310e4cedbd6). Only the production hunk is adapted to the exact locked preimage; no provider-request test or real MMS access is ported or executed.

The existing normal producer journals the one original MmsProvider Java file before patching and checks its bytes, mode and mtime on restoration. Android.bp, both manifest bodies and ProviderUtil.java are exact read-only dependencies. The request retains the complete strict user build, unchanged 651-project lock and original dependency/neverallow gates; it binds the normal TelephonyProvider module to `system/priv-app/TelephonyProvider/TelephonyProvider.apk` in the final system inventory. A different provider variant or missing required APK fails. The module-info check may include other ordinary installed paths; it does not claim to reject every additional installed entry. The final image inventory still binds the one exact required APK. The inherited HSUM selection is unchanged and this component does not qualify an HSUM output.

This exact source has an independently accepted MMS component result for six new ordinary Rust cases and four affected existing cases: **10 exact ordinary tests and 1 normal updater release**, with 22 commands, 44 complete streams and all 25 recorded subjects retired. Formatting and format checking ran successfully; `FORMAT.diff` is empty, and the actual source remains tree `84d74983ea2c6f3ad131272efb0ac939d9ddcf55`, with 2,271 files and 42,004,577 bytes. The complete updater catalog contains 492 names; this component executed ten, left 481 other ordinary cases unexecuted, and did not execute its one ignored case. The tests cover static patch placement and exact inputs, journal restoration and failure, strict requests, synthetic artifact metadata and completion scope. The historical af0 SMS result and the prior MMS fixture, resource and patch-header failures remain evidence for their original attempts. The original outer cgroup path was not captured; the recorded subjects, both unit scopes and exact native cgroup were checked. No Android provider request or TelephonyProvider APK build or execution occurred. The selected CP3A MmsProvider binary remains unreviewed under the unchanged R24 map; complete-workspace, fresh public CI, Android, DEX semantics, whole-CVE, signing and runtime qualifications are not established by this component.

Fresh full CI for this MMS source tree remains pending until the job below finishes and its complete artifact is verified. Accepted [SMS CI run 43924822321](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/43924822321) remains bound to af0 and its original 1,299 ordinary cases. Earlier [Profiling CI run 43889541305](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/43889541305), [f733 CI run 43854907113](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/43854907113), [5bd6 CI run 43804416572](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/43804416572), and [511 CI run 43788698194](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/43788698194) remain evidence for their original source trees only. The selected-lock check still rejects relabelling the actual CP2A source lock as CP3A; this repair does not create the missing CP3A source mapping.

The preserved task-control observation code records three distinct identities: the held socket inode SELinux xattr, the connected socket peer security bytes returned by the active LSM, and the separately authenticated message sender process SELinux context. `SO_PEERSEC` success does not establish that its opaque bytes identify a SELinux domain. Earlier component results include 13 focused supervisor cases and two binaries, and 14 MAC cases and two binaries with a separate 315-decision offline policy component preserving the original 211 tuples under strict `neverallow`. None receives fresh credit below. Selected provider and labels, socket creation rule, policy loading, positive MainReady and ExecutionAdmission remain open. Application runtime acceptance remains **0/42**.

## Fresh CI scope

The prepared metadata and catalogs define 28 workspace packages, 49 test harnesses, 1,335 listed cases and 19 normal binary targets. A successful new CI run must execute **1,305 ordinary cases**, preserve **30 existing ignored cases**, and build **19 normal release binaries** from the freshly reconstructed source. The catalog retains all parent identities and adds exactly the six Telephony MMS updater cases. All other 48 catalogs and all 30 ignored names remain unchanged. No historical test or ELF receives fresh credit.

| Execution group | Fresh ordinary cases | Ignored cases | Command bound |
| --- | ---: | ---: | --- |
| Updater cases in `UPDATER-EXACT64.json` | 64 | 0 | Each complete name, `--exact`, 60 seconds |
| Remaining updater catalog | 427 | 1 | One 300-second harness run; filtered catalog must first match the exact difference |
| Other 48 harnesses | 814 | 29 | 300 seconds per harness, including zero-test harnesses |
| Normal release builds | 19 binary artifacts | — | 900 seconds per package batch |

The updater package and the other 27 packages form two disjoint build batches. Test compilation and normal release compilation each use that partition, with a complete artifact-to-metadata join for each batch and an exact union check afterward. A fresh Cargo target directory is mandatory. The runner verifies the CLI executable paths embedded in integration harnesses and accounts for Cargo's original hardlink aliases. All ordinary harnesses use one test thread; Cargo uses one build job. The overall runner deadline is 5,400 seconds, including final artifact and source checks.

The terminal verifier counts the complete parent harness exactly once. The runner passes the complete name set already matched to that actual ELF's listing. The two existing fakeroot tests start a same-name, one-test child harness: each child must finish successfully with 491 filtered cases from the current 492-case updater catalog, and its parent must then finish successfully. The verifier derives this count from the caller's verified catalog, never from the child summary. Child records add no test credit. The three known image tests may emit their pinned EROFS 1.9.4 output in those exact positions. Unknown, recursive, duplicate, failed or incomplete child records and contradictory terminal counts are rejected. Unmodified historical 465-case fragments are tested only against their separately pinned original name set; the new 492-case transcript used by a Python control is explicitly synthetic.

Documentation tests, examples, the 30 ignored cases and positive hardware-specific branches are outside this result. A generic host test may retain an existing platform or permission early return. The report keeps `full_workspace_qualified`, `runtime_qualified` and `production_ready` false. Neither ordinary tests nor release compilation establish Android C++ ABI compatibility, ART/APEX/linker/MAC closure, a complete Android image, Play eligibility, APK freshness or the 42 application runtime contracts.

## Host requirements and dependency preparation

Use a disposable Ubuntu 24.04 amd64 CI host as a non-root user, with Python 3, the runner's preinstalled `rustup`, passwordless `sudo` for dependency installation, and at least four allowed logical CPUs. Both preparation and the Rust runner use the first two CPUs and leave at least two others outside their affinity. Do not set `RUST_MIN_STACK`: the ordinary stack must exercise the production heap-buffer fix.

The host must support Linux PIDFD, `/proc/self/task/*/children`, local Unix sockets and SCM_RIGHTS, a private D-Bus daemon and SysV fakeroot. Missing process-observation facilities are failures, not test skips. Use ordinary execute-enabled temporary storage with working hardlinks, symlinks, chmod and nanosecond timestamps. Keep the extracted source at the same absolute path while compiling and running its harnesses.

`prepare_ci.sh` installs the explicitly listed Ubuntu build/test dependencies, installs Rust 1.93.0 through the existing rustup client, and builds EROFS tools under its new private `erofs/` prefix. It does not compile the producer or install an Android system. The script has a 1,800-second deadline, finite per-command bounds, one make job, PIDFD-backed child cleanup, complete command logs and a `DEPENDENCIES.json` manifest of resolved package versions and tool identities. Preparation failures stay failures; a preflight failure can occur before the manifest exists.

The EROFS source is the Debian-published original **erofs-utils 1.9.4** archive:

- URL: <https://deb.debian.org/debian/pool/main/e/erofs-utils/erofs-utils_1.9.4.orig.tar.gz>
- Size: **273,489 bytes**.
- SHA256: **`7d135aa2550326a5acf20f53c518aea5a8900015ce50700044e40f818c31dd80`**.
- Published checksum record: <https://tracker.debian.org/news/1788045/accepted-erofs-utils-194-1-source-into-unstable/>.
- Upstream build instructions: <https://erofs.docs.kernel.org/en/latest/install.html>.

The size and whole SHA256 must match before extraction. The private build requires actual LZ4HC and xattr configure features, then verifies all three installed tool versions and identities. This is dependency preparation, not an image-preservation result. The source's ordinary EROFS tests still need to exercise `fsck.erofs --preserve --xattrs`, LZ4HC generation, and content, ownership, type, mode, links, timestamps and xattr preservation. In particular, creating an EROFS image or printing `1.9.4` alone does not establish the `security.selinux` preservation contract.

The ext4 fixture uses the fixed `/usr/sbin/mke2fs`, `/usr/sbin/debugfs` and `/usr/sbin/e2fsck` paths. It builds and checks a private 32 MiB synthetic image; no production image is required. `fakeroot-sysv` is exposed through a private PATH copy of the matching distro script, which retains its `/bin/sh`, `/usr/bin/faked-sysv` and installed SysV preload-library dependencies. Individual tests create their own fakeroot sessions. The outer suite must not inherit fake-root or private test-branch markers.

The runner removes inherited compiler flags, compiler wrappers, Cargo target/profile overrides, pkg-config overrides, preload/library paths and test markers before setting its fixed environment. It assigns new `CARGO_HOME`, `CARGO_TARGET_DIR` and `TMPDIR` directories. Cargo first performs a separately recorded locked fetch; every build and metadata command thereafter is locked and offline. Resolved Ubuntu dependency versions are recorded rather than asserted identical to an earlier private host.

## Running the same job

The public location is `compat/android/pocket4/runtime-current-source-r1/`. Obtain `CURRENT_SOURCE_INVENTORY_SHA256` from the reviewed workflow for the same public commit. It pins the complete `FILES.sha256` file, rather than trusting an inventory and its alleged hash from the same unreviewed directory. Never substitute an older inventory after editing these files.

```bash
set -euo pipefail
capsule="$PWD/compat/android/pocket4/runtime-current-source-r1"
: "${CURRENT_SOURCE_INVENTORY_SHA256:?use the reviewed workflow pin}"
: "${RUNNER_TEMP:?use an absolute private CI temporary directory}"
printf '%s  %s\n' "$CURRENT_SOURCE_INVENTORY_SHA256" "$capsule/FILES.sha256" | sha256sum --check --status
(cd "$capsule" && sha256sum --quiet -c FILES.sha256)
python3 -I -B "$capsule/test_verifier.py"
python3 -I -B "$capsule/test_runner.py"
python3 -I -B "$capsule/verify.py" \
  --inventory-sha256 "$CURRENT_SOURCE_INVENTORY_SHA256" \
  --output "$RUNNER_TEMP/current-producer" \
  --report "$RUNNER_TEMP/current-source-replay.json"
bash "$capsule/prepare_ci.sh" --work "$RUNNER_TEMP/current-dependencies"
python3 -I -B "$capsule/run_ci.py" \
  --inventory-sha256 "$CURRENT_SOURCE_INVENTORY_SHA256" \
  --producer "$RUNNER_TEMP/current-producer" \
  --work "$RUNNER_TEMP/current-ordinary" \
  --report "$RUNNER_TEMP/current-ci.json" \
  --erofs-prefix "$RUNNER_TEMP/current-dependencies/erofs"
```

All destination paths must be new. Do not reuse failed work directories or modify the frozen source to make a run pass. `-I -B` prevents ambient Python imports and generated bytecode from changing capsule membership. The workflow wraps verification and Python controls in additional finite timeouts and preserves evidence with an `always()` upload step.

`test_runner.py` checks catalog, artifact and hardlink rejection and uses actual short child processes for timeout, PIDFD-acquisition-failure and proc-stat-failure cleanup. It does not replace these operations with simulated process reports. The 13 verifier controls retain the previous method identities and original observed transcript constants, update their current-catalog expectations to all 492 exact names, and preserve catalog-name, nested-summary and complete-overlay rejection checks. The nine runner controls and their child-retirement behavior are unchanged. These Python controls are separate from the 1,305 Rust ordinary cases.

The always-preserved evidence artifact contains replay/runner/dependency reports, command stdout/stderr and EROFS configure evidence. It excludes Cargo caches, compiled target directories, private operator journals and APKs. The proposed separate success-only artifact preserves the 19 explicit normal binary paths and the actual `current-ci.json`; its names match the unchanged EXPECTED-BINS inventory and it receives no historical ELF credit. The complete source bookend must still match after testing. An individual test pass cannot override a failed controller, expired deadline, changed source or unretired child.
