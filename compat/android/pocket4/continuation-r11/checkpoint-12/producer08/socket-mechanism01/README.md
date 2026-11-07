# Owned socket projection kernel mechanism control

NORMAL03 reached the authenticated init HELLO, broker READY and PROJECT send,
then its diagnostic constructor failed at `project-bind-mount` with errno 22.
Its original result remains failed. This new request creates one fresh private
host fixture, with a second private mount namespace in its owned child.
The producer and actual NORMAL03 init share user namespace dev 5 / inode
4026531837; their mount namespaces differ. This control records and requires
that same user namespace, with two distinct owned mount namespaces.

The source socket is a new, owned 1069:1069 mode-0600 inode on a private 1 MiB
tmpfs. The child closes inherited source handles and receives exactly two
SCM_RIGHTS descriptors. Three observations must hold: a raw foreign attached
O_PATH source fails ordinary bind with EINVAL; reopening the identical source
through the child's own mount namespace binds successfully; a detached mount
cloned by its host owner moves onto the child's exact new held target. The
post-operation inode, ownership, mode and statx mount IDs are checked.

All mounts happen after unshare and recursive private propagation. There is no
Android, network namespace creation, production endpoint, pressure allocation,
or installed-file mutation. The owned C parent/child have parent-death signals,
pidfd/precise-child wait cleanup, and explicit private tmpfs unmount. The Python
controller remains outside those namespaces, retains the original MainFence,
and uses the unchanged held own-cgroup resource guard at CPU 1 / 512 MiB.
It binds actual compiler/readelf pins from successful build03, compares complete
preflight/actual MD sets and source inputs, and requires exact waits. A bounded
readelf check reports whether the already-pinned compat artifact exports mount
or syscall-related entry points; it is not source provenance for that artifact.

Upstream kernel source supports the mechanism hypothesis; it does not bind the
Pocket4 kernel binary. In Linux v6.17, ordinary bind and child-side open_tree
cloning use may_copy_tree, whereas move_mount accepts a detached anonymous root
and validates its target namespace. Source:
https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux.git/+/refs/tags/v6.17/fs/namespace.c

No namespace probe was run when freezing this source. The actual request must
be reviewed and scheduled by the root coordinator once. Even if it passes,
the paired Rust producer and Android constructor still require matching builds
and a fresh real init canary. This control never grants production readiness.
