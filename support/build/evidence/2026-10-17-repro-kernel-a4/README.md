# A4 schema4 cold source build and real kernel boot: passed

This phase freezes the actual completed A4 run at producer `4e8c7083575cec69efabe8d2250dfdd040c8dee8`, complete tree `d50cc2fd3fac4e8060ff26c324267b267767bca2`, derived kernel tree `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. Real QEMU entered the derived Asterinas Rust kernel, ran the small initramfs on one CPU, emitted every acceptance marker and powered off with raw exit 33. **Only this single case is accepted here. Cross-path byte equality remains a separate comparison; no cross-host or immutable-environment result is accepted.**

| Recorded result | Actual evidence |
| --- | --- |
| Source checkout | `/tmp/trillionnium-a01-normalized-A4` |
| Cold target precondition | Captured `target_absent_at_prelaunch=true` and exact producer runner guard |
| Compilation | 279 `Compiling` lines; two completed release stages before actual QEMU |
| Eight controller commands | All exit 0: worktree, source, build/boot, live artifacts, post-source, status, installed components, installed targets |
| Source pre/post | Identical successful verification receipts; postrun Git status empty |
| Profile/source/code custody | Three original postrun booleans true; captured profile bytes/identities match prelaunch snapshot |
| Schema4 jobs | Policy 1, actual child 1; caller value `1` retained |
| Actual QEMU | Raw 33, recorder 33, no timeout, complete stage; 1.275 seconds |
| Cleanup | Original `owned_removed`, passed true |

Fixed upstream remains Asterinas v0.19.0, commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, nightly `nightly-2026-07-21`, rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48`. The source `run_kernel` action cold-built and booted with combined make/action 0; no extra standalone `make kernel` subprocess is invented. The action ran from 2026-10-17T01:33:59.297825+00:00 to 2026-10-17T01:44:05.175631+00:00. Exact commands, environment, UTC records and log hashes are retained. Root supplied completed outer native session 48522/exit 0, separately from the original eight raw subprocess receipts. The v4 controller SHA256 is `b79ece02e233b9563a4418310d41fb64c4374740f5bb30c4a6e598fe11158805`.

The full 72,341-byte serial is `readable/serial.log`, SHA256 `82b1a0bd7f8f077b2e67a436057093c237887441f636fb802771c724a33b1a83`. It contains OSTD initialization, `TRILLIONNIUM_A01_INIT_BEGIN`, `TRILLIONNIUM_A01_CPU_COUNT=1`, `Successfully booted.` and `TRILLIONNIUM_A01_BOOT_OK`. Exact requested/executed QEMU argv, actual executable version/hash, loaded snapshot provenance and the successful postrun `check-boot.py --live-artifacts` receipt remain complete. The boot profile uses q35, TCG, CPU max, one CPU, 512M and fixed serial/debug-exit devices.

## Compiler accounting and provenance

There are 369 actual invocation records and 738 ledger rows. Each unique invocation PID has exactly one started/completed record whose unit equals the original compiler record. All 332 recorded Cargo units completed successfully: 271 retain original metadata and 61 calls use canonical local metadata (61 unique descriptors). Every incoming argument is retained except its explicitly recorded canonical metadata replacement and path-map insertion. Artifact filenames and extern execution arguments are preserved.

`compiler_unit=None` query/probe records are separate: exit-status counts are `{"0": 34, "1": 3}`. The three nonzero probe results are not failed Cargo compilation units. Their original statuses remain in the complete ledger. `analysis/compiler-and-custody.json` records the exact counts, descriptor hashes and scope. All original metadata query inputs/outputs, bindings and stderr are in the raw archive.

This is explicit schema4 opt-in behavior: fixed one-job scheduling preserves the strict completed-producer gate; the gate is not relaxed. Producer provenance records successful completion and device/inode/size/mtime, **not immutable content**. Synthetic embedded builder `a01-repro@a01-fixed-profile` and fixed epoch metadata are explicit; actual host `343e40cfefc1`, user `root`, uid 0 remain separately recorded. Full compiler version bytes and their hash are preserved, so the builder label does not masquerade as the actual cloud host.

## Exact preserved inputs

| Loaded input | Original bytes | SHA256 |
| --- | ---: | --- |
| Kernel ELF | 8,286,952 | `8c540288c6af2a1a97121031643c1af4c4db395d7e8b4082d6edc4604449849a` |
| Initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| BIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

All 61 original files are preserved, with 57 nonbinary regular members in the deterministic raw archive. Three binary payloads are deduplicated over four original paths. Every stored archive/binary chunk is at most 2 MiB, and the exact loaded inputs can be reconstructed. The kernel gzip is 2,570,137 bytes split into 2097152, 472985-byte chunks. One storage-wrapper decompression restores each original input; the initramfs remains the original `.cpio.gz`.

`capture.json` preserves stable read stats; `raw.manifest.json`, `artifacts/manifest.json` and `readable/manifest.json` bind complete logs, serial, QEMU/policy/result, source pre/post, actual make command and controller records. Source controls include 86 exact producer Git blobs and 30 Merkle tree objects, lockfiles and MPL license. Complete repository and host dependencies are not duplicated.

Packaging did not read the other active case output or any original worktree/target, acquire/write the shared profile lock, rebuild, start a VM, or clean/delete original inputs. Shared profile input bytes were copied read-only and match this case's prelaunch snapshot. Later comparison and ordinary baseline runs are separate phases.

## Offline checks and reconstruction

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-a4/verify.py
python3 -I -O support/build/evidence/2026-10-17-repro-kernel-a4/verify.py
```

The standalone verifier checks full checksum coverage, safe tar members/modes, gzip chunks and exact inputs, original/readable inventory, Git commit/tree/path/blob membership, profile snapshots, actual one-job selection and fixed nightly, incoming/effective compiler arguments and ledger units, successful Cargo units versus query probes, ELF64/Multiboot compatibility and all real guest markers. It needs no network or Git executable and invokes no build, controller, live artifact check or VM.

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-a4/verify.py --restore /absolute/new-directory
```

Optional reconstruction creates fresh verified evidence/source files and never executes them. Historical identities, permissions and target outputs are not recreated.

`DRAFT.json` is retained as the intermediate capture receipt and included in the final checksum inventory. Its recorded case/source/compiler facts agree with `report.json`; the final report and successful standalone verification carry acceptance.
