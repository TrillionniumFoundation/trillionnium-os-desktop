## Why

The existing Unix Fleet authority-test helper uses `Result::unwrap()` outside a test function, which fails the repository's strict Clippy policy. The original Ubuntu and macOS ARM Bazel logs identify the same helper; its input file already exists unchanged on main. `expect()` is also denied.

## Change

Capture the host admission result and assert success, retaining the result in the assertion message. All fixture values remain unchanged. This branch is based directly on main commit `f8c9419df6ddeb36ff8b522a50219981fb8d9345` and changes only `codex-rs/hepta-fleet/src/authority_port.rs`; it does not carry the separate Objective History or CI-timeout changes from #2815.

## Validation on this exact main-based candidate

- Commit `e770156ba8b35c77829d189fc053dc5f9eb69f8b`, tree `15a3b89f59052368e28ce5ed4943dc2ab638844b`.
- `just fmt --base <main>`: passed, source unchanged.
- Repository `just test`, scoped to Fleet library tests: **41 passed, 0 failed, 0 skipped**, including the existing live authority-lease test that calls this helper.
- Scoped `just clippy` with test targets and explicit denies for both `clippy::unwrap_used` and `clippy::expect_used`: passed.
- Linux x86_64, Rust 1.95.0, locked/offline, one build job, dedicated target. All validation receipts bind this exact source; previous d32-based results are preserved separately.

No lint exemption, dependency update, policy change, or new test is included. These are local Cargo results, not a Bazel or cross-platform CI pass. Separately recorded Windows sandbox boundary failures and dependency security debt remain unresolved.
