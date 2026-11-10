# Clock Timer04 on installed 433ff

The real trial succeeded on 2026-11-05 from 21:48:44.088668 to 21:50:38.976796 UTC. Eleven native inputs created one 15-minute timer, paused it, closed and reopened its owned task, resumed, paused, reset and deleted it. The paused value stayed exactly 891266 ms across normal close/reopen; the second pause was 881985 ms and reset was 900000 ms. Timer0 was the same object throughout. Tasks996 and997 were both normally removed. All three pending fields are empty and the final timer/stopwatch state is empty. The two original disabled alarms and protected sound/permission state were preserved.

A separate review of the already saved scheduler dumps proves the current pending sequence 0→1→0→1→0→0. Both active operations were foreground-service timer PendingIntents, with exact deadlines derived from this timer. Historical TIMER_EXPIRED lines are explicitly excluded. The original result and its conservative scheduler field are unchanged.

Only UI observation and lifecycle are proposed. The frozen clock.timer gate also requires completion on this APK; clock.persist mentions alarm/timezone behavior. Neither full gate is granted here. Sound, notification interaction, stress and whole-App release are also outside this evidence.

Full raw protected snapshots, sound/preferences, global alarm dumps and request payload are omitted. Their hashes and the exact selection source remain recorded; only Clock-owned selected records and safe controller/review sources are included.
