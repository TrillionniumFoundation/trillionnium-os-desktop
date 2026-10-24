# Unix socket credential snapshots

This slice fixes a reproduced identity lifetime error in the original Unix
socket credential owner. It does not replace sender authorization with a PID,
UID label, peer group, or transferred descriptor supplied by userspace. Native
qualification of this candidate is pending the complete source-bound run.

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
