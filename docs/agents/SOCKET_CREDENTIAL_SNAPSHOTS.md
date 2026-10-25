# Unix socket credential snapshots

This slice fixes a reproduced identity lifetime error in the original Unix
socket credential owner. It does not replace sender authorization with a PID,
UID label, peer group, or transferred descriptor supplied by userspace. Exact native qualification below belongs only to its recorded source and ELF.

## Reproduced lifetime errors

The [original probes](../../tests/workloads/linux/socket_credentials/README.md)
use only owned socket pairs and sequential owned children. For STREAM, DGRAM and
SEQPACKET, a child actually running as UID/GID 60001, with zero permitted and
effective capabilities and NNP set, creates a pair, transfers the receiver using
SCM_RIGHTS, and queues a credential-bearing message. It then legally changes its
real/effective IDs to its saved IDs 60002, executes the same binary, sends a new
message and exits. No forged credential authorizes this transition.

The same Linux-referenced binary on source
`4aabde6accaa37a09020d852bfcc8559faea4ab6` failed 15 assertions: each socket type
reported the new IDs in the old connection's SO_PEERCRED after change, exec and
exit, and in the old queued SCM_CREDENTIALS on peek and consumption. The fresh
message correctly carried 60002. All three children were reaped; probe exit 42
and raw QEMU 33 are a complete failure, not a pass. Linux passed all 59 records.

A separate STREAM/SEQPACKET probe creates pairs with supplementary groups
60003/60004, then actually replaces the sender's groups with 60005. It retains
only CAP_SETGID in both permitted and effective sets (64), UID/GID 60001 and NNP.
This is explicitly a group-administration fixture, not a caps-zero fixture. The
old kernel incorrectly reported 60005 after replacement and after sender exit,
failing four of 16 records. Linux retained the original two groups. Both children
were reaped. The raw Linux and kernel failures remain alongside the probes.

## Original owner and lock contract

[SocketCred](../../kernel/asterinas/kernel/core/src/net/socket/unix/cred.rs)
now captures real and effective PID/UID/GID scalars when the original connection
or message is created. It retains the original immutable supplementary-group
owner, not a live alias to mutable Credentials_. Queued messages, MSG_PEEK,
connection endpoints and their aliases therefore preserve capture-time identity
through credential changes, exec and exit. The existing real/effective selection
at each call site is unchanged.

The original Credentials_ group field is now an `RwLock<Arc<BTreeSet<Gid>>>`.
Read access clones that immutable Arc under the same short spin lock. Setgroups
prepares its new set and fallible Arc allocation before the existing credential
edit transaction, then swaps the owner under the group write lock. The replaced
Arc is dropped after releasing that lock. Forked credentials share an immutable
group owner until replacement; socket capture does not allocate or deep-copy the
group set. PermissionAttrRequest retains that same owner for the existing DAC
check, preserving owner/group/other priority and capability semantics.

Only the calling thread's credentials are captured in production. Each cloned
thread receives its own mutable Credentials_ through Credentials::new_from;
shared immutable groups do not permit one thread to mutate another's credentials.
This avoids adding image-lock acquisition under existing socket locks. Live
credential publication still uses the original image/credential edit transaction.
The G1d private credential construction prepares an empty group owner fallibly
before activation; it does not bypass trusted-role policy. No unsafe code is
introduced. Original BTreeSet construction and SO_PEERGROUPS result collection
remain infallible allocations; this slice does not qualify general heap recovery.

Two original-owner kernel tests cover distinct real/effective snapshots after
source-owner destruction, and immutable group sharing across fork/replacement,
128 repeated captures and final-alias release observed through Weak. All original
suites remain unfiltered: core 365 with 126 required names, OSTD 230, allocator 20,
MLSDisk 15. Existing qualification is not transferred to this candidate.

## Authorization and supported identity meaning

The existing AuxiliaryData::from_control gate compares SCM_CREDENTIALS against
the actual sender before publication. The actual probes retain both negatives:
forged Root IDs and an owned different PID return EPERM and publish no payload.
Reading only CredMessage::read_from would miss this gate. This fix does not claim
complete privileged, effective-ID or saved-ID Linux SCM_CREDENTIALS compatibility.

SO_PEERCRED describes the original connection creator, not the current holder of
an endpoint transferred using SCM_RIGHTS. A received FD still needs the consuming
protocol's own role, lifecycle and message checks. The probes use a one-byte
recvmsg for the SCM_RIGHTS handoff; Linux's legitimate ancillary merging across
a larger stream read is not a kernel defect. This slice is not production Root/
Host authority qualification and does not change Notes descriptor admission.

The primary interface contract is [unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html).
The recorded Linux executions are separate evidence; the reference link alone
is not a claim about the host's exact implementation or version.

## Separate nonblocking defect remains open

The first unchanged probe used recvmsg/recv with MSG_DONTWAIT to verify the empty
datagram queue. On the old kernel that flag is ignored, so the call blocked until
the original 60-second parent alarm (61.389 seconds total, probe 142/raw QEMU 33).
That incomplete run is retained as `native-4aab-baseline-01`. It does not prove all
lifetime assertions and is not a successful negative qualification.

The second probe uses the already supported O_NONBLOCK descriptor flag to isolate
the snapshot defect and completes all 59 records. That fixture change does not
fix or close the MSG_DONTWAIT API defect. It requires a separate production slice
and execution of the original first probe, without widening the deadline.

## Exact native qualification

Source `22e0a19f8ab95f730e0fedd85462157ed3d9a10e`, tree
`9cbd2a0762b42a63cb2c718746773d6555c46460`, passed all original unfiltered
core 365/365 (126 mandatory names), OSTD 230, frame allocator 20 and MLSDisk 15
suites. All four guests returned raw 33 with no failed or filtered tests; only
OSTD's three original TCG VMX soft skips remain. Both new snapshot owner tests
actually executed. The original physical PT exhaustion/recovery regression also
ran again without changing its memory, available-frame windows or assertions.

The fresh ordinary kernel passed all 18 boot/QueryAbi checks. That exact ELF
passed the existing SGID 30, Unix ownership 12, proc Groups/NoNewPrivs 12, memfd 4,
signal 22, dumpability lifecycle 164, stat 54, TRACEME 15, supplementary DAC 6 and
commoncap 16 checks. The unchanged Linux-referenced new binaries then passed
59/59 identity records in 1.724 seconds and 16/16 group records in 2.126 seconds.
All five owned children across the two probes were reaped, with raw QEMU 33 and
no timeout. The distinct capability-free identity and CAP_SETGID group fixtures
retained their exact original credentials. The old 15- and four-failure results,
and the earlier incomplete MSG_DONTWAIT run, remain unchanged.

The complete pipeline took 659.472 seconds. All tracked source bytes were equal
before and after, and the frozen checkout stayed clean. The ordinary ELF SHA-256
is `a3fb67d9ea48f981d8b26d10d0d9d9bd2e4d20e7a978e48abb1dda7d1d251baa`.
New lifetime/group serial hashes are respectively
`fe9390cb91d3b513e16a2ce20815ca226ae8b26579e3a35fce7f712d009c8a4c` and
`b65363d2a78b0878ed952f13eb7e8d3d3ac8981fdabef4e145602edadbddbe36`.
The [full receipt](../../results/integration/2026-10-23-audit-closure/socket-credential-22e0.json)
retains all input, ELF, source, log and negative identities. It separately records
84 host tests, 118 original source checks, four strict checker tests, and successful
ordinary/G1d feature Clippy compilations (113/124 warnings respectively). The G1d
feature build used a retained explicit initial-image input and is compilation
evidence only; this slice does not add new G1d guest qualification. Initial compile
failures remain recorded, including the missing required initial-image input.

The datagram MSG_DONTWAIT blocker is still open. Passing the supported O_NONBLOCK
fixture does not qualify that different operation flag, full Linux socket parity,
production Root/Host authority or global memory recovery.
