# Actual public kernel boot after custody fix

Published source a770f31a868d805524065c65a2bcfcbcf10ede2e, exact tree
af2e1bc4d215ac4dc6eadd0cecc147e1673b1c1e. The real public
`support/build/kernel.sh run_kernel` exited 0 and QEMU exited raw33 with
complete serial and initramfs markers. Both the live wrapper check and the
offline archive check passed. Existing Cargo target reuse is explicit; this
is not a second empty-target full compilation. The separate full kernel-mode
test run in this phase built and ran both test kernels.

The standalone supervisor reaped its worker. The new cleanup helper captured
and removed the exact FD8-owned inode, removed its private custody directory,
and returned 0. `post-boot-manifest-observation.json` records any later public
entry separately. A new entry appearing after completed cleanup does not
identify its writer or change the captured inode result; this archive never
deletes that later entry. The wrapper still refuses to overwrite existing
manifests on a later call.

Actual commands, selected environment, source verification, serial, QEMU argv,
kernel/initramfs and cleanup helper hash remain byte-bound in the adjacent
records. The retained ELF matches this QEMU record; no bit reproducibility
claim is made from reusing the same target cache. No host Linux kernel or ISO
installer is used as boot acceptance.

The initial post-boot observer reported stable_fd_read=false using whole stat_result comparison. Its record is unchanged. The separate follow-up preserves before/after content identity fields, both equal, and its independent snapshot; see post-boot-followup.json. No cause for the initial metadata change or external writer is inferred.
