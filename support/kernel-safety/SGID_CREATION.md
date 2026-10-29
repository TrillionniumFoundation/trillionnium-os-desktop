# Group inheritance when creating an inode

The original native Root creates its runtime directory as root:60002 with mode
02710. It binds Unix sockets and requires each resulting socket to be root:60002
with mode 0660. An actual ordinary-kernel probe reproduced the previous failure:
the parent was correct, but the bound socket was root:0, and the real dropped
UID 60002 could not connect. This was distinct from the earlier proc credential
fields and was found before repeating the large original-owner guest.

Ramfs (also the implementation behind tmpfs) and ext2 now initialize the owner,
group and mode before publishing a newly created inode. The shared
`fs/utils/inode_creation.rs` captures the current filesystem UID/GID, the real
immutable supplementary-group set, and a namespace-specific `CAP_FSETID` result
outside the parent metadata lock. The capability hook is needed only when a
non-directory explicitly requests both SGID and group execute; it may be
queried before knowing whether the parent group already matches. The current
hook has no mutation side effect, and a denied capability never overrides
membership. No credential or LSM lock is acquired during the pure decision.

Each filesystem supplies the parent's mode and GID from the same owning lock.
A setgid parent supplies the child's GID. A new directory also inherits SGID;
other inode types do not automatically inherit that bit. A nonmember without
`CAP_FSETID` requesting both SGID and group execute under such a parent has SGID
cleared. A non-executable SGID request retains the bit, as Linux does. Subsequent
chmod remains subject to the existing permission transaction, which prevents
that nonmember from adding group execute while retaining SGID. A parent without
SGID continues to use the creator's filesystem GID. UID remains the creator's
filesystem UID. Hard links and renames retain the existing inode's ownership.

The reference is Linux v6.17
[`inode_init_owner` and `mode_strip_sgid`](https://github.com/torvalds/linux/blob/v6.17/fs/inode.c).
This does not add idmapped mounts, ACL inheritance, general user-namespace
qualification, or group-inheritance support to unrelated filesystem backends.

Ramfs uses the helper for ordinary creation, sockets, symlinks, FIFO/device
nodes, and `O_TMPFILE`. Ext2's single initialized-child path supplies the decided
IDs and mode to `create_inode`, including its first descriptor write. Directory
and symlink initialization and existing rollback stay in place. There is no
post-publication chown, permission widening, or extra fallible metadata update.
The ramfs metadata lock covers the parent attribute decision, not the later
allocation; ext2 retains its existing parent inner lock through creation. The
outer VFS directory-entry lock remains part of the existing creation protocol.
This is not a claim of a transaction spanning every external credential or
parent attribute change, nor a crash-atomic directory creation claim.

`tests/kernel/sgid/run.py` reuses a verified ordinary product from the exact
clean source and runs its static C probe only inside QEMU. It creates a fresh,
private 64 MiB ext2 regular file itself, attaches no host block devices or
network, and retains raw serial, source identities, artifact hashes and the
fixture. Both two-CPU and four-CPU profiles are supported. The 130 assertions
exercise ramfs, tmpfs and ext2 through real syscalls: original Root socket
ownership/connect/deny, files, directories and nested creation, symlinks, FIFO
and character nodes, ramfs/tmpfs unnamed files, changed filesystem GID, parents
without SGID, hard links and renames, primary and supplementary group members,
nonmembers, executable and non-executable SGID, and the chmod escalation
negative. Ext2 is synced, unmounted and reopened read-only to verify persisted
IDs/modes. That last check is same-boot filesystem persistence, not power-loss
or cross-boot qualification. Ext2 `O_TMPFILE` is not claimed.

The old kernel runs the same final probe as a real negative control. The
original socket-only reproduction and any earlier probe revisions remain
separate evidence. No probe is executed on the host. Passing this stage does
not qualify original Root/Agentd/SQLite/HOS2 delivery, history recovery, or
production; the original owner must run again on the exact resulting source.
