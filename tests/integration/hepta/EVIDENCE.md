# Read-only observer evidence

Evidence recorded on **2026-10-17 UTC**. This change is a bounded Linux host
observation slice for the A10 stacked candidate, with files in the A07-owned
adapter area. It does not claim A07's durable Hepta → HOS2 effect gate.

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

## Executed checks

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

This proves the Session → facade → operating-system socket → bounded UI
projection path with fixture data. It is **not a live Hepta daemon**, model
provider, authenticated ObjectiveStart, HOS2 execution, or device-control test.
The source-derived verifier is a separate contract-conformance check; neither
fixture is described as a production owner.

## Remaining acceptance gates

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
