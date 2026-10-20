# Clean full Rust kernel build, live Rust-entry debug and boot

The clean worktree performed a real **offline source build of OSDK and the complete derived Asterinas kernel**, followed by live GDB attachment at the Rust entry and successful minimal userspace boot. The parent observed actual outer tool session **88997 exit 0**. GDB exited **0** after detaching; QEMU later exited with raw **33**, without timeout. This is the full kernel, not an OSTD example or a host Linux boot.

The launch record identifies detached runtime **`873cad772d17230ae77dee3973252c97d517dea0`**, clean status and absent target/temporary manifest at the start. Its complete tree **`af84f6dfedc3db7d8a9dc4498ea1e1681ea6940c`** equals published source **`9b381118fe8a1889d4523b4de999bbe45f1b0436`**. The launch environment explicitly sets `CARGO_NET_OFFLINE=true` and the new worktree's independent `CARGO_TARGET_DIR`. No target cache was copied into it. The worktree shares the repository's Git object store.

`logs.tar.gz` retains complete SDK/kernel compiler output, console, actual commands, tool versions, source guards, GDB/nm output and serial bytes. In `boot/gdb_server.log`, lines 10/116 show `Installing`/`Compiling cargo-osdk v0.19.0`; line 117 completes its release build in 1m17s; line 119 replaces the installed SDK with the newly built worktree source. Lines 342/347 show compilation of `asterinas` and completion of the kernel's release-with-debug-info build in 2m42s. The actual make command and minimal overlay are recorded. This execution establishes that the cached dependencies were sufficient for this native offline route; it does not complete every other platform in the OSDK lock.

Actual launch:

```sh
python3 -I support/build/debug/run.py \
  --output support/build/out/next6-clean-debug-01 \
  --ready-timeout 1800 --boot-timeout 120
```

## Runtime Rust entry and retained artifacts

| Evidence | Actual value |
| --- | --- |
| Rust symbol / live PC | `__ostd_main` / `0xffffffff88422840` |
| Live byte comparison | 32 bytes equal the symbol record and retained boot ELF |
| GDB / QEMU status | 0, detached / raw 33 |
| Boot ELF | 5,975,720 bytes; SHA256 `89c7f0bab00172e4a8d038a3d5c38396d952ff44e4ab159bbe8765edbaa16313` |
| Symbol ELF | 111,709,176 bytes; SHA256 `855e92c82ac3745d40320fd4451e8862e38e2fbfbf7b2c6e98f60d514018d6a8` |
| Small initramfs | 1,107,990 bytes; SHA256 `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| Complete serial | 72,299 bytes; SHA256 `bbcb07e958137c8fd41674b8b7834266c1fd50bcc7f3e6e146d7b84ef0410e02` |

The debugger uses the original ELF64 x86_64 symbol artifact. The boot wrapper uses the upstream QEMU-compatible ELF machine field; it is separately identified by its own digest. An independent PT_LOAD calculation maps Rust entry address `0xffffffff88422840` to retained boot-file offset **4,077,632**. Its 32 bytes match the actual GDB read and both artifact records. The actual GDB log shows the Rust `asterinas::__ostd_main` frame, `ostd::boot::start_kernel`, hardware breakpoint and detach.

The owned loopback GDB listener is inherited through QEMU spawn as FD 64 without a bind/close/rebind gap. Actual QEMU arguments select x86_64 q35, TCG, CPU `max`, one vCPU, 512 MiB, explicit SeaBIOS, direct multiboot and the retained small initramfs. Serial contains OSTD initialization, our init start, single-CPU check, the fixed upstream `Successfully booted.` marker and `TRILLIONNIUM_A01_BOOT_OK`; fatal-panic checks passed.

`artifacts/kernel.elf.gz` retains the exact boot ELF, with original/compressed digests in `artifacts.json`. It was secured and decompression-checked before the parent changed the target/source. The original symbol ELF was also hashed at that point, but its >100 MB raw bytes are deliberately excluded. Rebuild uses the recorded published source, pinned toolchain/locks, inputs and actual commands; a rebuilt digest must be measured rather than assumed. The new boot/symbol digests differ from earlier archived artifacts. Their difference has no established cause here, and this report makes no path-causality or bit-for-bit reproducibility claim.

The initramfs retains its original compressed bytes. All **25** CPIO entries were parsed and matched against its manifest, including modes, sizes and content digests. Its actual init and fixed upstream smoke-test bytes were checked against the runtime Git blobs. BusyBox/SeaBIOS/vDSO attribution and fixed tool checks are retained by the adjacent environment archive and runtime manifests.

## Source and serial integrity

`source-bindings.json` verifies **80** recorded comparisons covering **68 unique source paths** against `git show 9b381118:PATH`, including all runtime environment hashes, launch hashes, upstream guard inputs and retained initramfs scripts. Historical runtime metadata is unchanged. The newer live worktree was not used to replace these source bytes.

Before the later public boot reused `kernel/qemu.log`, its original bytes were compared with the completed run's `boot/serial.log` and QEMU expected size/SHA, then snapshotted. The original snapshot, completed copy, reopened tar and QEMU record agree. This archive never reads a subsequent run's reused serial path. Logs were finalized atomically and all **30** members reopened and checked against `members.json`; readable JSON/script copies are byte-identical to their tar members.

## Explicit post-run limitation

After the successful debug/boot result, the generated `kernel/OSDK.toml` pathname still existed. `post-debug-manifest.json` preserves its actual inode, bytes digest and dirty-status observation. Archival did not delete it, overwrite it or relax the existing-manifest guard. This is an observed cleanup limitation of this runtime source; later supervisor/manifest handling and public-boot results are separate evidence. The owned debug-session cleanup records are retained rather than used to erase this distinction.

This directory contains evidence only. No source changes, new compilation or guest execution occurred during archival. The earlier `environment/` archive is unchanged. `SHA256SUMS` covers every final file except itself.
