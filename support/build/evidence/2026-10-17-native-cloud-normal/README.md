# Ordinary cold make kernel followed by make run_kernel: passed

This phase preserves the actual completed N1 ordinary build/boot pipeline at producer `d879a9d2ffae8d0eb0df441370da54f9e3a38431`, full tree `a2baa0d707b8af80ae0e7d9f09b6e08379667bc2`, derived kernel tree `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. The first target directory was absent. `make kernel` compiled the pinned Rust kernel successfully; its resulting ELF was copied through a checked open file descriptor before the separate `make run_kernel` action reused that same target and booted the real kernel in QEMU. Full bytes of the first produced and actual booted ELF are equal.

**The first kernel build is cold; the subsequent boot action uses its warm target.** This ordinary run does not invoke the opt-in reproducibility launcher or projection wrappers. It is one build/boot pipeline, with no cross-path, cross-host, immutable-environment or entire-project closure claim.

| Actual stage | Evidence |
| --- | --- |
| Target before first build | Explicit absent check, exit 0, `/tmp/trillionnium-a01-final-normal/kernel/asterinas/target` |
| Cold `make kernel` | Exit 0; 279 `Compiling` lines; two completed release stages |
| First produced ELF freeze | Dedicated open-FD stable-copy check, exit 0; exact bytes retained |
| Subsequent `make run_kernel` | Exit 0; same target; zero `Compiling` lines and release completed in 0.39s |
| Actual guest | Rust OSTD/component/kernel initialization then small initramfs, one CPU; raw QEMU 33, recorder 33, complete stage, no timeout |
| Fresh postrun live check | Exit 0; original complete log retained |
| Source pre/post | Identical 118-file passing checks; empty postrun Git status |
| Manifest cleanup | Both build and boot independently returned `owned_removed`, passed true |
| Controller | All eleven original subprocess commands exit 0; outer native session 15521 exit 0 |

The complete original pipeline ran from `2026-10-17T01:56:23.690756+00:00` to `2026-10-17T02:03:03.676153+00:00`. All exact commands, cwd, selected environment, UTC start/end, exit codes and full log hashes remain in `readable/controller-N1/commands.json` and the raw archive. The actual source entry commands were:

```sh
bash support/build/kernel.sh kernel
bash support/build/kernel.sh run_kernel
```

Those invoke the upstream developer targets with the project small-initramfs overlay. Both actual expanded make command lines are preserved in `readable/kernel-build/command.sh` and `readable/kernel-boot/command.sh`. They select x86_64, q35/TCG, CPU max, 1 vCPU, 512M, fixed serial/debug-exit devices, Multiboot and no full NixOS installer ISO dependency.

## Ordinary environment and source identity

Fixed upstream remains Asterinas v0.19.0 commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, upstream tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`, full-kernel derivation. The actual rustc is nightly `nightly-2026-07-21`, commit `87e5904f5eb6398af6b22eac2802c78934260c48`; Cargo, native dependencies and QEMU versions are in both complete environment logs.

The actual controller script is preserved, SHA256 `3c4e1f2d6e70ec4211cebc80e456b0048aad16a7893db09a7a10c992ada5254b`. Its copied docstring still says “normalized”; that text is historical wording and is not a profile record. Its executable operations call the ordinary `kernel.sh` targets directly and explicitly remove known Rust wrapper, projection-policy, timestamp/builder and inherited make-control variables before launching. Both child environment logs explicitly show `RUSTFLAGS=<unset>`, `CARGO_ENCODED_RUSTFLAGS=<unset>`, `ASTER_BUILD_TIMESTAMP=<unset>` and `CARGO_BUILD_JOBS=2`. This phase does not invent a per-rustc compiler argv ledger for the ordinary run. Full actual environment and controller bytes establish the stated route.

QEMU `QEMU emulator version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)` ran for 1.271 seconds. Its actual executable SHA256 is `8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854`. The full 72,247-byte serial, SHA256 `3840526255cff7c53567f3e35e42739a11dba24f3feb03594719e92bec0ab5ca`, is `readable/kernel-boot/serial.log`. It contains OSTD initialization, `TRILLIONNIUM_A01_INIT_BEGIN`, `TRILLIONNIUM_A01_CPU_COUNT=1`, `Successfully booted.` and `TRILLIONNIUM_A01_BOOT_OK`. Complete requested and executed QEMU argv, BIOS/private-data selection, source/snapshot stats and exact input paths remain in `readable/kernel-boot/qemu.json`.

## Exact retained inputs

| Actual input | Original bytes | SHA256 |
| --- | ---: | --- |
| First cold-produced and subsequently booted kernel ELF | 8258112 | `c49ad7da1c76c1f559d065ac3f8cbcbad407242dda54f1ed00028f02d5c2413d` |
| Initramfs | 1107990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| BIOS | 262144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

The first-build ELF and boot ELF are deduplicated only after complete byte equality. Three binary payloads cover six original logical paths, including all three initramfs copies. Compression is a deterministic outer gzip wrapper; decompression restores the exact ELF, original `.cpio.gz` or BIOS. Stored chunks never exceed 2 MiB. The fixed OSDK ELF64 `EM_386` Multiboot compatibility marker remains intact.

All 41 original files are retained: 35 deterministic nonbinary tar members plus the six logical binary paths. Original build/boot logs, two cleanup receipts, initramfs manifests, source checks, actual controller script and all eleven command logs remain complete. Selected source controls include 80 exact producer Git blobs and 29 Git Merkle tree objects, including fixed source/OSDK locks, ordinary build controls and MPL license. Unused opt-in reproducibility helpers are excluded from this ordinary source-control snapshot. Read-only Git queries used to construct that snapshot are independently recorded in `source/commands.json` and do not replace the original build receipts.

Packaging did not reread original targets/worktrees, rebuild, start a VM, rerun a live check, alter the source/profile or remove original artifacts. All reads came from root-confirmed terminated N1 outputs, its controller and immutable Git producer objects. Complete repository and host dependencies are not duplicated.

## Offline checks and reconstruction

```sh
python3 -I support/build/evidence/2026-10-17-native-cloud-normal/verify.py
python3 -I -O support/build/evidence/2026-10-17-native-cloud-normal/verify.py
```

The standalone verifier checks full inventory/SHA coverage, safe archive paths/modes, exact reconstructable inputs, selected Git source commit/tree/blob membership, all eleven commands/logs and cold-target receipt, actual ordinary environment and make targets, both cleanups, first-built versus booted complete ELF bytes, fixed QEMU profile, serial acceptance and scope limits. It needs no Git/network, original source/target paths, build tools or VM and never executes captured commands.

```sh
python3 -I support/build/evidence/2026-10-17-native-cloud-normal/verify.py --restore /absolute/new-directory
```

Optional restore creates verified fresh evidence/source files only. It does not execute them or recreate historic inode identities, original permissions or target outputs.
