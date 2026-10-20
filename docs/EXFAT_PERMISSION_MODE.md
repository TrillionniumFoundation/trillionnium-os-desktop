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

The original full OSTD/core gate is retained. This candidate starts from merged
G1-c main and retains all nine required image/resource tests and the complete
238-test earlier core baseline. The two new ExFAT cases raise the full minimum
to 249; every required name must occur once and execute without a soft skip.
Integration with the separate inode transaction and G1-d changes must retain
the union of required names and the combined test denominator.

The same candidate includes the already reviewed Linux `pivot_root` reference
correction from permission PR #215: existing, searchable directory arguments
replace null pointers while the original unprivileged EPERM assertion remains.
The project cloud has verified all 32 cases with that exact probe under Linux
and the guest; this candidate still requires its own unchanged full CI.

## Fixed disk guest qualification plan

The mode correction is applied to merged main commit
`0c1de23a3754bc3a6976fed53c7dfa0ec3778e57`, tree
`0337884b57bf67350f27b22eb6af326fa19dcb7d`. The original four G1-c changes
and all original workflows remain present. This preparation does not copy
unmerged permission-transaction interfaces into main. Fresh runs must identify
the final reviewed descendant commit and every source byte before and after
execution. The disk profile below remains pending until implemented and run.

1. Keep the existing no-disk, one-CPU full gate and the original two-CPU
   CPU gate unchanged. Add a separate ExFAT evidence profile.
2. In the authorized disposable project CI environment, compile one static
   observation ELF and inspect its ELF identity. Create a fresh ExFAT image
   using the existing `mkfs.exfat` image path, record the formatter binary,
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
   use UID/GID 65534, clear every capability set and read all credentials
   back before `execve` of the copied file on ExFAT. The executed file reports
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

All Rust/C builds, kernel tests and guest execution occur in the project's
authorized GitHub Actions environment. Local work for this candidate is
source editing, static review and Python evidence-oracle checks only.
