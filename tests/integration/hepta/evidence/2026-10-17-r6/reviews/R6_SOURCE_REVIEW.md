# R6 independent source review

This review covers code and evidence inspected by the independent reviewer. Original native linking, the external consumer build and the focused Shell freshness regression have now executed successfully with separate source bindings. The first six-phase capture attempt failed after its first real Starting image; a complete persistent runtime and six-phase Shell capture are still separate pending qualifications.

## Exact-source scope

| Item | Source reviewed | Review conclusion |
| --- | --- | --- |
| Persistent original Session gate | `4839e94939dc529963a73c581d653618e19a1c28`, tree `833063da19cb964132d616df425becfc85ca53d9` | No remaining source-level blocker identified after the stale-tail race correction; native compile and actual persistent runtime execution remain separate gates. |
| One persistent Shell across six original phases | `585404a6694cf7fbe6549f6ca12407706598c638`, tree `11b7fe4e1dca4d9c1940fed0c933fe1a990b4842` | Source accepts only actual Session UDS snapshots and captures real X11 pixels. Mechanical success still requires independent visual review. |
| Initial combined harness | `9d2ef72a4183460b1b4f1cdad97c1c013fa9d8dd`, remote same tree `f0924a6e48c68101ec09b01ef2f69aec330a3da7` | Original native link succeeded locally. The generated external probe's locked build failed locally and in exact-f092 ARM CI before probe compilation/runtime; that source did not pass the continuous runtime gate. |
| Lock-corrected old-UI execution source | `c50d7b9b688135a22ced2f7f3cbe21c3028d8e17`, tree `1b606b1922751fe938fa4bcca0a923516323f418` | Actual external probe/observer build passed with two Rust contract tests. First real capture produced one Starting PNG but failed the overly strict health equality oracle before ACK. Old R5 UI bytes remained unchanged. |
| Visible Shell freshness RED | `821841baf5c106b7fc5e4b849ac94636b1b724f7` | Actual RED execution produced exactly 1 pass and 5 intended assertion failures; the real egui status widget incorrectly displayed OBSERVED for an expired queued sample. |
| Visible Shell freshness intermediate GREEN | `f0f10dff564037fabc35809a8d8bb174dc5becb9`, tree `85d75a56d80b044afa486f0cb4c6159b889a0a12` | GREEN-01 reused the RED test ELF and failed source binding. GREEN-02 genuinely recompiled this source and passed 6 freshness + 2 layout tests, then failed strict Clippy on one new test-helper type complexity warning. |
| Visible Shell freshness final GREEN | `84f0070b6e7e01238a8dac6044748b15101c9497`, tree `9c8e3627a970f9c3f2bea9bbdde583adeb4bc313` | GREEN-03 genuinely recompiled, passed the same 8 focused tests, strict Shell Clippy, workspace formatting and workspace binary build. Four actual ELF hashes and three retained test ELF hashes were independently rechecked. A six-phase capture using this new Shell remains required. |

## Findings corrected during review

### Persistent Session stale history

The original owner may legitimately append another Draining event while restarting an already-draining Agentd. A controlled stop can likewise move Running to Draining before the socket becomes unavailable. A continuously polling Session can observe that final successful tail after the previously held phase snapshot.

The corrected gate validates the first stale sample against fixed old Agentd identity, original lifecycle/generation bounds, nondecreasing cursors and preserved event prefix. It then waits for a strictly later failed attempt and requires the complete last successful observation to remain unchanged. This proves stale retention without assuming that the earlier phase snapshot was the last possible successful poll. Old-spawn rejection and stopped-owner unavailability have separately restricted error classes.

The Session receipt also records real child PID, Session instance and Linux observer-thread TID across each continuous interval; actual host task lists must remain empty. A deliberate Session replacement uses the same runtime directory and socket path but a new Session instance. Two actual kill/reap receipts are required.

### Shell source closure and cleanup

The initial capture's source binding includes `ui`, `services/hepta-os/src`, `services/hepta-os/Cargo.toml` and `services/hepta-os/Cargo.lock`, because the production Session links the service path dependency. Matching only the UI subtree would have been incomplete.

The capture's private child process wrapper sets Linux `PR_SET_PDEATHSIG(SIGKILL)` and immediately checks its parent before exec. This closes the leader-survival case when the inside Python process is killed and its normal finally block cannot run. The corresponding owned-child fault test checks the actual signal death and reaping. This is a leader-lifetime guarantee, not a general arbitrary-descendant guarantee. Normal cleanup retains the waitable-child anchor until group signaling is complete.

The phase-six consumer accepts an actually observed final Running or Draining historical state. Atomic phase acknowledgments use no-replace rename and are coordination receipts; they do not independently establish rendered pixels.

### P2 visible freshness bug

See [the precise source proof and deterministic scenario](SHELL_FRESHNESS_P2.md). The previous Shell could consume an old queued Observed snapshot and reset only its local receipt age, allowing an already expired runtime sample to appear current. The existing layout marker independently rejected the expired sample, so its success did not establish visible-state correctness.

The GREEN code consumes pending responses, then evaluates both monotonic receipt age and original Unix sample age before any page draws. Both ages use the existing inclusive 7-second limit. Missing/future times fail closed; an Observed view without an observation becomes Unavailable; existing unknown-state diagnostics remain intact. The full historical observation and Session attempt timestamp are preserved. Only a subsequent real Snapshot may restore Observed.

Six focused test functions cover the actual queue-to-Desktop path and real egui status text, boundary ages, future/missing times, historical retention, diagnostic preservation and recovery. These are intentionally synthetic queue/layout regressions. They neither invoke original Hepta nor prove physical display presentation or device effects.

The executed RED/GREEN evidence review is recorded in [ui-freshness-independent-review.json](ui-freshness-independent-review.json). All 42 files / 352,723 bytes in the curated archive match their checksums; the original logs, helper/guard snapshots, Git objects and retained/current ELF identities were independently compared. GREEN-01's relative dep-info contains neither absolute worktree path; its lack of recompilation, RED assertion line numbers and retained test hash establish the cache/source failure. GREEN-03's final production command explicitly compiled the observer, Session, Shell and AppWindow. `trill-ctl` is present and hash-verified but has no separate Compiling line in that command. AppWindow reproduced the same bytes as R5. [ui-r5-retention-independent-review.json](ui-r5-retention-independent-review.json) directly rechecks all four retained R5 ELF bytes.

### External probe unused-patch lock ordering

The original manifest maps the same pinned tungstenite target from two registry origins. Both are unused in the external probe graph. The prior passing c0 probe lock and the failed f092 probe lock were byte-identical; the failure did not indicate changed dependency identities. Actual Cargo 1.95 metadata diagnostics moved a duplicate unused-patch entry between list positions, after which `--locked` rejected the rewrite. Official Cargo 1.95 source compares the ordered unused-patch vector and serializes it in that order.

The corrected external manifest omits only the second exact-equal, single-package alias. All other mappings remain intact. It rejects a mismatch or additional mapping, an active omitted origin/target, or anything other than one remaining unused pinned target. The original source, Cargo.lock and dependency pins remain immutable. Actual metadata followed by two consecutive locked metadata calls left the lock at SHA256 `72cb7346158f4c3514922cc7b9020f9b9d290aec78e047264a738d52afe6ed68`. The complete 733 package entries match the pre-fix external lock.

The actual lock-corrected consumer build then passed all six commands, including original-linked probe compilation and both Rust stale-contract tests. [original-consumer-build-independent-review.json](original-consumer-build-independent-review.json) records independent source, helper, log, lock and three-ELF checks. This build receipt explicitly does not claim that Agentd lifecycle or persistent Session runtime ran in the build step.

### First capture exposed a legitimate Starting transition

The first real old-UI capture held the original lifecycle at Starting while the original app-server monitor completed readiness. Original `mark_app_server_ready` changes the startup prerequisites and appends an event; the Health response permits `promotion_ready=true` during Starting while `ready=false`. Actual before and after snapshots preserved AgentId, spawn/current generation 1, PID 612929, lifecycle Starting, ready false and fenced false, while promotion readiness advanced false to true and cursor 2 advanced to 3 with `app_server_ready` appended.

The harness rejected this legal progress because it required whole-health equality. The real PNG independently shows the exact after-snapshot identity, timestamp, readiness and event values. No phase ACK was written, and the producer subsequently failed its existing ACK deadline and cleaned its private runtime. This is a preserved failed capture attempt containing one real reviewed frame, not a successful six-phase gate. [shell-01-starting-independent-review.json](shell-01-starting-independent-review.json) records the visible facts and boundary.

The reviewed correction design keeps identity, current generation, lifecycle, ready/fenced state, capabilities and source continuity strict; only Starting promotion readiness may advance false to true. Events must preserve their prefix and cursors must not regress. The after snapshot must satisfy both the held phase and the actual before snapshot, preventing a true-to-false regression hidden by an older held false value. Health and Events are separate original RPCs, so their flag/event edge must not be forced to appear atomically. Full stale last-observation equality remains mandatory. The corrected harness must execute again on a new frozen source.

## Staged local build helpers

Read-only review of `next-tools/r6-original-runtime/common.py`, `build_consumers.py` and `run_session.py` found consistent before/after source and five-ELF binding, isolated build/runtime environments, bounded command execution, exact six consumer acknowledgments and separation from the stock fresh-work gate.

The original link build's resource-guard failure and verified cache migration require an explicit continuation receipt. The successful initial eight-GiB admission, failed retry and migration manifest must remain traceable. A resumed task-local build must not be described as a newly passed fresh-work gate. The reviewed runtime helper now requires the actual attempt-03 resume receipt, initial admission, failed build-02 receipt, successful migration-03 receipt and preserved migration-01/02 failure records; the 700-MiB active disk reserve and 7-GiB nonreclaimable-memory guard remain unchanged.

Migration-03 completed successfully at 22:18:01 UTC. Its receipt SHA256 is `1f6854af7ec3f66e6a2426ae70e85d7813fe2cf3a658628b948045094a5ec735`. An independent elevated read verified the old access-path symlinks, destination inode/ownership agreement, actual target root mode `0755`, actual Cargo root mode `0700`, absence of old duplicate paths, compressed manifest hashes and preserved prior failure hashes. The original Cargo.lock still has SHA256 `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389`. Directory mtimes alone are excluded from equivalence; file contents, file mtimes, modes, types and symlink targets remain strict. See [migration-final-review.json](migration-final-review.json) for the precise independent-review scope. The reviewer did not rerun every cache-file hash or infer any original runtime success from relocation.

The resumed original build completed at 22:21:35 UTC with exit 0. The actual x86_64 ELF is 329,001,344 bytes with SHA256 `f476f9bb435c5127839c48ae7135d5a6fa7695ff5253460fdd8d19d7b084d4fa`. [native-original-build-independent-review.json](native-original-build-independent-review.json) verifies the archive, all 24 retained input files, all three compressed full manifests, the original source/lock and the actual ELF. The archive accurately identifies helper copies as post-execution snapshots.

## Evidence boundaries still in force

- The prior exact-c0 CI archive proves the two runs recorded in [archive/README.md](archive/README.md). Its ARM run did not execute persistent Session or Shell, and its A10 Hepta input was a scripted UDS fixture.
- The failed exact-f092 run is preserved independently in [archive-f092-ci/README.md](archive-f092-ci/README.md). New HEAD `84e08165d2e753fe1fc780e1972dbab4317e8499` has its own ARM run `39075838558`; its result must be inspected independently and cannot inherit c0 qualification.
- A completed build is not a runtime acceptance result. A passed producer receipt is not an actual Shell capture receipt.
- The first capture on old R5 ELFs and the second capture on freshness-fixed ELFs must retain their own source, binary hashes, logs and screenshots. Old ELF evidence must not be reassigned to GREEN source.
- One initial layout marker does not prove all six phase renders. Each actual PNG must independently show the expected status and available original identity/lifecycle fields before visual acceptance is recorded.
- No objective submission, model turn, device effect, mobile platform acceptance, physical desktop input or production release is established by these read-only phase gates.
