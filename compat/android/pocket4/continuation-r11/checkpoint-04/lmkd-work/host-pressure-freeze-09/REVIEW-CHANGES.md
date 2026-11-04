# Revision09: bounded stale ramp and actual critical-event qualification

Parent `host-pressure-freeze-08` is immutable, source manifest SHA-256 `ffe555f1913e2d3f540ec115298580ddb95849e797926511e13acb0eab126de6`. Its complete positive pass and pre-aging stale failure retain their actual source/build receipts. See `owned-relay/PRESSURE.md` for exact invocation/result pins and scope.

Only three code files change from revision08: `owned-relay/fixture_init.cpp`, `owned-relay/qualify_pressure.py`, and `owned-relay/test_qualify_pressure.py`. Rust broker/driver code, Android r6, real PSI registration values, freshness/effect gates, all memory/swap limits and every outer retirement gate are unchanged.

The actor records a completed allocation ACK and stops only the stale ramp at the first above-high scoped full-total candidate. It keeps the same eight-second deadline for the whole ramp, then the existing 2200 ms no-new-stall age and 1200 ms resumed zero-kill observation. Candidate details remain evidence of when allocation stopped; they cannot certify a real critical event.

The qualifier now requires a successfully queued actual original level-2 event while LMKD was stopped. It allows the worker's asynchronous observation after the last ACK only if the event was sent before resume and its original freshness window had strictly expired. Every audit event must be aged, the joined audit must be complete, all five targets must have the required final exit classification, and exact outer retirement/resource gates remain mandatory. Medium-only stale evidence is rejected/inconclusive. Positive medium-only evidence remains explicitly partial.

The three new synthetic controls cover medium-only plus full-total rejection, an actual-audit-shaped asynchronous critical event after the last ACK that is still expired at resume, and ten malformed ACK/current/budget/candidate variants. Total synthetic controls: 23. Local strict native compilation executes no actor. Device matching build and both new real phases remain separate gates; there is no installed change.

# Historical revision06 qualification fixes

Parent freeze05 is retained unchanged. Its source manifest is `cec434f1e868248f70dbc8a4eea7c924193e9ba633bba61dcf6cea90b642ab29`. The independent read-only review receipt is `acceptance-lmkd-pressure05-review-r1/report.json`, SHA-256 `0377f94fa0927a85e8958a3eef1d02c7e2766fd29c69895e65b72cb7d0540597`. That review did not execute a device, namespace or pressure trial. It also reproduced the second gap using an ordinary self-owned local child; this was an actor-cleanup control, not a claim about an actual Android LMKD kill.

## A consumed cancellation-tail event is now visible

Before the fix, a successful `poll` could return both cancellation and PSI POLLPRI. The worker honored cancellation before incrementing its observation counter. Thus an already consumed but unsent PSI event could be absent from both the count and the bounded record array, and the terminal audit could incorrectly appear complete.

`observe_poll_batch` now counts every monitor's returned POLLPRI immediately after successful poll/time checks, before deciding the control-first stop reason. Cancellation still takes priority and sends no pressure packet. A consumed unsent observation therefore makes `observations != packets_queued`, which the terminal audit records as incomplete. The batch helper's new Rust control covers simultaneous cancellation/two monitors, another lifecycle-control event/two monitors, and the ordinary two-monitor case. It is a host control, not real PSI qualification.

## A late nonvictim exit can no longer disappear during cleanup

Before the fix, the actor checked live targets, then sampled and stopped LMKD, then used a generic `if (alive_fd)` cleanup. A wrong delayed kill between the first check and LMKD's exit could leave a dead foreground/protected/allocator process that the cleanup silently skipped before writing success.

After exact LMKD reap, the actor now rechecks every expected surviving target. Each one receives its owned `Q` command and must be reaped with normal exit code zero. Only the positive phase's previously verified and already reaped cached SIGKILL victim can be skipped. `target-cleanup.json` binds all five labels/PIDs/UIDs/start times to their actual final exit classification, and the aggregate qualifier requires this complete set. A new Python negative control rejects a delayed foreground SIGKILL, a missing cleanup row, an early cleanup check, and a stale-phase cached death.

## Qualification limits remain unchanged

The Android r6 binary, original PSI trigger/window values, memory budgets, actual effect gates and lifetime rules are unchanged. New expected controls are 20 Rust tests, seven ordinary IPC controls, strict C++ actor compilation and 16 synthetic Python qualifier tests. Actual revision06 matching build, real pressure and stale-queue device runs remain separate requirements. A medium-only result remains partial. Fresh critical-event correlation does not by itself prove that the native kill decision used the critical branch; the separate native reason field preserves that distinction. Installed supervisor recovery, cgroup.kill, PID reuse and application production readiness remain open.
