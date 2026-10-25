# Commoncap limits for sensitive process access

This slice closes an observed capability-ceiling gap in the original alien-access
owner. It does not add a new authorization ledger or a new ptrace implementation.
Exact native qualification is recorded below; every result belongs to its
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
The original SCM_CREDENTIALS path separately checks the supplied tuple against
the actual sender in AuxiliaryData::from_control before publication. Reading only
CredMessage::read_from would miss that gate and is not evidence of a spoofing
bypass. Socket credential lifetime and wider Linux credential semantics are not
qualified by this process-access fix.

## Exact native qualification

Source `4aabde6accaa37a09020d852bfcc8559faea4ab6` (tree
`77b73bd4413fb26dfd5dc3e0d2b938a95979a898`) passed the original unfiltered core
363/363 (124 mandatory names), OSTD 230, allocator 20 and MLSDisk 15 suites. All
four guests returned raw status 33; only OSTD's three original TCG VMX soft skips
remain. The three new owner tests actually ran, including the blocked credential
reader and final denied result after the parent revoked its permitted capability.

The fresh ordinary kernel passed 18 boot/QueryAbi checks. That same retained ELF
passed SGID 30, Unix ownership 12, proc Groups/NoNewPrivs 12, memfd 4, signal 22,
dumpability lifecycle 164, stat 54, TRACEME 15 and supplementary DAC 6. The
unchanged Linux-referenced commoncap binary then passed all 16 operations in
0.870 seconds: extra target permission was denied on all eight paths, dropping
that permission restored all eight reads, and the owned child was reaped. Its
actual UID 60001/caps0/NNP observer and both target capability sets were verified.
The old `690a7bb3` failure remains a separate retained result.

The full pipeline completed in 581.185 seconds with tracked source bytes
unchanged. Kernel SHA-256 is
`751ccb357f05d2607119a344aaf191c115ae8b02916181d7b22595b1a8a8734c`;
the new commoncap raw serial SHA-256 is
`1b2f160e52d2c439674cb9c52c2da51a9348106b4152beec6a481d0a346e57cf`.
The [receipt](../../results/integration/2026-10-23-audit-closure/commoncap-4aab.json)
records all source/ELF/raw identities, the original Linux and native negative,
84 host tests, 118 source checks, successful Clippy compilation with 113 existing
warnings, and four strict checker tests. The original 512 MiB, deadlines,
profiles, complete denominators and negative assertions were not relaxed.
