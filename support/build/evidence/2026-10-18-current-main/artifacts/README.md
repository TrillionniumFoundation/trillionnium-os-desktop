# Actual boot inputs

These bytes are the private snapshots QEMU loaded during the `c22891b` full-kernel boot on 2026-10-18. `kernel.elf.gz` and `bios.bin.gz` are lossless gzip storage of the loaded files; `initramfs.cpio.gz` is already the exact compressed input. `kernel-build.sha256` is the original receipt for the separately frozen first build ELF, whose bytes equal the loaded ELF.

See `../archive-source-map.json` for original paths, raw sizes/hashes and stored sizes/hashes. The exact QEMU receipt remains `../run_kernel/qemu.json`. Replaying these files is not a source-build test; use `support/build/kernel.sh kernel` and `run_kernel` to validate a new source build.

The corresponding complete Asterinas source is `kernel/asterinas/` at project commit `c22891b593f77c98ff4ea94d7aecb54f32222651`; its upstream MPL-2.0 license, file notices and documentation are retained. The initramfs contains static BusyBox from Ubuntu `busybox-static 1:1.36.1-6ubuntu3.1`, the project's `support/build/minimal/init`, and upstream `test/initramfs/src/boot_hello.sh`. SeaBIOS is Ubuntu package `seabios 1.16.3-2`. Exact package metadata, archive checksums and the packages' copyright/license/source notices are retained in `../runtime.tar.gz`, including the GPL/LGPL license texts. The initramfs manifest lists the complete contents.
