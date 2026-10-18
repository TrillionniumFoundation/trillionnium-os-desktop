# Hepta CLI process-loss boundary checks

This archive records the real local Rust 1.88 execution on 2026-10-18 from
14:59:47 to 15:00:24 UTC. All six recorded commands exited successfully. The
focused run passed both new SIGKILL tests. The full feature-enabled suite passed
43 tests: 2 library tests, 8 CLI tests, 15 objective transport tests, 16 read-only
socket contract tests, and 2 compile-fail documentation tests. The focused two
are already included in those 43; they are not 45 distinct tests. The default
feature-off all-targets check, strict Clippy with `-D warnings`, and format check
also passed.

## Exact execution source

The checked-out HEAD was `00796f6f6e10027e12b83d37d9ab4b8ab913f72e`, with base tree
`9336e6e6daab3b45d5f92a9eaa4161395603036f`. The actual source was that HEAD plus the
uncommitted test-only patch archived at [execution/source.patch](execution/source.patch).
Its SHA-256 is `077347ec84b75f57f7a73e0944772a94027549f0adb4e487ee4c8c97b86c7a56`.
All 20 tracked service inputs were captured before execution and verified equal
after execution. Only `services/hepta-os/tests/objective_cli.rs` differed from
the execution HEAD. No production code, manifest, lock, issuer, ledger or
technical documentation differed from that HEAD during these checks.

The tested file is 18,082 bytes, Git blob
`4136d3d78da1e7dbf7b36b046e6cad6cccda56f0`, SHA-256
`f1cafe25930066e92f93e0b8b8ec06fbe218a353dfa180c421a513fb8e4d684b`.
This is a source-and-patch qualification, not an execution of a later commit or
CI run. The source closure, toolchain, raw command lines, profile, and actual
test/CLI executable hashes are retained under `execution/`.

## What the two new tests prove

| Boundary | Actual observation | Scope of the conclusion |
| --- | --- | --- |
| Complete input written, stdin EOF withheld | A producer handshake confirms the original bytes were written while its pipe stays open; the actual CLI is killed with signal 9 and reaped; stdout and stderr are empty; no socket connection is queued. | The private fixture independently proves no connection before EOF. The missing output itself is not a CLI `not_sent` receipt. The test does not claim that the child reached a particular internal read. |
| Complete request read, response withheld | The private UDS peer reads and verifies one complete original frame and its request identity before the explicit kill; the actual CLI is killed with signal 9 and reaped; no receipt, second frame or retry connection appears. | A complete send is proved and the caller has no receipt. This is not an emitted `SubmitUnknown` record or proof that an original Agentd published an objective. |

Both tests preserve the complete input in the caller's test process. The
`OwnedCli` guard retains the hold channels through kill/reap, including assertion
unwind, so cleanup cannot accidentally release EOF or a peer response first.
Channel handshakes identify the fault boundaries; elapsed sleeps are not their
evidence. Existing bounded listener readiness polling is separate from those
handshakes. Every outer command finished with its owned process guard disarmed.

## Evidence and limits

- [Raw execution receipt](execution/receipt.json), [full test log](execution/full-feature-suite.log), and [focused test log](execution/focused-kill.log).
- [Source binding](SOURCE_BINDING.json), [post-execution hash verification](execution/post-execution-verification.json), and [independent A07 source review](a07-objective-cli-kill-source-review.json).
- Fixed Rust 1.88, one build job, development/test debug information disabled,
  and incremental compilation disabled were used. The approved private memory
  filesystem held Cargo dependencies and build outputs. The archived ELF
  identities were re-read in that same execution view; ELF bytes are not copied
  into this archive.

This run launches actual owned `hepta-submit` subprocesses against private test
peers. It adds no persistent request owner, original issuer, signing ability,
automatic replay or reconciliation ledger. It does not start the original
Agentd, Session, Shell or a kernel guest. Original ObjectiveStart admission and
journal evidence already recorded in R8 remain a separate qualification. Caller
input retention here is process-local, and the missing receipt cannot establish
a durable result or authorize retry.

`MANIFEST.json` and `SHA256SUMS` preserve the raw execution files, including an
empty successful format log. The sibling review is explicitly source-only; its
reviewer did not rerun these tests. The post-execution verifier records the two
readback-assumption corrections separately from the successful test execution.
