# Pocket4 continuation: host regression fixes and release evidence coverage

This source publication addresses observed host and source defects and records their actual verification. Whole Android and application production qualification remains open.

## Current continuation state

Both actual strict r12 full builds failed and retired. The exact missing-input repairs are now available as independently committed, normally tested source: Audio `b555f4538547a2dffa3349e914e489858ef3d3d0`, Native `c0522b7877485d786b58b67b02e8297e41d53c8c`, and the separate Android Java environment successor `7113c8fe36fc34b6350cb61478bf2082bb211d2e`. Their complete patches, preimages and postimages replay exactly. Shared source reconciliation, the next strict full builds, actual Android startup and all 42 application acceptances remain pending.

The foreground owner's `caed30a83c3af70bf7a769968e6365b46d99d26c` publication adds the ordinary ProductionCell foundations. This continuation preserves those source and CI changes. It does not claim that the foundation is integrated into a running production cell. The canonical foreground-owner state and original user images are untouched.

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

The actual A08 run 42662100482 on 11c32359708244886c29064eeb36a46ccc5f75ee completed successfully with all 33 steps. Its complete original job log confirms the exact three-file C11 and seven-file vendor Audio source replays, 21 vendor candidate controls, 29 application-generation controls with two explicit privileged controls ignored, and the then-current 26 Audio source-library tests. The preceding bed3989 run 42656749197 also passed all 32 steps. This successor changes the Audio source test step to the exact new 27-test library and adds the Audio/Native r12 and Java environment source replays plus the 14-test Java environment harness. Those new CI executions are pending at publication preparation; remote normal results are described separately below.

The earlier A08 run 42640649729 on c5b5319 was cancelled at the 15-minute job limit while downloading JDK packages, before repair tests executed. Tool preparation now verifies and reuses the runner-provided Java 17 JDK/JNI headers and existing compiler/media tools, installing only missing components. The same JNI/media tests, source inventories and job deadline remain required.

Complete Native/Audio output qualification, same-QPR1 compatibility, ProductionCell integration, writable init proc and actual Android boot still gate final application acceptance. A current runtime generation must then pass all 42 applications' actual common and business checks. Source or host CI does not grant that credit. The foreground owner retains the canonical CURRENT and original Android data; this continuation does not modify them.

## Application runtime generation successor

The immutable R3 source commit deacfc207c99a74a8aac056b086dc1b8f7e8f0c2 extends the R2 entry with one initial read-only runtime observation and a sticky generation fence. Missing runtime blocks the entire selection before package calls; transport failure or an observed generation change stops subsequent calls, without replaying a failed operation. The actual daemon currently owns DevelopmentCell and reports that lifecycle explicitly. The report continues to grant no application acceptance or production qualification.

The real workspace passed 14 supervisor, 36 application library and three CLI tests. The same-source harness passed 29 tests with two explicitly privileged controls ignored; those counts overlap the workspace tests. A real Unix-socket negative control made exactly one runtime observation, zero package calls and returned all 42 rows blocked. All three original source/test/negative-control jobs were independently reread as succeeded with exit 0 and complete durable output. The patch was independently applied to the exact R2 parent and reproduced all 14 copied source files. Source, tests, receipts and the current production/selected-leaf integration audit are frozen under apps-runtime-fence. The A08 entry now executes this successor harness; R2 evidence remains historical.

The actual d6960d6 A08 run 42648494252 completed successfully with all 32 steps, including four exact source-patch replays, the ordinary-UID proc access regression, the R2 22-test module harness, the ten-test evidence checker and the full 26-test Audio source suite. The exact Audio and Native Rust replay verifiers also compiled and replayed successfully as UID 1000 on Pocket4. These are source and host controls; selected Android application acceptance remains 0/42.

## Exact C11 Binder review fixes

`binder/c11-review` preserves the original C11 preimages and two independent patches: deadline acceptance checks and mapped ownership of Binder root/features inodes. Both patches together compiled from a fresh target and passed 11 distinct ordinary tests in 13 executions; the private control remained explicitly ignored. The initial zero-test attempt is retained as rejected evidence. The exact remote capsule is `/home/alex/work/pocket4-production-binder-stage-20261109-2840-r1/c11-review-capsule-r1`.

The three-file combined patch is only the concatenation of the two disjoint patches. The Rust verifier beside the capsule checks exact preimages, creates a new private replay tree, applies that combined patch and requires the three exact postimages. The agent's frozen 36-file capsule remains unchanged. The active owner's private Binder result must retain its actual source-generation binding; ordinary review tests cannot transfer private-control credit to a successor.

## Vendor-only Audio candidate staging

`audio/vendor-candidate` contains the final Rust updater source at 207cb626934534e0c4600312d1afa8552c835df1. Its command consumes a pinned successful normal full-build terminal and stages only the complete vendor Audio APEX. It leaves official ART, runtime/bionic, framework and Connectivity outside this staging operation. All six signing, compatibility and runtime qualifications remain false in the candidate manifest.

The actual updater passed 21 controls, built normally and rejected the real SDK-source-only receipt without creating a candidate. The final follow-up synchronizes both files after their final permissions, every new directory from the deepest directory outward, and the existing parent. The portable harness compiles the exact three final source/test files after byte-for-byte comparison and passed the same 21 controls; these counts overlap. Seven changed source files and four original preimages replay exactly. The new CI step repeats the exact source replay and those portable controls. No real Audio APEX was built or deployed by this staging-source work.

## Current public application input refresh

`apps/current-input-refresh` contains two complete new publisher artifacts' exact metadata and verification evidence. Beike remains 3.06.71 / 3067100 with the same signer, but its whole-file digest is now 6984af4bbeda2818ad0a35183dd59af798eceebb9e441ef869b32dcc5095f728. Air China is now 7.53.3 / 75303 with digest f16f429b21c3402b362f5d3058476dfd97c29986f688e95e0d5294368d104fab and the same signer; its official page's older 7.53.2 text is not used as the APK version.

Both complete APKs passed fresh aapt and apksigner verification and are held read-only for foreground-owner custody. They are not installed or selected. Separate bounded GET checks resolved the Pinduoduo and Douyin HEAD differences to their previously selected official objects, without claiming new whole-file hashes. None of these observations increments the 0/42 current-runtime acceptance count.

## Verified retirement of owned obsolete probes

After immutable source/evidence publication at bed3989, three owned, superseded executables were removed: the Audio and Native source-replay probes and the ordinary proc-access probe. Exact file hashes and identities, process/mount references, inactive units and CURRENT path references were checked before removal. The deletion held the original coordination lock, preserved canonical CURRENT, synchronized containing directories and checked physical absence. A subsequent independent job again observed all three absent. The exact intent, result and readback are in `cleanup/owned-probe-retirement-r1`.

This retirement removed 12,579,512 bytes. It does not represent final old-generation cleanup. Active builds, selected inputs, original user data and unresolved signers remain protected until their replacement and consumers are verified.

## R12 original input closures

The Audio r12 failure exposed missing SDK33 module-lib and original zygote Rust providers. `audio/r12-provider-closure` preserves the exact actual failed full-build receipts and output, then selects only four additional paths at the existing revisions: SDK33 `module-lib/android.jar`, `module-lib/core-for-system-modules.jar`, `zygote-sys` and `zygote-proc-macros`. All 430 project revisions and original SDK consumers remain unchanged. The complete normal source library passed 27 tests, the Audio updater passed 55, both normal tools built and the source CLI verified 430 projects with eight root links. There were no failing or ignored tests in those two groups. These source and normal-tool results do not qualify a full APEX.

The two complete official SDK JARs were subsequently obtained from the exact fixed Gitiles commit into an isolated input directory. Their full-file SHA256 and Git blob identities matched, and every one of their 13,961 and 1,869 ZIP entries passed a complete CRC read. All eight original Rust files in the newly selected zygote directories were also read and matched against the fixed original Git tree; no extra module-path or include input was found. The two follow-up raw receipts are beside the frozen capsule as `audio/r12-original-sdk33-jars.json` and `audio/r12-original-zygote-rust-inputs.json`. The root independently read those complete receipts and terminal states; it did not claim a separate rehash of the 65,516,972 JAR bytes or shared-source materialization.

`native/r12-flags-provider` adds the complete original Telecom and update-engine `flags` directories while keeping all 601 revisions and both strict full targets unchanged. The update-engine dependency on `fake_device_config` is already covered by the full frozen `build/make` selection. All 28 provider files plus two project-root Blueprint context files match their exact recorded Git blob identities. The root independently recalculated all 30 full-file hashes and replayed the three-file source patch.

The Native repair passed 35 distinct ordinary tests: 22 module controls, 11 existing Android pair controls and two source-plan controls. Both normal tools built and the source CLI verified 601 projects with eight root links. The original controller's 33-versus-22 count assertion remains a failed controller receipt; the actual 33 passing test names and full output were independently checked. The continuation ran only the two remaining tests and the build/CLI commands. It did not rerun or relabel the failed controller. Both ordinary units and cgroups were independently verified retired.

The exact Audio and Native Rust replay verifiers are beside their frozen capsules. The updated Audio CI helper copies the new complete library and lock together with the previously published, independently pinned historical fixture, Cargo manifest and dependency lock. It checks all five inputs before and after real Cargo execution and requires all 27 exact test names, with no filtering or ignoring. The historical 26-test capsule remains unchanged as source provenance; its result is not attributed to the new library.

## Android Java operation environment

`apps-java-environment` carries the exact successor to the R3 application command entry. Explicit `am instrument` and `app_process` operations now obtain a bounded allowlist of Android framework environment variables from the already held framework process and proc directory. Required classpaths and Android roots must be present and canonical. Duplicate, empty, traversal and oversized values are rejected. Unrelated host, loader and private variables are discarded. The framework identity and selected environment are revalidated after the operation, within the existing absolute deadline.

The change passed 14 ordinary workspace tests and the same 14 tests in the same-source harness; those are overlapping executions, not 28 distinct tests. Nine controls are new, including parser rejection, a real owned host child environment/PIDFD exit case and an expired operation that never executes. Two privileged cgroup/namespace controls remain explicitly ignored for this successor. The exact three changed source files replay from the published R3 preimages, and the three unchanged real CPU/PIDFD dependency files remain byte-identical. This source is not deployed, adds no ProductionCell adapter and grants no actual Settings or other application acceptance.

## Actual retirement of six obsolete Binder roots

After immutable publication and full readback of 11c323, six exact superseded Binder source/target/sealed-executable roots were deleted. The removal checked exact integer file identities, every selected content hash, hard links, Cargo locks, live processes and mapped files, mounts, loaded units and canonical-state references. It retained the combined C11 source, frozen review capsule, foreground-owner source and all original evidence. All 30 protected file hashes and canonical-state bytes remained unchanged.

The actual deletion removed 3,514 file names containing 1,410,490,310 logical bytes. A separate durable job subsequently observed all six paths physically absent, no remaining live references and no temporary cleanup lock. Both original raw receipts and actual H terminal states are under `cleanup/obsolete-binder-roots-r1`. This is additional to the previously recorded 12,579,512-byte three-probe retirement. These precisely scoped removals do not represent final obsolete-generation cleanup.
