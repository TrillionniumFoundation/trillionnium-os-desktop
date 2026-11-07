# Pocket4 Android continuation — checkpoint 14

Snapshot: 2026-11-05 10:46:42 UTC. Parent: `da53634c6309c2e189e98ecf59b26714b09e1d5f`.

**Whole-App production readiness remains 0/45. Repair and actual acceptance continue.**
This checkpoint preserves the actual results, corresponding source, original failures,
and scope limits. It does not deploy a new Main engine or supervisor.

## Actual progress

| Area | Result and practical limit |
| --- | --- |
| Candidate07 native engine | The full build and host suite passed previously. Four isolated Android cases now passed against the exact candidate engine: SVC, SMC handler, SMC default, and SMC signal-mask edit. All 16 original case files were read back. Four owned services retired, packages were restored, and Main was unchanged. The controller recorded 61,356 memory.max events; those are retained separately from the four services' zero memory events. Metadata generation and full-App acceptance remain disabled/unqualified. |
| Paired builder462 | Actual matching compile, 24 focused tests, and five real image controls passed across 57 commands. The suite registered 197 tests; this does not claim all 197 were executed. The actual builder ELF is pinned. Soong, enabled ART lifecycle, and platform APEX signatures remain unqualified. |
| Producer11 | The retirement diagnostic now preserves the first relay error separately from the outer lifecycle error. Matching actual compile and ordinary execution passed: 30 relay, 122 supervisor, and seven IPC tests, including four new preservation controls. No authority decision or lifecycle gate was loosened. |
| Owner11 | Fresh preparation passed, but the actual instance failed after init DONE and before ACTIVE. Original Owner retirement was incomplete. The outer coordinator subsequently removed the exact attempt's unit and cgroup and reaped all four direct children; Main stayed unchanged. The new diagnostic captured `open relative pinned directory: No such file or directory (os error 2)`, bound to this exact nonce, generation, and cgroup. The failed relative name and validation phase remain unknown. |
| Bilibili R5 | Actual installation03 passed. The public search and selected-course path completed with three post-navigation reads. A repaired structural predicate admitted the two actual SurfaceViews with their distinct, exact geometries. Two viewport crops passed before/after scope checks and were privately inspected: lecture content was visible and presenter position changed. The third capture observed a 320-pixel horizontal window movement and correctly failed the unchanged scope gate. The original run remains failed. Sustained playback, controls, lifecycle, renderer attribution, and App-attributed audio remain unqualified. |
| Amazon | The dedicated helper actually built, signed, installed, and completed one no-UiAutomation state read. The actual helper UID is 10175. All 13 commands completed; state was command eight. Commercial Amazon's exact three APKs were freshly hashed and held before/after, with identity and bytes unchanged. Owned staging, three APK FDs, the held Main binding, and the action lock were released. Main stayed unchanged. Public UI and business-flow acceptance have not yet run. |
| Factory/ART work | Fixed, read-only AOSP ingress/exit and policy sources were collected. A private native FS-query policy entry retains all stock BPF programs and changes only eight native query decisions in 213,512 comparisons; 16 real native/x32/stacking/NOFILE controls passed. Earlier compatibility failures are retained. A separate factory-role protocol passed 14 local receive/held-thread controls with 471 assertions. Root-parent positive grants, fork lifecycle, early policy, JNI/ART/APEX integration, and service enablement remain unqualified. |

## Evidence and source

`status.json` is the current checkpoint status. The continuation's delivery manifest
points to `checkpoint14` as its current status key; older checkpoint records remain
historical. `payload-index.json` describes this checkpoint's source and evidence,
excluding its own bytes to avoid self-reference.

Relevant original reports are under:

- `evidence/candidate07-android-result-read01` and `evidence/candidate07-android-cases-read02`
- `evidence/paired-builder462-compile01-transport02`
- `evidence/producer11-retirement-compile01` and `evidence/producer11-retirement-ordinary01`
- `evidence/owner11-normal01-prepared-read01`, `evidence/owner11-normal01-runtime-read01`, and `evidence/owner11-normal01-logs01`
- `evidence/bili-r5-player-geometry01-read01` and `evidence/root-bili-r5-geometry-visual-review01`
- `evidence/amazon-artifact-readonly01`, `evidence/amazon-qa-r1-build01`, and `evidence/amazon-qa-r1-install-state01-read01`

Frozen source is grouped under `source/owner`, `source/native`, and `source/android`.
Source indexes bind each payload to its original local bytes, SHA256, Git blob,
and origin tree. Original transport text is retained without reserializing large
timestamps or fingerprints. An uncertain Bilibili reader acknowledgement was
reconciled against its original durable job; it was not replayed.

Private screenshots, commercial UI trees, APK/ELF binaries, signing material,
caches, and unrelated job metadata are excluded. The visual review contains only
scoped observations and original-image hashes.

## Work that continues after this cut

Identify and repair the exact Owner lifecycle ENOENT operation with matching
compile, ordinary controls, and a fresh NORMAL run. Give every Bilibili capture
its own fresh pre-capture observation while retaining strict scope checks through
the capture. Complete playback/control/lifecycle/audio acceptance. Admit Amazon's
actual launcher and observed public UI, then continue the remaining per-App queue.
Finish the matched factory-role positive/fork mechanisms and paired ART integration.
All 45 Apps still require whole-App acceptance; this checkpoint is not completion.
