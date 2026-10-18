# Loaded main355 boot artifacts

These are the actual private input snapshots loaded by QEMU at producer `40c901c6e189058bdd6f42bb43bf46b3bbcf8ffa`. The complete ELF is 8,303,048 bytes with SHA256 `1eb66b33baef6b338c232598d25f743dc83526a2715811b430e5a7208e249ecd`; its bytes equal the separately frozen incremental-build ELF.

`kernel.elf.gz` and `bios.bin.gz` use lossless gzip for storage; `initramfs.cpio.gz` preserves the already-compressed loaded input. Raw/stored hashes and paths are in `../archive-source-map.json`, and exact QEMU argv is in `../run_kernel/qemu.json`.

Complete corresponding Asterinas source and notices are retained in `kernel/asterinas/` at that producer. The unchanged BusyBox and SeaBIOS package metadata and license/source notices remain in [the installation archive](../../2026-10-18-current-main/runtime.tar.gz). No ISO or host Linux kernel is an input.
