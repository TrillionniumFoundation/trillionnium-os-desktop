## Why

The existing scoped native CI job exhausted its runner filesystem while compiling the unchanged 134-package impact plan for Fleet PR #2882 at `b34cb44f06db0a66acb3d25b183a2a05c4cebc7e`. The original job reported `rustc-LLVM ERROR: IO failure on output stream: No space left on device` at 2026-10-19 03:52:53 UTC; the runner's own diagnostic write then failed for the same reason. `CI required` correctly rejected the failed job.

The retained Cargo log shows test compilation in `target/debug` with debuginfo and an incremental directory. This job lacks the smaller build settings already used by the repository's consolidated native qualification and inference maintenance workflows.

## Change

Add the same four job-scoped environment settings to `hepta-scoped`:

- `CARGO_INCREMENTAL=0`
- `CARGO_BUILD_JOBS=2`
- `CARGO_PROFILE_TEST_DEBUG=0`
- `CARGO_PROFILE_DEV_DEBUG=0`

This removes incremental compilation storage and debug information from these disposable CI builds. The build concurrency limit applies to Cargo compilation. The existing impact plan, package set, Cargo lock, feature selection, nextest profile, test concurrency rules, command arguments and required-job rejection behavior remain unchanged. The patch does not delete SDKs or move the target directory.

## Validation

- The changed workflow passes actionlint 1.7.12. The repository's scoped formatting check exits successfully with no applicable formatting changes.
- YAML comparison confirms that removing only the new environment mapping yields the original workflow exactly.
- Replanning the original Fleet tree preserves all 134 packages and the complete original `just test --locked` argument vector. The CI scripts, Cargo configuration, lock and nextest configuration are unchanged.
- 102 distinct existing Python contract tests pass across the recorded invocations. These cover impact selection, real nextest feature-failure propagation, and execution-record rejection for failures, zero tests, output limits, source drift and timeouts.
- The existing `codex-utils-string` library's 18 tests pass with these four settings on Rust 1.95.0. Captured compiler commands omit incremental/debuginfo arguments and include `strip=debuginfo`; build output records `NUM_JOBS=2` and `OPT_LEVEL=0`.

The evidence retains two corrected local invocation errors: importing two executor test modules without their expected discovery path, and using nextest `-vv` instead of its documented Cargo verbosity options. No test or production source was changed to make validation pass. The local nextest is the already installed 0.9.148; the workflow's original 0.9.103 pin is unchanged.

## Scope and remaining gates

This is a standalone workflow-only commit based on main `f8c9419df6ddeb36ff8b522a50219981fb8d9345`; it does not include the Fleet helper change or objective-history product changes. Existing policy still routes workflow changes to full-repository CI. No scope exception is added.

The original 134-package scoped job has not been rerun with this candidate. The local checks establish configuration and contract behavior; successful remote execution is still required before claiming the ENOSPC issue is resolved. Existing repository-wide security and platform failures remain separate and their gates stay in force.
