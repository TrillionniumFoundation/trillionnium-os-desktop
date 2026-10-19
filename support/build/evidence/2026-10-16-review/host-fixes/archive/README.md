# Archive helper review — host only

Source commit: `b5030737451cd7b57813fc4e3c39665a6bb66cfc`.
A00 stacked PR #32 was read at exact `5af5ed301bcdb18b4a0c14cfe2ddfa245dc6a963`; its 13 tests passed under both `-I` and `-I -O`. Independent disposable reproductions then demonstrated index overwrite, a hardlink added between lstat/open being accepted, and a changed source-root pathname being traversed. The adopted helper anchors traversal to the opened root, checks stable single-link regular files, and rejects reserved index paths. Final 20 tests passed in both modes at the production paths.

Compatibility re-archived existing native-07 (320 files, 4,419,026 bytes, largest299,844) and capture-v2-02 (353 files, 14,984,220 bytes, largest5,496,220). All673 selected payloads were byte/hash checked, including decompression and generated checksum indexes. This is a read-only validation of old run evidence, not a new kernel/QEMU result. The selected-file caps remain128MiB each and1GiB total. Old native data, generated targets, production source copies, and tool binaries are omitted.

`review-report.json` includes size distributions and exact semantics. Symlinks in non-excluded directories or selected files fail closed; generated excluded directories are pruned. This is a sequential capture, not an atomic whole-tree snapshot. The output parent must be trusted. Commands, requested patches, helper scripts, original reproductions, and raw logs are retained. `raw-logs.members.json` hashes every tar member; `subSHA256SUMS` hashes this package.
