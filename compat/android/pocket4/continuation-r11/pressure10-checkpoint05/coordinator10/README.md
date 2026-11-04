# Revision10 owned coordinator

Source manifest bc996fe6c763b0270de97d85c0f7ace71fd3804ca432c49d79f05ec21edec9e5; matching build receipt 153c08dd7744149e0a1ff67f035d6a42cb218800521baca229f4950715076d46. All 38 inputs, 20 Rust tests, seven IPC controls, strict actor build and 28 Python controls are bound. Actor cc610f548fc567ceab31695aacb3c80f4397321051b3a45459835854526c2011; Rust driver/broker and Android r6 remain unchanged.

Profiles are exclusive fresh pressure04/coordinator06 and stale03/coordinator07. The once script preserves first-observed outer cgroup identity, successful InvocationID/ExecMainPID and monotonic lifetime binding, fixed 512MiB/high384MiB/swap0/oneCPU/64tasks/60s bounds, exact stop and Main epoch fences. It never retries a cell. Stale requires an externally pinned same-revision complete critical positive receipt; medium-only positive remains partial and cannot admit stale.

The new stale result can set only stale_relief_critical_qualified=true. Both stale_qualified and stale_critical_qualified remain false, as do native_stale_drop_observed and above_high_stale_zero_kill_verified. The exact scope is relieved-domain-aged-critical-queue. Actual queued original critical pressure, owned allocator release, strict quiet aging, zero kills, joined retirement, external unit binding and cleanup must all complete before this limited scope passes. This is not an independent native expiry execution witness.

Preparation, execution and export remain separate create-only actions. This source/control package does not prepare or run a namespace/unit. Parent scripts are frozen preimages for review. A final root review precedes any actual invocation.
