# ExFAT permission mode correction

## Defect and production change

The ExFAT inode path used `InodeMode::all()` as its initial synthesized mode.
That value includes set-user-ID, set-group-ID and sticky bits (`07000`), in
addition to the access bits (`0777`). The default mount masks are zero, so
ordinary ExFAT files and directories could report `07777`, with the mount's
default owner and group of zero. The mode/owner/group setters currently
return success without changing the synthesized fields.

The production correction makes `FatAttr::make_mode` start from access bits
only. Its caller no longer supplies an arbitrary initial mode. Existing DOS
read-only behavior, separate file/directory masks, mount IDs and timestamp
behavior are retained. This is not an implementation of ExFAT permission
attribute transactions, persistent Unix permissions or new mount options.

The reference is [Linux v6.16 `exfat_fill_inode`](https://github.com/torvalds/linux/blob/v6.16/fs/exfat/inode.c#L643-L654),
which calls `exfat_make_mode(..., 0777)` for both directories and regular files.
The retrieved `inode.c` Git blob is
`b22c02d6000f79d6157bdd21fdc71176dda80d67`.

## Security consequence and evidence boundary

The ordinary Asterinas `execve` path reads the file mode and owner/group when
preparing new credentials. A `nosuid` mount or `no_new_privs` can suppress the
identity change; neither makes invented set-ID bits correct. Missing ExFAT
extended-attribute support also does not stop this path: reading file
capabilities maps `EOPNOTSUPP` to no file capabilities.

These facts establish a source-level authorization defect. Successful guest
execution, an observed privilege transition on the old behavior, and its
absence on the corrected kernel require the fresh disk-profile evidence
below. A source change, a kernel test listing or a parser test is not that
evidence. This document does not claim the disk profile has passed.

## Kernel regressions

Two default kernel tests call the same production helper used by
`ExfatInode::mode` and `metadata`:

- `exfat_modes_never_invent_setid_or_sticky` checks all combinations of the
  supported DOS attribute bits against access-bit-only results.
- `exfat_modes_keep_file_directory_masks_and_readonly` checks distinct file
  and directory masks, the file-only DOS read-only rule and masks containing
  unrepresentable Unix special bits.

The original full OSTD/core gate is retained. This combined candidate includes
the complete 238-test earlier core baseline, five permission transaction tests,
nine G1-c tests, eight G1-d tests and these two ExFAT cases. The full minimum is
262; all 24 required complete names must occur once and execute without a soft
skip. The separate SMP permission profile adds three tests, so its compiled
denominator must be at least 265 for the positive and both frozen negatives.

The same candidate includes the already reviewed Linux `pivot_root` reference
correction from permission PR #215: existing, searchable directory arguments
replace null pointers while the original unprivileged EPERM assertion remains.
The project cloud has verified all 32 cases with that exact probe under Linux
and the guest; this candidate still requires its own unchanged full CI.

## Fixed disk guest qualification

The initial mode correction was prepared from merged main commit
`0c1de23a3754bc3a6976fed53c7dfa0ec3778e57`, tree
`0337884b57bf67350f27b22eb6af326fa19dcb7d`. The combined candidate now joins
merged G1-d main `f2f5d5587ff3210c975ac4162e5094ad0abfb2cc`, permission/SMP
head `5579ca95d02eeac62ccdff92b0ae4ab0522358e0` and ExFAT disk-profile head
`59a4eb31dccc1980b399d756ae65177778d89e02`. It retains all original workflow
gates and both sets of independent negative controls. The final base is main
`e524064d985ad2e1ade2099bc3d701c29484b3eb`; its five publication-maintenance
paths from PR #223 are preserved without changes. Fresh runs must identify
the final reviewed descendant commit and every source byte before and after
execution; earlier individual-head results do not qualify this combined tree.
The implemented disk profile follows every original A06 step and the added SMP
permission profile. Its cloud execution and raw-evidence verification remain
pending.

The first disk-profile head stopped at the clean-source prerequisite after the
original CPU probe scripts had run without Python `-B`. The SMP parent already
adds `-B` to those two commands to prevent imported helpers from leaving
untracked bytecode; this union retains that change without altering their
arguments or acceptance criteria. Preparation also records the actual Git
status before invoking the unchanged strict source-snapshot check.

1. Keep the existing no-disk, one-CPU full gate and the original two-CPU
   CPU gate unchanged. Add a separate ExFAT evidence profile.
2. In the authorized disposable project CI environment, compile one static
   observation ELF and inspect its ELF identity. Create a fresh ExFAT image
   using the original 512 MiB `mkfs.exfat` image recipe, record the formatter binary,
   command and version, then freeze the image and ELF hashes before any run.
3. Use only disposable copies of that image. The Linux reference may attach
   its own image to a temporary loop device inside a private mount namespace;
   retain ownership of that loop device until it is detached. No existing
   block device or host filesystem is supplied as guest test data.
4. Boot the exact ordinary product kernel with the pinned Q35/TCG/max/512 MiB,
   one-CPU firmware configuration and one fixed virtio block device containing
   the disposable image. Do not enable NICs or host filesystem sharing.
5. The same ELF verifies actual ExFAT `statfs`, root/regular-file/directory
   `stat` mode and IDs. Separate forked children clear supplementary groups,
   use UID/GID 65534, clear effective/permitted/inheritable/ambient and bounding
   capability sets, and read all credentials
   back before `execve` of the copied file on ExFAT. Each child enters the
   already mounted directory before dropping its identity; private evidence
   parent directories remain `0700`. The executed file reports
   real/effective/saved/filesystem IDs, capability sets and `no_new_privs`.
   A companion execution with `no_new_privs=1` must remain unprivileged.
6. Run a frozen one-production-line negative patch that restores the old
   `InodeMode::all()` baseline. The tests and observation ELF remain identical.
   Qualification requires the actual old synthesized `07777` observations
   and an actual UID/GID transition on the unprotected exec, while the
   `no_new_privs` companion remains unprivileged. A build error, missing case,
   timeout, panic or arbitrary nonzero status does not qualify this negative.
7. Preserve raw stdout/stderr/serial and exits, input and output image hashes,
   original and mutated kernel ELFs, tool identities, full source snapshots
   and the independently evaluated results. Keep the mutation under an
   identified temporary source checkout and restore the reviewed tree without
   force before returning.

The implementation is in `tests/workloads/linux/exfat_mode_probe.c`,
`run_exfat_mode_guest.py`, `exfat_mode_evidence.py` and
`run_exfat_mode_negative.py`. `test_exfat_mode_guest.py` checks malformed,
missing, reordered and contradictory evidence, every recorded identity and
capability field, the held loop descriptor's backing inode, and the exact
one-path mutation. A separate host check applies the pinned negative patch to
the actual production inode source and compares it with the mutation builder;
the builder uses the production helper's `ret` binding. These host checks do
not execute a kernel.

The Linux runner creates its own image copy and loop attachment. It retains
the block descriptor and verifies `LOOP_GET_STATUS64` against the fresh image's
device/inode before execution and before clearing that attachment. The actual
probe runs under a private mount namespace with anchored process-group cleanup.
The guest has one fixed modern virtio block device and the original Q35, TCG,
one-CPU, 512 MiB profile. Its ordinary product ELF comes from the unchanged
build-and-QueryAbi gate.

The negative builder creates an owned detached worktree, applies only the
frozen `InodeMode::all()` patch, and records a local diagnostic commit whose
sole parent is the reviewed positive head. Full source inventories must differ
at exactly the ExFAT inode path; the probe, tests, formatter input, build pins
and evidence oracle remain identical. It invokes the same original ordinary
build-and-QueryAbi entry point before the negative disk boot. Only the five
specified observations qualify: old modes on all three inode types, changed
normal-exec IDs, and unchanged `no_new_privs` IDs. All capability sets remain
zero in both exec cases, including the negative. No privileged command or
external effect is performed by the executed observation program.

The A06 artifact retains `a06-exfat-checks`, `a06-exfat-bundle`,
`a06-exfat-linux`, `a06-exfat-guest` and `a06-exfat-negative`, including complete
raw logs, image pre/post hashes, the frozen ELF/image, both kernel ELFs,
source snapshots, patch bytes and process exits. A successful helper test,
Linux reference or build alone does not close the disk qualification.

All Rust/C builds, kernel tests and guest execution occur in the project's
authorized GitHub Actions environment. Local work for this candidate is
source editing, static review and Python evidence-oracle checks only.
