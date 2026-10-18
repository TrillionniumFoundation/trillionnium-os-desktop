# Linux host Session / Hepta observer evidence

The final candidate source is commit
`b53d7fbb406581ead53fd4b98d28ffc6b5f52c5c`, tree
`87d3cd65d9a587fe5610f7112e541d47e7a8d98e`.
The UI tests, Clippy and runtime probe checked commit
`c699766c1c0783b7e19156b631938b2f6b28feda`, tree
`d86983e5f6ce7c8305d17d930bdc6ca249a19684`. The final source commit changes
only the blocking host script and A00-coordinated CI workflow: the complete
`ui` tree and A07 source/fixture paths are identical to the tested commit.
The 14 facade tests and final script/workflow checks ran after the final
source commit. Neither the later evidence-only commit nor an unexecuted CI
matrix is claimed to have produced these binaries.

The source is stacked on A10
`f093fb3d5e97156e3bdd13fae06d1a3860d874b1` and the local A07 adapter commit
`1a1ef6b9c0b8f9ddd74a5e800229c487e08120da` (original A07 commit
`66b013e0202151a526fedd6c30fdaecd5a6654ab`). The A07 files are unchanged;
`services/hepta-os` and `tests/integration/hepta` are normal directories.
The adapter pins upstream Hepta
`f8c9419df6ddeb36ff8b522a50219981fb8d9345`.

## Observed results

| Check | Result | Raw evidence |
| --- | --- | --- |
| UI workspace Rust tests | 66 passed, 0 failed | `cargo-test.log` |
| A07 facade tests, invoked independently | 14 passed, 0 failed | `hepta-cargo-test.log` |
| Strict UI workspace Clippy, all targets | Exit 0 with `-D warnings` | `cargo-clippy.log` |
| UI workspace rustfmt check | Exit 0 | `rustfmt.log` |
| A07 facade rustfmt check | Exit 0 | `hepta-rustfmt.log` |
| Eight separate Bash syntax checks and CI YAML/path checks | Passed; workflow not executed | `host-gate-checks.json` |
| Actual Session / facade / scripted v2 UDS probe | Validated observation, then stale state after endpoint shutdown | `session-observer-probe.json` and `.log` |
| Host dispatch after fixture shutdown | Unknown-task cancellation request rejected in 100.349 ms | `session-observer-probe.json` |
| Renderer objective / generic RPC requests | Both rejected by the actual Session | `session-observer-probe.json` |
| Root README | Still exactly 0 bytes | `summary.json` |

The 66 tests comprise 8 application-window tests, 2 CLI tests, 21 Session
unit tests, 2 Hepta negative IPC tests, 1 Session reconnect integration test,
19 Shell tests, and 13 shared-core tests. The stalled-peer integration test
waits through the five-second observer deadline while host snapshots and
action dispatch remain responsive.
The separately invoked A07 suite adds one timeout/admission unit test and
13 real Unix-socket protocol tests. A Cargo path dependency does not run its
own tests automatically, so the blocking host script now invokes that suite
explicitly. The final script also includes A07 in each formatter list and
checks every listed Bash file individually. A00 added both Hepta dependency
paths to PR/push triggers and the missing-UI source-change check.

The positive endpoint is the committed A07 **scripted protocol fixture**.
It has an actual Linux PID and private Unix socket, so the production
facade's peer-PID/UID, identity, generation, framing and typed projection
checks execute. It supplies three advertised capabilities and three
lifecycle events. Stopping it changes the Session projection from
`observed` to `stale`; the last successful identity, health and event
metadata are preserved. Advertised `objective.start` does not enable any
renderer write path.

The final Session binary SHA256 is
`de77ea95498d2a63d13b8bdd4236c2287c0bc6d9610abaf5ca41b7ed959f5b67`.
`summary.json` records the fixed `nightly-2026-07-21` compiler, command
arguments, source-file hashes, Rust subtree equality, and evidence-file
hashes. The formatter and Clippy checked identical Rust source bytes
immediately before `c699766`; UI Cargo tests and the runtime probe ran after
that commit. Raw log bytes, including trailing blank lines, are preserved.
Code/document whitespace checks exclude the raw evidence directory.

## Qualification

The verified scope is a Linux host Rust Session and native Shell consumer
of read-only runtime metadata. This run did not start upstream Agentd,
assemble AuthBus credentials, submit an objective, or exercise any device
effect. The fixture and synthetic widget tests do not qualify physical
GUI/GPU output, Chinese fonts/live IME, Asterinas graphics, or Android,
iOS or WASM transport. The full `tests/ui/check-host.sh` script was not run
in this invocation; its new observer probe was run directly, and its
remaining historical gates are not inherited as passed.
The cloud A10 workflow separately pins Rust **1.88.0** and runs Weston.
Neither that compiler/matrix nor Weston was executed here; local fixed
nightly results do not establish their outcome.

The initial restricted invocation denied `AF_UNIX` bind. The final private
socket tests ran in the approved local execution context. No remote branch,
pull request, message, production service or device was changed by this
probe.

Development, configuration and next-step boundaries are documented in
`support/ui/HEPTA_OBSERVER.md`. The candidate also fixes the pre-existing
Shell borrow error caused by moving `task.detail` before borrowing `task`
for the fresh-window predicate, and applies the fixed formatter's two
existing application-test layout corrections.
