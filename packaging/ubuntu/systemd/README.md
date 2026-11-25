# Native generator private tmpfs

Cal11 reached the original environment generator, then the stock systemd generator
sandbox failed when mounting its private /tmp. The exact retained serial is
296,862 bytes, SHA-256 8d83292d66ef611902c2375938d32ee89891d9b1371d3ad4c75494eabb521d1a.
The original owned VM ended unsuccessfully; this source change is not runtime qualification.

Apply the quilt patch to the exact normally unpacked Ubuntu source in source.lock.json,
with the original Ubuntu quilt series already applied. Add one normal changelog entry
for the locked candidate source version and build through the original Debian packaging.

The actual raw native manager context selects an internal flag before clone. The child
uses only literal labels on a newly created tmpfs. Its original new mount namespace,
slave propagation, nosuid/nodev options, mode, resource limits, generation and wait/error
handling remain. No environment variable, supplied path, capability increase, generic
Android tmpfs mount, or fallback on the failed mount is introduced.

Kernel 6.18's may_context_mount_sb_relabel requires the native manager's exact
tmpfs:filesystem relabelfrom source permission and relabel-to the new native
filesystem type. The following inode context checks also require relabel-from the
new filesystem and association of the one native temporary-inode type. These are
explicit policy boundaries; no original Android inode is relabelled.

The normal source package, binary package dependency closure, full payload readback,
original package rollback, strict original-nine-CIL policy build, and a fresh actual
enforcing boot are mandatory downstream gates. A patch application alone passes none
of those runtime or package gates.
