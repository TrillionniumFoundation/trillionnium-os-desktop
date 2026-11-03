# Signed signal arguments and original target identity

## Scope and original defect

The existing syscall dispatcher casts register arguments to the handler's Rust
types. `tkill` and `tgkill` accepted `u8`, so 256 became permission-only zero
before validation. `kill` and `pidfd_send_signal` accepted `u64` then cast to
`u8`; 266 became SIGUSR1. The Linux syscall parameter is `int`: all four now
accept `i32`, and checked `SigNum::try_from(i32)` validates the complete signed
value. Register high bits still follow the original Linux int ABI: `1 << 32`
becomes zero, not a new out-of-range u64 error.

The unchanged `6c26e3ae` ordinary ELF was tested with the twenty-case candidate:
its original fourteen cases passed, then `full int signal range` failed because
a call succeeded with errno zero. Probe exit 1 was rejected despite raw QEMU 33;
the failed source, binary and serial remain separate. This is a bounded self
send with SIGUSR1 blocked, not an exhaustion or kernel-panic scenario.

## Ownership and error ordering

The original permission, pending queue, standard coalescing, RT FIFO and
irreversible fatal receipt remain the owners. Existing boxed and owned helper
APIs remain wrappers. New deferred preparation runs after original target
lookup and TGID validation, before credentials or enqueue. A failed conversion
therefore publishes no signal and does not turn a missing target's ESRCH into
EINVAL. Target membership and selected Thread/Process strong references are
captured under the original PID table lock. The positive-PID kill lookup also
accepts a real nonleader TID, applying that selected thread's actual credentials
and delivering to the original shared process queue. The existing self fast
path is unchanged.

| Entry | Validation order within the qualified scope |
| --- | --- |
| kill | PID/group interpretation, original live target, full signal, actual permissions |
| tkill/tgkill | positive IDs, original TID/TGID pair, full signal, actual permissions |
| pidfd_send_signal | flags, actual fd/type, supplied siginfo copy and code, original live target, full signal, actual permissions |

A pidfd target holds its original Process Arc across user-memory access.
Dispatch compares it with the Process associated with the original membership
lookup; a numeric PID alone cannot authorize a replacement process. An already
expired weak target stays expired. Supplied siginfo is copied and checked even
for signal zero; a bad pointer still produces EFAULT before a reaped target's
ESRCH. Payload PID/UID are never permission evidence. Sender payload fields are
captured before group membership locks, so deferred preparation introduces no
new credential-lock nesting under the group/broadcast helpers.

The group and broadcast helpers return ESRCH when there is no eligible target;
they do not call the preparation closure or publish in that case. Existing
permission aggregation for groups is otherwise unchanged. This slice does not
qualify all Linux broadcast or group-lifetime semantics.

## Actual checks and remaining scope

The original unfiltered core inventory remains 353 with 114 required names;
OSTD 230, allocator 20 and MLSDisk 15 are unchanged. The standard ordinary
builder and strict [syscall runner](../../tests/workloads/linux/inline_signal/README.md)
retain 512 MiB, one CPU, original deadlines, actual reap and raw QEMU 33.
The original fourteen assertions remain and eight bounded cases make twenty-two.
Linux reference is separate from the exact native qualification below. No test
invokes kill(-1), unbounded allocation or global exhaustion.

The first twenty-case Linux reference failed only because its new observation
used libc sigtimedwait, which normalizes SI_TKILL to SI_USER. That failed source
and log remain retained. The corrected test uses the raw kernel syscall and
requires the original code, PID and UID. The final twenty-two-case reference
includes a real pthread nonleader and isolated single-child group.

The original pidfd implementation still supports process pidfds and main-thread
selection, not arbitrary thread pidfds or all /proc-directory pidfd forms.
A process-group pidfd target after its process identity has expired remains
outside this qualification. Compat ABI, RT queue quotas, unknown siginfo-layout
expansion, complete signalfd fields, all kernel heap/physical OOM paths and full
recovery remain open. This adds no reserve and no shadow signal owner.

## Primary implementation references

- [Linux v6.17 signal.c](https://github.com/torvalds/linux/blob/v6.17/kernel/signal.c):
  check_kill_permission, kill_something_info, do_send_specific and
  do_pidfd_send_signal establish the lookup/validation order.
- [glibc sigtimedwait](https://github.com/bminor/glibc/blob/master/sysdeps/unix/sysv/linux/sigtimedwait.c):
  libc's SI_TKILL normalization is separate from the raw kernel ABI.
- [Original helper changes](../../kernel/asterinas/kernel/core/src/process/kill.rs),
  [pidfd handler](../../kernel/asterinas/kernel/core/src/syscall/pidfd_send_signal.rs),
  [signal number](../../kernel/asterinas/kernel/core/src/process/signal/sig_num.rs).

## Exact combined native qualification

Frozen source `02521c15edbd8b2308248f28fcecf285b863a4c6`, tree
`7def41fc2e4f043cc260f75abf68f617d7e7a9f5`, passed the original unfiltered
core 353 / 114 required, OSTD 230, allocator 20 and MLSDisk 15 suites. All four
raw QEMU exits were 33; only OSTD retained its three original TCG VMX skips.
The same source's ordinary kernel passed 18 boot/QueryAbi checks, then the same
ELF passed SGID 30, Unix ownership 12, proc Groups/NoNewPrivs 12, memfd 4 and
all 22 ordered signal cases. The full source snapshots stayed unchanged.

[The source-bound receipt](../../results/integration/2026-10-23-audit-closure/signal-bounds-0252.json)
records all source, kernel, serial and probe identities, including the rejected
6c26 baseline and corrected Linux observer. Existing memory sizes, deadlines,
negative controls and original cases were retained. The open limits above are
not superseded by these results.
