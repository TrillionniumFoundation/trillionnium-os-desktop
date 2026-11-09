# Pocket4 continuation: host regression fixes and release evidence coverage

This source publication addresses observed host and source defects and records their actual verification. Whole Android and application production qualification remains open.

## NSS process-exit regression

The same root-sealed diagnostic executable returned 0, 1, and 0 in three consecutive owned observations. The failure occurred after a process was enumerated under /proc and exited before its directory was opened.

The supervisor patch retries the entire SSSD process inventory after Changed, ENOENT or ESRCH, at most eight times within the original five-second deadline. A successful complete scan is required. Live service credentials, permanent I/O errors and unproven worker retirement remain failures. The retry is local to the process inventory; provider, configuration and authority checks retain their original behavior.

Actual qualification: 41 relevant ordinary Rust tests passed, the normal supervisor binary built, and the same corrected root-sealed binary passed five real host observations. Every test unit retired. The byte-pinned preimage, patch, replay verifier and compact observations are included under nss. The active owner subsequently adopted the exact NSS postimage; its combined supervisor qualification passed 97 controls and all eight ordinary-UID CLI rejections.

## Proc namespace directory access

The active owner's actual private proc attempt r4 still failed. The new queued-failure diagnostic recovered stage 1, source line 137, errno 13 from the owned PID 1 after actual PIDFD retirement. That line is the shared openat helper, so the original result does not itself name the failing path.

The source opens `/proc/1/ns` with `O_RDONLY` although it only needs to traverse the fixed `pid` namespace link. The exact running kernel's proc implementation gives this directory mode 0511 and can assign it to the root of `mm->user_ns` when the process is nondumpable. An ordinary child can therefore have search permission without directory-read permission. The minimal patch uses `O_PATH|O_DIRECTORY` at this one call. No dumpability or capability policy changes. `O_NOFOLLOW`, namespace-type validation and the parent's independently held PIDFD namespace identity check remain required.

The included ordinary-UID Rust regression ran on Pocket4 kernel 7.0.14-p4cred1 with zero effective capabilities. It reproduced EACCES with the old mode, opened and verified its own PID namespace using the new mode, restored its own dumpability and confirmed the original baseline again. It created no namespace or mount and performed no Android action. The isolated patched source also passed 21 ordinary namespace tests and a normal supervisor build; five privileged tests were deferred. The exact preimage, patch, replay verifier and actual receipts are under processfs. This source-supported cause candidate still needs the active owner's actual private-stage retest before that blocker can close.

## Running host Binder

On running kernel 7.0.14-p4cred1, the std-only Rust probe completed nonce-bound request/reply cases with and without TXN_SECURITY_CTX. The requested context was unconfined and matched the client's observed device-opening credential. Both cases passed without EINVAL or BR_FAILED_REPLY.

The private mount, processes, unit and cgroup retired; an independent readback verified cleanup. The 4,092,744-byte temporary probe executable was then removed. This qualifies the host Binder IPC check. Android startup, service publication and application use require their own runtime observations.

## Audio released SDK prerequisites

The real r11 build stopped because android-support-test-nodep requested SDK 23 without its original android.jar. The new source commit 557bff5c84eef7eea9af4533ac7391e3ae676d0f selects 32 additional original SDK paths and checks the complete 55-file prerequisite set. All 430 AOSP project revisions and the original consumer SDK levels are retained.

The patch passed 53 focused Audio tests and normal source-lock verification for 430 projects and eight root links. Source reconciliation, a new full APEX build and playback/capture qualification are pending. These historical SDK inputs are necessary for the current retained build graph.

## Application evidence completeness

The application patch adds a read-only release-check command. An independently pinned manifest and selected count are required. Missing apps or gates, mismatched declared identities or Main bindings, non-passing results, and missing/corrupt evidence prevent evidence_complete. Forty-two expected apps with only thirteen result rows remain incomplete.

The post-review correction rejects understated evidence sizes before reading the payload, keeping the aggregate read budget meaningful. The independent harness compiles the single published release.rs through a path module and runs its ten regression tests. Its exact external dependency versions/checksums come from the previously published broker harness lock.

The report always retains production_ready=false, runtime_qualified=false and tests_executed_by_checker=0. It checks declared coverage and file bytes; it does not authenticate claims, inspect current Android state or replace actual application tests. The older 19-test remote observation precedes the read-budget correction. Its original durable operation was subsequently reconciled as successful commit d88c3dc642b9484ddb7e84c812d6ed0dcfb5899d; the final corrected module in this capsule has its separate ten-test CI pass.

The proposed five Firefox browser gates and six common gates are included under apps/firefox-contract with their observed preimage binding. A separate continuation now has an independently verified matrix and registry successor and is building the real flow entry and 42-application dispatcher. Those later changes are not represented as deployed by this capsule. Every application execution acceptance remains pending.

## CI and remaining work

A08 verifies the complete capsule inventory, replays the NSS and proc directory-access patches against their exact preimages, runs the ordinary-UID proc access regression, compiles the Binder probe and runs its device-free ABI self-check, and executes the ten application checker regressions with the pinned Rust toolchain. CI leaves Android runtime and production qualification unchanged.

The execution channel recovered. The active owner's Native601 strict full r11 subsequently failed on original platform-tools providers etc1tool and hprof-conv; its original failure, source restoration and owned retirement are preserved. Audio's original SDK reconciliation remains active, and the source-library history correction is separately published in a291c1fbef3aa0b381109aec9af5dad0112dab09. Complete Native/Audio artifacts, production namespace qualification, Android boot, all 42 application acceptances and final obsolete-artifact retirement remain pending. The active coordinator's CURRENT and original Android data were not changed by this continuation.

