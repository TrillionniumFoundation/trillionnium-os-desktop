# Real full-kernel Rust-entry debugging, 2026-10-16

The fourth real run hit `__ostd_main` at `0xffffffff88426860`, read its live 32 instruction bytes, matched them with both the original Rust symbol ELF and the executed stripped boot ELF, detached, and completed the full Asterinas-derived minimal userspace boot with raw QEMU status 33. The earlier two failures and third successful PC/source run are retained unchanged. No new guest was launched to create or recheck this archive.

| Run | Actual result | Rust entry / bytes | Final QEMU |
| --- | --- | --- | --- |
| 01 | Failed after complete Rust release+DWARF compilation: rust-strip absent | No GDB connection | Not started |
| 02 | Failed before build: existing kernel/OSDK.toml refused | No GDB connection | Not started |
| 03 | Passed: actual entry PC, Rust DWARF source/line and early frames, detach, full boot | PC matched; runtime bytes were not captured | raw33, no timeout |
| 04 | Passed: entry PC plus live 32 bytes bound to both recorded ELFs, detach, full boot | PC and runtime bytes matched | raw33, no timeout |

Run01's log records `Finished release [optimized + debuginfo]` in 2m46s before the strip failure. The later official cargo-binutils 0.4.0 installation is fully retained in `../host-tools/`. Run02 preserved the existing manifest rather than replacing it; its preserved inode/content context is in the raw archive. An earlier observer saw a different inode deleted, but the reappearance's writer and cause are unknown. No cause is invented.

## What the successful GDB sessions establish

Both logs begin at firmware PC 0xfff0, then install a hardware breakpoint and continue to the Rust entry. They show `PC == __ostd_main == 0xffffffff88426860`, Rust src/lib.rs line21, source language rust, DWARF4, RIP and early Asterinas/OSTD/Multiboot frames. This is a real Rust breakpoint, not just a firmware register read. Run04 independently reads 32 bytes through GDB inferior memory and compares them with executable ELF mappings from the original symbol file and actual QEMU boot input before detach. Its original entry-artifact-binding.json and result.json preserve the exact bytes, offsets and hashes. Both GDB and kernel driver exit0; the ordinary live boot checker then accepts the raw33 boot.

The logs also contain unknown tail frames after the early boot chain. This is not a claim of complete reliable unwind, source single-stepping, local-variable inspection, VSCode execution or host ptrace access. The prior ptrace probe was denied; the real debug sessions used the owned loopback QEMU GDB stub. The observer used inotify, and its original metadata records the ptrace boundary.

Run03's independent comparison of all 19 allocated sections and the entry bytes was performed later on host files whose SHA matched its records. `run03-elf-binding-review.posthoc.json` explicitly preserves that scope. It does not retroactively give run03 a live-byte test; run04 provides that new evidence.

## Retention and artifacts

Each runs/NN/raw-logs.tar.gz contains complete original logs, tool versions, commands, environment, statuses, QEMU metadata, GDB script/output and symbol table when produced. The first run also contains the original observer records; later runs include their original parent console. SHA256 and original size are indexed for every member, with deterministic tar/gzip headers. Important JSON, GDB output, script and successful serial logs also have readable byte-identical copies. There are 82 indexed raw members across the four runs. Repeated initramfs binaries are retained once outside the text archives.

`artifacts/kernel.elf.gz` retains the actual stripped boot ELF, original 5,996,200 bytes and SHA256 `fcec53875dec2ca19b20e285df94590e9c21036cdabec54799fbda6bddb84026`. Its legacy multiboot ELF machine field is 3 as produced by OSDK. The original Rust symbol artifact retains ELF64/machine62, size 111,867,352 and SHA256 `a1c7a44cb844553d00c2942760df0f2389919f1e530bfaa45081c7463d31e21a`; that 112MB raw DWARF file is not committed. This hash was recorded by runs03/04; run01 had no symbol-artifact.json and is not assigned the later hash as historical evidence. `rebuild.json` records how to regenerate and re-exercise it, with the DWARF absolute-path limitation stated.

The initramfs is retained unchanged at 1,107,990 bytes, SHA256 `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`. Runs03/04 use identical kernel/initramfs bytes. Their complete serial streams have distinct hashes: run03 `726c942ded93d74e9d7ca13d5545e54cefc1f8c5b4edf117896a284915adf3be`, run04 `487cdcfebe8ec8e05caaf11fb0b23024a3e6961bb01b01aa789c9495719ca3b0`. BIOS and tools are package dependencies recorded by hash/version, not duplicated executable payloads.

Actual QEMU is x86_64 q35/TCG/CPU max, one vCPU, 512MiB, SeaBIOS, serial/debug-exit and a prebound owned loopback listener handed to QEMU as inherited FD64. This test does not establish other architectures, hardware virtualization, network/data disks or a full OSDK regression matrix.

## Source identity and reproducibility

The fixed base remains Asterinas v0.19.0 commit c4b7ed575b7b32773475b194d2ad41fb6d03765b and nightly-2026-07-21. The original environment files preserve the real execution HEADs and dirty state. Run04 recorded HEAD 1cc76b90dfd162e18a946a01e0bcaa31b8e03b4f with dirty/untracked debug support, so that HEAD is not presented as the complete executed source. Its 63 recorded input hashes all match published code commit `40f6c7ae47626df9eb66eb3c4a4c9036bc5c8ccc`, tree `a41f900f4fc9d61a007d673870e74cdf0e037a71`. The nine files introduced by that commit also byte-matched the working files in a separately labeled posthoc check. Later upstream-lock/evidence changes are not claimed to preserve all old execution hashes.

The earlier three runs used the previous debug helper, before runtime-byte verification. A minimal reverse patch under source-recovery restores those three measured helper files from the published commit. Actual git-show/git-apply replay reproduced their recorded SHA values. Production helper or kernel source is not duplicated here. The 49 OSDK production source files matched the corresponding execution HEAD Git objects; the original root/OSDK Cargo locks and helper input hashes are preserved in each environment.

The host-regressions directory preserves the final 7-test helper checks in normal and optimized Python, the 3-test listener checks, the 15-test boot-evidence checks and 10-test shell-runner checks. They are host checks, separately identified from the real kernel/GDB runs.

From this directory, `sha256sum --check SHA256SUMS` checks local files. `python3 -I verify_archive.py` verifies every compressed raw member, readable copy, retained boot input, successful serial/GDB result, run04 runtime byte binding, published Git source hashes and older-source patch reconstruction. It needs the repository's published Git object, not the original scratch paths, raw DWARF ELF or a running VM. The saved archive-recheck.json is an offline evidence check, not another guest run.
