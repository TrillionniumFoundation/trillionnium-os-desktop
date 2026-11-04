# Next owned real-event fixture contract

**Prepared design only. A granted short quiet window was explicitly returned because the event allocator/witness/health source was not yet frozen. No event-pressure run has started. Coordinate a fresh window after publishing the exact source/binary/manifest and one idempotency key.**

This stage qualifies actual target PSI notification delivery only. It creates no Android/private cell, changes no Main service, and makes no LMKD victim decision. It cannot replace the unresolved r7 foreground-loss or Android pressure gates.

## Fixed resource and lifetime bounds

Keep the proven job hierarchy and its total `cpu.max=100000 100000` / `memory.max=536870912`. The target remains 64 MiB maximum with swap disabled. Set its high boundary to 24 MiB while it is quiet, then create/freeze the authority and registration; the budget may not change afterward. Admission requires the target including its small witnesses to remain at or below 8 MiB.

One owned allocator has `oom_score_adj=900`, a 32-MiB allocation ceiling, and touches a fixed allocation in small page-faulting chunks. It runs in the same target as the authenticated peer and witnesses. An owned foreground witness has adj 0 and a protected witness adj -1000, each at most 1 MiB. Their exact pidfds, births, expected UID, cgroup membership and score values are pinned before allocation starts. These are host fixture roles, not Android foreground claims.

Use one critical/full trigger with the already controlled exact string `full 70000 1000000`. The pressure phase is at most three seconds; the allocator's entire lifetime is at most six seconds. A first strictly validated genuine event ends allocation cooperatively, followed by normal release and exit. A forced cancellation or timeout is a failed trial, not a successful cached kill. Do not extend the phase or lower the threshold to obtain an event.

## Admission and continuous guards

Copy the existing r9/r10 guard semantics unchanged. In particular, Main's 80% memory comparison uses **memory.max**, not memory.high, and comparisons stay integer arithmetic:

- Host MemAvailable at least 8 GiB and SwapFree at least 2 GiB.
- Main `memory.current * 100 < memory.max * 80` and `pids.current * 100 < pids.max * 80`.
- Host and Main memory `full.avg10 < 10`.
- Main high/max/OOM/kill counters and pids events exactly equal their fresh baseline throughout.
- The current formally activated Main epoch, launcher/init, zygote64, system_server and SurfaceFlinger identities remain unchanged. Use the signed/frozen activation identity and a fresh read; never silently accept a replacement generation or reuse the old Main pins.
- Parent budgets, controller/generation identities, and bound process membership remain exact. No target max/OOM/kill counter may increase, and target current reaching 48 MiB aborts.

Persist each health frame and fsync it **before** applying thresholds. Sample at least every 100 ms during the pressure phase. An admission failure produces a saved exact frame and stops before allocation. A runtime failure stops the owned allocator, records the triggering scope/value/comparison, and preserves cleanup evidence. Do not infer that global pressure came from an external source merely because a global guard fired.

## Event and cleanup acceptance

Accept only the real registered target's critical event with exact generation, cgroup identity, budget, configuration and consecutive sequence. Observation time must be nonfuture and younger than the unchanged window at receipt and after current statistics are read. Kernel event observation time is not an exported original trigger timestamp.

Correlate the notification with current target-over-high state, increased target high events and target PSI total counters. The host worker remains the sole poller of the actual pressure descriptor. No injected packet or mock counter may satisfy this gate. Initial host-side event receipt does not claim Android SCM_RIGHTS/grant-client integration.

All foreground/protected witnesses and the authenticated peer must retain their pinned generations and scores through event observation. Require zero OOM/kill, cooperative allocator release/exit, retired notification aliases, actual worker completion, zero PSI descriptors, normal child reaping, exact original job-member restoration and empty removed owned hierarchy. Preserve every failed attempt and all earlier r7/r8 results.
