# Pocket4 continuation: host regression fixes and release evidence coverage

This source publication addresses three observed defects and records the real host Binder check. Whole Android and application production qualification remains open.

## NSS process-exit regression

The same root-sealed diagnostic executable returned 0, 1, and 0 in three consecutive owned observations. The failure occurred after a process was enumerated under /proc and exited before its directory was opened.

The supervisor patch retries the entire SSSD process inventory after Changed, ENOENT or ESRCH, at most eight times within the original five-second deadline. A successful complete scan is required. Live service credentials, permanent I/O errors and unproven worker retirement remain failures. The retry is local to the process inventory; provider, configuration and authority checks retain their original behavior.

Actual qualification: 41 relevant ordinary Rust tests passed, the normal supervisor binary built, and the same corrected root-sealed binary passed five real host observations. Every test unit retired. The byte-pinned preimage, patch, replay verifier and compact observations are included under nss. Adoption by the active production namespace owner is pending.

## Running host Binder

On running kernel 7.0.14-p4cred1, the std-only Rust probe completed nonce-bound request/reply cases with and without TXN_SECURITY_CTX. The requested context was unconfined and matched the client's observed device-opening credential. Both cases passed without EINVAL or BR_FAILED_REPLY.

The private mount, processes, unit and cgroup retired; an independent readback verified cleanup. The 4,092,744-byte temporary probe executable was then removed. This qualifies the host Binder IPC check. Android startup, service publication and application use require their own runtime observations.

## Audio released SDK prerequisites

The real r11 build stopped because android-support-test-nodep requested SDK 23 without its original android.jar. The new source commit 557bff5c84eef7eea9af4533ac7391e3ae676d0f selects 32 additional original SDK paths and checks the complete 55-file prerequisite set. All 430 AOSP project revisions and the original consumer SDK levels are retained.

The patch passed 53 focused Audio tests and normal source-lock verification for 430 projects and eight root links. Source reconciliation, a new full APEX build and playback/capture qualification are pending. These historical SDK inputs are necessary for the current retained build graph.

## Application evidence completeness

The application patch adds a read-only release-check command. An independently pinned manifest and selected count are required. Missing apps or gates, mismatched declared identities or Main bindings, non-passing results, and missing/corrupt evidence prevent evidence_complete. Forty-two expected apps with only thirteen result rows remain incomplete.

The post-review correction rejects understated evidence sizes before reading the payload, keeping the aggregate read budget meaningful. The independent harness compiles the single published release.rs through a path module and runs its ten regression tests. Its exact external dependency versions/checksums come from the previously published broker harness lock.

The report always retains production_ready=false, runtime_qualified=false and tests_executed_by_checker=0. It checks declared coverage and file bytes; it does not authenticate claims, inspect current Android state or replace actual application tests. The older 19-test remote observation precedes the read-budget correction. The final remote commit operation is unresolved during the execution-channel outage and must be reconciled by its original identity.

The selected Firefox replacement has no integrated business-gate contract in the last observed matrix. The proposed five browser gates and six common gates are included under apps/firefox-contract with their observed preimage binding. Every execution state is pending; integration requires the real matrix schema and current preimage verification.

## CI and remaining work

A08 verifies the complete capsule inventory, replays the NSS patch against its exact preimage, compiles the Binder probe and runs its device-free ABI self-check, and executes the ten application checker regressions with the pinned Rust toolchain. CI leaves Android runtime and production qualification unchanged.

At this publication checkpoint, the private host execution channel returns Internal error. The latest coordinator publication records Native601 tools, import and materialized source as qualified. New Native/Audio full builds, production namespace qualification, complete Android boot, application delivery/acceptance and final obsolete-artifact retirement remain pending. The active coordinator's CURRENT and original Android data were not changed by this continuation.

