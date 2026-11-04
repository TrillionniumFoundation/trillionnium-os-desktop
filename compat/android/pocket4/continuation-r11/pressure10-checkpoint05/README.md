# Pocket4 LMKD pressure continuation: revisions 09 and 10

This checkpoint preserves the original failed revision09 stale run and adds the exact revision10 source, matching build, reviewed coordinators and two completed owned invocations. Main was not deployed or restarted by these canaries. No installed supervisor integration or all-app production qualification is claimed.

## Actual results

| Revision / unit | Actual result | Evidence scope |
| --- | --- | --- |
| 09 / p4-lmkd-relay-pressure-r11-03 | PASS | Original critical PSI correlated with the native cached-target kill; exact outer binding, cleanup and Main fence completed. |
| 09 / p4-lmkd-relay-stale-r11-02 | FAIL, preserved | Strict aging detected new pressure stalls before resume. The allocator still kept the domain above memory.high. Exact cleanup and Main fence completed; final joined pressure/outer audit was not produced. |
| 10 / p4-lmkd-relay-pressure-r11-04 | PASS | Same-revision actual critical positive, native critical kill decision, foreground/protected survival and complete retirement. |
| 10 / p4-lmkd-relay-stale-r11-03 | PASS within relief scope | Actual critical events queued while LMKD was stopped; only the owned allocator was unmapped, current fell below high minus the existing reserve, strict quiet aging completed, and resume caused zero kills. All five owned targets exited normally. |

The revision10 stale result can set only **stale_relief_critical_qualified=true**, with scope **relieved-domain-aged-critical-queue**. The original **stale_qualified**, **stale_critical_qualified**, **native_stale_drop_observed**, and **above_high_stale_zero_kill_verified** gates remain false. Low pressure after relief can independently suppress an effect; zero kills is not an independent witness that Android executed its stale-rejection branch. The current r6 native path does not export a sequence/time/drop-reason witness for that branch.

Revision09 failure is not relabeled. It is retained byte-for-byte under evidence/revision09/stale, together with its original coordinator error, terminal, phase sample and read-only archive audit. Sample max/OOM counters were zero, but the failed run did not produce the final joined outer counters; this checkpoint does not claim otherwise.

## Source and validation

The full 38-file pressure10 freeze is in source10. Its historical manifest remains unchanged, including its pre-build status text. Subsequent matching evidence is separate in matching/build-result.json. The real matching build passed 20 Rust tests, 7 ordinary IPC controls, strict native actor compilation and 28 Python qualifier controls. The 8 coordinator controls and exact revision09 preimages are in coordinator10.

The source change is limited to the owned stale fixture and its verifier. PSI thresholds remain some 70000 / full 700000 microseconds in the original 1000000-microsecond window. The whole allocation ramp retains its 8-second deadline. Unit memory.max remains 512 MiB, the measured domain memory.high remains 384 MiB, swap is zero, CPU is one core, TasksMax is 64, and the runtime bound is 60 seconds. Revision10 did not alter the Rust broker/driver or Android r6 LMKD binary.

The new fixture releases only the allocator after a complete acknowledgment and critical candidate; PSI totals are not sufficient for qualification. The verifier still requires a real queued level2 event, a complete joined audit, every observed and completed-send timestamp strictly older than its original window at resume, exact target identity, zero kills, complete classified target exits, and external unit/InvocationID/ExecMainPID/cgroup identity binding.

The actual source review receipt is reviews/root-pressure10-review.json. The source review diff and exact executed build/audit scripts are included. They retain their original create-only destinations and pins for audit; do not rerun them against an already retired cell or overwrite a historical result.

## Evidence and pins

| Record | SHA256 |
| --- | --- |
| Source10 manifest | bc996fe6c763b0270de97d85c0f7ace71fd3804ca432c49d79f05ec21edec9e5 |
| Matching build10 | 153c08dd7744149e0a1ff67f035d6a42cb218800521baca229f4950715076d46 |
| Root source/coordinator review | 76b30f2226e06be84c6ec33e47d93850010e567e9aff2004ab5d8f09b3a13ec8 |
| Revision09 positive original result | cf081ede4d6d757b522bd35b6280bda03a27e5517e0119e9dabb219cbd13e98a |
| Revision09 stale original failure | f028dd348031341f3ef8ed1f8f26b8e1ff87d8e560e919ddb5a807b07e9cc663 |
| Revision10 positive original result | 158ec28a6c0cd05c36314f30a14feec6a93d7a793e34790fe5b957d3b9f5c67e |
| Revision10 relief-stale original result | 8e1099ca1f0491ce4a59c04cef93bb460ee8ad8612d2d8084748899e6b089893 |
| Revision09 raw archive audit | 284323b77fde5ee349ae218dfee9b978c648b3b626a815861313dc6cf45eab49 |
| Revision10 raw archive audit | be19e8ea7db991bf8fe0201868b0351a239cf2322f254ad4c15a5c9722dad267 |

Each exported archive was downloaded in version-bound chunks and its complete SHA256 verified on the client. The audits rechecked archive membership, all member pins, original result bytes, required evidence rows, the exact pinned qualifier and external unit binding. They did not repeat a runtime invocation.

This publication contains UTF-8 text only. Original owned logdw.records files are binary protocol captures; their hashes remain in the immutable original manifests, and publication-omissions.json records their deliberate exclusion. APKs, ELF binaries, signing configuration, commercial application logs and broad UID tables are not included.

## Remaining production work

Installed supervisor/domain/init-peer lifecycle integration and daemon-loss recovery remain open. The owned route is PIDFD-only in a minimal Android root; production cgroup.kill, PID reuse qualification, independent native stale-drop observation, stale behavior while remaining above high, foreground behavior in real app sessions, and all-app production readiness remain unqualified. The existing cleanup01 candidate is source-bound and tested separately but has not been deployed by this work.
