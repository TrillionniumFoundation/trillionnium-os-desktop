# Clock expiry05: current-binary evidence delta

The original worker finished with exit 1 at 2026-11-05 16:18:17 UTC. Its inner timer flow passed; the outer result retained an unproved audio-power flag. Both original outcomes remain intact.

On the installed e4ff4b46 APK, the sole 60-second timer survived normal task removal and process death. AlarmManager cold-started TimerService, the exact timer became EXPIRED, and its standard title and body reached the fixed host Notify consumer. Stop reset that same timer and Delete removed it. Tasks 958 and 959 closed normally; pending effects were empty, protected state was preserved, and the owned monitor was joined with both pipes at EOF.

## Saved audio reconciliation

The executed observer only parsed completed 1000 ms power rows ending in `] sum(...)`. The pinned raw dumps contain an ongoing burst with open 1000 ms and multiline 50 ms records after this timer's due time. A separate offline review admits those actual timestamped rows, excludes old UI-click history and graph coordinates, and rechecks the sole active Clock UID/track plus increasing output frames/writes. Four negative controls pass.

This establishes nonzero HAL signal-power telemetry contemporaneous with the sole active Clock track in three snapshots. It does not establish physical speaker audibility, a matched host Pulse stream, desktop popup display, or whole-app readiness. No PCM was recorded and no sound setting changed. The original `HAL=false` and exit 1 were not rewritten as success.

## Reproducibility and scope

`metadata/combined05-result-original.json` is byte-for-byte original. The 63,508-byte inner result, three full AudioFlinger dumps, and full NMS/DBus payloads stay private; their hashes and selected Clock-only fields are included. `review_saved_audio05.py` reruns against those pinned private inputs in their original delivery05 directory. The execution sources are frozen copies. delivery04 was never staged or executed. The earlier dfec1b20 bundle remains unchanged.

The new resource profile validates the actual 6144 PID limit with the existing guard logic. This flow made no Main resource/configuration writes. Existing core03 evidence is bound to this same APK; it was not replayed here.
