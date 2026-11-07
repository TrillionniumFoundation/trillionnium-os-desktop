# Pocket4 Android — checkpoint 11

Whole-App production readiness remains **0/45**. This is a source-and-evidence checkpoint while repair work continues. Main engine and supervisor are not deployed by this checkpoint. The original failed attempts remain available alongside each new result.

The machine-readable current scope is [status.json](status.json). The preceding checkpoint's 4,049 payloads remain byte-identical; this checkpoint adds independently verified source, exact requests, actual receipts and bounded summaries. Raw commercial UI trees, APKs, ELFs, archives and build caches are excluded.

## Actual changes and evidence

| Area | Actual result at this snapshot | Remaining gate |
| --- | --- | --- |
| NOFILE descriptor owner | Matching Android preimage/candidate differential passed all 26 expected cases in each arm. Preimage retains 11 precise EMFILE failures; candidate matches all expected outcomes, including intentional startup denials. | Initial NOFILE-zero authority, fresh-generation admission after zero, trusted virtual O_PATH reopen, full-engine integration and production lifecycle remain separate. |
| Candidate06 engine | Three source files integrated; all 11 tested production inputs match exactly. Preparation verified 948 total files, 925 engine files and the exact 450-file runtime builder. | Full build02 is running after fresh resource admission. No complete artifact, host-suite or Android-canary result is inferred. |
| Real Rust Owner / init | Real init HELLO and broker READY reached PROJECT. The diagnostic constructor identified project-bind-mount, errno 22, before PROJECTED or ACTIVE. | Matching host/init projection fix and real ACTIVE-to-Stop lifecycle are still required. |
| Bilibili owned QA R3 | Exact helper provenance, search entry, fixed public text edit, current-value-bound submit, independent restoration and exact task cleanup passed. | The actual final tree shows the public query and a loading indicator with an empty result pager. Video/result success is not established. |
| ART and updater pairing | Source review identified PROCMET2 engine/bridge versus remaining PROCMET1 ART-runtime and updater pair expectations. | An independent matched revision, actual ART build, contract production/consumption and enabled lifecycle are required. |

### NOFILE: actual Android differential

The [original runtime result](actual-evidence/nofile-recovery03-android-runtime01/coordinator/coordinator-result.json) is bound to the matching build and the exact candidate/preimage APKs. Both arms reaped 26 direct and five nested children, preserved the expected capability/signal-mask/clear-tid invariants, removed their owned packages and completed the Main fence without a forced cleanup kill.

Root independently checked all 52 case records and all 18 original artifacts; the original pure instrumentation assessment was also re-applied. Owned peak memory was 90,783,744 bytes with zero swap and zero recorded owned memory-event deltas. These figures describe this scoped runtime. Main's historical swap peak is not claimed to be zero, and the matching build's memory-max counter is not claimed to be zero.

The original harness's hardcoded Android-qualification field is preserved. The separate actual Android differential assessment establishes only its stated 26-case scope.

### Candidate06: exact integration and current build

[Composition](actual-evidence/candidate06-composition01/composition-report.json) binds candidate06 to the original candidate05 manifest and the actual host/Android NOFILE results. The behavior change is in the raw metadata owner implementation; the two header changes preserve matching tested comment text. Of 948 total sources, 945 are unchanged; of 925 engine sources, 922 are unchanged.

The compiled builder still has its original 450-file manifest. The derived runtime manifest changes only one byte in the existing Go heap-budget patch, from Go6 to Go5; the other 449 entries, compiled Rust ELF and Blueprint streaming patch remain exact. [Preparation](actual-evidence/candidate06-go5-prepare01/preparation.json) and the copied manifest were collected in full and independently verified.

The [first fullbuild fence](actual-evidence/candidate06-go5-build01/terminal.json) failed before the compiler subprocess because fresh MemAvailable was below 13 GiB. The original controller did not persist that numeric memory reading; it is not reconstructed from a later sample. Main before/after identities and OOM deltas passed.

A separately reviewed request binds that original failure and a new, independent read-only memory sample. It preserves build-fences-01, creates build-fences-02 and requires the original attempt directory to remain absent before invoking the unchanged controller. There is no retry loop. The controller still makes its own fresh kernel admission with a 13 GiB RAM / 2 GiB swap minimum, a 10 GiB RAM / 1 GiB swap owned limit, two CPUs and one build job.

The [actual startup observation](actual-evidence/candidate06-go5-build02/startup-observation.json) records 14,372,683,776 bytes of available RAM and 4,361,625,600 bytes of free swap, then starts the normal two-target build on CPU affinity 22 and 23 out of 24 available CPUs. The normal source projection, builder lock and journal recovery remain mandatory. Streaming allocation savings from the earlier bounded Go comparison are not proof that this complete build cannot OOM.

After successful actual artifacts and all five build receipts exist, the [fence02 qualification template](native-work/engine-qualification-template-02/) binds them to the original full 3,793-test host suite and four owned Android signal cases. Earlier engine/canary PASS results cannot substitute for those new runs. SMC is never rewritten as SVC.

### Owner03: first failure now identified

The original NORMAL01 runtime failed at PROJECT without a detailed C diagnostic. Diagnostic build02 compiled successfully but its controller rejected the actual dependency-file target; that failure is retained. Build03 fixes only the exact expected target comparison, passes all 13 matching commands, preserves the original 147 inputs / 140 dependencies and passes 20 protocol, 20 close-errno and seven diagnostic controls.

NORMAL02 preparation failed before owned-root creation because the old exact scope predicate rejected its new scope. NORMAL03 retains the original nonce, identity, image, source, artifact, Main and resource checks with its own exact scope/kind. Its first local runtime binder also preserved an ASCII-serialization mismatch and fixes only the expected fixed serializer; preparation was not replayed.

The [actual NORMAL03 runtime](actual-evidence/owner07-normal03-runtime01/runtime-result.json) and [15-member fixed log collection](actual-evidence/owner07-normal03-logs01/reader-report.json) establish the first constructor failure:
`project-bind-mount errno=22`. Both producer and init use the same user namespace and different mount namespaces. The cross-namespace mount mechanism is under investigation; the precise kernel cause is not yet claimed as proven by this checkpoint.

The actual failed generation retired without broker authority, gaps or cleanup failure. All four helpers were reaped without forced kills; the original actor died, the exact unit disappeared and its cgroup was absent. Main before, gate and after snapshots match. Owned peak memory was 170,573,824 bytes, swap was zero and recorded owned high/max/OOM deltas were zero.

No ACTIVE, pressure-effect, property-reload or whole-App qualification is inferred. The original RC/property hooks and coherent same-generation LMKD update remain paired work, because restoring a property hook alone would re-enter a one-shot lease.

### Bilibili: submit passed; real result page is still loading

R3 has an independently built and signed APK, installed as UID 10166. Its finite complete-tree protocol remains strict. The first R3 click refused a changed whole tree before attempting the node action; that failure is preserved. A subsequent bounded read-only stability gate allowed the original strict fresh click and reached the actual search page.

The [public-query attempt](actual-evidence/qa-r3-public-query01/coordinator.json) performs at most two clicks and one fixed public edit. It verifies the input value by helper readback and then verifies the same value again in the submit action's own fresh inspection. A local negative control demonstrated that the old submit path could click after the value changed; the strengthened view refuses the click and still completes independent after-state handling. The underlying Session, Java helper, held-namespace transport and cleanup code remain unchanged.

All query control phases, restoration checks and cleanup passed. Owned task 880 was removed and original Home task 851 remains. Main and helper/source identities match before and after. Owned peak memory was 118,517,760 bytes, with zero swap and zero recorded owned memory-event deltas.

The original `business_success_verified=false` result is retained. The private final tree has 28 nodes: the public query is visible, the loading indicator remains and the result pager has no child. The next fresh flow must wait through bounded successful read-only observations in its still-owned task, then obtain current result evidence before selecting a video. No retired node, window or task is reused.

Private UI bytes stay outside Git. This checkpoint includes only fixed reader source, safe summaries, hashes and the derived loading classification. Continued playback, pause, seek, Back, reopen, cold start and App-attributed audio remain open.

## Delivery and continuation

All new payload bytes, SHA-256 values and Git blob identities are verified. Checkpoint subtrees and each changed ancestor are independently reconstructed; unrelated siblings remain unchanged. The final delivery manifest inventories every inherited and new payload, excluding itself.

The active build is a durable job; stream EOF alone is never treated as a terminal result. Actual terminal status, complete durable logs, artifact validation, normal journal handling, Main fences and exact owned cleanup are required before accepting it.

This checkpoint does not conclude the repair task. Continue the [open gates](status.json), preserve every original failure, and keep the PR in draft until complete App-level acceptance exists.
