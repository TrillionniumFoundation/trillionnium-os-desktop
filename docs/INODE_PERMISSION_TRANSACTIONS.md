# Inode permission attribute transactions

## Scope and acceptance

This change makes permission decisions and the corresponding inode attribute
updates share each migrated backend's existing metadata lock. The unit of
serialization is the inode, including its hard-link aliases. It covers mode,
owner, group and the associated in-memory ctime update for chmod, chown and the
mode portion of privilege stripping.

It does not make file data writes, removal of the `security.capability` xattr,
and attribute changes one transaction. It does not provide crash atomicity or
prove every filesystem backend race-free. The compatibility paths below remain
explicitly unported. A `Path`-local mutex would not close those boundaries,
because separate dentries and external writers can refer to the same object.

Qualification requires the exact candidate's complete original A06 gates, the
five mandatory ordinary permission ktests, and the independent two-CPU positive
and negative gate. Source review and host parser tests alone are insufficient.
The two-CPU tests are kernel-mode backend tests; the separate 32-case Linux and
guest probe continues to exercise real syscall credentials and capabilities.

## Public contract and capability decisions

`Inode::try_permission_attr_transaction(dentry, request)` returns
`Option<Result<()>>`:

- `Some(Ok(()))` means the selected backend completed its attribute operation.
- `Some(Err(...))` preserves the actual permission or backend error.
- `None` explicitly selects the named legacy path for an unported backend.
  It does not mean successful atomic execution or `EOPNOTSUPP`.

Every concrete implementation either supplies this method or inherits the
explicit SysTree compatibility implementation. There is no default successful
fallback in the `Inode` trait.

`PermissionAttrRequest` snapshots the caller's filesystem UID/GID and
supplementary groups outside the inode lock. A backend evaluates against its
current locked mode/owner/group. If it needs a capability decision that is not
cached, evaluation records a separate `pending_cap` value and returns before
any mutation. The request executor releases the backend guard, invokes only
the requested LSM capability hook, caches its result, and evaluates fresh
metadata again under the backend lock. Each of CHOWN, FOWNER and FSETID is
requested at most once per operation.

The pending field is the sole retry criterion. A genuine backend or LSM
`EAGAIN` is returned to the caller. No metadata field is committed before all
required capability and backend mode-policy decisions have completed. This
also avoids invoking unused LSM hooks merely to precompute permissions.

The `for_test` constructor supplies explicit credential/capability values to
focused backend tests. Those tests do not replace the syscall probe or claim
to test the missing-capability/LSM retry loop directly.

`Path::chmod` and `Path::chown` preserve the mount-writable check before backend
dispatch and notify only after success. Unported backends run
`legacy_chmod_split_lock` or `legacy_chown_split_lock`. Xattr privilege stripping
uses the same migrated mode-update primitive, with
`legacy_clear_set_id_bits_split_lock` for unported backends. Its existing
no-set-ID early return remains; a concurrent content write and privilege
stripping are still outside this attribute-only contract.

## Backend inventory

All paths in this table are relative to
`kernel/asterinas/kernel/core/src/fs/`.

| Implementation or delegate | Current owner and transaction | Preserved behavior or remaining boundary |
|---|---|---|
| `RamInode`, `fs_impls/ramfs/fs.rs` | One existing `SpinLock<InodeMeta>` covers decision, mode policy and the complete update | Shared by RAMFS, tmpfs and devtmpfs inode instances; all real hard-link aliases use the same lock |
| `MemfdInode`, `fs_impls/ramfs/memfd.rs` | Existing seals mutex, then the underlying RAM inode metadata lock | Keeps the order used by `add_seals` and raw `set_mode`; `F_SEAL_EXEC` rejects executable-bit changes before any ownership/mode mutation |
| `Ext2Inode`, `fs_impls/ext2/impl_for_vfs/inode.rs` and `ext2/inode/attrs.rs` | One `inner` write guard covers evaluation and existing dirty-descriptor setters | Normal errors precede mutation; a focused test also syncs and reopens the block-device fixture to check persisted IDs/mode, without claiming power-loss atomicity |
| `PseudoInode`, `fs_impls/pseudofs/mod.rs` | Existing metadata spin lock | Anonymous pseudo inodes retain `EOPNOTSUPP` for mode changes; normal pseudo modes remain writable |
| `AnonPipeInode`, `pipe/anon_pipe.rs` | Explicit delegation to the same `PseudoInode` transaction | Keeps the pseudo inode's mode policy and metadata owner |
| `NsInode<T>`, `fs_impls/pseudofs/nsfs.rs` | Existing common pseudo metadata lock with a separate mode policy | Namespace inode chmod retains `EPERM`, including requests for the same mode |
| Devpts `RootInode`, `Ptmx`, `PtySlaveInode` | Each existing metadata `RwLock` write guard | Preserves their existing chmod ctime behavior; successful chown updates ctime in that same guard |
| `ProcDir`, `ProcFile`, `ProcSym`, `fs_impls/procfs/template/` | **Unported: explicit `None`** | Ownership may be derived from another thread's credentials, outside common metadata storage; locking only the common fields would give a false serialization boundary |
| `SysTreeInodeTy` blanket implementation, `utils/systree_inode.rs` | **Unported: explicit `None`** | Owner/group are immutable, mode has a separate lock, and setters have intentional `EPERM`/no-op semantics |
| `SysFsInode`, `ConfigInode`, `CgroupInode` | **Unported: inherit the explicit SysTree implementation** | Preserve original specialized metadata/setter behavior; successful operations are not silently changed to `EOPNOTSUPP` |
| `ExfatInode`, `fs_impls/exfat/inode.rs` | **Unported: explicit `None`** | Mode/IDs are synthesized from mount options and attribute setters intentionally succeed as no-ops; requires its own contract |
| `OverlayInode`, `fs_impls/overlayfs/inode/mod.rs` | **Unported: explicit `None`** | Copy-up, lower/upper aliases and publication must share an authorization boundary; a wrapper-local lock does not provide it |
| `VirtioFsInode`, `fs_impls/virtiofs/inode/mod.rs` | **Unported: explicit `None`** | A guest cache lock cannot serialize host-side writers; one FUSE SETATTR is not a host compare-and-update contract, and the caller credential contract needs separate work |

The inventory contains 19 `Inode for` declarations: 16 direct or blanket
transaction methods and three SysTree specializations inheriting the explicit
compatibility method. Adding a filesystem requires choosing its actual owner
and preserving its documented errors, timestamps and delegating wrappers.

## Ordinary regression coverage

The default feature set keeps the original one-CPU full OSTD/core gate. Its
checker requires at least 252 tests: the original 238, these five permission
tests and the nine G1-c regressions. All 14 new complete names must be observed
exactly once without soft skipping:

| Test leaf | What the real backend must do |
|---|---|
| `permission_rejection_has_no_partial_update` | Reject a CHOWN-only caller when clearing mode requires FOWNER; leave mode, UID, GID and ctime unchanged, then allow the fully authorized update |
| `permission_noop_chown_updates_ctime` | Allow non-owner `chown(-1,-1)` on a plain file without changing IDs/mode, while updating ctime; uses a sentinel time rather than sleeping |
| `permission_alias_observes_new_owner` | Change ownership through a real hard link, reject the old owner's later chmod and allow the new owner |
| `permission_ext2_reject_then_commit` | Reject without partial metadata, then persist authorized mode/IDs through Ext2 sync and reopen |
| `permission_memfd_exec_seal_preserves_attributes_on_error` | Reject executable-bit changes on a sealed memfd without metadata changes; preserve allowed same-mode behavior |

The full 32-case Linux/guest permission probe remains a separate unchanged
denominator. In particular, `chown(-1,-1)` on a non-owner ordinary file is a
successful ctime update, not a blanket `EPERM` case. Tmpfs root UID/GID creation
was fixed separately before this change and remains checked by its mount case.

## Independent two-CPU gate

`permission-attr-smp-ktest` is an empty, default-off Cargo feature. Checkpoints,
their fields and all three test registrations also require `cfg(ktest)`.
The original one-CPU full suite never enters a two-CPU rendezvous. The build
input verifier accepts only the exact reviewed empty feature insertion; no
dependency, external lock or toolchain pin is relaxed.

`support/build/ktest/run.py --permission-attr-smp` fixes the crate to
`aster-core`, the complete test-path suffix to `permission_attr_smp`, and the
feature to `permission-attr-smp-ktest`. Its independent QEMU profile fixes
exactly two CPUs with Q35, TCG, `max`, 512 MiB, serial output and the existing
debug-exit device. It has no network or data disk. Conflicting crate or test
selection is rejected before building.

Each test asserts the actual CPU count before spawning workers. Worker A is
pinned to CPU 0; worker B is pinned to CPU 1. After the real production decision,
A reaches a test-only atomic checkpoint while retaining the relevant owner
guard. B observes that exact metadata/seals lock using its nonblocking
`try_lock`:

- If busy, B resumes A before attempting its normal production operation.
  A commits and releases the owner guard; B then completes normally.
- Under the frozen split-lock defect, the guard is already released. B performs
  its real production operation first, then resumes A's stale decision.

The hook performs only atomic accesses and `spin_loop`. It does not allocate,
log, sleep or schedule while holding a spin lock. A test-only worker guard
records a failure sentinel and releases the rendezvous if a worker unwinds or
returns before normal completion. Unexpected failures remain failures, and
the ordinary QEMU timeout remains a failing gate.

| Exact test module, each with leaf `permission_attr_smp` | Required positive state | Frozen defect and required real counterexample |
|---|---|---|
| `ramfs::fs::permission_smp_tests::owner_alias` | A chmods 04755 as UID 1000; B chowns to UID 1002; final UID 1002 and mode 0755 through both aliases | Release the RAM owner lock between decision and update: B changes owner first, then A incorrectly installs 04755 for the new owner |
| `ramfs::fs::permission_smp_tests::clear_setid_alias` | A strips set-ID from 04755; B chmods 0600; final mode 0600 | Same RAM lock gap: A's stale read/modify/write overwrites B's 0600 with 0755 |
| `ramfs::memfd::permission_smp_tests` | A chmods 0777 while holding the seal lock; B then seals; both final and at-seal mode are 0777 | Release the seal guard after caching writable policy: B seals mode 0666, then A incorrectly adds executable bits and leaves final mode 0777 |

The RAM negative changes only `ramfs/fs.rs`; the seal negative changes only
`ramfs/memfd.rs`. Their patch SHA256 values are frozen in
`tests/organ_backend/run_permission_attr_smp.py`. No test or assertion changes
between positive and negative guests. Metadata outcome assertions precede lock
observation assertions, and the raw oracle requires the actual forbidden
metadata values as well as the exact failed-name set. Merely reporting a free
lock or failing a checkpoint cannot qualify a negative control.

## Execution and evidence

The existing A06 workflow runs the SMP step after all original full kernel,
CPU negative, Linux compatibility and ordinary product stages. It archives the
original successful core ELF before the SMP feature reuses the OSDK target.
The runner creates identified local negative commits in disposable worktrees,
executes each at the original source path embedded in the source-built OSDK,
and restores the exact candidate without forced checkout.

Evidence includes positive/negative raw serial and QEMU records, actual kernel
ELFs, exact patch bytes and hashes, changed negative source bytes, clean source
head/tree and all-file snapshots before/after, generated locks, toolchain,
OSDK/VDSO/firmware/QEMU identities, and command/exit receipts. The strict oracle
requires all three exact names, actual CPU IDs 0/1, real operation return codes,
one hook entry, metadata results, no soft skip, no timeout, raw QEMU exit 33 for
the positive and 65 for each expected negative. The compiled test denominator
must remain at least 255 and match across all three feature builds. Selecting
the three SMP cases cannot replace the earlier complete 252-test core gate.

Host parser tests deliberately tamper with metadata, CPU IDs, hook counts,
per-test outcomes, summaries, input hashes and QEMU arguments. They also run
under Python `-O` to ensure no acceptance condition disappears with assertions.
These synthetic parser fixtures never execute a kernel and are not guest
qualification evidence.

Use the project A06 GitHub Actions environment for the real build and guest
entry. All original gates and the new independent positive/negative gate must
pass for the same reviewed head, and their raw artifacts must be audited before
claiming the migrated backend contract is verified.
