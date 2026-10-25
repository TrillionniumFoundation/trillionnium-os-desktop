# Detached memfd metadata and sealing

`RamInode::new_file_detached_in_memfd` has no directory entry. It now uses the
original unnamed-file metadata constructor, which sets link count to zero.
Owner UID/GID, mode, page-cache and sealing owners remain unchanged. The existing
core memfd permission fixture asserts zero links before and after its successful
and rejected attribute operations; all its earlier assertions remain.

The four mandatory native cases exercise real `memfd_create`, `fstat`, `fchmod`,
`F_ADD_SEALS`/`F_GET_SEALS`, `dup`, read/write and truncate: root-owned regular
inode with zero links, mode 0400 plus all four seals, original bytes after the
first descriptor closes, and sealed mutations refused with metadata unchanged.
No loader acceptance rule is relaxed. This does not qualify the Root bootstrap
protocol or persistence across process/OS restart.

Run `python3 -B -m unittest discover -s tests/workloads/linux/memfd_metadata -v`
for checker rejection cases. The native entry is `run_guest.py --kernel ELF
--initramfs ORIGINAL_INITRAMFS --output NEW_DIRECTORY`; bind its exact hashes to
the source-matched ordinary build receipt. It retains 512 MiB/one CPU TCG, no
host disk/network, the original 120-second guest deadline and actual QEMU 33.
Every case, completion, probe exit zero and boot marker are required; partial
markers or a successful poweroff cannot pass. The C probe's 30-second alarm and
explicit disposable-guest marker remain mandatory. A root Linux reference run
uses `--linux-reference` and does not qualify Asterinas.

Native qualification is pending until the combined original kernel suites and
this same-ELF probe pass. The earlier inode link-count-one baseline remains a
failure; it must not be relabeled by changing the loader's zero-link check.
