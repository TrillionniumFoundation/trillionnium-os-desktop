# Fixed original Agentd build review

This review keeps original Hepta pinned to
`f8c9419df6ddeb36ff8b522a50219981fb8d9345`. The successful real Rust 1.95 metadata,
original-owner probe `cargo check`, and original Agentd `cargo check` runs record
the same clean original checkout before and afterward. Metadata resolution and
the original-lock subset check passed; the unchanged probe API and original
Agentd/App Server graph both passed their actual compiler checks.
The final executable link and original-process qualification remain
**`not_run`**. The earlier manifest-only findings and local resource snapshot
below are historical; they do not describe the later provisioned environment.

## Corrected external workspace resolver

The original [`codex-rs/Cargo.toml:191`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/Cargo.toml#L191)
sets `resolver = "2"`. The external probe package previously wrote an empty
`[workspace]` below its edition-2024 package. A separate root cannot inherit the
original workspace setting, so its implicit resolution policy could diverge
from the binary's original workspace.

`prepare_runner` now copies the explicit resolver along with the original
profiles and rebased patch entries. A missing, unknown or incorrectly typed
resolver fails before creating the generated runner directory. The three
manifest-generation tests use the actual verified original source. The valid
case first failed against the previous gate and then passed after correction;
the two negative cases also passed. Source-bound raw evidence is in
[evidence/2026-10-17-build-manifest](evidence/2026-10-17-build-manifest/README.md).
Those three Python tests do not invoke Cargo. The separate real Cargo
resolution below supplies a later prerequisite result; it does not retroactively
change the qualification of the manifest-test receipt.

## Real resolution and compiler checks

The source-bound records are archived in
[evidence/2026-10-17-original-probe](evidence/2026-10-17-original-probe/README.md).
They preserve failed attempts as well as the completed narrow check:

| UTC on 2026-10-17 | Attempt | Recorded result |
| --- | --- | --- |
| 12:11:26–12:11:34 | Isolated official Rust 1.95 minimal toolchain bootstrap | Installation exit 0; no Agentd execution |
| 12:26:05 | First probe metadata attempt | Exit 101: `rustc -vV` could not be executed because the temporary command environment could not find it; stdout was empty |
| 12:26:38–12:26:54 | Corrected probe metadata attempt | Exit 0; 733 packages and 733 resolve nodes; shared dependency identities/checksums remained in the original lock |
| 12:30:05–12:30:06 | First probe compile-check wrapper | Prerequisite selection assertion failed before any Cargo check command or resource sample was recorded |
| 12:31:09–12:36:39 | Corrected original-owner probe compiler check | Rust 1.95 `cargo check --locked --profile dev-small --manifest-path ... -j1` exited 0; Cargo reported 5m 28s; original source and resolved lock unchanged |
| 12:39:47–12:46:37 | Original Agentd compiler check | Rust 1.95 checked the unchanged `codex-hepta-agentd` bin selection with `--no-default-features -j1`; exit 0, Cargo reported 6m 48s; original source and lock unchanged |

The successful command used the generated external root, its explicit
`resolver = "2"`, the unchanged original owner libraries, and Rust 1.95. The
resolved lock SHA256 is
`9d1de5fab85aa6400a1d178e1791b3b01453b1b2b37e2b986bbe97cad55ceec1`.
The original checkout, tree and lock stayed clean and identical before and
afterward. The new external probe package is the only package identity allowed
by the subset check to be absent from the original lock.

**733 is the metadata result for this external Supervisor-library probe.** The
command did not specify `--filter-platform`; its package/node count is not an
Agentd-only minimum graph, a count of Rust compilation units, or a measurement
of actual build memory or disk requirements. It does not include a successful
original binary build, link, daemon launch, Session connection or process
assertion. The raw 3,539,591-byte metadata output is stored as lossless gzip with
both original and compressed SHA256 values. Receipts, stderr, generated
manifest and resolved lock retain their original bytes and absolute paths.

The successful check compiles/type-checks the actual external probe against the
original owner-library graph. It confirms the reviewed public API calls without
replacing an upstream module or DTO. Its raw log retains unused-patch warnings
and the original Supervisor library's five warnings. It does not qualify a
linked runnable probe/Agentd ELF or any runtime assertion. The separate wrapper
reserved 700 MiB of temporary filesystem space and imposed a 900-second deadline;
these bounds do not replace the full gate's 8 GiB admission estimate.

The check receipt contains 330 resource samples. `memory.current` is sampled
usage of the whole cgroup, while `memory.peak` is its accumulated high-water
mark, including earlier activity. Neither is a measured peak for this compiler
process. The minimum observed filesystem free space was 2,553,098,240 bytes;
the cache was already warm from metadata resolution. These measurements do not
establish the original Agentd link/build resource requirement.

The later Agentd command ran from the untouched `codex-rs` workspace:

```sh
rustup run 1.95.0 cargo check --locked --profile dev-small \
  --no-default-features -p codex-hepta-agentd --bin codex-hepta-agentd -j1
```

Its actual log includes the original App Server and Agentd crates and finishes
successfully, with upstream warnings retained. This closes the original binary
source's compiler-check prerequisite; it does not link the final executable or
launch a process. It reused the warm target from the passed probe check. The
receipt records 410 resource samples and 1,234,903,040 final/minimum-observed
free bytes. Whole-cgroup counters still cannot be attributed to this build;
`maximum_observed_nonreclaimable_bytes` is the wrapper's configured 7 GiB stop
threshold, not a measured per-process maximum. The full 8 GiB build/runtime
gate remains separate and unexecuted.

## Minimum original selection and build products

The Agentd manifest has no control-only build feature. Its
`--no-default-features` selection disables `production-cognitive-write` while
retaining the real App Server, runtime and owners. The command remains:

```sh
rustup run 1.95.0 cargo build --locked --profile dev-small \
  --no-default-features -p codex-hepta-agentd --bin codex-hepta-agentd -j1
```

The original `dev-small` profile inherits dev, uses optimization level 0, no
debug information and stripped symbols. The harness disables incremental
compilation and uses one Cargo job. It keeps the observer under Rust 1.88 and
its own committed lock, separate from the original 1.95 graph. The original
binary and external library probe share an external target directory, although
Cargo may need different dependency artifacts for their different feature
graphs. A shared directory is not a promise that every artifact will be reused.

The probe root copies the original lock as a seed, resolves its added external
package, and rejects any shared dependency identity or checksum absent from
the original lock before its `--locked` build. The original binary itself
always uses the untouched original workspace lock. Actual resolution and the
subset check passed for the archived external root above. Every new full-gate
invocation still resolves and checks its own root; copying the seed alone does
not qualify that later resolved graph.

| Successful build product | Path below the new work directory |
| --- | --- |
| Original Agentd ELF | `original-target/dev-small/codex-hepta-agentd` |
| Original-owner library probe ELF | `original-target/dev-small/hepta-original-observer-probe` |
| Read-only observer ELF | `observer-target/debug/hepta-observe` |
| Generated external manifest and resolved lock | `probe/Cargo.toml`, `probe/Cargo.lock` |
| Build/resolve diagnostics | Four named build/resolve `.log` files at the work root |
| Runtime observations | `original_agentd_process_probe.log` |

Only a completed `--execute` run whose report has both `status: passed` and
`live_agentd_acceptance: passed` qualifies original process observations. The
preflight exit code alone cannot qualify or authorize packaging a successful
original runtime result.

## Dependency and resource findings

A read-only walk of the fixed workspace manifests found **144 local crates**
reachable from Agentd through nonoptional top-level normal/build dependencies,
and **41** from the original Supervisor library. Including all target tables
for the Agentd walk raised its count to **145**; none of those local edges was
optional. These are manifest-walk counts, not Cargo's platform/feature-resolved
package counts. They omit registry transitive packages and must not be used as
a measured compilation size or memory requirement.

Neither Agentd manifest walk reached `code-mode-runtime` or `v8-poc`. The
separate code-mode runtime declares V8, and the broader upstream qualification
workflow provisions V8 for its larger test graph. That broader workflow is not
evidence that this particular binary selection requires V8. Preserve the real
binary selection and let the actual resolved graph decide; do not substitute a
smaller daemon or remove upstream dependencies.

The reachable source includes SQLx with bundled SQLite and Rustls with AWS-LC.
The fixed workspace also enables Reqwest defaults, so native TLS discovery
must be accounted for. Provision a C/C++ toolchain, make, Perl, CMake,
pkg-config and OpenSSL development files on the Linux runner. The code-mode
protocol build script uses `protoc-bin-vendored`; the standalone process gate
does not require a model service, API key, objective issuer, V8 test run or
device provider. Additional native prerequisites remain subject to the actual
unchanged build scripts.

The initial local snapshot observed only **125,796,352 bytes** free on the writable
overlay and only Rust 1.88 installed. Its installed 1.88 toolchain occupied
602,060,530 apparent bytes; that is a local observation, not a size measurement
for the missing 1.95 toolchain. Of 1,316 registry package identities in the full
original workspace lock, only 110 matching name/version source directories
were present in the existing cache. The full lock includes tests and other
platforms, so the remaining count is not an Agentd download estimate. No
cached AWS-LC, SQLite-sys, OpenSSL-sys or V8 crate source was found in that
task-local registry source cache. No original Agentd executable was found on
PATH or among the task's source and build filenames.

Container memory is limited by cgroup, not `/proc/meminfo` alone. One observed
cut had `memory.max = 8,589,934,592`, `memory.current = 7,638,487,040`,
`file = 6,796,570,624`, `anon = 125,435,904`, and `kernel = 715,132,928` bytes,
with `shmem = 0` and no recorded OOM kill. Much of that usage is file cache;
its potential reclaim is not a guaranteed compiler/linker allowance. The
visible `/dev/shm` mount was read-only in the regular sandbox. The manifest
regression did not write to tmpfs, remount, delete caches or attempt a build.
This resource snapshot predates subsequent provisioning; a later toolchain or
execution environment needs its own resource and build evidence.

The gate's **8 GiB free-disk threshold remains a conservative admission
estimate**. It is neither a measured lower bound nor proof that an admitted
build will fit. This change does not lower it or fabricate available space.
For a fresh execution runner, budget roughly **20 GiB writable headroom** and
**16 GiB RAM** with one build job as provisional provisioning targets, then
measure actual peak target/cache size and cgroup usage. These are planning
budgets, not established minimums. A smaller runner must supply measured
evidence that its selected caches, toolchains, native build and linker fit.

Before refining admission policy, account separately for the work/target
filesystem, Cargo source/git cache, Rustup installation and temporary files;
the current gate measures only the work parent's filesystem. Capture stage
failures, memory events and bounded diagnostics when running the actual graph.
Readiness failures should retain the original supervisor's bounded diagnostics
for investigation. Neither improved preflight accounting nor these manifest
checks can replace the unexecuted original build and process assertions.
