# Pocket4 Android — checkpoint 24

Cut: **2026-11-07 00:12:51 UTC**. Parent: `32df6ea6403c24588638e3fbbfe6edc1897393e9`.

**Whole-App production acceptance remains 0/45. Main has not been deployed or restarted.** This checkpoint contains completed source repairs, host tests, an owned helper installation, an independent fixture retirement, and bounded read-only deployment observations. It preserves every failed or unknown attempt and the resource limits that still block normal builds.

## Results at the cut

| Workstream | Verified result | Remaining boundary |
| --- | --- | --- |
| United helper | 85 controls and 13 install/state commands passed; helper UID10163, four target APKs unchanged, staging removed and owned resources closed | United business/UI and whole-App acceptance remain pending |
| 12306 helper install02 | Failed during the read-only helper-absence post-command guard, before installation | The transport marks that command outcome unknown; the full worker separately reports no install/state attempt and no retained helper. The consumed pair is retired |
| Original NDK fixture | APK05 installed as UID10162; run01 failed with command005 return153; independent retire01 completed eight commands, restored task state and closed the owned FDs/locks | Return153 cause and the original twelve Android tests remain unqualified |
| NDK output capture | Replaced the inherited file-size limit with two bounded pipes; five real owned-child tests and two pure first-error tests passed | Host tests do not authorize a new Android run or explain the old153 |
| Status/Readiness | Release build passed 38 commands, 15 Rust/CLI tests and three real child-lifecycle controls | Four release tools are available; they are not deployed |
| Deployment facts | Nine existing files read completely, actual system/user service scopes and commands observed, five drop-ins examined privately, four binary permissions/ACL/xattrs checked | Existing presenter is a separate binary and must not be replaced with the release supervisor |
| Native normal/Composer | Latest public memory read completed with all observation FDs closed | MemAvailable13,807,906,816 B is below the unchanged16,106,127,360 B gate; neither build was admitted |
| Hyatt | Fifteen parser controls and bounded ELF/APK diagnostic passed with all105 owned FDs closed | Static JNI bytes do not establish the historical minus500 cause or business acceptance |

## Failed, unknown and scoped results

The original NDK run remains **FAILED / outcome unknown**. Its independent retirement is a separate successful operation: it stops only the owned fixture UID, observes two complete empty UID tables, restores the previously observed task set, and leaves the installed fixture package available for a separately admitted future operation. It does not turn the failed instrumentation into a passing test.

Command005 returned153 with empty stdout/stderr. The held namespace helper can map either a direct child exit or a signal into that number, so no signal or particular failing write is attributed. The removed source-level RLIMIT_FSIZE restriction was a concrete inherited-limit risk; the host regression demonstrates that the replacement permits an owned file larger than the log cap while retaining each stream's first262144 bytes and observing at most262145 bytes. Failure cleanup keeps the first cause, signals the owned unreaped group before reaping, and closes its own FDs. Escaped sessions and Binder-created processes remain outside that claim.

The 12306 report is deliberately represented at both layers. Its read-only transport encountered a failed post-command Main guard and marks its outcome unknown. The full worker confirms `install_attempted=false`, `state_attempted=false`, no retained helper and aggregate `outcome_unknown=false`. Worker/coordinator checks recorded `OWNER_SINGLE_DIRECT_CHILD_REQUIRED`; a later successful stage-final guard does not erase that intermediate failure. The subsequent three-parent read-only diagnostic was complete and stable at its own observation times, but did not identify the past transient child and does not grant new runtime authority.

Shared UI holds remain. IHG's original London outcome and the ownership history of other task IDs are not reclassified. Hilton install02 remains unrun with its unused pair. No failed or unknown action is automatically replayed.

## Deployment scope established by actual observations

The active daemon is a system service. The active presenter and application catalog are user services. The observed presenter is the existing B02 binary (7026568 B, SHA256 `47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24`), reached through an existing override; it is not one of the four newly built release binaries. Installed-file content, mode, owner, group, empty ACL and empty xattr observations have been retained for concrete backup/rollback preparation.

The package marker says version0.1.0/release20/x86_64. Exact dpkg queries found no owner for seven paths. Neither fact proves an installed source revision or an unmanaged installation. The private systemctl outputs, actual private paths, drop-in bodies and private original command005 evidence are not exported here. Public projections are labeled derived and retain original byte/hash pins.

No deployment transaction, service stop/start or new Main baseline is claimed by this checkpoint. Any later change must preserve the actual presenter and configuration, use a concrete backup/rollback plan and qualify a new Main generation rather than rewriting B02.

## Evidence and reconstruction

- [status.json](status.json) records scoped outcomes and explicit pending gates.
- [acceptance-matrix.json](acceptance-matrix.json) preserves all45 rows with production readiness false and links the original CP23 matrix.
- [cut_scope.json](cut_scope.json) fixes canonical original roots and exact subtree cuts.
- [payload-index.json](payload-index.json) lists the retained file bytes, SHA256 and Git blob identities.
- [assembly/fixed-seed.original.json](assembly/fixed-seed.original.json) and [assembly/root-authority.original.json](assembly/root-authority.original.json) fix157 new roots and934 inherited canonical roots.

The collector fully verifies each original UTF-8 body before normalization. Each normalized package adds two schema3 reconstruction metadata files; original retained leaf bodies are byte-identical. Real Git subtrees may be cut only at an explicit canonical root. The33 encountered `archive-references.json` documents remain opaque original files and authorize no traversal.

The cut is immutable. Work observed or prepared after it belongs to the next checkpoint and must not be backfilled as a result at this cut. Original manifest fields and the historical file-array text are preserved when the new checkpoint is appended.

## Work still required

Complete the remaining source and runtime gates for a fresh NDK run and its independent retirement; prepare and validate the complete Main update and rollback; resolve the current runtime/UI admission holds with fresh evidence; meet the unchanged memory gate for normal/Composer builds; and complete functional, process/FD/resource and recovery acceptance for every App. Host or helper success alone does not satisfy whole-App production readiness.
