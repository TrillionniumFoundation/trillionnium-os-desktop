# Commoncap limits for sensitive process access

This slice closes an observed capability-ceiling gap in the original alien-access
owner. It does not add a new authorization ledger or a new ptrace implementation.
Native qualification of this candidate is pending; prior results belong to their
recorded source and ELF.

## Reproduced condition

The [unchanged owned-child probe](../../tests/workloads/linux/commoncap/commoncap_probe.c)
constructs one child with actual UID/GID 60001, effective capabilities zero,
permitted CAP_CHOWN only, NNP set, and dumpability explicitly 1. Its actual
same-UID parent has zero effective and permitted capabilities. Linux refuses all
eight sensitive operations: maps, mem, environ, auxv, fd/exe/namespace symlinks,
and pidfd_getfd. After the child drops the extra permitted capability, all eight
operations succeed. Only an owned `/dev/null` descriptor and public sentinel are
used; all children are reaped.

The exact same static binary on qualified kernel `690a7bb36a8bc355cbc0d99f72c34feda1fb06b2`
incorrectly allowed all eight first-stage operations. It completed in 0.917 seconds
with probe exit 42 and raw QEMU 33: poweroff alone is not a pass. The original
[Linux records](../../tests/workloads/linux/commoncap/linux-reference.jsonl) and
[failed native serial](../../tests/workloads/linux/commoncap/native-baseline-serial.log)
remain unchanged. This is not evidence for PTRACE_ATTACH or process_vm_readv,
which are not implemented by this kernel.

## Original owner and permission decisions

[CapabilityLsm](../../kernel/asterinas/kernel/core/src/security/lsm/modules/capability.rs)
now requires the original ordinary UID/GID condition **and** a capability superset:
READ/ATTACH_FSCREDS compares the caller's effective set with the target's permitted
set; REALCREDS uses the caller's permitted set. The actual SYS_PTRACE capability
in the target namespace remains an exception to both conditions. The existing
same-thread-group shortcut, dumpability, Yama and trusted-image checks remain.
No user-supplied PID, UID, capability label or proc text supplies authority.

The ordinary caller already owns its per-thread credentials. The target is read
under its original Process VMAR mutex and shared ProcessVm policy mutex, and the
existing AlienAccessGuard remains held until the actual file/image/path capture.
All live credential edits take that same shared-image transaction, including
CLONE_VM peers; there is no read-then-lock credential snapshot.

Voluntary TRACEME has a distinct mode. The actual selected parent must have a
permitted superset of the calling child's permitted set, or SYS_PTRACE. Ordinary
UID matching and dumpability do not apply to consent. Yama scopes 0/1 permit
consent; scope 2 still requires SYS_PTRACE and scope 3 rejects it. The G1c trusted
initial-image attachment prohibition still includes consent. The syscall captures
the actual parent thread and releases the child parent-pointer mutex first.

The independently running parent's credentials are checked under its Process
VMAR and shared-image mutex. That same coherent snapshot captures the original
SYS_PTRACE bit retained by the existing ptrace relationship. Those guards are
released before the original tracer.tracees -> tracee.state locks. No two memory
images are locked together, and a later parent capability gain cannot change the
retained bit. This is the existing single-namespace tracer-credential contract,
not complete Linux credential/namespace tracing compatibility.

Only the [initial UserNamespace](../../kernel/asterinas/kernel/core/src/process/namespace/user_ns.rs)
can currently be constructed: clone and unshare explicitly reject NEWUSER. The
original on_capable implementation is not a namespace-hierarchy implementation;
namespace creation must not be enabled without replacing that original limitation.

Primary semantic references are Linux v6.17
[commoncap access and consent checks](https://github.com/torvalds/linux/blob/v6.17/security/commoncap.c)
and [Yama consent policy](https://github.com/torvalds/linux/blob/v6.17/security/yama/yama_lsm.c).
The host reference is a separately recorded actual execution; these source links
do not assert the host runs that kernel version.

## Regression and remaining limits

Three new original-owner tests cover effective/permitted selection with a held
image guard; distinct ordinary identity and consent rules plus the real capability
exception; and a real kernel thread blocked on parent credential publication,
then rejecting the revoked superset. All original tests remain unfiltered:
core 363 with 124 required names, OSTD 230, allocator 20, MLSDisk 15. Existing
source checks, ordinary kernel build and every previously qualified native probe
must run again on this candidate, followed by the unchanged 16-operation probe.
The strict checker rejects wrong identities, setup failures, ENOSYS masquerading
as a denial, omitted/reordered/duplicate records, missing reap, timeout and
marker-only rewrites of the actual old failure.

Full user namespaces, ptrace attach, process_vm_readv, general exec/capability
parity, kernel heap/PT accounting and global recovery remain outside this slice.
The independently queued SCM_CREDENTIALS sender-validation review is also open;
this fix must not be used as evidence for that socket credential mechanism.
