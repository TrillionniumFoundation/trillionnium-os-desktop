# Case A before the OSDK action-flags fix

This phase freezes the terminated real cold-build/boot case A at producer `542e09ebf0471124a01e3d721b531a29e141e54b`. Compilation completed and real QEMU entered Rust OSTD, then component initialization panicked. **Project kernel boot acceptance failed.** No later support fix, A2/B2 run or result is included.

| Recorded fact | Evidence |
| --- | --- |
| Complete producer tree | `8e7a594456108c9a9e796bdee2d22a26f9ebfbda` |
| Derived `kernel/asterinas` tree | `6b3cab110aa6d30d5b89f99c4389c9c3e01022da` |
| Fixed upstream | Asterinas v0.19.0, commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`; nightly `nightly-2026-07-21` |
| Real checkout | `/tmp/trillionnium-a01-normalized-A` |
| Cold target precondition | Captured policy records `target_absent_at_prelaunch=true`; exact v1 runner's source absence guard is preserved |
| Real Rust compilation | 279 `Compiling` lines and two completed release stages, then actual QEMU launch |
| QEMU result | Raw exit 65, recorder 65, `timed_out=false`, duration 0.467 seconds |
| Combined `make run_kernel`, runner and controller | Exit 2 |
| Profile/source/code custody | All three captured result booleans true |

The controller completed only worktree creation, source verification and the failing clean-build-and-boot action. Its live boot recheck and subsequent planned checks did not execute. The exact v1 controller SHA256 is `726dab78bb9d9ff2ac83f3c9a0d8c495d4c7dfe3bf7c36774fe360dc0b433559`. Its subprocess commands, selected parent environment, UTC timestamps, statuses and log bindings are in the raw archive, with a readable copy of `commands.json`. The build-and-boot action ran from 00:37:42.256656 to 00:43:14.905663 UTC on 2026-10-17. Root supplied outer execution session 57795/exit 2; this attribution is explicitly separate from the raw subprocess records.

The generated upstream make command is in `readable/command.sh`. This experiment used `run_kernel`, whose cold build logged both completed compilation stages before QEMU. The combined action returned 2 after the guest panic. There is no separate successful `make kernel` command receipt to invent for this phase.

## Failure and path mismatch

The full 4,627-byte serial is `readable/serial.log`, SHA256 `cbbfa86e2e44c0f0c2073d10fbdc8f56c4886436343cf11e4decfee027e62a05`. It includes firmware handoff, OSTD frame/interrupt initialization, `OSTD initialized. Preparing components.`, then:

```text
NotIncludeAllComponent("/tmp/trillionnium-a01-normalized-A/kernel/asterinas/kernel/core/comps/virtio")
at /tmp/trillionnium-a01-normalized-A/kernel/asterinas/kernel/core/src/init.rs:26
```

`analysis/path-mismatch.json` binds the diagnosis to all 369 original rustc records and all six original/mapped Cargo metadata pairs. Actual calls for `aster_core`, `ostd`, `component_macro` and `aster_virtio` each lack `--remap-path-prefix`; their manifest directories are real `/tmp/...` paths. The metadata wrapper, meanwhile, mapped component IDs and manifest paths to the private virtual root. Every full metadata payload, binding receipt and stderr is retained.

The captured environment shows outer `RUSTFLAGS=--remap-path-prefix=<real>=<virtual>`. Exact producer `support/build/repro/run.py` set that outer variable. Exact producer OSDK `commands/build/mod.rs` constructed its action build flags and replaced the child `RUSTFLAGS` at line 269. These source controls and actual argv support the inference that the outer-only remap did not reach the kernel action, leaving virtual metadata identities inconsistent with real runtime component paths. This phase records that failure; it does not test the subsequent fix.

The run used private QEMU BIOS and data selection, q35/TCG/CPU max, 1 vCPU, 512M and fixed serial/debug-exit devices. The complete requested and executed argument arrays, real QEMU version/hash, input provenance, statuses and duration remain in `readable/qemu.json`. Host was `343e40cfefc1`; full compiler/tool versions are in `readable/environment.log`. The v1 profile requested a fixed build timestamp/epoch and embedded builder metadata. No offline build, immutable host or independent-host reproduction is claimed.

## Complete preserved inputs

The package includes every file in terminated `normalized-cloud/A` (44), `controller-A` (4), the frozen v1 controller (1) and the v1 `full-kernel-profile` (6): 55 original files. It does not read or package targets, later profile v2, A2/B2 or their controllers. Original stable read stats are in `capture.json`; the full original profile owner, lock, Components and helper bytes are recoverable from the raw archive. The policy contains its original profile snapshot. Profile helper/Components hashes match the exact producer source and recorded owner/policy hashes.

| Content | Storage |
| --- | --- |
| All 51 nonbinary original files, including all metadata and complete rustc argv log | Deterministic `raw.tar.gz`; per-member bytes, mode and hashes in `raw.manifest.json` |
| Three exact binary inputs, represented at four original paths | `artifacts/manifest.json` and gzip containers/chunks |
| 86 exact producer build/repro/OSDK/component source controls, lockfiles and MPL license | `source/controls.tar.gz`, `source/members.json` |
| Offline Git commit → tree → path → blob bindings | `source-binding.json`, 30 original tree objects in `source/tree-objects.json` |
| Full significant serial, build logs, command, environment, QEMU/policy/result/cleanup JSON | `readable/`, bound to original paths in its manifest |
| Precise status, scope, custody and diagnosis | `report.json`, `analysis/path-mismatch.json` |

| Actual QEMU input | Original bytes | SHA256 |
| --- | ---: | --- |
| Kernel ELF | 8,257,464 | `dff0561c820dc0c84db66402996ecb320e49da85ec44cf4da5268825ecb65a2e` |
| Minimal initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| BIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

The 2,561,583-byte ELF gzip is split into 2,097,152 and 464,431-byte chunks. Every stored archive/binary chunk is at most 2 MiB. Initramfs storage wraps its exact original already-gzipped input; decompressing the storage wrapper once restores the original `.cpio.gz`. No original profile, target, source or manifest was modified or cleaned during packaging. The complete Git repository and host dependency installation are not duplicated in this phase; the exact producer commit and selected controls are bound explicitly.

## Offline verification and reconstruction

From the repository root:

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-before/verify.py
python3 -I -O support/build/evidence/2026-10-17-repro-kernel-before/verify.py
```

The verifier checks checksum coverage, safe regular tar members and recorded modes, gzip/chunk/input reconstruction, the complete original inventory, readable copies, Git commit/tree/path/blob membership, private profile bindings, command log hashes, the actual argv/metadata mismatch and failed guest status. It does not invoke Git, Cargo, make, QEMU, tests or captured controllers.

To reconstruct all original evidence/profile files plus the 86 selected source controls into an explicitly selected fresh directory outside this phase:

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-before/verify.py --restore /absolute/new-directory
```

Reconstruction only writes verified bytes. It creates fresh files with normal creation permissions, not historical inodes, timestamps or profile ownership; their original metadata remain in the receipts. It never executes reconstructed scripts or starts a guest.
