# Role-authorized sealed snapshot: source freeze 01

This is a new, independent connection from the already tested Registry to the ordinary V2 sealed snapshot maker. It is not installed or enabled. Candidate07, ordinary V2 factory, the original NOFILE 26 cases and all four Registry/context core files are unchanged. The copied Registry/context files are byte-for-byte the build02/run02 inputs; INPUT_BINDINGS.json identifies each inherited file.

## New production boundary

`CreateAuthorizedSnapshot` first uses `Registry::AuthorizeCreate` to acquire the approved PIDFD-bound subject and held caller. It checks the exact held canonical tgid/maps inode, actual raw source metadata, a same-subject sealed input memfd, payload bounds, and source status flags. It creates a real root-owned memfd, copies only the supplied bounded payload, writes the existing V2 provenance tag, sets mode 0444, seals it, and obtains the readonly CLOEXEC descriptor through this factory thread's fd directory. All final inode/status/seal/tag bytes are checked. StoreMetadata remains byte-identical to the old V2 function and uses raw KernelStatfs, including ST_VALID; it is not the Bionic libc-normalized representation.

Both successful and failed creation finish the Registry transaction. A failed final caller/generation recheck closes the output and revokes the same owner's slot; when the maker already failed its original errno remains primary. An unrelated fork/thread cannot use this cleanup path to revoke another owner's grant. No reply, listener, service, policy installation, or runtime lifecycle hook is added here. The caller still owns the bounded authenticated response and must revoke on transport failure. The trusted root parent must already attest immutable pre-guest policy; sampled snapshots do not establish absence of transient privilege changes.

## Four owned cases to be run

1. An actually approved child sends its own ordinary O_RDONLY `/proc/self/maps` FD and an owned sealed fixed payload; the real root factory returns a real root-owned sealed V2 inode.
2. A wrong source FD is rejected with EINVAL and the same grant can subsequently create the valid snapshot.
3. An unsealed input is rejected with EINVAL and the same grant can subsequently create the valid snapshot.
4. A payload size mismatch is rejected with EINVAL and the same grant can subsequently create the valid snapshot.

Each case has a fresh fork child, real SCM_RIGHTS/SCM_PIDFD and exact fork/PIDFD approval, EPI/NNP/filter fixture, real canonical source and all-stat/raw-120-byte oracle, real output descriptor sent to that same child, independent child content/tag checks, normal exact child reap, Registry death sweep, and descriptor-count restoration. It reuses pinned source02 helpers; its old ten-case main is renamed and never called. Payloads are fixed owned text. No commercial app maps or data are copied. The fixture's role filter is not production platform policy.

## Observed and unobserved

The exact current source completed a strict local GCC full link and default PLAN. The original result and command logs are in evidence/local-build03. No root-positive snapshot case has run yet; no Android case, full engine integration, factory service or Main action is qualified. Build-only remote matching must precede any actual positive run. The eventual actual ELF and source/tool/authority closure must be bound into a separately reviewed owned runtime request.

## Confirmed inherited O_NOFOLLOW red gate

The separate own-fd control preserved in evidence/inherited-nofollow opened maps with O_NOFOLLOW and observed that F_GETFL retains this bit. Reopening a memfd through `/proc/thread-self/fd/N` with those flags returned ELOOP. The inherited V2 maker uses that precise reopening pattern. This is an observed syscall mechanism with a source-derived inherited defect, not a run of the old factory entry. This freeze first covers ordinary O_RDONLY only. It does not clear the bit, fake F_GETFL equivalence, or fix/qualify O_NOFOLLOW. Full semantics remain the next independent repair.

The inherited 2-second frame/creation bounds, 5-second child command idle and 30-second fixture deadline remain explicit. No arbitrary callback, namespace transition, app-zygote capability transition, last-host-thread exit, complete factory authority/reply service, ART pairing or platform-policy qualification follows from these four cases.
