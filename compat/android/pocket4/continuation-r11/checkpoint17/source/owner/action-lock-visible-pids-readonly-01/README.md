# One bounded visible-PID lock-FD observation

This is the next read-only diagnostic after two retained zero-action UI lock
admission failures and the fixed Main-seven-PID observation. It does not retry a
UI action, acquire a lock, start a runtime, or change Main.

The previous seven-PID job remains FAIL. Its exact 28,778-byte stdout SHA256 is
`44e2f3f48c5da236c3c9c292a306a6a38c7d926740165e1e753dacdd26f8681c`.
It records 844 successful FD target stats, zero matches, and three process/self
namespace timestamp mismatches. The observed namespace labels/device/inode and
other identity fields stayed equal. Three final named-process gates did not run
after those assertions failed. This new source does not reclassify that result.

## Exact scope

The lock path remains `/run/lock/android-digitalis-actions.lock`, device 28/inode
8312, root UID/GID, regular mode 0600, one link. Only an O_PATH metadata handle is
opened; its original full metadata and a final no-follow named handle must match.

One `/proc` directory pass considers at most 4,096 canonical positive numeric
PID names and at most 8,192 total directory entries. Non-numeric names are not
opened. The collector's own PID is excluded explicitly, avoiding its newly
created O_PATH lock handle and transient directory-enumeration FDs.

Each visible numeric PID's held directory permits at most 4,096 FD entries, with
131,072 entries total. Only FD target stat metadata is read initially. A process
that has no exact device/inode match contributes aggregate counts and sanitized
errno/type coverage gaps only; no PID, name, FD number, cgroup, executable,
cmdline, environment or FD content is exported for that process.

Only an exact lock-inode match permits that process's bounded stat/birth/comm,
UID/NSpid, PID/mount namespace, cgroup and executable-link/O_PATH metadata reads.
A held pidfd is only polled for liveness. Named/held process identities and birth
are sampled before/after. Initial identity failure prevents later fdinfo reads
for that process and stays the first error.

At most 64 matching FDs may read their own numeric fdinfo: 16 KiB each and 32
lock records each. Only regular-file scalars and exact-inode lock rows are
exported. Their numeric PID is not used to find other processes or grant any
signaling, cleanup or historical-sender authority.

The unchanged Main support source still checks the same five SHA-pinned inputs
and calls the original Main guard before/after, including pids.max 12288. Boot,
input held/named identity and exact lock identity remain required. Namespace
identity uses label/device/inode/type/owner; nsfs timestamps remain recorded
observations. The proc root's changing link count is also recorded, not treated
as identity. This follows the namespace identity documented in
<https://man7.org/linux/man-pages/man7/namespaces.7.html>; it does not prove the
cause of a specific timestamp change in the running kernel.

Own PID/namespace and the one `/proc` mountinfo record provide context. Unrelated
mount rows are not exported. `os.uname().release` records the current release
string only. No namespace link's text is used as an external pathname.

## Coverage and result semantics

The collector has a 15-second cooperative deadline, 2 MiB output bound, and a
30-second/one-CPU/128-MiB outer request. Each opened FD is registered before later
operations can fail. Close is attempted once, with first errors and ambiguous
close failures retained.

`scan_completed` means the bounded initial list was processed. `coverage_complete`
also requires every listed, non-self process/FD observation to complete without
gaps. Process disappearance, unavailable FD metadata, bounds, or changed matched
identity prevent complete coverage; partial matching evidence remains explicit.
`collection_complete` additionally requires all original Main/input/boot/lock
and FD-cleanup gates. It does not grant runtime or cleanup authorization.

This is one sequential view, not an atomic inventory or a proof of all host PID
namespace visibility. Numeric leader directories do not cover nonleader private
FD tables. Kernel-held in-flight references and transient processes/FDs are not
ruled out. Zero matches do not prove no holder. Matching an inode does not prove
the same open file description or identify the original locker or sender.

There is no flock/lockf, signal, getfd, SCM_RIGHTS, namespace entry, subprocess,
lock read/write/replacement/deletion, UI action or /proc/locks reread. The only
output is stdout. Original failed source/results remain frozen.

## Local verification

Five new local controls cover the retained actual timestamp differences,
continued rejection of namespace identity changes, proc-root link-count
semantics, real owned numeric-directory enumeration, and production scanning of
owned nonmatching FD fixtures. A separate owned-file seam checks that an initial
matched-process identity failure remains sticky and never opens fdinfo on a
later match. These controls never call collect, read live /proc or run Hepta.
They do not qualify a device or kernel. Unchanged old parser/close controls are
not rerun or relabeled as new device evidence.

The packet contains exactly three pinned UTF-8 members: this task's reader, the
unchanged 18,537-byte Main support source, and the exact retained Ticket failure.
Every packet/member SHA and length is verified before source is loaded in memory.
The default entry is PLAN-only. Root alone dispatches the reviewed exact request.
