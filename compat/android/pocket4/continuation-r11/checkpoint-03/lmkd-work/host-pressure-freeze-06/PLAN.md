# Owned real-PSI continuation: revision06

This revision starts from immutable `host-pressure-freeze-05`, whose manifest is retained as `parent-source-manifest.json`. The earlier bootstrap04 manifest remains in `ancestor-bootstrap04-manifest.json`. This source freeze is not a matching build or pressure result. The Android executable remains the already compiled r6 candidate. No device action is performed by preparing this source.

## Scope and immutable limits

The next owned phase must use a new root, state directory, unit, invocation, actor/init identities, nonce, authority and lease. The already retired bootstrap/protocol trees are never reused. Main stays on R16; Main epoch and unrelated sessions remain under the coordinator's fence.

The outer unit remains bounded to 512 MiB, one CPU, no swap and 64 tasks. Its new child workload domain is configured **before init/bootstrap** with `memory.max=512 MiB`, `memory.high=384 MiB`, and `memory.swap.max=0`. No memory budget is changed after authority construction. Native PSI remains `some 70000 1000000` and `full 700000 1000000` in the minimal root; there is no property or trigger override.

The actual successful pressure-registration write must produce a retained receipt containing its raw trigger bytes, return count, pressure-file inode, cgroup scope, and monotonic before/after times. This comes from the real `register_exact` path, not the Android request alone. Each successfully queued actual POLLPRI event retains bounded level/sequence/observed/send-completed times. A fixed-capacity audit reports overflow explicitly; overflow, missing registration, clock failure or incomplete event data cannot qualify the canary.

Audit data travels over the already authenticated inherited lifecycle channel in a separate fixed-size terminal record. It is emitted only after the actual admission/PSI worker join, before the final RETIRED status. The caller binds it to the original nonce, authority generation, lease generation, cgroup and budget, and still requires exact broker reap. Audit is observation, not authority; it does not change native admission, pressure qualification or effect gates.

## First positive pressure phase

Keep the actual protocol checks and real native r6 endpoint. The self-owned cached target is 64 MiB at oom_adj 900, foreground is 128 MiB at 0, protected is 16 MiB at -1000, plus a small sentinel and an unregistered bounded allocator. The foreground target is deliberately larger than the cached victim, so priority selection is observable.

First establish a quiet plateau below the immutable high limit: stationary private PSI totals, no high/max/OOM changes, zero kill count and live exact target pidfds. A live lease and occupancy alone must not produce a kill.

Then one bounded allocation progression crosses high. It stops at the first observed cached exit, workload deadline, or admission bound. The allocator never exceeds 216 MiB. First-kill current is capped at 432 MiB including a conservative 16 MiB per-step charge reserve around each 4 MiB request; the intended plateau is approximately 412–416 MiB, and reaching the reserve stops further allocation. The 472 MiB check is only an emergency rejection boundary, never the target. Any `memory.events` max/oom/oom_kill/oom_group_kill increase rejects the result. After cached release, current must return below 384 MiB with headroom; allocation requests do not continue after the first observed victim. If the original 700 ms critical trigger is not observed before that exit, record medium-only partial evidence or an incomplete trial without lowering a threshold or rerunning the same cell.

Success needs actual kernel POLLPRI/queued receipts, unchanged exact trigger registration, increasing scoped PSI/high counters, one exact cached pidfd SIGKILL plus matching LMK_PROCKILL identity, kill count exactly one, surviving foreground/protected/sentinel/allocator/LMKD identities, and no kernel OOM. Record the cached exit-observation monotonic upper bound for correlation with the real event window. Preserve PIDFD-only/minimal-root and unqualified cgroup.kill/PID-reuse labels.

## Separate stale-event phase

Use another fresh owned cell. Stop only the exact self-owned LMKD through its retained pidfd after actual enrollment. Generate a bounded real pressure workload, then stop allocating and allow all queued observations to age beyond the unchanged 1000 ms window before continuing that exact LMKD. Hold the budget unchanged and retain the targets. No forged packets or substitute test server are used.

The terminal audit must prove at least one real queued event, every queued observation before the measured resume boundary by more than its window, and no fresh event in the zero-kill observation interval. If later PSI activity makes the interval ambiguous, the phase is inconclusive. The real LMKD must remain responsive, all targets must remain alive, and kill count must stay zero. Only after that above-high observation completes, the actor asks its own allocator to unmap its pages, retains every target alive, and checks below-high cleanup headroom before retirement I/O. It records the release time/bytes and keeps the budget unchanged. Host and native monotonic namespace identity checks remain enabled. This temporal negative is separate from already measured HUP retirement and never bypasses one-shot enrollment.

## Completion and cleanup

Both phases keep real broker retirement, same-cell admission refusal, exact broker/actor/init exit, unpopulated domain, exact unit cleanup and Main epoch checks. A phase's native workload result alone cannot claim the complete pressure pass; the trusted caller must also validate its terminal host audit. No retry is automatic. Production cgroup.kill and installed supervisor recovery remain separate gates.

## Current implementation state

The bounded actual-write/event audit, terminal codec, pressure/stale actor, real driver wiring and externally pinned read-only qualifier are implemented in this isolated copy. Local strict actor compilation and 16 synthetic qualifier tests are recorded separately. The new Rust source still needs its actual matching device build (20 expected Rust controls plus seven ordinary IPC controls). No revision06 namespace, pressure or Android execution has occurred as part of preparation. The original Android r6 executable is unchanged; no Android rebuild is required for this host/actor continuation.
