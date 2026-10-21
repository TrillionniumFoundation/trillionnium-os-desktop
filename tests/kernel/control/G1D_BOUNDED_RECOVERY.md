# G1-d bounded recovery after manager failure

The experimental native CPU owner now supports a finite recovery subset after
the ordinary manager image closes or its 300-second delegation expires. This
uses the existing five HOS2 v2 operations and the original delivery namespace;
it introduces no wire field, opcode, recovery ledger or new root syscall.
It is not a complete user-pause protocol or an automatic watchdog.

## Authority and resource owner

`CpuBandwidthState.trusted_management` now contains the same two canonical
`ManagementGrantState` values plus their recovery policy. The policy lives
under the existing IRQ-disabling CPU bandwidth lock. It records:

- The pre-delegation restore limit (50 ms per 100 ms), which is immutable.
- The most recent successful budget source: bootstrap, ordinary manager,
  recovery process, or an unclassified zero-cap pause.
- The first manager-image closing BOOTTIME cut, or an explicit unavailable
  clock state. Repeated image-close calls cannot renew this cut.
- Whether the single post-failure restoration has already taken effect.

The current budget, consumption, positive debt, revision and resource identity
remain in their original owners. The policy has no copy of their mutable state.
Budget source and one-use consumption change inside the same original
`NativeResourceState::apply` callback as the actual budget effect. Original D
reservation, immutable terminal receipts and retirement behavior remain intact.

Before the manager fails, both roles retain the existing ordinary 300-second
control behavior. After failure, the recovery process has only the restricted
transition below. Its canonical delegation has an outer expiry of 330 seconds
after bootstrap, but the owner checks a tighter window beginning at the first
failure cut. It never grants 330 seconds of unrestricted management.

| Condition | Required behavior |
| --- | --- |
| Manager image closes before ordinary expiry | Recovery window begins at the first reliable closing cut and ends 30 seconds later, exclusive |
| Manager reaches ordinary expiry | Window begins at the original 300-second endpoint, ends at 330 seconds, exclusive |
| Closing is observed after ordinary expiry | The original expiry remains the start; a late close cannot extend it |
| Clock is unavailable or precedes the last owner observation during close | Manager is revoked; recovery effects fail closed as indeterminate |
| Recovery itself is revoked or its window has ended | New recovery effects and usage observations are refused |
| The same D is retried after its effect or after the window | The original saved result is returned; the budget is not executed again |

The bootstrap page remains version 2, 192 bytes. Its existing 300-second lease
word describes the ordinary interval. The exact profile build manifest also
records `recovery_grace_ns=30000000000`; no change is made to the public five-op
HOS2 v2 encoding or its QueryAbi mask. Old clients that stop using their handle
after the ordinary interval remain conservative.

## The one permitted restoration

After manager failure, an InstallBudget request succeeds only when all of the
following hold under the same original CPU owner lock:

1. The recovery image's original capability, target, stable object and grant
   epoch remain valid, the owner is current and the clock/accounting is sound.
2. The current budget was last successfully set by the ordinary manager and
   is strictly greater than zero and lower than the pre-delegation restore cap.
3. The requested cap equals that exact restore cap, the request carries the
   current original revision, and no post-failure recovery effect has occurred.
4. The request reaches the owner before the exclusive recovery endpoint.

On success the original revision advances once, consumption and positive debt
remain intact, and the recovery transition is consumed. No later new D can use
this authority to lower a budget, pause work, select another cap or restore it
again. Same-D replay and delivery-history reads keep their original semantics.
The owner never creates a replacement resource or resets a fenced instance.

## User pause stays conservative

The existing InstallBudget payload supplies only a number. It cannot prove
whether `cap=0` came from a user pause or an unsuccessful management policy.
Consequently a zero cap is explicitly classified as **unclassified pause** and
post-failure recovery refuses to change it. Bootstrap budgets, recovery-authored
budgets and budgets already at the restore limit also do not establish a
recoverable manager throttle. There is no inferred auto-resume.

`SIGSTOP` remains owned by the actual Process job-control state. Restoring a CPU
quota neither sends `SIGCONT` nor changes that state. The guest exercises:
nonzero manager throttle → actual `SIGSTOP`/`waitpid(WUNTRACED)` → manager exec
and old-image revocation → one recovery budget restoration → at least two full
periods of unchanged CPU use and heartbeat → explicit `SIGCONT` → increasing
CPU use and heartbeat. A second post-failure budget request must fail.

The earlier live-manager zero-cap experiment remains an explicit request to a
still-live recovery role within the ordinary control interval. It is not the
new post-failure recovery path and does not establish user-intent handling.
Production recovery of zero caps requires a reviewed explicit pause/recovery
intent contract and an authorized producer, with backward-compatible ABI
admission. This subset does not claim that full requirement is complete.

## Evidence and test scope

The unchanged clean-source build gates, positive/altered-image boots and
[old-root workload negative control](G1D_WORKLOAD_ISOLATION.md) continue to run.
The positive guest additionally requires the exact stop, old-image revocation,
restoration, still-stopped measurements, second-effect refusal and explicit
continue observations in causal order. Counts, original revisions and actual
PIDs must agree with the raw apply/accounting records; a success label alone
cannot qualify them.

Four new original-owner ktests cover ordinary expiry, last valid and first
expired recovery cuts, one-use enforcement, immutable replay, zero/unknown
sources, original close-cut preservation, unavailable clock and accounting
faults. The existing revoke/history test now restores a nonzero manager cap and
checks preserved consumption and positive debt. Full core qualification keeps
all previous required names, adds these four, and requires at least 266 tests
and 28 specific names, with no skipped required test.
The separately filtered three-test SMP permission profile requires a compiled
denominator of at least 269, retaining its three extra feature-gated tests.

Ktest BOOTTIME cuts are fixtures against the real CPU owner and production
delivery backend. They do not prove a real guest waited through 300 seconds.
The ordinary guest's manager-exec scenario exercises a real calibrated clock,
live syscalls, independent process and scheduler. Only successful actual CI
results qualify either path; local C compilation and Python verdict tests are
reported separately.
