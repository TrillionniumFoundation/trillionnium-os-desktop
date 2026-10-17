# Read-only observer evidence

Evidence recorded on **2026-10-17 UTC**. This change is a bounded Linux host
observation slice for the A10 stacked candidate, with files in the A07-owned
adapter area. It does not claim A07's durable Hepta → HOS2 effect gate.

**Latest separate execution:** the [original Agentd ARM64 archive](evidence/2026-10-17-original-agentd-arm/README.md)
now records a passed original build/link/run and all eight read-only process
checks, with independently verified executable hashes. The earlier records
below retain their original source/time boundaries. The ARM gate uses fresh
observer CLI instances and does not qualify persistent Session/Shell, model
turns, authenticated objective submission or device effects.

## Frozen inputs and execution environment

| Input | Value |
| --- | --- |
| Desktop implementation base | `88f859bd2da13aa9e43a321edd172bdf0f7bfcf8` |
| Hepta source checkout | `f8c9419df6ddeb36ff8b522a50219981fb8d9345` |
| Rust toolchain | `nightly-2026-07-21` |
| rustc actually executed | `rustc 1.99.0-nightly (87e5904f5 2026-07-20)` |
| cargo actually executed | `cargo 1.99.0-nightly (3efb1f477 2026-07-17)` |
| Host | Linux `6.18.55`, x86_64 |
| Dependencies | serde `1.0.219`, serde_json `1.0.140`, Tokio `1.52.3`; committed Cargo.lock |

The implementation used the session's isolated fixed-toolchain wrapper:
`python3 /workspace/scratch/98f315e377b2/next-tools/run-rust.py`. The following
commands were run through that wrapper where they invoke Cargo. The reusable
commands in `services/hepta-os/RUN.md` select the same toolchain directly.

## Initial executed checks

| Actual command after the wrapper, or Python command | Result and scope |
| --- | --- |
| `cargo fetch --manifest-path services/hepta-os/Cargo.toml` | Pinned dependencies fetched; no full Hepta build |
| `cargo test --locked --offline --manifest-path services/hepta-os/Cargo.toml` | **1 unit test + 13 integration tests passed**; real private Linux UDS fixtures, 0 ignored |
| `cargo fmt --manifest-path services/hepta-os/Cargo.toml` | Rust source formatted |
| `cargo clippy --locked --offline --manifest-path services/hepta-os/Cargo.toml --all-targets -- -D warnings` | Passed with warnings denied |
| `python3 tests/integration/hepta/check_upstream_contract.py --hepta-source /workspace/scratch/98f315e377b2/next-hepta-source --emit-reference /workspace/scratch/98f315e377b2/hepta-reference-wire` | Exact Hepta HEAD and **11 SHA-256/Git blob source bindings** passed; emitted original-source verifier |
| `cargo run --offline --manifest-path /workspace/scratch/98f315e377b2/hepta-reference-wire/Cargo.toml` | **4 original-source payload roundtrips, 4 request roundtrips, AgentId/envelope encoding, and the exact upstream EventBuffer gap/resume/ahead behavior passed** |

The initial default-sandbox Rust test attempt compiled successfully but all UDS
tests failed at bind with `Operation not permitted`. The suite then ran in an
authorized local socket environment and passed. The environment failure was not
converted into a skip or a green test. No root, system configuration, device,
business data, or production socket was changed.

The passing socket tests verify these failure boundaries: wrong envelope
schema/request ID/Agent ID/spawn/current generation; mismatched kernel/health
PID; fenced and inconsistent health; unexpected privileged payloads; bounded
newline framing; redacted owner errors and exact overload handling; invalid,
duplicate and oversized capability sets; event order, duplicate/gap/cursor
integrity; rejection of extra fields; partial poll failure at the final health
check; private directory/socket/UID/symlink requirements; missing endpoints;
invalid read requests; and the five-second stalled-socket deadline. Known-run
reads retain historical generation and discard private receipt fields.

The separate unit test holds a real blocking metadata job past its waiter
timeout. It verifies that the permit stays with that job, replacement work is
rejected without queuing, and admission resumes only after actual completion.
The test does not claim to interrupt an OS filesystem syscall.

## Lifecycle compatibility correction

Further original-runtime review found that the initial fixture and client both
incorrectly equated Running `current_generation` to immutable `spawn_generation`.
The original fleet `AgentLifecycleState::successor` increments every lifecycle
transition, and Agentd `state.rs:336-345` accepts exactly Starting/+0,
Running/+1 and Draining/+2. The initial serialization checks did not test that
runtime rule. Their previous pass must not be treated as live interoperability.

On 2026-10-17, the new socket regression
`upstream_running_uses_spawn_plus_one_and_draining_uses_spawn_plus_two` was first
run against the old implementation and failed at the valid Running cut with
`GenerationFenced`. After the correction, the full small suite passed:
**1 metadata unit test + 16 real private UDS socket tests, 0 failed, 0 ignored**,
with the same fixed nightly toolchain. `cargo fmt` and
`cargo clippy --locked --offline --all-targets -- -D warnings` also passed.

The regression covers all three valid phases, advancement inside one four-RPC
poll, retaining earlier lifecycle events, reporting the final current value,
wrong phase/offset pairs, future-phase events, and generation rollback during
or between polls. Original spawn, kernel PID, schema and request correlation
checks remain in force. The fixture now uses spawn 7 / Running current 8.

The conformance generator additionally binds `state.rs` (12 source hashes total)
and extracts the original fleet transition methods and Agentd accepted-phase
expression. Hash verification and reference generation passed. The generated
program was then compiled and executed with **Rust 1.88.0** using
`python3 /workspace/scratch/98f315e377b2/next-tools/run-host-rust.py cargo run --offline --manifest-path /workspace/scratch/98f315e377b2/hepta-reference-lifecycle/Cargo.toml`.
Its lifecycle/restart/overflow behavior assertions, four payload and four
request roundtrips, identity/envelope, and original EventBuffer tests passed.
This is execution of extracted source with explicit surrounding shims, not a
live original Agentd process.

## Integrated Session fixture evidence

The coordinated A10 candidate also ran its actual Session IPC worker through
this client against `tests/integration/hepta/agentd_fixture.py`, a separate
Python process with a real UDS and kernel-visible PID. The UI-owner probe
observed the expected Agent ID, generation 7, the actual fixture process ID,
three capabilities and three lifecycle events. After the fixture stopped, the
Session changed to stale while retaining the last successful projection. Its
local action/IPC path remained responsive; objective submission and raw RPC
requests were rejected by Session. The integrated probe and its detailed
evidence belong to the A10 candidate (`tests/ui/probe-hepta-session.py`).
That initial fixture probe predated the lifecycle correction above and used
the incorrect current=spawn envelope. Re-run it with corrected spawn 7/current
8 data; the initial result is retained here as historical fixture evidence.

This proves the Session → facade → operating-system socket → bounded UI
projection path with fixture data. It is **not a live Hepta daemon**, model
provider, authenticated ObjectiveStart, HOS2 execution, or device-control test.
The source-derived verifier is a separate contract-conformance check; neither
fixture is described as a production owner.

## Remaining acceptance gates

### Original-process harness cleanup correction

Review found a separate flaw in the initial `a92d8ed` qualification harness:
`Popen.wait()` or `poll()` could reap the dedicated session leader before later
numeric PGID signals. The correction retains the leader with Linux
`waitid(WNOWAIT)` through the final signal, then disarms before the actual
`waitpid` reap. ECHILD permanently revokes signaling and fails the gate. This
requires a standalone process with waitable SIGCHLD and no competing reaper;
the precise preconditions and bounded-cleanup limits are in
[ORIGINAL_AGENTD.md](ORIGINAL_AGENTD.md#process-group-identity-and-cleanup).

On 2026-10-17, the independent command
`python3 -B -m unittest discover -s tests/integration/hepta -p test_original_process_guard.py -v`
passed **6 tests, 0 failed, 0 skipped**. It used real, test-owned Python children
and actual WNOWAIT/ECHILD results; stale signal attempts were intercepted, and
no PID/PGID reuse was created. At 11:35:47 UTC a safe probe of `a92d8ed` produced
the expected regression RED: actual ECHILD at the mocked first TERM call after
the exit-1 child had already been reaped. No signal was actually sent in that
old-source probe. Neither this probe nor the guard tests built or launched
original Agentd, modified shared Rust target binaries, or changed the earlier
`live_agentd_acceptance: not_run` qualification.

### Unexecuted original-process and production gates

The next original-process gate is now concrete in
[ORIGINAL_AGENTD.md](ORIGINAL_AGENTD.md). Its actual 2026-10-17 preflight exited
2 before any build/launch because of disk, missing original Rust 1.95, and
`cmake`. Exact-SHA CI/release inspection found no applicable Linux executable.
The runner was syntax/formatted and its manifest/lock preparation checked;
original-library compilation and every original-process assertion remain
unexecuted. Those facts do not change the fixture evidence class above.

1. Supply an independently trusted live Hepta profile, binary/build features,
   configured owners/providers, Agent identity, spawn generation, and endpoint
   UID; run the four supported reads against that actual daemon.
2. Qualify actual daemon restart/generation replacement and history loss with
   Session freshness and source-change handling. The observer itself creates
   no task replay or durable effect conclusion.
3. Assemble the existing authenticated objective issuer/provider boundary.
   The UI draft must not self-sign, self-assign authority, or use SessionIngress
   as a substitute for authorization.
4. Assemble the restricted HOS2 effect adapter and original durable operation
   owner, with immutable intent/K/D binding, real effect results, revoke/fence,
   lost-response uncertainty, restart, acknowledgement, and retirement tests.
   This observer does not supply that chain or introduce a second ledger.
5. Separately qualify Asterinas, Windows and mobile transport/process boundaries.
   A Rust UI build and a Linux observation fixture do not establish those
   platform/device capabilities.
