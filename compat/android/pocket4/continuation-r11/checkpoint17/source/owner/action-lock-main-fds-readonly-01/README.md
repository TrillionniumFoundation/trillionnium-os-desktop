# Fixed seven-process action-lock FD observation

This request prepares one read-only diagnostic after Ticket's retained zero-action
launch failure. It is not a new UI attempt. Root alone submits the exact request
after review. The earlier Amazon/Ticket failures and the two empty lock-table
observations remain unchanged.

## Reads and bounds

The exact lock is `/run/lock/android-digitalis-actions.lock`, device 28, inode
8312, root UID/GID, regular mode 0600 and one link. It is held with O_PATH and
checked again by a no-follow named walk. Its contents are never read.

The process list is exactly the existing Main daemon, launcher, presenter, init,
surfaceflinger, system_server and zygote64. Numeric PIDs and birth ticks are fixed
in source. Parent PID, UID, namespace-PID list, PID/mount namespace, executable
and cgroup must match the unchanged SHA-pinned activation input. Each process is
sampled around its FD enumeration using a held proc directory and held pidfd;
the pidfd is only polled for liveness and is never used for signaling/getfd.

Only the seven fixed `/proc/PID/fd` directories are enumerated: at most 4,096
entries each and 16,384 total. Each entry receives a target stat only. No
unrelated FD content or link target is read or exported. Only exact device/inode
matches may open the corresponding numeric `fdinfo` entry; those reads are at
most 16 KiB each, with at most 64 matching FDs and 32 lock rows per FD. Filtered
output contains regular-file fdinfo scalars and exact-inode lock records. A
malformed/changed entry or unavailable metadata remains explicit and prevents
complete collection. There is no whole-/proc scan and no /proc/locks reread.

Fixed self PID/mount namespace metadata and the one `/proc` mountinfo record
provide context. Unrelated mountinfo rows are not exported. Namespace labels are
evidence, never paths used to enter or read another namespace. The `/proc` record
does not establish the superblock's PID namespace by itself.

The original 18,537-byte Main support source and all five existing input hashes
are unchanged. The exact original guard runs before/after and still requires
pids.max 12288. Boot, five held/named inputs and lock identity are checked at the
end. The collector has a 15-second cooperative deadline and 2 MiB output bound;
the original outer contract remains 30 seconds, one CPU and 128 MiB.

## Meaning of the result

This is sequential sampling, not an atomic process/FD/lock snapshot. Matching
inode metadata does not prove the same open file description, who acquired a
lock, or who historically transferred an FD. FDinfo numeric PID 0/-1 or another
PID is reported without probing that PID or granting birth/cleanup authority.
No matches do not prove no holder. Collection never grants a retry, signal,
cleanup or runtime authorization. All such qualification fields remain false.

There is no flock/lockf, pidfd_getfd, SCM_RIGHTS, signal, subprocess, namespace
entry, lock write/replacement/deletion or Android action. Only the process's
stdout is emitted. Opened descriptors are registered before later failures;
close is attempted once, close errors remain explicit, and a first error is not
replaced by cleanup errors.

## Local verification

Ten actual local controls cover the production parsers, exact retained Ticket
failure binding, numeric names and bounded owned-directory enumeration. They
also use real local owned directory/pipe descriptors to check first/last parent
close failures, iterator-close failures and preservation of an earlier error.
They do not call collect, read /proc/Main or execute Hepta. PLAN is the source
default; the separately reviewed exact request explicitly asks for collect-once.
These controls are not device or kernel qualification.

The transport has exactly three UTF-8 members: new reader, unchanged original
support source, and the retained 6,053-byte Ticket failure. The in-memory wrapper
checks full packet length/SHA and every member before loading either module.
Python -I -B preserves isolated imports and disables bytecode writes. The input
transport bound is 128 KiB; this does not change any observed-data bound above.
