# Owner15 retired metadata reboot-reason read

Review-only exact request. Root alone may dispatch it once. No Hepta call has been made by the author.

The original Owner15 runtime remains failed before ACTIVE. This reader binds its actual prepared and failed runtime receipts, original state/image identity, and the previously observed debugfs executable. It uses only read-only held FDs and at most seven bounded debugfs children: three fixed stats before, one optional reason-body read, and three fixed stats after. It reads no unrelated image paths.

The metadata UUID was not present in the original mkfs output. The reader records the actual current UUID without inventing a prior UUID or treating it as authority. Image authority is original inode/size/fresh-creation proof plus current label/header/clean ext4 and before/after metadata. There is no mount, write, fsck, recovery, or journal replay.

A complete collection can preserve a missing/unsupported file observation with no body read. This does not prove the file is absent or establish a cause. Even a valid reason body does not establish which process wrote it. Upstream InitFatalReboot can bypass the persistence helper; absence cannot exclude a namespace reboot. Current init ELF source provenance is not expanded by upstream reference material.

All observed data and original failure records are retained. Output remains collection-only; production/runtime/App qualification is false.
