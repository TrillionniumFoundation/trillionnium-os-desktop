# Pocket4 continuation: host regression fixes and release evidence coverage

This source publication addresses observed host and source defects and records their actual verification. Whole Android and application production qualification remains open.

## NSS process-exit regression

The same root-sealed diagnostic executable returned 0, 1, and 0 in three consecutive owned observations. The failure occurred after a process was enumerated under /proc and exited before its directory was opened.

The supervisor patch retries the entire SSSD process inventory after Changed, ENOENT or ESRCH, at most eight times within the original five-second deadline. A successful complete scan is required. Live service credentials, permanent I/O errors and unproven worker retirement remain failures. The retry is local to the process inventory; provider, configuration and authority checks retain their original behavior.

Actual qualification: 41 relevant ordinary Rust tests passed, the normal supervisor binary built, and the same corrected root-sealed binary passed five real host observations. Every test unit retired. The byte-pinned preimage, patch, replay verifier and compact observations are included under nss. The active owner subsequently adopted the exact NSS postimage; its combined supervisor qualification passed 97 controls and all eight ordinary-UID CLI rejections.

## Proc namespace directory access

The active owner's actual private proc attempt r4 still failed. The new queued-failure diagnostic recovered stage 1, source line 137, errno 13 from the owned PID 1 after actual PIDFD retirement. That line is the shared openat helper, so the original result does not itself name the failing path.

The source opens `/proc/1/ns` with `O_RDONLY` although it only needs to traverse the fixed `pid` namespace link. The exact running kernel's proc implementation gives this directory mode 0511 and can assign it to the root of `mm->user_ns` when the process is nondumpable. An ordinary child can therefore have search permission without directory-read permission. The minimal patch uses `O_PATH|O_DIRECTORY` at this one call. No dumpability or capability policy changes. `O_NOFOLLOW`, namespace-type validation and the parent's independently held PIDFD namespace identity check remain required.

The included ordinary-UID Rust regression ran on Pocket4 kernel 7.0.14-p4cred1 with zero effective capabilities. It reproduced EACCES with the old mode, opened and verified its own PID namespace using the new mode, restored its own dumpability and confirmed the original baseline again. It created no namespace or mount and performed no Android action. The isolated patched source also passed 21 ordinary namespace tests and a normal supervisor build; five privileged tests were deferred. The exact preimage, patch, replay verifier and actual receipts are under processfs. The active owner subsequently adopted the same O_PATH change in its exact C10 source. Its private proc/devpts r5 control passed the real PTY peer/data roundtrip and wrong-context rejection, followed by independent physical unit/cgroup, fixture, loop and mount retirement verification. The exact original receipts and logs are under processfs/owner-r5. This closes that construction-stage access failure; writable Android-init proc policy and Android startup remain separate pending gates.

## Running host Binder

On running kernel 7.0.14-p4cred1, the std-only Rust probe completed nonce-bound request/reply cases with and without TXN_SECURITY_CTX. The requested context was unconfined and matched the client's observed device-opening credential. Both cases passed without EINVAL or BR_FAILED_REPLY.

The private mount, processes, unit and cgroup retired; an independent readback verified cleanup. The 4,092,744-byte temporary probe executable was then removed. This qualifies the host Binder IPC check. Android startup, service publication and application use require their own runtime observations.

## Audio released SDK prerequisites

The real r11 build stopped because android-support-test-nodep requested SDK 23 without its original android.jar. The new source commit 557bff5c84eef7eea9af4533ac7391e3ae676d0f selects 32 additional original SDK paths and checks the complete 55-file prerequisite set. All 430 AOSP project revisions and the original consumer SDK levels are retained.

The patch passed 53 focused Audio tests and normal source-lock verification for 430 projects and eight root links. Source reconciliation r2 subsequently completed with durable exit 0. The independent terminal check reread all 55 original SDK blobs under the same three locks, verified the 430-project materialized manifest, and confirmed physical source-unit retirement and lock release. Exact receipts and original inputs are under audio/source-r2. A new full APEX build and playback/capture qualification remain pending. These historical SDK inputs are necessary for the current retained build graph.

The later normal qualification reuses the exact source-library history correction published in a291c1fbef3aa0b381109aec9af5dad0112dab09. A narrow test-only change isolates recovery-lock assertions from unrelated test threads that spawn children, while production locks retain their deliberate exec inheritance. With the required private attr and official EROFS 1.9.4 tools, the actual combined command passed 26 source tests, 223 updater tests and two integration tests, then built both normal tools. Two existing environment-specific tests remained ignored. The tested recipe, full log, dependency provenance and exact recovery patch replay are under audio/normal-source-update. This normal-tool qualification is separate from the completed source-only r2 reconciliation and does not qualify a complete APEX or Android runtime.

## Native601 original platform-tools providers

The active owner's strict full r11 next failed on the original platform-tools dependencies etc1tool and hprof-conv. The new recipe 92c6194201f93ec10b3e5127b0fbdb4a971266d1 supplies their complete original cones under development and dalvik. All 601 upstream project revisions remain unchanged. Four original implementation/Blueprint files matched the pinned Git trees, and the other direct platform-tools providers were found in the current source.

The successor passed 21 actual Native graph tests, both normal tool builds, and normal verification of 601 projects and eight root links. The exact three-file preimages, minimal patch, replay verifier, original failed r11 receipts and qualification are under native/platform-tools. A new source reconciliation and strict full build remain pending. The frozen full targets still identify CP2A.260605.016; compatibility with the selected official CP3A QPR1 system and preservation of its ART require separate work.

## Application evidence completeness

The application patch adds a read-only release-check command. An independently pinned manifest and selected count are required. Missing apps or gates, mismatched declared identities or Main bindings, non-passing results, and missing/corrupt evidence prevent evidence_complete. Forty-two expected apps with only thirteen result rows remain incomplete.

The post-review correction rejects understated evidence sizes before reading the payload, keeping the aggregate read budget meaningful. The independent harness compiles the single published release.rs through a path module and runs its ten regression tests. Its exact external dependency versions/checksums come from the previously published broker harness lock.

The report always retains production_ready=false, runtime_qualified=false and tests_executed_by_checker=0. It checks declared coverage and file bytes; it does not authenticate claims, inspect current Android state or replace actual application tests. The older 19-test remote observation precedes the read-budget correction. Its original durable operation was subsequently reconciled as successful commit d88c3dc642b9484ddb7e84c812d6ed0dcfb5899d; the final corrected module in this capsule has its separate ten-test CI pass.

The proposed five Firefox browser gates and six common gates are included under apps/firefox-contract with their observed preimage binding. The independently verified matrix/registry successor and actual Firefox flow entry plus 42-application dispatcher are now included under apps-runtime. The final source passed 41 normal full-workspace tests and two separate real host-control groups. The real 42-row registry with a deliberately absent private control socket preserved all 42 rows as blocked and pending. The CI harness compiles the delivered probe, transport and checker modules directly and requires 22 ordinary passes; its two explicit privileged host controls are represented by their separate actual execution. The local harness stdout completed, while the later durable-status reread is explicitly pending during the H outage. The new daemon entry currently uses DevelopmentCell; integration with the production cell lifecycle remains open. None of this source is deployed. Every application execution acceptance remains pending.

## CI and remaining work

A08 verifies the complete capsule inventory, replays the NSS, proc directory-access, Audio recovery-test and Native provider patches against their exact preimages, runs the ordinary-UID proc access regression, compiles the Binder probe and runs its device-free ABI self-check, and executes the ten original checker regressions plus the 22 same-source application probe/transport/checker controls with the pinned Rust toolchain. The full-crate Audio and Native test logs record their actual build-host executions. CI leaves Android runtime and production qualification unchanged.

The execution channel recovered for the recorded source and normal-host work, then timed out again during later status reads. Original operations were not replayed. The active owner's Native601 strict full r11 subsequently failed on original platform-tools providers etc1tool and hprof-conv; its original failure, source restoration and owned retirement are preserved. Audio's original SDK reconciliation completed successfully and its independent 55-blob and physical-retirement checks passed. The source-library history correction is separately published in a291c1fbef3aa0b381109aec9af5dad0112dab09. Complete Native/Audio artifacts, production namespace qualification, Android boot, all 42 application acceptances and final obsolete-artifact retirement remain pending. The active coordinator's CURRENT and original Android data were not changed by this continuation.


The earlier A08 run 42640649729 on c5b5319 was cancelled at the 15-minute job limit while downloading JDK packages, before the repair test steps executed. Tool preparation now verifies and reuses the runner-provided Java 17 JDK/JNI headers and existing compiler/media tools, installing only missing components without recommended packages. The same actual JNI/media tests, source inventories and job deadline remain required.

## Application runtime generation successor

The immutable R3 source commit deacfc207c99a74a8aac056b086dc1b8f7e8f0c2 extends the R2 entry with one initial read-only runtime observation and a sticky generation fence. Missing runtime blocks the entire selection before package calls; transport failure or an observed generation change stops subsequent calls, without replaying a failed operation. The actual daemon currently owns DevelopmentCell and reports that lifecycle explicitly. The report continues to grant no application acceptance or production qualification.

The real workspace passed 14 supervisor, 36 application library and three CLI tests. The same-source harness passed 29 tests with two explicitly privileged controls ignored; those counts overlap the workspace tests. A real Unix-socket negative control made exactly one runtime observation, zero package calls and returned all 42 rows blocked. All three original source/test/negative-control jobs were independently reread as succeeded with exit 0 and complete durable output. The patch was independently applied to the exact R2 parent and reproduced all 14 copied source files. Source, tests, receipts and the current production/selected-leaf integration audit are frozen under apps-runtime-fence. The A08 entry now executes this successor harness; R2 evidence remains historical.

The actual d6960d6 A08 run 42648494252 completed successfully with all 32 steps, including four exact source-patch replays, the ordinary-UID proc access regression, the R2 22-test module harness, the ten-test evidence checker and the full 26-test Audio source suite. The exact Audio and Native Rust replay verifiers also compiled and replayed successfully as UID 1000 on Pocket4. These are source and host controls; selected Android application acceptance remains 0/42.
