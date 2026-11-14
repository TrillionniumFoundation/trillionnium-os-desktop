# Targeted Settings and production-foundation review

This capsule freezes the first independent source review. It records two Settings findings, the exact first source pins, primary-source semantics and their version boundary, and the unchanged seccomp/readiness file identities. It does not contain a new test result, an Android execution, a deployment or an application approval. `REVIEW.json` remains pending until a separately pinned successor is reviewed.

## Settings: creation authority must precede automatic cleanup

The first Settings launcher accepted a successful command containing a reuse warning, one successful status and one Activity identity. A Settings task created by another Android actor after the before-snapshots could therefore be registered, claimed from the ID difference, and later removed. The shared host flock does not serialize Android touch input or noncooperating Android callers.

The relevant first-source functions are `launch_settings_observation_with_paths`, `start_settings_activity_once`, `checked_activity_output`, `Tasks::claim` and `cleanup_task`. Their exact source files are pinned by `sources/settings-first-source-integrity.json`; the original ordinary-control receipt is preserved without alteration beside it.

Rejecting reuse warnings is necessary but does not establish new-task ownership. The official `ActivityStarter` also permits adding an Activity to an existing task with a success return. A fixed `NEW_TASK` flag, or adding `MULTIPLE_TASK` without proving the actual activity semantics and causal association, is insufficient. Generic success, JSON, a task ID absent from an earlier snapshot, or a native registration ACK must not become cleanup authority.

The reported successor plan is to reject both public Settings entry points before any start while selected-framework new-task authority is unavailable, and to keep the snapshot/cleanup prototype under `cfg(test)`. This plan was not yet reviewed at this capsule's freeze. Such a gate can remove the unsafe path; the actual Settings observation capability and runtime acceptance would remain blocked.

## Settings: durable pending must reach every cooperating entry

The first `ActionScope` correctly retained its flock and pending intent on unknown outcomes. A new Settings request also rejected the marker after a daemon restart. However, other daemon mutations such as `OpenBrowser` and `Launch` did not check it. The separately audited external helper acquired the same flock and dispatched without checking the marker.

A daemon exit releases its flock. If Android instrumentation remains unsettled, a consumer that only acquires that flock can then overlap the unresolved Android work. Stopping the rest of one 42-application batch does not block another client or external consumer.

A successor must reject pending state at all applicable daemon mutation admissions and define the same marker check for cooperating external consumers. The external helper already holds the flock when invoking the daemon; taking another independent flock in that daemon path would introduce a lock-reentry conflict. No installed helper was changed by this review. The reviewed helper copy and entry excerpt are pinned in `sources/external-helper-first-source-pin.json`.

## Controls examined without a new defect

Unknown start/ACK and unsettled helper paths retain scope without issuing cleanup. Instrumentation timeout or missing restoration proof is not converted into completion by retiring the host invocation cgroup. The pending file and its directory are synced before start; unresolved destruction retains the open-file-description lock.

The business phase uses the same absolute lease minus a 25-second reserve. Per-command deadlines are bounded by that lease and a 20-second cap. Cleanup uses the original deadline and at most eight seconds for final readbacks. Host invocation retirement can use up to two additional seconds, but expired output still fails the success check. Removal is sent once, with no uncertain retry. These are static findings about the reviewed source, not new executed controls.

## Official source version boundary

The primary references are Google's `platform/frameworks/base` sources at commit `1cdfff555f4a21f71ccc978290e2e212e2f8b168`, whose author and committer date is 2025-03-26. The initially read `refs/heads/main` resolved to that commit. This is not the selected 2026 QPR1 release.

- [ActivityManagerShellCommand.java](https://android.googlesource.com/platform/frameworks/base/+/1cdfff555f4a21f71ccc978290e2e212e2f8b168/services/core/java/com/android/server/am/ActivityManagerShellCommand.java): shell start status and reuse-warning behavior.
- [ActivityStarter.java](https://android.googlesource.com/platform/frameworks/base/+/1cdfff555f4a21f71ccc978290e2e212e2f8b168/services/core/java/com/android/server/wm/ActivityStarter.java): task reuse and successful Activity addition into an existing task.

Both fixed-commit files were independently fetched read-only over HTTPS from the official Gitiles endpoint. Full byte lengths, SHA-256 values and Git blob IDs match the previously observed official source pages. Exact receipts and the fixed-commit URLs are included. The first reader used an incorrect Git object separator; its Git hash fields were not accepted. The corrected reader used one NUL byte, verified both original blob IDs, and observed identical full-file SHA-256 values. Both observations and the correction are retained.

These sources provide concrete semantic counterexamples to treating ordinary start success as task-creation authority. No exact selected QPR1 framework source or DEX comparison, newest-release claim, Android execution or compatibility qualification is implied.

## seccomp and readiness generation check

The review covered the two full modules at desktop publication commit `caed30a83c3af70bf7a769968e6365b46d99d26c`, the related module wiring, source origins, README and qualification boundaries. It also read the corresponding complete files from both `normal-production-writable-proc-r1` and `normal-production-binder-review-r1` on Pocket4.

| File | Bytes | SHA-256 in all three generations |
|---|---:|---|
| `production_runtime_seccomp.rs` | 9969 | `7acc608ea9dfc538ac7e1309ac0fddaf3aee60255fcc7ec8e05a43795d9126ee` |
| `production_readiness.rs` | 11704 | `5b7e4974229d74e1531bdba37282501e4859a26ba6faefe1bf5deb2092bf795b` |

No new demonstrated reachable host-global or cross-generation readiness acceptance was found beyond the r33 publication's pending integration and mount/proc/MAC gates. This does not prove that the filter is installed for Android or that a production execution witness binds the property file. A property `Complete` value alone is not Running authority. The 117-test foundation result must not be transferred to later source generations.

## Reading this capsule

`INDEX.json` lists every member with byte length and SHA-256, excluding itself. No producer source, selected image, shared source tree, lock, canonical CURRENT, installed consumer or Android cell was modified. First-source reconstruction and byte hashing are integrity checks only. The first owner's reported 78 ordinary controls were not rerun or upgraded into runtime credit.

The next review must bind the exact final diff and source hashes, check both causal gates and all pending-admission consumers, and list any remaining limitation separately from ordinary test success. Findings and qualification fields in this frozen capsule do not automatically change when a later patch is published.
