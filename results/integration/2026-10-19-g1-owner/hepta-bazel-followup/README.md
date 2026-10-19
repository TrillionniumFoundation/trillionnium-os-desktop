# Bazel follow-up evidence: three original remote failures

[中文完整诊断](BAZEL_FAILURE_DIAGNOSIS.md) · [Source comparison](source-comparison.json) · [Original log hashes](log-preservation.json) · [Failure excerpts](failure-excerpts.json) · [Final status](final-status.json)

This is an append-only follow-up to the frozen R10 security debt package. It analyzes the actual decoded remote logs of jobs 117846024935, 117846024963 and 117846025117, retrieved at 2026-10-19 02:18:45.651–02:18:46.907 UTC. All three fetches succeeded. No local reproduction, build, dependency update, policy change, rerun, cancellation or PR mutation was performed.

The exact check head is `d32e795f0d24df89fc57745f6fae70fbd0642eba`. The logs check out prospective merge `60a3376902982d79e85173d6aaf6bd631b4c4cf3`; the commit API confirms its tree `a3e718280a7e17b8c4a226a0232bf18c23fd3586` equals the head and local equivalent `1b0fedb8c2b510106848f6feaf530c9b3698399d`. Thirty preserved failure-site, supporting implementation and policy files are byte-identical at f8, 2be and the current equivalent tree. This is source attribution, not a baseline CI rerun or proof of every dynamic causal path.

## Conclusions

Ubuntu and macOS ARM Clippy reject the same ordinary test helper's `admit_host(...).unwrap()` at hepta-fleet/src/authority_port.rs:197–210. Both `unwrap_used` and `expect_used` are denied; changing to `.expect(message)` is insufficient. A minimal candidate keeps the original fixture fields and asserts that the captured admission result is successful, including its Debug value on failure. No lint exception or product behavior change is required. This suggestion was not implemented or tested in this task.

Windows shard 2 reports **103/142 targets executed: 89 pass, 1 fails to build, 14 fail locally, 38 skipped**. Its build failure is process_wrapper copying a disappearing `.lib.temp-archive-*.a` file; the existing temporary-output patch filters `.tmp` and `.rcgu.o`, but not that observed filename class. This supports a narrow classifier candidate, while the exact disappearance timing remains unproven. Real stable dependency copy failures must remain errors.

The fourteen failing test targets span path fixtures, unsupported non-Unix durable registry paths, directory/file synchronization, an incomplete SQL schema-rewind fixture, a stale source-string assertion, runfiles lookup, session state/feature behavior and native Windows sandbox boundaries. The Chinese report maps all fourteen separately. The truncated CLI output gives no specific cause. App-server NotIdle/terminalizing errors and MCP 404/timeouts do not establish a single shared root cause and must not be hidden by automatic resubmission or weaker fences.

**The Windows sandbox failures are material:** the restricted-token test receives success for outside file and directory deletion where it expects PermissionDenied; the real legacy-process test finds the outside sentinel unreadable/absent and the protected directory absent. These are observed fixed-fixture failures, not a claim about every production installation. They prevent accepting the tested Windows deletion-isolation/device-control boundary. Preserve the negative assertions and investigate the native token/ACL behavior separately from the owner history PR.

## Final bounded observation

At **2026-10-19 02:24:28–29 UTC**, the exact head has **47 checks: 24 success, 6 skipped, 1 neutral, 6 failure, 10 in progress**. Architecture required succeeds; CI required is not yet present. The PR remains Ready/open/unmerged/blocked with normal squash auto-merge. New Windows shard 1 and shard 3 failures are status-only observations; their logs were not fetched and no matching cause is inferred. No further polling was performed.

## Package verification

The delivery contains a sorted strict `files-manifest.json`, `raw-evidence.tar.xz`, an `artifact-manifest.json`, and convenient primary copies. The archive's first entry is the exact files manifest, followed by every listed regular file. Names, order, lengths and SHA-256 are verified before an atomic directory rename. Primary copies match the same archive entries. All logs and the full connector response wrapper are present as lossless `.xz`; raw originals remain in the working evidence directory and their exact identities are listed in `excluded-raw-copies.json`.

The package contains no checkout, Cargo/Rustup cache, installed tools, product binaries or private keys. It does not modify the earlier security package. The failure excerpts use 1-based original log lines; they supplement rather than replace the complete logs. The test-output parser accounts for the CLI's mid-line termination and does not attribute the following app-server panic to it. Existing job shard/retry output is retained as evidence, not treated as new locally executed tests.

