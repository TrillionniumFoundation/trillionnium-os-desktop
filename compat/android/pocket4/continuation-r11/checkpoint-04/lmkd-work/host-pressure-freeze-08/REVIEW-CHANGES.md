# Revision06 closes two independently found qualification gaps

Parent freeze05 is retained unchanged. Its source manifest is `cec434f1e868248f70dbc8a4eea7c924193e9ba633bba61dcf6cea90b642ab29`. The independent read-only review receipt is `acceptance-lmkd-pressure05-review-r1/report.json`, SHA-256 `0377f94fa0927a85e8958a3eef1d02c7e2766fd29c69895e65b72cb7d0540597`. That review did not execute a device, namespace or pressure trial. It also reproduced the second gap using an ordinary self-owned local child; this was an actor-cleanup control, not a claim about an actual Android LMKD kill.

## A consumed cancellation-tail event is now visible

Before the fix, a successful `poll` could return both cancellation and PSI POLLPRI. The worker honored cancellation before incrementing its observation counter. Thus an already consumed but unsent PSI event could be absent from both the count and the bounded record array, and the terminal audit could incorrectly appear complete.

`observe_poll_batch` now counts every monitor's returned POLLPRI immediately after successful poll/time checks, before deciding the control-first stop reason. Cancellation still takes priority and sends no pressure packet. A consumed unsent observation therefore makes `observations != packets_queued`, which the terminal audit records as incomplete. The batch helper's new Rust control covers simultaneous cancellation/two monitors, another lifecycle-control event/two monitors, and the ordinary two-monitor case. It is a host control, not real PSI qualification.

## A late nonvictim exit can no longer disappear during cleanup

Before the fix, the actor checked live targets, then sampled and stopped LMKD, then used a generic `if (alive_fd)` cleanup. A wrong delayed kill between the first check and LMKD's exit could leave a dead foreground/protected/allocator process that the cleanup silently skipped before writing success.

After exact LMKD reap, the actor now rechecks every expected surviving target. Each one receives its owned `Q` command and must be reaped with normal exit code zero. Only the positive phase's previously verified and already reaped cached SIGKILL victim can be skipped. `target-cleanup.json` binds all five labels/PIDs/UIDs/start times to their actual final exit classification, and the aggregate qualifier requires this complete set. A new Python negative control rejects a delayed foreground SIGKILL, a missing cleanup row, an early cleanup check, and a stale-phase cached death.

## Qualification limits remain unchanged

The Android r6 binary, original PSI trigger/window values, memory budgets, actual effect gates and lifetime rules are unchanged. New expected controls are 20 Rust tests, seven ordinary IPC controls, strict C++ actor compilation and 16 synthetic Python qualifier tests. Actual revision06 matching build, real pressure and stale-queue device runs remain separate requirements. A medium-only result remains partial. Fresh critical-event correlation does not by itself prove that the native kill decision used the critical branch; the separate native reason field preserves that distinction. Installed supervisor recovery, cgroup.kill, PID reuse and application production readiness remain open.
