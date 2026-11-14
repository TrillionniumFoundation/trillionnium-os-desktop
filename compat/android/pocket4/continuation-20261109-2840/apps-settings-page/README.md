# Settings admission and pending action corrections

This capsule closes unsafe acceptance and retry paths in the prepared Settings integration. **Real Settings page execution is still blocked before any Android command because no selected-framework task-creation authority is available.** Nothing in this capsule qualifies an Android application or installs a new binary. Actual application acceptance remains **0/42**; runtime qualification and production readiness remain false.

## Source identity and application

The eight maintained Rust changes are private source commit `75492962a9b9afdd6b9f28fec979b9c40419ec0b`, parent `7113c8fe36fc34b6350cb61478bf2082bb211d2e`, tree `b7f7ad4b0b0acfd9993f9a7db4d4be6278453a90`, on `fix/pocket4-settings-owned-page-20261109-2840`. The commit was observed clean on Pocket4 under UID 1000; it was not pushed or installed. The commit receipt and authoritative H terminal are in `evidence/SOURCE-COMMIT*.json`.

`source-binding.json` contains the exact four original files and four additions. Apply `settings-failclosed.patch` to that exact source parent. Its SHA-256 is `972500d13d451ce5d07a23fbfbd8cd9e113726029e59b81fd715ad64b4353d0c`. The four originals are supplied under `preimage/`; every postimage is under `source/`. An actual local `git apply --check`, apply, and eight-file byte comparison succeeded (`evidence/local-patch-replay.json`). No separate replay implementation was introduced; the publication workflow can reuse its existing source verifier with these pins.

The six additional unchanged Rust source files are dependencies of the CI harness, including the actual package observation module and existing native IPC/protocol/transport implementations. They are not replacement implementations of the daemon or dispatcher.

## Closed unsafe acceptance boundaries

1. **Task differences and successful starts cannot grant task ownership.** The public native Settings launcher validates its fixed request shape and returns a missing-authority error without starting Android or connecting to task control. Its advertised protocol is `droidloom-settings-observation-v2:blocked-no-framework-created-task-authority`. The daemon checks the Android user and existing host cell/UID authorization, then calls a gate that has no probe or deadline argument and always fails. It does not construct `LiveApplicationProbe`: that constructor would already query Android properties. Ordinary interactive launcher behavior is unchanged.

2. **Candidate preparation is test-only.** The single-start candidate flow, task snapshot parser, action-scope writer/retirement logic, native tree matching, and candidate cleanup calls are behind `cfg(test)`. They exercise fixtures and normal host primitives, and cannot be reached from the production Settings entry. Task receipt terminology is `TaskCandidate`. `SettingsObservation::completed_partial()` always returns false; JSON declarations cannot create an authority. No candidate task snapshot or ACK is treated as proof of the creator.

3. **Reuse warnings never register even a test candidate.** The existing native host-process/AF_UNIX fixture now covers stdout and stderr warning responses with `Status: ok`. They close the peer without sending `RegisterDirect`; the command log contains one start and no task cleanup. This is a defense against a particular reuse result, not a claim that warning-free starts prove creation.

4. **Pending state gates every daemon mutation.** Only Status, Readiness, WaitReady, Diagnostics, ObserveRuntime, InspectApplication, ListApplications, and ApplicationIcon bypass this guard. Install, InstallMultiple, Start, Stop, Restart, Launch, OpenBrowser, ObserveSettingsPage, SetDpi, and future variants default to the pending check. It opens the held `/run/lock` directory without following a symlink, checks UID 0, and checks the fixed marker name relative to that descriptor. Any marker inode, including a dangling symlink, blocks. Only an absent marker clears admission; missing/untrusted directories and other I/O failures block. There is no marker parsing, removal, automatic recovery, or second flock acquisition.

5. **Every failed Settings result stops later mutations in the selected run.** This includes top-level RPC errors, contradictory identities/pages, retained scopes, and structured `ok:false` observations whose JSON says `action_scope_retained:false`. No read-only epoch check can reauthorize the run after any unsuccessful Settings result. Diagnostic observations remain in the report, and all rows become blocked. The complete-looking JSON fixture proves that later Firefox is not opened, the runtime query is not repeated, and all 42 rows remain present with zero accepted gates.

6. **The two staged UI consumer sources obey the same persistent marker.** The narrow patch in `consumer/` adds the check before `arun`, `ui`, and `dispatch`, covering direct imported entry functions as well as the CLI. It blocks all those Android entry operations while pending, including helper reads. The helper's existing flock is not reacquired, so a helper that calls `droidloomctl` while holding it does not deadlock. The check never reads or clears the marker payload. These are isolated source successors, not changes to installed consumers.

## Why the real Settings operation remains blocked

The independent selected **CP3A.260905.010 / 16176746** DEX audit is pinned by `reference/selected-framework-dex-INDEX.json` (SHA-256 `4767e9083da80c561e96ac21884ad10096bab9b29aec89ccccd59dca4b82702e`). The full method evidence is maintained in the separate `native601_closeout/qpr1-stock-dex` publication package, not duplicated here.

The actual selected framework preserves Intent identifiers through relevant copies and stores baseIntent, task identity, window-container token, and launch cookies in typed task information. However, the current `cmd activity stack list` route prints RootTaskInfo without baseIntent/identifier. The actual WaitResult has no task ID. `removeTask(int)` has no nonce-conditioned cleanup argument. A pair of task-list snapshots and a successful shell start therefore cannot prove this request created the task or authorize its removal. Adding flags or trusting a JSON boolean is insufficient.

A future implementation needs an actual, selected-framework creation/observation authority and safe cleanup association, or an independently held exclusive test-cell authority. Neither exists in these APIs. A future provider must also preserve the actual task/window, lease, epoch, helper, and byte bindings. No such provider is claimed here. The daemon still owns the existing DevelopmentCell lifecycle; this change does not add a ProductionCell.

## Test evidence and source generations

All reported execution occurred as ordinary UID 1000 on Pocket4 with affinity CPU 2, one Cargo build job, and a 2 GiB job memory limit. No Android UI command, application install, production service start, network test, account login, message, call, or purchase was performed.

| Evidence generation | Actual command groups | Scope |
|---|---|---|
| r2, H `1a1c1954ce3-e62c-d2` | Settings 23; daemon pending 1; real cold-daemon socket 1; native 30 library + 5 CLI; applications 42 library + 3 CLI; consumer 6 | Historical **111** passes on the earlier r2 pins. Kept verbatim; the later control/Settings/dispatcher corrections do not inherit this generation's credit. |
| r3, H `1a1c19d1019-e62c-de` | Settings 23; daemon pending 1; real cold-daemon socket 1; applications 42 library + 3 CLI | **70** actual workspace passes after the two final review corrections, with all eight final source pins recorded. |
| Same-file harness in the same r3 H job | Settings 23; native 30 library + 5 CLI | **58** passes using `#[path]`/Cargo lib/bin paths to the exact delivered sources. The 23 Settings cases overlap r3 workspace execution. This is CI packaging qualification, not extra app coverage. |
| Unchanged consumer sources from r2 | 6 Python controls, each checking both complete consumer sources | Their exact postimage hashes did not change in r3. These tests use the original AST function bodies and real temporary filesystem inodes; they do not import PIL or invoke Android. |

Every named group has the full raw test output, byte length, SHA-256, argv, and exit code. Both successful H jobs have authoritative exit 0, complete output, and durable output records. The cold socket test's explicit marker proves its actual AF_UNIX exchange ran on Pocket4; no sandbox skip was credited. Cargo stdout and stderr were intentionally captured together in each group log. The H job's separate stderr was empty and is retained as an empty file.

The original first-draft 78 passes are not added to these counts. The r2 111 are not added to r3 70 or to same-file 58. Most cases overlap across generations; these numbers are executions of ordinary controls, not independent end-to-end proofs or application acceptance counts. No privileged lifecycle tests were run or credited in these new groups.

## Reproducible CI and exact dependencies

`CI.md` provides three commands for the existing source controls: Settings 23, native 35, and consumer 6. There is no fabricated daemon, fake public control handler, or duplicate dispatcher implementation in the harness. Daemon and dispatcher qualification remains the actual workspace execution in the r3 evidence.

`harness/Cargo.lock` is 8,456 bytes with SHA-256 `09b1618ccdaff1511d938536ce54fb119df215be57663aa45cc28e9acdbc9fe6`. All **34 external package name/version/source/checksum tuples** match the actual source workspace lock, SHA-256 `ca5300907a8e609ac0340d016ecfe7b4292bf45fe5ab3cbe8dd0c013f12a2285`, included under `reference/`. The observed comparison and actual locked executions are in `evidence/r3/HARNESS.json`.

The first unseeded offline lock generation selected five newer transitive packages. The exact-dependency gate rejected that run before tests. Its failed terminal and original output are retained under `evidence/initial-harness-lock-rejection/`. The final lock was resolved from the complete original lock, all 34 external tuples were checked again, and the successful test commands used `--locked --offline`. The gate was not weakened and no checksum was invented.

## Deployment and cleanup boundaries

`consumer/source-binding.json` binds the two **staged, intentionally undeployed** source preimages and the existing deployment manifest. This patch must be adopted as a coherent source/deployment successor; it does not change current canonical pointers or installed helpers. Legacy prepared leaf scripts that import earlier helper bytes need fresh source bindings and qualification before using the new marker protocol. The exact staged-versus-installed distinction is retained in `reference/consumer-deployment-preimage.md`.

No canonical CURRENT, shared registry, owner source, installed artifact, signing material, app data, or official APK custody copy was changed. Meituan data and both newly verified AirChina/Beike candidate APKs remain protected pending owner adoption. Any retirement of these isolated source/test directories must follow durable publication and a fresh check for live references; publication of this capsule alone is not evidence that a process has exited.

### Remaining functional blockers

- Real framework-created-task authority and associated safe cleanup semantics.
- ProductionCell lifecycle admission and deployment of a coherent current binary/consumer set.
- Actual Settings pages, pixels, permissions, round trips, and the six common release gates.
- The other applications' actual business leaves, authenticated official delivery where absent, and all 42 runtime acceptance results.

The source defects that could falsely accept a candidate or continue after failure are closed in this reviewed revision. Those functional and runtime blockers remain explicit.
