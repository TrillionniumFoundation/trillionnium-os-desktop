# DeskClock timer: verified core flow, clean final state

The real single-run job `1a1ab134b6b-fc05-49ff` succeeded with exit 0. From an empty timer and stopwatch baseline, the UI created one 15-minute timer, ID 0, paused with **891,439 ms** remaining, preserved that exact state through normal task closure and a new launch, resumed and paused at **882,695 ms**, reset to **900,000 ms**, and deleted the timer through the App. The final timer ID set, object fields, allocation fields and stopwatch values were all absent.

The run made **11 UI inputs**, normally removed its exact tasks **917 and 918**, and retained no pending effect. The actual interval was **2026-11-05 09:39:00.057437–09:40:48.024504 UTC**. UID 10063, version 37, full installed APK hash, notification permission and R16 epoch stayed unchanged. Original alarm IDs 1 and 2 remained disabled with no instances; their full content fingerprint was identical. No raw existing alarm label, time or ringtone is included here.

This qualifies the tested timer core workflow and pause persistence. **Timer expiry, background notification delivery, alarm delivery and audible output remain unqualified.** The timer was deliberately longer than the bounded test so it would not expire during this run.

The public result is a selected projection; `actual_result_sha256` identifies the unchanged 14,740-byte private original result. The source reader accepts empty timer membership and an allocation counter as metadata, preserving any such values rather than deleting them to fit a test. On this installed build, the real final Delete removed both.

The archived controller depends on the already-published stopwatch and held-session sources whose exact hashes are recorded in its `PINS`; it is not a new instruction to replay this completed task. Local tests cover the specific parser ownership and empty-metadata boundaries; they do not replace device evidence. UI ownership was explicitly returned to DocumentsUI after the real empty readback, two normal task removals and terminal success.
