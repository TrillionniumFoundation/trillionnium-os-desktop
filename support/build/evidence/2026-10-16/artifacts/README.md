# Actual accepted boot artifacts

`kernel.elf.gz` contains the exact QEMU-loaded Rust kernel ELF, compressed only
for storage. Its **uncompressed** SHA256 is
`e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63`.
`initramfs.cpio.gz` is the exact accepted initramfs, SHA256
`86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`.

From the repository root, on the recorded native QEMU host:

```sh
gzip -dc support/build/evidence/2026-10-16/artifacts/kernel.elf.gz > /tmp/a01-kernel.elf
qemu-system-x86_64 \
  -kernel /tmp/a01-kernel.elf \
  -initrd support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  -append 'earlycon console=ttyS0 loglevel=info --' \
  -machine q35 -accel tcg -cpu max -bios /usr/share/seabios/bios-256k.bin \
  -m 512M -smp 1 -nodefaults -no-user-config -no-reboot -nographic \
  -display none -monitor none -serial stdio \
  -device isa-debug-exit,iobase=0xf4,iosize=0x04
```

Success is raw exit **33**, plus the guest CPU/smoke/project markers. The
precise original invocation, including serial logfile settings and all
original absolute paths, is in `../acceptance/boot/qemu.json`.

Kernel source and MPL-2.0 license: `kernel/asterinas/` and its `LICENSE-MPL`.
The generated initramfs contains Ubuntu's static BusyBox 1.36.1
(`1:1.36.1-6ubuntu3.1`); its GPL-2.0 copyright/source notice is preserved as
`busybox-copyright.txt`, with the complete license in `GPL-2.txt`.
Exact package/source information and archive hashes are in the adjacent
`../host/` records. `../acceptance/boot/initramfs-manifest.json`
enumerates every included file, symlink, mode and hash. The Linux vDSO build
dependency and its upstream attribution are recorded in the build README.
