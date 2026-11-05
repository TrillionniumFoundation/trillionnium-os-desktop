# Pocket4 Android — checkpoint 13

Snapshot: 2026-11-05 07:25:23 UTC. Repair and actual acceptance continue. **0 / 45 launcher Apps are qualified as whole-App production ready.** Main engine and supervisor have not been deployed by this checkpoint. This is an immutable evidence and source checkpoint, not completion of the user’s request.

## What changed and what actually ran

| Workstream | Actual result at this snapshot | Qualification boundary |
|---|---|---|
| Candidate07 engine | Complete build succeeded; engine SHA-256 `3aa9b479a9b66f56ae827477cf9f957fdeb6dcb21f1f8f981e34a1089f80048a`. The full host receipt registers 3,793 tests, executes 3,791, completes 3,788, skips 3 and retains 2 disabled, with zero failures. | Resource-limit events in the full build remain evidence; they do not qualify runtime resources. |
| Candidate07 Android | Input checking, actual preparation, runtime checking and exact root-review staging passed. Four-case run `1a1aa971fa5-fc05-44d9` was admitted against those exact artifacts. | Actual case outcomes and cleanup remain pending here. No old userdata or Main deployment is admitted. |
| Matching builder451 | Original compile01 failure is retained. Compile02 succeeds with 55 commands, all 22 exact tests and five real image controls. Each selected test has one independent libtest success record; the deliberately nested fakeroot control retains its two stdout summaries. | This is builder and pairing validation. Platform-signed ART APEX and enabled lifecycle qualification remain open. |
| Owner09 ABI3 | Actual Rust build, 23 relay / 122 supervisor / 7 IPC checks, Android DSO and private mount mechanism passed. NORMAL09 fails after InitHello, before BrokerReady and ACTIVE. | The audit reports lifecycle packet framing/ancillary rejection. A specific triggered broker gate is not inferred without its actual log. |
| Bilibili QA | R4 reached acknowledged query entry, then failed with 21 unfocused window samples in 2 seconds. R5 adds confirmed public own-connection cache clearing; build01’s stale package regex failure and build02’s successful correction are both retained. | Cache causation and playback remain unproven. Actual R5 install/state02 failed; its worker first error is being collected. No successful installation or UID is inferred. |

## Concrete repairs and preserved failures

The completed engine contains the previously reviewed host-UAPI compatibility fix and tested descriptor owner implementation. Its original oversized collector failure is retained; a separate terminal supplement binds all 926 effective engine sources and eight actual artifact records. The full host run uses the original filter, repetition and disabled/skipped policy, without sharding or replacing tests.

Builder451’s first actual runner rejected an otherwise successful exact test because `mkfs.erofs` output split the libtest console line. The repair uses the pinned libtest’s independent result file while retaining exact registered-name selection, single-test counts, process exit, held-file identity and cleanup gates. Compile02 peaks at 946,839,552 bytes, records zero swap and zero owned memory-event deltas, and leaves no remaining child. Those are scoped observations, not a Main identity measurement.

ABI3 hands the finite Android cgroup through a private holding view and places init in its exact bootstrap leaf while leaving the stock cgroup mount target available for Android setup. NORMAL09 captures the same live init through pidfd, process birth, executable and namespace identities, plus separately bounded clock samples. The original Owner Stop/retirement does not succeed. The external exact-unit cleanup does retire the actor, unit and cgroup, and the attempt’s Main fences match. No global kernel journal line is attributed as the cause.

The R5 helper preserves the focused application window, display, package, complete-tree, time and query limits. Public `UiAutomation.clearCache()` must succeed before every window query. Synthetic cache controls establish the candidate’s local behavior only. The actual build02 keeps all nine exact sources, all seven unchanged tool records, eleven joined commands and strict manifest/signature checks. Install/state02 remains failed; its primary worker error and installed-package state must be read before any next admission.

## Evidence layout and continuation

`source/` contains the 684 frozen source and control payloads enumerated by the unified source allowlist. `evidence/` retains 147 independently inventoried originals plus this checkpoint’s explicit later supplements. `requests/` preserves additional exact executed or admitted requests. `metadata/` records source mappings, original selection decisions and actual receipt provenance. Existing checkpoint-12 payloads are inherited byte-for-byte.

The current machine-readable scope is [status.json](status.json). The complete file/byte inventory is the parent [delivery manifest](../delivery-manifest.json). Publication verification covers exact payload hashes and Git blob identities, the checkpoint subtree, changed ancestors and manifest readback. Binaries, signing secrets, caches, raw commercial UI, screenshots and private runtime journals are excluded.

Continue the actual four-case run, the paired broker repair, the R5 failure diagnosis and fresh business-flow validation, complete ART/APEX lifecycle integration, and all 45 App acceptance gates. No source-only work, preparation, collector success or partial App flow is promoted to whole-App readiness.
