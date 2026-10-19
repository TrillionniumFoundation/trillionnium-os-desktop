## Why

The existing `ledger()` helper in the Unix Fleet authority tests uses `Result::unwrap()`, which fails the repository's strict Clippy gate. The original Ubuntu and macOS ARM Bazel jobs both reported this same helper. Its source was unchanged from the pre-Objective-History baseline. `expect()` is also denied by the existing policy.

## Change

Capture the host admission result and assert that it is successful, retaining the result in the failure message. All host fixture values remain unchanged. The patch changes one test helper and adds no lint exemption, policy change, dependency update, or new test.

## Validation

- `just fmt --base <parent>`: passed before committing the frozen source.
- Existing `codex-hepta-fleet` library tests via repository `just test`: 41 passed, 0 failed, 0 skipped, including `allocation_issue_consumes_exact_live_kernel_authority_lease`.
- Scoped `just clippy` with test targets and explicit denies for both `clippy::unwrap_used` and `clippy::expect_used`: passed.
- Linux x86_64, Rust 1.95.0, locked/offline, one build job, isolated target. Source, dependency lock, and lint policy were unchanged across tests and Clippy. The test runner's scoped-metadata package-ID warnings are retained in the original log.

This is local Cargo validation. The patch has not been run on Bazel, macOS, ARM64, or Windows, and does not resolve the separately recorded Windows sandbox boundary failures or dependency security debt.
