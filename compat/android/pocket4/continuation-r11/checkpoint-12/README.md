# Pocket4 Android — checkpoint 12

Whole-App production readiness remains **0/45**. Repair work continues. This checkpoint preserves the completed scoped fixes, new failures and the running candidate07 full build. It does not deploy a new Main engine or supervisor, enable the metadata feature by default, or qualify any complete App.

[status.json](status.json) is the current machine-readable scope. The earlier 4,794 payloads remain byte-identical. This checkpoint adds 586 verified UTF-8 payloads, including these two documents. Raw commercial UI trees, screenshots, kernel journal data, APKs, ELFs, archives and build caches are excluded.

## Actual progress and remaining gates

| Area | Evidence at this snapshot | Remaining gate |
| --- | --- | --- |
| Native engine | Candidate06 reached host compilation and failed on a missing old-sysroot header. A private compatibility header fixes that failure in five complete translation units using the same compiler, target, sysroot and warnings. | Candidate07's complete build is running. Its actual full host suite and four owned Android signal cases have not run. |
| Real Owner / init | The matching ABI2 detached-mount path passed real HELLO, PROJECT, PROJECTED, COMMIT and DONE. | The Android cell then exited with SIGHUP before ACTIVE. Exact startup cause, enrollment, pressure behavior and Stop remain open. |
| Bilibili | Fresh public search, exact current course selection, acknowledged click and three independent DetailsActivity observations completed. | The later observations still show buffering. Frames, pause, seek, Back, reopening, cold start and App-attributed audio remain unqualified. |
| LMKD reinitialization | A separate source revision retains the original RC/property semantics and proposes coherent same-generation policy reinitialization. | Matching complete LMKD/Rust builds and real property/lifecycle behavior remain open. |
| ART / updater | Source candidates cover PROCMET2 pairing and stopping the native owner before the actual kernel single-thread wait. | The 451-file updater, real image fixtures, complete ART targets and enabled runtime lifecycle remain open. |

## Native engine: actual compile failure, narrow fix, full rebuild

The [complete candidate06 evidence](evidence/candidate06-go5-build02/reader-report.json) preserves both original fences, the inner terminal, stdout, stderr and the actual effective input receipt. At Ninja step 2,113 of 2,247, the host `proc_maps_provenance.cc` compile failed because the pinned glibc 2.17 sysroot does not provide `linux/memfd.h`.

The job exited with a compile failure, without an OOM kill. It did reach its owned memory and swap limits and recorded memory-max pressure, so resource pressure is not represented as absent. The normal source projection was restored and its journal was absent afterward. Main's recorded pre/post identities, limits and OOM deltas passed; the observed socket-pressure and swap-current changes are retained without causal attribution or a claim about the whole interval.

A [fixed UAPI reader](native/host-glibc-uapi-reader01/) recorded eleven headers and five missing fixed paths. A missing architecture-specific path was not treated as proof that the compiler lacked the associated macro. The subsequent actual preprocessing showed that all four relevant syscall macros were already defined.

The [private compatibility patch](native/host-glibc-uapi-next01/host-glibc-uapi.patch) adds missing Linux ABI declarations, with exact constant assertions and architecture-bounded fallbacks. Four implementation files change only their includes. Runtime kernel errors, authority checks, descriptor ownership and existing denial paths remain intact.

The [matching complete-TU result](evidence/host-glibc-uapi-tu01/result.json) first reproduces the old header failure, then compiles provenance, raw metadata owner, descriptor owner, path and factory wire. Their actual dependency counts are 779, 332, 340, 747 and 183. Precompile dependencies match the compiler's emitted MD files, all observed source/tool/header bytes remain unchanged, and all owned children are reaped. Peak memory is 97,468,416 bytes, with zero observed swap and memory-event deltas. These are compile results; none of the produced objects is executed.

[Candidate07 composition](evidence/candidate07-composition01/result.json) contains 949 source files and 926 engine files: four existing files change, one private header is added, and 944 total / 921 engine files remain identical to candidate06. Its original NOFILE host/Android evidence and the new five-TU evidence are both revalidated.

[Preparation](evidence/candidate07-prepare01/preparation.json) retains the exact 450-file runtime builder, compiled Rust executable, Blueprint streaming patch and one-byte Go5 runtime-data change. The [fresh build admission](evidence/candidate07-go5-build01/startup-observation.json) starts the normal complete targets on CPUs 22 and 23 of 24, with one build job, a 10 GiB memory limit, a 1 GiB swap limit and the original 13 GiB / 2 GiB admission minima. It observes 15,124,082,688 bytes of available memory and 3,761,086,464 bytes of free swap before starting. This is not a physical-memory reservation or a completed build.

The [qualification template03](native/engine-qualification-template03/) keeps the original 3,793-test host suite and four owned Android signal cases. It must bind the new build's actual artifacts, five receipts, fresh fence, cleanup and source recovery. Historical suite/canary results cannot substitute. SMC is not rewritten as SVC. Initial NOFILE-zero authority, a fresh generation after NOFILE-zero, and trusted virtual O_PATH reopen also remain separate open gates.

## Owner08: real cross-namespace projection is fixed; ACTIVE is still open

The [actual host mechanism probe](evidence/socket-projection-mechanism01/result.json) distinguishes the failing foreign O_PATH bind from a detached mount. The [paired source revision](producer08/socket-pair-source01/) uses host `open_tree` to clone the pinned socket mount and init `move_mount` to place it on the held, freshly created target.

The pair advances the entry and wire protocol to ABI2. Old ABI1 traffic is rejected; there is no fallback to the foreign raw bind. Nonce, exact peer identity, endpoint device/inode/owner/mode, held descriptor, single-use and retirement checks remain required.

The matching Rust compile, 23 relay tests, 120 supervisor tests and seven IPC tests pass. The Android DSO build passes all 13 commands with the original 147 inputs / 140 dependencies and 20 protocol, 20 close-errno and seven diagnostic controls.

The [actual NORMAL08 runtime](evidence/owner08-normal01-runtime01/runtime-result.json) records all five real ABI2 frames and matching endpoint identity. It then records the Android namespace child exiting with SIGHUP before ACTIVE. There is no broker grant or registration. The exact actor dies, unit disappears and cgroup is absent. This failure remains a failure despite the newly completed projection stage.

The [fifteen original records](evidence/owner08-normal01-logs01/reader-report.json) contain no constructor failure. A bounded kernel-ring read finds that the ring no longer covers the original attempt. A separate persistent-journal read reaches its 256-record export limit, preserves the partial evidence and exactly reaps its sole owned reader child.

That partial journal contains init service-start failures and a reboot request, but it has no trusted caller identity tying them to this init's birth. Its source and receive clocks differ and are not interchangeable. Those records remain diagnostic candidates; this checkpoint does not label them the proven cause of Owner08's exit. Raw kernel data remains private.

The [paired reinitialization source](producer08/paired-reinit-source-wip01/) is independent of the frozen Owner08 run. Its Session socketpair controls pass locally, while complete matching LMKD/Rust builds and actual lifecycle remain unfinished. Source work is not a pressure-effect or whole-App qualification.

## Bilibili: fresh course navigation passes; buffering remains observed

The fresh result observation reaches a populated result page. Course selection is bound to the current public-query result, the exact title hash and the same card's uploader and duration hashes. It does not use an old node path, rank or a translated title fallback.

The [first video-open attempt](evidence/qa-r3-video-open01/navigation.json) acknowledges the exact course click and completes after-state restoration, then fails the immediate foreground read. An independent later inspection observes DetailsActivity, but does not make the original failed sequence successful. The old dump was not retained, so a null focus is not asserted as its proven cause.

The [new scoped foreground view](bilibili/r3-video-transition01/video_navigation.py) runs only after the current click is acknowledged and independent restoration is complete. It permits at most six successful read-only foreground samples within three seconds, and only a single explicit null-focus record allows another sample. Other packages, malformed or missing focus, ambiguous focus, transport failure and prior state failure terminate normally. The original Session, Java helper, held transport and cleanup remain intact.

Twelve local controls exercise this boundary. The [fresh actual flow](evidence/qa-r3-video-transition01/coordinator.json) completes all navigation and cleanup with three DetailsActivity observations of 72, 152 and 152 nodes. Its first foreground sample is valid after 34 ms; the null-wait branch is therefore not exercised by this device run and does not explain the original failure.

The later private trees still show buffering, with no eligible play/pause/seek control. A SurfaceView alone is not a decoded-frame or audio result, and its full bounds are not assumed to contain only the video. The next fresh flow must continue bounded observations and use current, independently bound image/control evidence. The retired private trees grant no new action authority.

Main, source and installed helper identities remain unchanged, the exact owned task is removed, and owned peak memory is 133,378,048 bytes with zero observed swap and memory-event deltas. Playback, sound and complete Bilibili readiness remain false.

## ART pairing and continuation

[PROCMET2 pair source](native/paired-v2-next01/) and [ART prefork source](native/art-prefork-quiesce-next02/) are separate candidates. The latter addresses the actual source ordering in which the raw owner thread can still exist when ART waits for kernel single-threaded state. Its opt-in macro belongs on the common compilation defaults for both affected translation units. It is not enabled by this checkpoint, and source inspection does not prove what the installed ART executes.

The complete updater, real ext4/erofs/APEX tool closures, full ART compilation, generation contracts, child-zygote capability behavior and enabled lifecycle remain required.

All 586 new payloads have independently checked bytes, SHA-256 and Git blob identities. The checkpoint subtree and every changed ancestor are reconstructed independently; unrelated siblings and inherited payloads remain unchanged. The delivery manifest inventories every inherited and new payload, excluding itself.

The durable build is still running at this snapshot. Stream EOF is not terminal evidence. Continue the [open gates](status.json), collect complete actual outcomes, and keep the PR in draft until all App-level acceptance is complete.
