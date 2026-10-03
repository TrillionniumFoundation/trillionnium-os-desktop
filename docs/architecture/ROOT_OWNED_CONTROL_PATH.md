# Root-owned control pathname custody

Plan revision: `2026-08-29-d6`. This Linux source candidate supplies a pathname
and kernel-incarnation boundary, without installed startup or an attestation
broker. The closed API inventory is
[`root-owned-control-path.v1.json`](../../contracts/root-owned-control-path.v1.json).

`RootControlPathPolicy::new` accepts only an externally selected absolute ASCII
pathname and exact directory/socket group and mode values. The pathname is at
most 107 bytes and 32 components, without abstract addresses, NUL, controls,
empty components, dot/parent components, encoding aliases or a trailing slash.
The direct parent supports root-owned 0700 or 0750; the root-owned socket supports
0600 or 0660. Every ancestor is a real root-owned directory without group/world
write. A 0750 traversal group and 0660 socket group can admit a separately
configured non-root client without letting that group replace the pathname.
These arguments are configuration, not authenticated policy provisioning. No
observed UID, GID, executable, principal or unit becomes approved configuration.

`RootOwnedControlListener::from_inherited` consumes an existing AF_UNIX
SOCK_SEQPACKET listening descriptor. Its name describes descriptor consumption;
its supported profile requires actual effective UID zero and the listener's
actual SO_PEERCRED creation PID equal to the calling process. A descriptor from
another creator, including PID1, is refused. The constructor never calls bind,
listen/relisten, chmod, chown, unlink or service activation. Linux listening
credentials belong to the listener's creation/listen incarnation; accepting in
a different process does not make the creator that process. No identity is
rewritten to make an inherited systemd listener pass a control protocol.
The original listening SO_PEERCRED is retained and checked again before/after
acceptance. A foreign process can change that kernel incarnation by calling
listen through a descriptor alias. Observing that change permanently retires
the typed listener and its shared pathname scope; a later relisten restoring
the original credentials cannot revive them. Cleanup closes only owned FD
copies and leaves the foreign alias and pathname alone.
The listener's actual O_NONBLOCK status is also checked before native accept.
Clearing that shared flag through an alias is refused and latches retirement;
the constructor's accepted-socket SOCK_NONBLOCK flag alone cannot bound a
blocking listener. Restoring the flag cannot revive an observed failed scope.

Socket FD inode and filesystem pathname inode are different objects. A stale
listener can retain the same `getsockname()` text after its pathname is unlinked
and replaced. The constructor therefore calls actual Linux `SIOCUNIXFILE`,
retains its O_PATH/CLOEXEC bound dentry and requires that exact device/inode to
match the independently walked named leaf. Linux requires CAP_NET_ADMIN in the
socket's network user namespace for that ioctl. Missing privilege or support
fails; there is no stat/address fallback or capability installation. The
privileged test helper is separate from the unchanged production service graph.
The bound-dentry and privilege behavior comes from Linux's
[`unix_open_file`](https://github.com/torvalds/linux/blob/v6.16/net/unix/af_unix.c#L3019).

The pathname walk opens `/` and each component with O_PATH, O_NOFOLLOW and
CLOEXEC, keeps the descriptors, rejects symlinks and checks actual metadata.
The leaf must be a socket, root-owned, the exact configured GID/mode and one
link. Subsequent checks reopen the complete absolute chain, compare every
retained directory and leaf identity, recheck metadata and validate the retained
listener binding and cookie. An observed failure permanently retires that
scope; restoring permissions or putting an old name back cannot revalidate it.
Directory identities/permissions are checked without requiring directory
timestamps to stay constant when unrelated root-owned entries change.

`accept_before` and `RootPathControlConnection::connect_before` use a caller's
original absolute Instant. They reject past/over-20-second entry ceilings,
charge path checks and native polling to that same ceiling and refuse late
results. No Duration creates a replacement transaction or reporting deadline.
An invalid accept entry ceiling (past or over 20 seconds) is caller preflight,
before admission begins, and does not retire the still-owned listener. A
foreign creator is likewise refused before touching its copied scope. Once a
valid accept attempt starts, any observed native/path/identity/deadline failure
retires that listener and its shared pathname scope. Admitted connection
verification failures remain permanent for that connection's custody.
The connector compares protected path snapshots before/after connection and
checks the explicitly approved kernel PeerPolicy. It does not independently
obtain the server's SIOCUNIXFILE dentry. The exact kernel-bound-listener proof
belongs to the server; the connector's evidence is the protected pathname and
the original kernel peer. Neither evidence establishes a live approved
executable or unit across UIDs.

Both connection directions obtain actual SO_PEERPIDFD from that connected
socket. They retain its original incarnation, socket cookie/FD identity and
exact deadline, and poll the same pidfd before/after later path checks. A later
numeric `pidfd_open` lookup is not used to manufacture original-peer continuity.
Death, metadata/path drift, deadline or descriptor mismatch latches refusal.
Exec with the same PID is not detected by this path-only boundary; live
executable/unit checks remain the peer-attestation layer's responsibility.

`consume_before` transfers the same OwnedFd, unchanged Instant and unique
`RootControlPathCustody` in one callback. It supplies no naked-FD proof. The
consumer must retain that custody and its opaque `RootControlPathVerifier` and
check it at every later boundary. Dropping same-process custody revokes its
verifiers; raw escaped or duplicated descriptors do not regain proof. Fork
checks precede copied-state/path/clock/syscall use. Child teardown closes only
child descriptor copies, without parent shutdown, foreign unlink or a mutex
unlock. No thread or unbounded Drop join is introduced.

`root_control_path_kernel` uses an explicitly privileged sudo test helper and
independently selected root/non-root test roles. It exercises actual root-owned
paths, root/non-root connections, SIOCUNIXFILE, SO_PEERPIDFD, capability removal,
foreign creator/fork, symlink/hardlink/metadata drift, unlink-rebind, original
deadlines, a live foreign alias relisten and full FD inventories. Its 12 groups
retain the original 10 cases and add incarnation and nonblocking-status
drift/restore refusal.
Missing required facts fail rather than skip.
These host kernel operations do not run Servo, activate product daemons, issue
semantic principals or provision approved production executable policy.

Remaining integration needs a strictly retained root-owned policy loader,
approved UID/GID/unit/executable/principal provisioning, a reviewed cross-UID
live attestation broker/source, and an installed owner that preserves this
path verifier alongside original Agent/custodian and journal/native gates.
Default binaries and service capability/activation settings remain unchanged.
Administrator-controlled concurrent path changes, unowned raw FD aliases and
all C-return/opcode interruption windows are not claimed atomically eliminated.

The existing custody workflow's absence guards now distinguish native grep
status 0 (match/refuse), 1 (absent), and read errors (refuse). Binary strings are
read into a fresh temporary file before matching so a failed strings command
cannot be hidden by a negative pipeline. The source regression executes the
complete workflow bodies with isolated source/build fixtures; those runs prove
guard behavior and create no installed or kernel isolation qualification.
