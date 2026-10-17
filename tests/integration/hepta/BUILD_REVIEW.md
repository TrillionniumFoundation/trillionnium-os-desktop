# Fixed original Agentd build review

This review keeps original Hepta pinned to
`f8c9419df6ddeb36ff8b522a50219981fb8d9345`. The complete checkout was clean before
and after the checks. No original Cargo resolution, Rust build or Agentd launch
was attempted. The existing original-process qualification is **`not_run`**.

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
This does not claim Cargo has resolved or compiled that graph.

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
always uses the untouched original workspace lock. Resolution is still a real
gate: the seed check alone does not prove the resolved graph will be accepted.

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
