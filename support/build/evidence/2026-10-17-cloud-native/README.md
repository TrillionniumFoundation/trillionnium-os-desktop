# Terminated cloud native build and failed boot evidence

This phase preserves a real source `make kernel` success, followed by a failed QEMU boot and a later preflight rejection. **It contains no successful project kernel boot.** Packaging only read the terminated `current-cloud` directory and its two controllers. It did not run new builds, host suites, controllers or VMs, and excluded active `normalized-cloud` and target directories.

| Recorded step | Actual source | Result |
| --- | --- | --- |
| Source verification | Local producer `0053c98e787391ef566305296ffd2b7c912a1095` | Exit 0, 118 files checked, intentional derived tree (`pristine=false`) |
| `support/build/kernel.sh kernel` → upstream `make kernel` | Producer `0053c98e787391ef566305296ffd2b7c912a1095` | Exit 0; 279 `Compiling` lines |
| `support/build/kernel.sh run_kernel` → upstream `make run_kernel` | Same producer; cached build, 0 `Compiling` lines | QEMU timeout status 124; recorder 124; make/worker/controller 2; SeaBIOS `No bootable device.` |
| Retry with explicit private QEMU data | Published `31543f71a247add15ce8e026a25385c535746bca` | Exit 1: existing `kernel/OSDK.toml` rejected before make or QEMU; raw QEMU status, serial and timeout are null |

The actual compile producer is local `0053c98e787391ef566305296ffd2b7c912a1095`. Its complete Git tree is `8c1902eb85f94a9285a0b34689c8c696fd716c17`, exactly equal to published `a8f1ed1252a7eaccf74b9a717f862413b7c6650d`. Later published `31543f71a247add15ce8e026a25385c535746bca` has complete tree `8913083575cd63c00cdcfa14f6d747187b878777`. All three have the same `kernel/asterinas` tree `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. Checking out 31543f71 after the build does not make this a fresh compile of that commit. Exact commit objects and selected Git blob inputs are in `source-binding.json` and `source/`.

The fixed upstream is Asterinas v0.19.0, commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, upstream tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`; nightly is `nightly-2026-07-21`. The cloud host was `343e40cfefc1`, Ubuntu 24.04.3, Rust 1.99.0-nightly (87e5904f5), Cargo 1.99.0-nightly (3efb1f477), QEMU 8.2.2, GCC 13.3.0 and Make 4.3. `/dev/kvm` was absent; the actual QEMU used q35, TCG, CPU max, 1 vCPU, 512M, fixed serial and debug-exit device. Full version output and selected environment are retained. The controller did not set Cargo offline mode, and `ASTER_BUILD_TIMESTAMP` was unset.

The first QEMU selected a private BIOS through `A01_QEMU_BIOS` but had no explicit `-L` data directory. The log reports missing `kvmvapic.bin` and `multiboot_dma.bin`. The entire 217-byte serial contains SeaBIOS and `No bootable device.`; this is failed firmware boot, not project kernel acceptance. `boot/qemu.json` literally records `raw_exit_code=124`, `timed_out=true`, duration 300.005 seconds and `recorder_exit_code=124`. A separate underlying wait signal/status was not retained and is not reconstructed. The later data-directory retry never started a new VM.

Build cleanup recorded `owned_removed`. Boot cleanup recorded `foreign_restored`, with a different anchored versus captured inode. Both original cleanup receipts are retained. The unexpected manifest's retained metadata and exact 1,019 bytes are preserved; SHA256 is `1ff39174c39411f8b9a7fd328f762268e62d88521b43ebbde384d03d7d9a9f9f`. Its writer is unknown. Packaging neither reopened nor removed its original public path. Helper `passed=true` reports its cleanup outcome and does not mean that public path was absent.

## Recorded commands and preservation

`readable/current-cloud/commands.json` contains the four completed baseline subprocess commands, selected environment, cwd, UTC timestamps, exit codes and full log hashes. `retry-commands.json` contains the five completed retry commands and explicit overrides. The controllers are retained under `readable/controllers/`. They stopped at their first failing command; their later planned checks were not executed. The exact generated upstream make commands are in `build/command.sh` and `boot/command.sh`; exact requested and executed QEMU argument arrays and shell command are in `boot/qemu.json`. Nothing in this phase is an instruction to execute those historical paths.

The source build ran from 00:21:45.054059 to 00:27:41.829698 UTC on 2026-10-17. The failed boot command ran from 00:27:41.830533 to 00:32:43.561638 UTC. The retry failed at 00:33:29.167316 UTC. Capture timestamps and stable read stat receipts are in `capture.json`.

| Preserved item | Storage |
| --- | --- |
| All 40 original `current-cloud` files plus two controller files | 37 text/metadata/controller regular members in `raw.tar.gz`, matching `readable/`; five binary logical paths in `artifacts/manifest.json` |
| Original directory inventory, including empty `boot-data-retry` | `capture.json` |
| Actual loaded ELF, initramfs and BIOS snapshots | Three deduplicated exact-byte gzip containers under `artifacts/`, with original path mappings |
| 20 producer and three retry source controls, including lockfiles, toolchain and MPL license | `source/controls.tar.gz`, 23 regular members; `source/members.json` contains byte SHA256 and exact Git blob identity |
| Interpretations, nullable statuses and limits | `report.json` |
| File hashes and executable verification logic | `SHA256SUMS`, `verify.py` |

| Actual boot input | Exact original bytes | SHA256 |
| --- | ---: | --- |
| Kernel ELF | 8,287,984 | `acb9d5528282dbd8880372e47365b5c5d61d431cad0cdb0d2599aead39426e11` |
| Minimal initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| BIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

The 2,570,543-byte kernel gzip is split into 2,097,152 and 473,391-byte chunks. Every stored binary gzip/chunk is at most 2 MiB. The initramfs container wraps the exact original already-gzipped `.cpio.gz`; one decompression of the storage wrapper restores that original input. The ELF hash was captured by the actual failed boot recorder after its cached build; a separate earlier build-stage ELF hash is not invented. A second clean build, immutable environment or reproducibility claim is outside this phase.

## Verify or reconstruct

From the repository root, these commands only read and verify the package:

```sh
python3 -I support/build/evidence/2026-10-17-cloud-native/verify.py
python3 -I -O support/build/evidence/2026-10-17-cloud-native/verify.py
```

The verifier checks complete SHA256 coverage, gzip/tar members and modes, all readable copies, binary chunk reassembly, original input bytes, capture inventory, source Git commit/blob hashes, command-to-log bindings and recorded failure semantics. It never invokes Cargo, make, QEMU or a captured controller.

To reconstruct all 40 original evidence files plus both controllers into an explicitly selected fresh directory outside this phase:

```sh
python3 -I support/build/evidence/2026-10-17-cloud-native/verify.py --restore /absolute/new-directory
```

That optional command only reconstructs files; it does not execute them or install dependencies. Reconstruction creates fresh files, not the historical inodes, timestamps or permissions; those original metadata remain in the receipts. No restore was needed to package this phase. A later isolated build/boot experiment belongs to a separate evidence phase.
