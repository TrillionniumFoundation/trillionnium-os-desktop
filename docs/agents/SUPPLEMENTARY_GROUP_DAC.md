# Supplementary groups in original VFS DAC

The original default inode permission check selected group bits only when the
inode group equalled the caller's filesystem group. A caller whose supplementary
groups included the inode group was incorrectly evaluated against other bits.

The fix adds membership in the original `Credentials::groups()` set to that
existing group branch. Owner matching still has precedence. Group members do not
fall through to more permissive other bits when group bits deny an operation.
The existing DAC_OVERRIDE behavior and read/write/execute mask checks are
unchanged. No group cache, extra credential owner or alternate permission ledger
is created. The inode metadata is captured before the original groups read lock
is taken, and that guard ends with the membership expression.

Root's controlled Linux and old-kernel probe uses its own temporary files and two
sequential children. Both children have actual UID/GID 60001, no effective or
permitted capabilities and no-new-privileges. The member has supplementary group
60002; the nonmember has none. A root:60002 0640 file and 0710 search directory
must permit member reads/search, deny nonmember reads/search, and deny writes to
both. All six original assertions and both reap records are retained.

The exact same original C source and already-built static binary are used for the
new native check, with the original 512 MiB, one-vCPU KVM and 120-second bound,
8 MiB archive / 16 MiB ELF shape checks. Linux passed all six; source 0252's
ordinary kernel incorrectly denied the two member operations and returned probe
42 after reaping both children. That negative remains recorded separately.

New-source native qualification is pending. The original complete kernel suites
and ordinary compatibility probes remain required; their denominators are not
changed by this one-condition fix. This does not implement ACLs, new user
namespaces, or full Linux permission parity.
