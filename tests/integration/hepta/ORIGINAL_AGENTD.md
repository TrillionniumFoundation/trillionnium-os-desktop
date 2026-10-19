# Original Agentd read-only qualification gate

**Latest archived result: the original Agentd and original-owner probe were
built, linked and executed successfully on native ARM64 Linux.**
[Run 39037037916](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39037037916)
ran the exact desktop `1974d9a94037440da358253e1f449b395daa4b64` and unchanged
original `f8c9419df6ddeb36ff8b522a50219981fb8d9345`. Its eight read-only process
checks passed, including original restart, rejection of the old spawn and
controlled stop. The [ARM evidence archive](evidence/2026-10-17-original-agentd-arm/README.md)
preserves the original report/logs/locks, final clean source identities and
independent verification of all three actual ARM64 ELF hashes. This run used
fresh observer CLI instances; persistent Session/Shell integration, objective
submission, model turns and device effects remain separate unqualified gates.

The new optional [persistent Session extension](ORIGINAL_SESSION.md) adds real
Session/ctl lifecycle checks and a bounded Shell capture handoff. It preserves
the eight process checks and reports its additional qualification separately;
the archived result above is not evidence that this new extension ran.

The earlier local Rust 1.95 compiler checks did not link or execute the original
process. Their metadata/check commands, failed attempts, source/lock bindings
and raw logs remain in
[BUILD_REVIEW.md](BUILD_REVIEW.md#real-resolution-and-compiler-checks) and
[the original-probe evidence archive](evidence/2026-10-17-original-probe/README.md).
`cargo check` does not produce the runnable binaries or pass the live gate.
The separate [live-source review](LIVE_SOURCE_REVIEW.md) records the startup,
Session and trusted-objective contracts checked before the first process run.

**Historical preflight result, 11:12:19 UTC on 2026-10-17:** that snapshot found
29,278,208 free bytes, only Rust 1.88
installed, and no `cmake` on PATH. The gate returned exit **2**, with both
`large_build_attempted` and `runtime_probe_attempted` false. The machine-readable
record is [original_agentd_preflight_2026-10-17.json](original_agentd_preflight_2026-10-17.json).
The 8 GiB disk threshold is a conservative build budget, not a measured size of
the minimal graph. No original source, registry, device or production process
was changed to work around these limits.

`run_original_agentd.py` and `original_agentd_probe.rs` make the original
process check reproducible. The Python syntax, runner manifest/patch generation,
seed-lock validation and rejection of a deliberately changed dependency
identity were exercised. The later Rust 1.95 check compiled/type-checked the
unchanged probe against the original owner libraries, and a separate check
passed for the original Agentd binary selection. **None of the original-process
assertions is recorded as passed by those compiler checks.** A link or startup
incompatibility remains a real gate failure to fix and report, never a reason
to relabel a fixture as Agentd.

## Fixed original source and minimum profile

The sole original checkout is
[`hepta-private-ci@f8c9419d`](https://github.com/TrillionniumFoundation/hepta-private-ci/tree/f8c9419df6ddeb36ff8b522a50219981fb8d9345).
The gate verifies that exact HEAD, a clean complete working tree, the reviewed
source hashes, original toolchain, package name, and original Cargo.lock hash.
Its target/log directories must be new and outside both source checkouts.
The original checkout is checked again after building and running.

| Original source | Binding used by the gate |
| --- | --- |
| [`codex-rs/rust-toolchain.toml`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/rust-toolchain.toml) | Original Rust 1.95.0; never substitute the desktop host compiler |
| [`hepta-agentd/Cargo.toml`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/Cargo.toml) | Build the real `codex-hepta-agentd` binary with default features disabled; no control-only feature bypasses App Server/core |
| [`hepta-agentd/src/config.rs`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/config.rs) | Registered Starting generation, exact agent/workspace/home/run binding and original writer lock |
| [`hepta-agentd/src/app_runtime.rs`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/app_runtime.rs) | Original App Server, disabled ephemeral remote-control startup, no default cognitive writer in this build |
| [`hepta-agentd/src/runtime.rs`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/runtime.rs) | Original control listener, local CognitiveStore/AutomationStore, prerequisite/health monitoring; no optional issuer/provider CLI flags |
| [`hepta-agentd/tests/support/fleet.rs`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/tests/support/fleet.rs) | Existing public FleetRegistry/Supervisor/UnixProcessDriver startup, tick, restart and cleanup pattern |
| [`hepta-supervisor/src/unix.rs`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-supervisor/src/unix.rs) | Original owner sets child identity/generation/private roots; real health/drain RPC and OS process control |
| [`app-server/tests/common/config.rs`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/app-server/tests/common/config.rs) | Existing provider/config keys used for a no-turn private profile |

The runner links those original owner libraries. It does not reconstruct a
Supervisor, forge registry JSON, acquire a lease independently, implement a
second agent, sign ObjectiveStart, or supply a replacement operation ledger.
The real process creates its own ordinary local runtime stores in a fresh,
private, short `/tmp/hp-*` directory. This is expected original startup I/O.
It never opens an existing user fleet, account, workspace or business database.

The original process starts with no optional AuthBus trust/checkpoint, objective
profile, intelligence invocation, evidence, production-writer or effect-host
arguments. The supervisor's production-authority feature is disabled. A private
config selects an inert loopback Responses endpoint with no service or mock
responses, no credentials and no retries. No model turn is submitted. This
configuration qualifies process observation only; it cannot qualify inference
or real production effects. The turn `read-only` configuration is not a claim
that all daemon startup filesystem writes are blocked by an OS sandbox.

## Reproducible commands

Use a Linux build runner with Python 3.11+, Git, C/C++ compilers, `cmake`,
`pkg-config`, and the native prerequisites required by the unchanged upstream
graph. Install **Rust 1.88.0 and 1.95.0** with `rustup` beforehand. The harness
uses `rustup run`; a missing compiler blocks preflight and is never silently
replaced or installed. Git/network dependencies and any additional native
archive requirements remain governed by the original source/build scripts.
The complete graph has not been measured here, and V8 is not assumed to be a
mandatory dependency of this particular minimal binary selection.

The fixed upstream process workflow is
[`hepta-gap-agentd-process.yml`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/.github/workflows/hepta-gap-agentd-process.yml).
It exercises a broader owner/process qualification graph and does not publish
an Agentd executable artifact. This desktop gate uses the original standalone
binary with no default features; it does not claim the broader workflow passed.

Run from the desktop repository root, using authorized local source checkouts:

```sh
# Default: source/tool/resource checks only. No Cargo build or daemon launch.
python3 tests/integration/hepta/run_original_agentd.py \
  --hepta-source /absolute/hepta-private-ci \
  --work-dir /absolute/new-original-agentd-work \
  --report /absolute/new-preflight.json

# On a provisioned runner: build original source and run the actual process.
python3 tests/integration/hepta/run_original_agentd.py \
  --hepta-source /absolute/hepta-private-ci \
  --work-dir /absolute/new-original-agentd-work \
  --execute --report /absolute/new-live-evidence.json
```

Exit **0** in default mode means only `preflight_pass_build_and_runtime_not_run`.
Exit **2** is blocked prerequisites/resources. Exit **1** is a failed source,
build, lock, runtime or acceptance check. Only an executed run that completes
every process assertion writes `live_agentd_acceptance: passed`. Never use a
successful preflight exit as a live acceptance result.

The exact original binary build is equivalent to:

```sh
rustup run 1.95.0 cargo build --locked --profile dev-small \
  --no-default-features -p codex-hepta-agentd --bin codex-hepta-agentd -j1
```

The gate directs targets outside the checkout and disables incremental builds.
It builds the observer separately with Rust 1.88 and its committed lockfile.
For the external original-library runner it copies the original Cargo.lock and
rebases the original workspace patch paths into a new manifest. Cargo metadata
resolves that external package; every shared dependency identity/checksum must
still occur in the original lock before a `--locked` runner build is allowed.
The external manifest omits one exact duplicate, unused SSH tungstenite patch
alias to avoid Cargo 1.95's unstable unused-patch ordering. The retained target
must remain unused, every other patch mapping is preserved, and two consecutive
`--locked` metadata commands must leave identical lock bytes before compilation.
The [lock stability record](PROBE_LOCK_STABILITY.md) gives the failure, exact
scope, unchanged dependency graph and rejection checks.
The original Agentd binary itself always uses the untouched original workspace
and `--locked`. Binary, source and resolved-lock hashes are recorded.

Use `--offline` only after the required inputs have been populated. The gate
does not replace a missing original dependency with a local DTO or stub.

## Required process assertions

The original owner registers a fresh agent and launches the real executable.
The runner gets the socket, AgentId, immutable spawn and expected UID from that
registered layout and supervisor snapshot. It does not discover a socket and
trust the identity returned by the same socket. Each observer CLI call performs
the already reviewed Linux credential/framing/health/event checks.

1. Read the actual Starting phase before the owner ticks its promotion.
2. Tick the original Supervisor until Running and observe current = spawn + 1,
   the same PID, actual capabilities and original lifecycle history.
3. Read one absent run from the fresh original owner, expecting `null`.
4. Ask the original Supervisor to drain; observe current = spawn + 2 and the
   same process while the original drain protocol is active.
5. Ask the original Supervisor to restart, wait for its new spawn/PID, and
   observe Running again. The old spawn must fail, followed by another
   successful new-spawn read to distinguish fencing from an unavailable server.
6. Stop via the original Supervisor, confirm no active process, and verify the
   observer cannot produce a successful post-stop snapshot.

Each CLI invocation creates one observer instance. The default gate does not by itself
qualify a persistent Session worker or Shell display across restart. For a
separate Session probe, `--hold-seconds 30` leaves a bounded first-Running window
and emits a `trusted_endpoint` record. Only a trusted test launcher may hand
that configuration to Session; the renderer still receives projections only.
The existing same-client lifecycle socket regression remains a separate test.
For the complete six-phase persistent-consumer extension, supply both
`--session-bin` and `--ctl-bin` as described in [ORIGINAL_SESSION.md](ORIGINAL_SESSION.md).

The default runtime subprocess has a 240-second outer deadline and its own dedicated
process group. The original Supervisor performs normal cleanup; timeout,
interruption or nonzero subprocess exit starts bounded group termination.
Cleanup applies only to processes and directories created by this invocation.
A timeout or cleanup failure is a failure, never a skip or a successful
observation.

## Process-group identity and cleanup

Run the harness as a standalone Linux process with the default, waitable
`SIGCHLD` disposition and sole ownership of reaping its direct children.
Preflight and every bounded spawn reject unavailable `waitid(WNOWAIT)` support
or an ignored/custom Python `SIGCHLD` handler. This is not an embedding API for
an application with a competing `waitpid` loop, child watcher, or native
`SA_NOCLDWAIT` setup. The Python disposition check alone cannot establish those
embedding properties; the standalone sole-reaper contract is required.

`ChildGroup` observes its own session leader with
`waitid(P_PID, WEXITED | WNOHANG | WNOWAIT)`. The leader remains alive or an
unreaped child throughout TERM, the three-second grace period, and KILL. That
retained kernel identity prevents its numeric PID/PGID from being recycled
before the final group signal. Each signal performs another non-reaping check.
Only after all signals finish does the guard permanently disarm signaling and
use `waitpid` for the final reap and actual exit status. This cleanup also
applies when the leader exits successfully: exit zero does not prove that its
same-group descendants stopped. The leader's actual zero status is retained
while the existing bounded TERM/grace/KILL path runs under that identity anchor.

An `ECHILD` result permanently revokes the guard's identity anchor. The guard
then fails with `child_identity_lost` and never signals that numeric group
again, even if a later stub or kernel result appears valid. It does not treat
`Popen.wait()`'s possible ECHILD-to-zero behavior as a successful exit. If a
competing reaper violated the contract, safe cleanup of all descendants cannot
be guaranteed; the harness reports failure instead of using the stale ID.
Final reaping is bounded to three seconds after signaling is disabled. A child
that remains unreapable fails with `child_cleanup_incomplete`; the timeout does
not claim to interrupt an uninterruptible kernel wait or prove every process
has stopped.

The Linux regression command is independent of the original build:

```sh
python3 -B -m unittest discover -s tests/integration/hepta \
  -p test_original_process_guard.py -v
```

All six tests passed on 2026-10-17. They use disposable Python children in new
private sessions to verify an exited leader remains waitable before both
signals, bounded timeout cleanup, actual ECHILD before cleanup and between
TERM/KILL, permanent revocation, rejection before spawn of nonwaitable signal
dispositions, and successful exit status without signaling. Deliberately stale
signal paths are mocked; no real PID/PGID reuse is attempted. A safe probe of
the initial `a92d8ed` harness observed actual ECHILD at its mocked first TERM
call after `Popen.wait()` had already reaped the exit-1 child. The repaired
regression requires that same child to remain waitable until both signal
boundaries finish. These are process-guard tests, not an original Agentd run.

The six-test count above describes the 2026-10-17 source, including its old
success-path policy. On 2026-10-19, the current seven-test guard suite additionally
proved that an exit-zero leader cannot leave its real same-group plugin writer
active at the reap boundary. A private fixture subreaper owns both children;
bounded socket handshakes verify peer credentials and group identity, WNOWAIT
checks precede each signal, and a pidfd observes writer exit before leader reap.
The unchanged two focused tests first failed against the old production bytes
and then passed after the success-path fix. The current related suite passed
47 tests (7 guard, 6 Session receipts, 12 Objective receipts, 22 history
contracts). Five fixed-original build-manifest tests were not run in that local
environment because the full original checkout was absent. Raw results and
the distinct failed ARM run are in the [integration archive](../../../results/integration/2026-10-19-main-sync/README.md).

## Why no downloaded original binary was used

At **2026-10-17 10:47:51 UTC**, the authorized GitHub read snapshot found **12**
workflow runs for the exact original SHA. The nine skipped runs and the
successful push housekeeping run had no artifacts. The failed postmerge and
blocking aggregate runs exposed **39 artifacts** in total: timing/Bazel logs
and Windows archives. No applicable Linux Agentd binary was present. The one
listed acceptance release was for an older source and contained receipts, not
an original Agentd executable.

[upstream_artifact_snapshot.json](upstream_artifact_snapshot.json) retains the
run IDs, artifact IDs, source bindings and release metadata. No artifact was
downloaded, no CI run was dispatched, and no upstream file was modified.
This snapshot is limited to that exact-source search at that time.
