# Read-only Main fences for full engine build

This revision is a frozen source and offline control handoff. It remains bound to the already prepared candidate04 and is **not admitted to run**, because the newly reproduced SCM_PIDFD ownership defect requires candidate05 and a new build root/source manifest. No build request is generated for this paused candidate.

The outer process stays UID1000. Only the fixed, hashed snapshot source runs through sudo as root. That helper reads the pinned activation and epoch module, checks the actual daemon/launcher/presenter identities and framework epoch, and reads the service root `/sys/fs/cgroup/system.slice/droidloomd.service`; it does not use the Android init leaf as a substitute. It never invokes Android, starts services, changes Main limits, or writes Main files. Its alarm is a self-only watchdog.

The outer controller records before and after snapshots, activation/epoch/config/process/limit/cgroup identity equality, every memory.events delta, current memory/swap/PID deltas, and the raw pressure/CPU counters. Any OOM/oom_kill/oom_group_kill increase or invariant change fails the observed Main fence. Other pressure-counter increases remain explicit, even when the narrower OOM/invariant gate passes. No result asserts absence of unobserved transient effects or infers lack of influence from Main_actions=0.

Twenty-seven offline checks execute the real outer control flow with explicit Main-snapshot and inner-build seams. They cover activation/identity/limits/OOM changes, regressed counters, pressure reporting, before/inner/after failures, and a terminal-save ENOSPC after the post-fence attempt. No root snapshot, build, service or Android operation ran. The epoch guard remains the exact original framework_epoch.py source f43f766f…; installed engine bytes are deliberately not claimed as newly observed.

For candidate05, copy this wrapper into a new revision and bind its new source controller/preparation/root. Preserve this revision and its tests. The frozen candidate04 controller and its actual successful preparation remain unchanged.
