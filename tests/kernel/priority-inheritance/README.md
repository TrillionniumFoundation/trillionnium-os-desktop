# Per-thread priority and scheduling inheritance

This probe is compiled on the host and executed only in an owned ordinary
Linux-ABI guest without host disks or network. Each outer scenario starts in a
fresh process. It compares actual scheduling attributes, `getpriority`, and
public `/proc` scheduling fields; a successful call alone is insufficient.

The before commit preserves P2 kernel bytes. Scenarios cover owner/capability
checks, zero/nonzero/infinite NICE limits, normal/RT/declared Idle static nice,
fork and real pthread/CLONE_THREAD inheritance, explicit non-leader TIDs,
`who=0` thread selection, thread-based group/user aggregation, and partial group
updates that retain EPERM/EACCES while applying permitted changes.

Run `python3 -I -B tests/kernel/priority-inheritance/run.py --smp 4 --output
/new/external/path` using OSDK compiled with `OSDK_LOCAL_DEV=1` from this exact
worktree. An exact-source ordinary product receipt can be reused with
`--product-evidence`. This is scheduling ABI evidence, not physical migration,
real-time latency, or production authority qualification.

References: [Linux v6.17 sys.c](https://github.com/torvalds/linux/blob/v6.17/kernel/sys.c)
and [getpriority/setpriority](https://man7.org/linux/man-pages/man2/setpriority.2.html).
