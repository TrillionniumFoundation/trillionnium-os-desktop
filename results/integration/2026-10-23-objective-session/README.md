# Objective Session local evidence — 2026-10-23

**Latest execution:** the original dependency blocks below were resolved. See
[`LOCKED_EXECUTION.md`](LOCKED_EXECUTION.md) for actual Rust 1.88/1.95 package
tests, Clippy, and the additional owner-start refusal regression. The original
sections below are retained as the historical first attempt, not current status.

This evidence describes the exact new adapter source on Desktop base
`39c1d84ebf854958f5829c0118b0c8b92a6b4926` (tree
`87bc4e4d72697a7583fb0afafe4db4b41582941c`). `source-manifest.json` binds each
changed source path to its original Git blob, if present, and its final bytes.
`local-execution.json` contains actual commands, exits, raw output, timestamps,
source hashes before/after execution and unchanged lock hashes.

## Actually executed locally

* Rust 1.95.0 `rustfmt --check` on all seven changed Rust files: exit 0.
* Rust 1.95.0 `rustc -D warnings --test` on the actual production
  `ui/session/src/objective_pending.rs`: compiled; **8 passed, 0 failed**.
* Original UI `cargo test --locked --offline -p trill-session --all-targets
  --features objective-submission`: exit 101 during dependency resolution,
  because the offline workspace cannot find `eframe`. It did not compile or run
  the adapter/UDS tests.
* Original transport locked/offline identity regression: exit 101 before
  compilation because `bytes v1.12.1` is not cached and offline mode prevents
  downloading it. The original transport regression did not run.

Both original lockfiles remained byte-identical to the base. No dependency was
substituted and no alternative-manifest result is presented as a locked-package
pass. The local Rust version is **not** the A10 pinned Rust 1.88.0 toolchain.

## Authored integration coverage and remaining gates

The ten Session integration tests exercise the actual original transport using
disposable UDS fixtures and a test-only owner; their source is present but their
local execution is blocked as described above. One new original transport
test checks pre-send identity preview against the real subsequent attempt and
ensures preview opens no connection. The A10 workflow explicitly enables the
new Session feature for tests and Clippy and retains the resulting raw logs.
Until that CI runs successfully, full adapter compilation and UDS integration
are unqualified.

The eight pure policy tests are limited evidence for local linearity and
unknown/cancellation behavior. They do not prove original-owner persistence,
authentication, actual chat submission, model/tool/device effects, GUI, IME,
accessibility, mobile support or Makepad renderer unification.

Production still requires a concrete original-owner durable retention
implementation and trusted composition. This patch provides no local ledger,
signer, production test-owner implementation, default-enabled Send command or
run cancellation endpoint. See `ui/session/OBJECTIVE_SUBMISSION.md` for the
call order and exact unresolved interfaces.

The workflow change is a single new feature-test step against the base A10 file
blob `e845909fa48508222cce75be9e2a73d1324ccef2`. When combining with the separate
README-guard migration in PR #247, apply that hunk and preserve #247's guards;
do not replace its full workflow with the old-base file.
