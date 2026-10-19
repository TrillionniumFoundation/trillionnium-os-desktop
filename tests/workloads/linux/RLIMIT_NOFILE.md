# RLIMIT_NOFILE allocation enforcement

Owner: A04, assigned by A00 to repair the existing A05 file-table path. This
change depends on the SCM_RIGHTS/CLOEXEC fix. It does not change the HOS2 wire
protocol, the Hepta pin, or the fixed Debian 13 compatibility inputs.

## Problem and behavior

The previous kernel stored the process limit and returned it through
`getrlimit`/`prlimit64`, but `FileTable::insert` and `dup_ceil` could allocate
descriptors above that limit. Checking only the final insertion would also be
incorrect: an exhausted `open(O_TRUNC)` could already truncate a file, an
`accept` could consume a queued connection, and the second descriptor of a
pipe/socket pair could fail after publishing the first one.

The soft limit bounds the **new descriptor number**, not the number of open
descriptors. Lowering it preserves existing higher descriptors. A newly freed
hole below the limit remains allocatable even if the process has more open
descriptors than its new limit. Processes sharing a table through `CLONE_FILES`
can have different limits; each allocation uses the calling process's limit.

Allocation exhaustion returns `EMFILE`. `F_DUPFD` and `F_DUPFD_CLOEXEC` reject
a lower bound at or above the limit with `EINVAL`. `dup2`/`dup3` reject an
out-of-range target with `EBADF`; the valid `dup2(fd, fd)` no-op still succeeds
for an existing descriptor above a reduced limit.

References:

- [Linux getrlimit ABI](https://man7.org/linux/man-pages/man2/getrlimit.2.html)
- [Linux dup ABI](https://man7.org/linux/man-pages/man2/dup.2.html)
- [Linux F_DUPFD ABI](https://man7.org/linux/man-pages/man2/F_DUPFD.2const.html)
- [Linux v6.18 accept implementation](https://github.com/torvalds/linux/blob/v6.18/net/socket.c)
- [Linux v6.15 FD allocation and duplication](https://github.com/torvalds/linux/blob/v6.15/fs/file.c)
- [Linux v6.15 SCM_RIGHTS delivery](https://github.com/torvalds/linux/blob/v6.15/net/core/scm.c)

## File-table design and concurrency

The existing `FileTable` and `SlotVec` remain the sole descriptor owner.
An occupied slot is either a reserved number with FD flags or an installed
`FileTableEntry`. `FileTable::reserve_fd(ctx, flags)` reads the caller's limit
and selects the lowest available number in one table write critical section.
It clamps allocation to the existing `SYSCTL_NR_OPEN` ceiling. A dense table
retains the previous constant-time append path; a table with holes uses the
existing linear search policy.

`FileDescReservation` owns an `RwArc` to that exact table and releases its
unpublished slot in `Drop`. It holds no table lock or thread-local borrow
while the caller creates a file, blocks, or copies data to userspace.
`install` publishes the file and its final flags under one write lock after
fallible work has succeeded. There is no infallible public `insert` bypass.

Reserved numbers count as occupied for allocation but have no visible file:
lookup, `close`, `/proc` iteration and ordinary `close_range` ignore them.
`dup2`/`dup3` return `EBUSY` when their selected target is reserved, matching
Linux's allocation-versus-duplication race. They cannot overwrite another
operation's reservation. `close_range(CLOEXEC)` marks both installed and
reserved slots, and installation uses the latest reserved flags.

`fork_from` copies installed entries only. A parent's pending syscall retains
its original reservation; the child can allocate the resulting hole.
The existing exec path unshares the table before closing CLOEXEC entries, so
a reservation held by another thread cannot be published into the new exec
table. Normal close cleanup still occurs through `ClosedFile` outside the
table lock.

## Integration points

| Path | Allocation and error handling |
| --- | --- |
| `open` | Validate flags, reserve, then resolve/open/create/truncate; errors release the slot. |
| `socket`, `accept` | Both use the common allocator. `accept` reserves before consuming or waiting for a connection. |
| `pipe`, `socketpair` | Reserve both numbers; publish after the result array is copied. A second-slot failure or copy fault releases the exact reservations. |
| `dup`, `fcntl` | Duplicate under the table write lock with the calling process's limit and syscall-specific range errors. |
| `SCM_RIGHTS` | Reserve/copy/install each delivered FD; report the actual prefix and `MSG_CTRUNC` when the limit or a copy fault stops delivery. |
| Anonymous descriptors | epoll, eventfd, timerfd, inotify, memfd and new signalfd use the same allocator; updating an existing signalfd requires no new slot. |
| Process descriptors | pidfd_open, pidfd_getfd and clone PIDFD use the same allocator; clone copies its output before publication. |
| File-operation ioctls | PTY peer and namespace file creation use the current caller and the original table. |
| Mount API and boot | fsopen/fsmount use reservations; initial console descriptors use the same allocator with the boot-time limit. |

SCM_RIGHTS payload delivery still succeeds when no descriptor fits; its
ancillary length is zero and `MSG_CTRUNC` is set. If only a prefix fits, the
header describes that prefix. A fault while copying one FD releases that
unpublished slot; successfully copied earlier FDs remain installed, as on
Linux. A fault in the ancillary **header itself**, written after the prefix,
can still leave installed descriptors; this is an existing Linux corner case,
not an assertion of transactional rollback for the entire received message.

## Real Linux differential probe

`rlimit_nofile_probe.c` runs **37 fixed cases** in separate child processes.
The parent retains its own limits, checks real child termination and reaps
children. The probe uses disposable files and local Unix sockets, an overall
90-second alarm and a 12-second alarm per case. Guest execution needs its own
outer deadline and full boot/panic/raw-QEMU verdict.

The cases cover:

- Exhaustion, lowest-hole reuse, lowered and zero limits, dup/fcntl errors,
  and O_CREAT/O_TRUNC side effects.
- Pipe/socketpair second-FD and user-copy failures, socket creation,
  accept queue preservation and accept copyout cleanup.
- eventfd, timerfd, epoll, inotify, memfd, signalfd update/create, pidfd_open
  and PTY peer allocation.
- Six threads competing for exactly two free numbers, blocked-accept versus
  dup2/dup3, fork omitting a reservation, and close_range marking one CLOEXEC.
- `CLONE_FILES` processes with different soft limits sharing the same table.
- Stream/datagram/seqpacket SCM_RIGHTS delivery with zero free slots, one free
  slot, PEEK followed by receive, and a second descriptor crossing into a
  protected page. Each received prefix preserves descriptor identity and
  per-call CLOEXEC semantics.

Compile once and freeze the digest **before** the Linux execution. The
maintained runner copies those pinned bytes to a new evidence directory and
executes that private copy. Its `probe.sha256` and `input.json` are also written
before the child starts:

```sh
nofile_work=$(mktemp -d /tmp/a04-nofile-build.XXXXXX)
cc -O2 -std=c11 -Wall -Wextra -Werror -static -pthread \
  tests/workloads/linux/rlimit_nofile_probe.c -o "$nofile_work/probe.elf"
sha256sum "$nofile_work/probe.elf" > "$nofile_work/build.sha256"
nofile_digest=$(cut -d ' ' -f 1 "$nofile_work/build.sha256")
python3 -I -B tests/workloads/linux/run_rlimit_nofile_guest.py reference \
  --probe-elf "$nofile_work/probe.elf" \
  --expected-probe-sha256 "$nofile_digest" \
  --output "$nofile_work/linux-reference"
sha256sum --check "$nofile_work/build.sha256"
```

Retain compiler version, exact compile command and compile output alongside
these records. The runner requires the 37 fixed case names in source order,
every result `PASS line=0`, empty stderr, the exact final line
`NOFILE_COMPLETE total=37 passed=37 failed=0`, and the child's actual exit zero.
It checks both the private executed copy and the original build ELF after
execution. A failure, timeout, signal, incomplete case set, changed input or
process cleanup failure produces a failed receipt.

Run it as a standalone Linux process with the default, waitable SIGCHLD
disposition and sole ownership of reaping its children. It reuses
[`ChildGroup` and `terminate_group`](../../integration/hepta/run_original_agentd.py)
for its 100-second outer reference deadline. On every terminal state, including
successful exit or the C probe's own alarm, `waitid(WNOWAIT)` retains the owned
leader through bounded TERM/grace/KILL cleanup; only then is it reaped. The
fixed C probe does not create another session. Loss of that identity fails
without signaling a stale numeric process group. The receipt records this
helper's SHA256 and verifies the runner and helpers stayed unchanged.

The guest mode has **no alternate probe-ELF argument**. It reads the exact ELF
from the successful Linux reference, checks the pre-execution digest and raw
stdout/stderr/actual-exit records, and independently reevaluates all 37 cases.
Set `product_evidence` to an ordinary-kernel A06 product candidate directory and
`reviewed_head` / `reviewed_tree` to its independently reviewed Git identity:

```sh
python3 -I -B tests/workloads/linux/run_rlimit_nofile_guest.py guest \
  --linux-reference "$nofile_work/linux-reference" \
  --expected-probe-sha256 "$nofile_digest" \
  --product-evidence "$product_evidence" \
  --expected-source-head "$reviewed_head" \
  --expected-source-tree "$reviewed_tree" \
  --a01-initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --output "$nofile_work/guest"
```

The ordinary product receipt, all three equal source snapshots, source identity,
kernel ELF, original A01 initramfs and BIOS use the existing reviewed
[SCM_RIGHTS runner](run_scm_rights_cloexec_guest.py) checks. CPIO packaging keeps
every original entry and header field, except the injected init script's size,
and adds the fixed probe. The original `set -eu` remains; an `if` captures and
prints the real probe status even for a diagnostic RED. QEMU uses TCG, one CPU,
512 MiB, no disks or networking, and a 120-second maximum outer deadline.

Raw QEMU exit 33 is only the shutdown condition. A passing guest additionally
requires all 37 cases, the exact success summary, actual probe exit zero,
ordered complete/exit/original-boot markers, no kernel panic and unchanged
inputs. Unknown, skipped, duplicate, missing, malformed or reordered cases
cannot reduce the denominator. A signalled child remains an explicit failed
case with its signal recorded. Baseline RED receipts and raw serial bytes are
retained; they are never presented as a passing qualification.

The serial parser has a 64 MiB input ceiling; Linux reference logs retain their
8 MiB ceiling. The old kernel's per-syscall logging during three bounded
reservation-observer failures produced 14,761,415 bytes in the first full
baseline run. Its original 8 MiB parser rejected that log, so that attempt
remains an explicitly failed runner receipt. The complete raw stream still
contains 37 failed cases and actual probe exit 1. The runner now records QEMU's
actual process status before parsing, so even an oversized or unreadable serial
log cannot erase the known exit/timeout facts or qualify as a pass.

Runner regressions cover these negative verdict/input boundaries, original
CPIO preservation and this caller's real owned-child success/failure/signal/
timeout cleanup. They do not substitute for Linux or guest execution:

```sh
python3 -I -B -m unittest discover -s tests/workloads/linux \
  -p test_rlimit_nofile_guest.py -v
python3 -I -B -O -m unittest discover -s tests/workloads/linux \
  -p test_rlimit_nofile_guest.py -v
```

### Current evidence and remaining qualification

On original Linux 6.18.55 x86_64, GCC 13.3.0 produced the static ELF
`c3533e3b343ffb719e22d736aba4f9bc9c3040826547530f24e0556292b1ea3e`
from source
`7e86277f3e55da43328ad8da980d23709a84adf6c6543268a3a4699493b75317`.
It passed 37/37 with process exit zero and empty stderr, followed by ten more
complete runs of the same ELF to check the corrected reservation-race setup.

Earlier evidence is preserved: sandbox `bind` restrictions caused five
setup failures, and the first unrestricted 36-case probe exposed three
failures in its own assumption that accept must reserve a preselected lowest
FD. The corrected probe discovers the real reservation by `dup2` returning
`EBUSY`; it neither treats a sleep as synchronization nor changes the kernel's
expected behavior. The 36-case version then passed before adding the separate
CLONE_FILES case. Original source, ELF hashes and all outputs remain available
in the A04 validation handoff.

These are **host ABI observations**, not results from the new kernel. The
[frozen evidence archive](../../../results/compat/2026-10-19-rlimit-nofile/README.md)
also records the ordinary pre-fix kernel executing every fixed case: 0 PASS /
37 FAIL, real probe exit 1 and QEMU exit 33, without timeout or kernel panic.
At this handoff, fixed-nightly Rust formatting and whitespace checks passed;
kernel compilation and same-ELF **new** guest validation remain with A00. The
privileged fsopen/fsmount, namespace-ioctl and pidfd_getfd paths have source
coverage but are not runtime-qualified by this 37-case probe. Original full
OSTD/core and A04 Debian 13 profiles must also be retained during integration.

Linux's separate per-user accounting for descriptors **in flight in sendmsg**
(`ETOOMANYREFS`) remains an explicit existing TODO in `FileMessage::read_from`.
This allocation/receiver fix does not close that sender-side requirement or
claim complete RLIMIT compatibility, Hepta qualification, or device support.
