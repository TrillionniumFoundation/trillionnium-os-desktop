# DeskClock stopwatch: verified and clean

The real two-run sequence verified an empty stopwatch starting, pausing at **9,170 ms**, remaining stable while paused, surviving normal task closure and a new launch, resuming to **17,817 ms**, and resetting through the observed Reset control. The final preferences contain **no `sw_*` keys**, with state, elapsed time and lap count all zero.

The first run remains recorded as a failed controller run: its reopen selector encountered both the selected tab container and its label, then its cleanup selector encountered a layout move while the observed snackbar disappeared. Neither gate is reported as an App crash. The second run continued only that exact retained paused stopwatch, with its prior result, APK, UID, epoch and original alarm contents pinned. It did not repeat any unknown input.

| Evidence | Actual result |
| --- | --- |
| Original run | `1a1aae28f48-fc05-4871`, failed/exit 1; tasks 911 and 912 normally removed; paused state retained |
| Continuation | `1a1aaf15b94-fc05-48ea`, succeeded/exit 0; complete and durable output |
| Continuation time | 2026-11-05 09:01:49.373581–09:02:22.839201 UTC |
| New continuation inputs | Resume, Pause, Reset — exactly 3 |
| Continuation task | 913, normally removed exactly once |
| Pending action | None |
| Original alarm templates | IDs 1 and 2 remain disabled; zero instances; full contents fingerprint unchanged |
| Timer objects | None before or after |
| App identity | UID 10063, version code 37, full APK SHA-256 unchanged |
| Notification permission | Still false; no permission, global ringtone or volume change |

The byte-preserved continuation result is `clock-stopwatch02-result.json`, SHA-256 `4993ba35ee6fc2aaa02b4fd196f04540f1ecbc16ccc637b0600ea8fad9937c15`. The unchanged original result is `clock-stopwatch01-result.json`, SHA-256 `9af4d7b19f8687563fc5fbe1bf526024d89e690a46d444d76af35884e52a95ed`. The full original template contents fingerprint is `655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea`.

This evidence qualifies the tested stopwatch workflow. **It does not qualify timer expiry, alarm delivery, audible output, reboot recovery or the whole Clock App.** UI ownership was handed to the DocumentsUI acceptance owner only after the successful Reset, normal task removal and terminal result.

SOURCE_MANIFEST identifies every selected publication file. CURRENT_STATUS records the combined stopwatch outcome. The earlier read-only alarm preparation remains in the working source directory. Private raw UI observations stay in the task-specific device journals.

## Publication boundary

The two public result files are selected projections of the byte-preserved private result receipts. Their `actual_result_sha256` fields bind those originals. Exact archived controller sources and local validation results are included. The continuation's actual native-tree regression input and the original raw result it pins remain private; the seven-case validation result records their hashes. No raw window tree, screenshot, old alarm content, full package dump or command journal is in this publication set. These task-specific sources are an audit record; they are not instructions to replay either completed run.
