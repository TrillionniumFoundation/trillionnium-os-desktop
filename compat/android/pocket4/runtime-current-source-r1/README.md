# Complete current producer source and fresh CI

This directory reconstructs the complete 2,250-file producer source from its verified committed parent and exact formatted Launch, MAC, task-control observation, selected-lock identity, Settings AddAccount and Profiling overlay. It runs the ordinary Linux tests and normal release builds in a new CI work directory. It contains source and verification code; it does not require earlier source capsules, private caches, old ELF files, APK collections or a production Android image.

| Identity | Value |
| --- | --- |
| Parent source commit recorded inside the baseline capsule | `61a38baa745483fbfb757466a1cf352febc20552` |
| Parent Git tree | `db6249e80209abeda8000eeced6d045a1d57e0a2` |
| Complete current source Git tree | `099efb9fadd27a8dd073ce935b89109ea41ddb36` |
| Current source files / bytes | 2,250 / 41,593,433 |
| Baseline archive members | 2,224: parent source files, portable manifest and original commit body |
| Baseline archive SHA256 | `7ab244365184ef670c244b6a0ed75857c6f942897f3fc59c00e6375e76f51816` |
| Formatted cumulative overlay | 50 complete path bodies / 532,672 compressed bytes |
| Overlay SHA256 | `bffc722c1171c5e472aafb21176963052cf9fb529acb85fa10fc5afdca787009` |

The Git commit containing this public wrapper is a different identity from the parent source commit above. `verify.py` first checks all 2,222 parent bodies, modes, Git blobs, the parent tree and original commit object. It then verifies the complete pinned overlay, requires all 50 before-rows to match that parent, verifies every replacement or added body and mode, and reconstructs the exact 2,250-file current Git tree. The output is a self-contained source directory. The source report records `source_parent_commit` and leaves `source_commit` null because this overlay has no newly created producer commit. It does not copy old runtime evidence into a fresh CI result.

The XZ overlay must be one complete frame with no trailing data and expands to at most 4 MiB under a 64 MiB decoder memory limit. The actual expanded overlay is 4,025,575 bytes. Undeclared members, missing bodies, unsafe paths, changed parent rows, wrong modes, sizes, digests, Git objects or complete tree identities are rejected. The repository source-integrity check verifies both compressed binary inputs by full size and SHA256.

The current increment changes exactly 11 producer paths relative to the accepted Settings source tree `f733276e866388548b9995c8040d24f1799057fe`: four existing build/consumer files and seven new Profiling source-repair inputs. It applies the official Profiling defensive patch to the exact locked revision, registers the original Java preimage in the existing durable restore journal, requests the normal `com.android.profiling` and `service-profiling` targets, and requires the resulting APEX/JAR/DEX to match their normal provider and image consumers. The fifth APEX has an exact member contract. The original 651-project lock and strict dependency/neverallow gates remain unchanged. All 2,239 other producer files and 39 prior overlay bodies remain unchanged.

The existing build flow restores the original source before accepting its normal output receipt. The Profiling component cannot substitute a standalone JAR or an older APEX for the selected normal product output. This source-level repair does not modify the separately captured CP3A image. Its observed `sendAnomalyProfile` method lacks the validation call required by the official patch; that static component observation does not establish whole-CVE applicability or exploitability. A complete Android build and final APEX/JAR/DEX semantics still require independent verification. The earlier Settings AddAccount repair and its original-provider restoration contract remain in the same source.

This exact formatted source has an independently accepted component result for six new Profiling updater cases, four affected existing cases, and one normal updater release: **10 exact ordinary tests and 1 normal release**, with 22 commands, 44 complete streams and all 25 recorded subjects retired. Its complete updater catalog contains 480 names; only those ten selected cases ran in that component. The original outer cgroup path was not captured; recorded subjects, both unit scopes and the native cgroup were checked. The accepted source map contains 2,250 files and 41,593,433 bytes, and all 11 published producer bodies come from the actual formatted output.

Fresh full CI for this tree remains pending until the job below finishes and its complete artifact is verified. Earlier [f733 CI run 43854907113](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/43854907113), [5bd6 CI run 43804416572](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/43804416572), and [511 CI run 43788698194](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/43788698194) remain evidence for their original source trees only. The selected-lock check still rejects relabelling the actual CP2A source lock as CP3A; this repair does not create the missing CP3A source mapping.

The preserved task-control observation code records three distinct identities: the held socket inode SELinux xattr, the connected socket peer security bytes returned by the active LSM, and the separately authenticated message sender process SELinux context. `SO_PEERSEC` success does not establish that its opaque bytes identify a SELinux domain. Earlier component results include 13 focused supervisor cases and two binaries, and 14 MAC cases and two binaries with a separate 315-decision offline policy component preserving the original 211 tuples under strict `neverallow`. None receives fresh credit below. Selected provider and labels, socket creation rule, policy loading, positive MainReady and ExecutionAdmission remain open. Application runtime acceptance remains **0/42**.

## Fresh CI scope

The checked-in metadata and catalogs define 28 workspace packages, 49 test harnesses, 1,323 listed cases and 19 normal binary targets. A successful new CI run must execute **1,293 ordinary cases**, preserve **30 existing ignored cases**, and build **19 normal release binaries** from the freshly reconstructed source. The catalog retains all parent identities and adds exactly the six Profiling updater cases. All other 48 catalogs and all 30 ignored names remain unchanged. No historical test or ELF receives fresh credit.

| Execution group | Fresh ordinary cases | Ignored cases | Command bound |
| --- | ---: | ---: | --- |
| Updater cases in `UPDATER-EXACT64.json` | 64 | 0 | Each complete name, `--exact`, 60 seconds |
| Remaining updater catalog | 415 | 1 | One 300-second harness run; filtered catalog must first match the exact difference |
| Other 48 harnesses | 814 | 29 | 300 seconds per harness, including zero-test harnesses |
| Normal release builds | 19 binary artifacts | — | 900 seconds per package batch |

The updater package and the other 27 packages form two disjoint build batches. Test compilation and normal release compilation each use that partition, with a complete artifact-to-metadata join for each batch and an exact union check afterward. A fresh Cargo target directory is mandatory. The runner verifies the CLI executable paths embedded in integration harnesses and accounts for Cargo's original hardlink aliases. All ordinary harnesses use one test thread; Cargo uses one build job. The overall runner deadline is 5,400 seconds, including final artifact and source checks.

The terminal verifier counts the complete parent harness exactly once. The runner passes the complete name set already matched to that actual ELF's listing. The two existing fakeroot tests start a same-name, one-test child harness: each child must finish successfully with 479 filtered cases from the current 480-case updater catalog, and its parent must then finish successfully. The verifier derives this count from the caller's verified catalog, never from the child summary. Child records add no test credit. The three known image tests may emit their pinned EROFS 1.9.4 output in those exact positions. Unknown, recursive, duplicate, failed or incomplete child records and contradictory terminal counts are rejected. Unmodified historical 465-case fragments are tested only against their separately pinned original name set; the new 480-case transcript used by a Python control is explicitly synthetic.

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

`test_runner.py` checks catalog, artifact and hardlink rejection and uses actual short child processes for timeout, PIDFD-acquisition-failure and proc-stat-failure cleanup. It does not replace these operations with simulated process reports. The 13 verifier controls retain the previous method identities and original observed transcript constants, update their current-catalog expectations to all 480 exact names, and preserve catalog-name, nested-summary and complete-overlay rejection checks. The nine runner controls and their child-retirement behavior are unchanged. These Python controls are separate from the 1,293 Rust ordinary cases.

The CI artifact contains replay/runner/dependency reports, command stdout/stderr and EROFS configure evidence. It excludes Cargo caches, compiled target directories, private operator journals and APKs. The complete source bookend must still match after testing. An individual test pass cannot override a failed controller, expired deadline, changed source or unretired child.
