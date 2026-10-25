# Process dumpability and sensitive proc access

This slice replaces the successful `PR_SET_DUMPABLE` stub with an actual memory-image
policy. Core-dump file generation is separate. Exact native qualification is recorded below; it belongs to that source and ELF.

## State and ownership

[ProcessVm](../../kernel/asterinas/kernel/core/src/process/process_vm/mod.rs) owns a
sleeping `Mutex<bool>`. `true` means Linux `SUID_DUMP_USER`; `false` is the fixed
non-dumpable reset policy, equivalent to `suid_dumpable=0`. No configurable sysctl
or root-only core-file policy (`2`) is implemented. PR_SET accepts only 0 and 1;
PR_GET returns the retained state. There is no mirror process boolean.

Threads and distinct CLONE_VM processes use the original shared Vmar/ProcessVm,
so both use the same policy mutex. Fork snapshots that policy into its independent
new VM. It takes the snapshot before the original heap lock, preserving the
policy -> heap order used by sensitive metadata capture. A fresh ordinary image
starts dumpable. Failed executable/argument preparation preserves the old image.
Successful exec starts a new policy and never carries forward a user SET0 blindly.

The actual prepared exec credentials and read access to the executable, each
shebang interpreter, and the ELF dynamic interpreter can disable the new image.
A changed effective/filesystem ID or an increase in permitted capabilities also
disables it. No-new-privileges and NOSUID retain their existing credential logic.
The executable identity/permission races and general exec/capability compatibility
outside the existing loader are not redefined by this slice.

## Publication and access locks

All original live credential mutation call sites now use a scoped
`with_credentials_mut` closure. The original credential Arc is edited; no new
credential ledger or replacement authority is introduced. The borrowed
`Credentials<ReadWriteOp>` has no Dup right, no DerefMut, and cannot escape the
closure. Existing user copies precede the transaction.

The lock order is:

1. The original target Process VMAR mutex, which fences image replacement.
2. The shared ProcessVm policy mutex, also shared across different CLONE_VM processes.
3. Original target namespace, file-table, or VM metadata locks needed by that operation.

[CredentialsEdit](../../kernel/asterinas/kernel/core/src/process/posix_thread/credentials_edit.rs)
records the original effective UID/GID, filesystem UID/GID, and permitted set.
Before releasing the shared mutex it clears dumpability if any of those IDs
changed or the new permitted set is not a subset of the old set. Lowering
permitted capabilities alone does not clear it. Failed, no-op and query calls
preserve state. This locking transaction differs from Linux's immutable credential
publication/barrier mechanism: sensitive reads are forbidden from observing the
intermediate credential writes because they hold the same image mutex. Exec
uses its already-held original VMAR guard and does not recursively acquire it.

[AlienAccessGuard](../../kernel/asterinas/kernel/core/src/process/posix_thread/alien_access.rs)
retains the shared mutex through the authorized capture. Non-dumpable alien access
requires the original CAP_SYS_PTRACE capability check; existing capability, Yama,
and trusted-image restrictions still apply. The current single-user-namespace
limitation remains. Same-thread-group introspection retains its original exception.
Voluntary PTRACE_TRACEME keeps its distinct original LSM policy. It captures the
actual parent thread and releases the parent mutex before the original Yama
ancestry walk, which takes that same mutex. Existing PEEK/POKE operations keep the
original tracee-state guard, then the VMAR and shared image-policy guards through
actual memory I/O. Non-dumpable access requires the original SYS_PTRACE authority
captured when that tracer relationship was published; a later capability gain
does not grant it. Detach clears that snapshot. The current caller must still be
the recorded tracer. This scalar snapshot is limited to the current single user
namespace and must become namespace-aware if that original limitation changes.
Unimplemented
PTRACE_ATTACH and process_vm_readv are not represented as protected implementations.

## Exposed paths and old descriptors

- `/proc/PID/{maps,mem}` retains its original per-open VmarSnapshot. Access checks
  now use the actual requested thread, the locked target image, and dumpability.
- `/proc/PID/{auxv,environ}` now checks READ_FSCREDS at open and captures that same
  image identity. Reads after exec return empty, rather than following the new
  image. An already-authorized descriptor may still read its same old image after
  SET0, just as existing maps/mem open authorization is not retroactively revoked.
  Linux can retain old auxv bytes after exec; this implementation returns empty.
- Task fd, exe and namespace symlinks check READ_FSCREDS while capturing the
  original referenced path. The graph and object ownership of those paths is unchanged.
- pidfd_getfd holds the original target Process, VMAR and access guard until the
  original file description has been captured. Installing it in the caller happens
  after target locks have been released.
- `/proc/PID/stat` keeps public PID/starttime/size/RSS and scheduling information.
  Unauthorized start/end code fields become 1 for a live image; stack/data/brk,
  argument/environment addresses and exit code become 0, as in Linux. It captures
  authorized addresses under the same image-policy guard and drops locks before
  copying the formatted output to userspace.
- Dynamic proc ownership uses root for non-dumpable images, with Linux's public
  0555 task-directory exception. The original default VFS DAC implementation is
  reused unchanged. Only the fd/fdinfo directory template can override an EACCES
  result for the actual same thread group, preserving non-root self-FD inspection.

The original dumpability-qualified source did not implement the commoncap
permitted-set ceiling. The separate [commoncap slice](COMMONCAP_ALIEN_ACCESS.md)
adds that check and distinct consent policy, with its own source-bound qualification.
User namespaces, ptrace attach, coredumps, and a general security-policy framework
remain outside these rules.
Existing read-only proc metadata and ordinary command-line visibility are not
blanket-denied. Kernel heap/PT accounting and global recovery remain open.

## Regression and evidence contract

Six new original-owner kernel tests are mandatory in the unfiltered core suite:
real shared VM/fork/new-image state; no-op/query/denied credential updates; all four
ID reset conditions; capability drop versus gain; original capability and same-group
exceptions; and a real kernel-thread writer on a second Process sharing the same
Vmar, blocked until the alien-access guard is released. No synthetic stopped flag
or second resource ledger is used. The retained core floor becomes 359 with 120
required names; original OSTD 230, allocator 20 and MLSDisk 15 are unchanged.

The [bounded native probes](../../tests/workloads/linux/process_dumpable/README.md)
exercise original syscalls with owned child processes, actual UID 60001/caps0/NNP
observers, explicit reap, and the same guest limits. Their earlier Linux and old
kernel failures remain separately retained. Native qualification is granted only
after source-matched full suites, a fresh ordinary build, the retained prior probes,
and these new probes all finish with their strict original exits and denominators.

Primary references: [Linux ptrace access](https://github.com/torvalds/linux/blob/v7.0/kernel/ptrace.c),
[credential publication](https://github.com/torvalds/linux/blob/v7.0/kernel/cred.c),
[proc image lifetime and ownership](https://github.com/torvalds/linux/blob/v7.0/fs/proc/base.c),
[stat field filtering](https://github.com/torvalds/linux/blob/v7.0/fs/proc/array.c).

## Exact native qualification

Frozen source `4d32d94f0a3647155245d0a1b1dbe0d3caec8e7f`, tree
`dfeff07356b3255ad91722a4fd2bf91ad720abca`, passed the original unfiltered
core 359 / 120 required, OSTD 230, allocator 20 and MLSDisk 15 suites. All four
raw QEMU exits were 33; OSTD retained its three original TCG VMX skips.
The source-matched ordinary kernel passed 18 boot/QueryAbi checks, then that same
ELF passed SGID 30, Unix ownership 12, proc Groups/NoNewPrivs 12, memfd 4, signal 22,
and the new lifecycle 164, stat 54 and TRACEME 15 ordered observations. Every new
probe completed, reaped its children and returned raw exit 33 without timeout.
Source snapshots stayed unchanged; the complete pipeline took 577.893 seconds.

[The exact receipt](../../results/integration/2026-10-23-audit-closure/process-dumpable-4d32.json)
binds all source, ELF, serial, probe and checker identities. Linux references and
old-kernel failures remain separate; the old TRACEME timeout happened before PEEK
and is not classified as a demonstrated memory-read bypass. Successful qualification
does not supersede the open limitations above. Supplementary-group DAC membership
is a separately reproduced issue awaiting its own implementation and qualification.
