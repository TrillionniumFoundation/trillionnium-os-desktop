# A2 cold source build and real QEMU boot: passed

This independent phase freezes **A2's actual successful boot** at producer `bdf7a08dcc0980fa85c0ba5abdf365b7d2c42e80`, using the explicit v2 same-host path-projection profile. Real QEMU reached the derived Asterinas Rust kernel, ran the small initramfs on one CPU, emitted all acceptance markers and powered off with raw exit 33. It accepts only this A2 run. **B2, cross-path byte reproduction and cross-host reproduction are not accepted in this phase.** No B2 outputs or targets were read.

| Recorded fact | Actual evidence |
| --- | --- |
| Complete producer tree | `eff51eb940d1f415aedb84555752ecbc97d58faa` |
| Derived `kernel/asterinas` tree | `6b3cab110aa6d30d5b89f99c4389c9c3e01022da` |
| Fixed upstream | Asterinas v0.19.0, `c4b7ed575b7b32773475b194d2ad41fb6d03765b`; nightly `nightly-2026-07-21` |
| Actual source checkout | `/tmp/trillionnium-a01-normalized-A2` |
| Cold target precondition | Captured `target_absent_at_prelaunch=true` and exact runner absence guard |
| Rust compilation | 279 `Compiling` lines; two completed release stages, then real QEMU |
| QEMU | Raw 33, recorder 33, `timed_out=false`, `stage=complete`, duration 1.169 seconds |
| Combined `make run_kernel`, action and controller | Exit 0 |
| Actual live artifact recheck | Exit 0; kernel/initrd/BIOS snapshot bytes and full raw serial checked |
| Source before/after | Both exit 0 and equal; 118 checked files, intentional derived source (`pristine=false`) |
| Worktree status after boot | Empty output, command exit 0 |
| Profile/source/code custody | Three original postrun booleans true; captured shared-profile inputs match A2 prelaunch hashes and identities |

The controller completed eight commands, all with exit 0: worktree creation, source verification, cold build/boot, live artifact recheck, post-source verification, worktree status, installed components and installed targets. Complete arguments, cwd, selected parent environment, UTC timestamps, log byte sizes and hashes are preserved. The v2 controller SHA256 is `fe9b1180aaa1316075701553f82b5b129c1f541bf3a0f4513ae1ff2e234043e8`. Delegating root supplied outer session 21161/exit 0; the raw subprocess and profile receipts are retained separately.

The cold build/boot action ran from 00:50:30.452352 to 00:56:16.765257 UTC on 2026-10-17. Its generated upstream make command is `readable/command.sh`; this real `run_kernel` action built source then booted, with combined make/action 0. No separate `make kernel` subprocess is invented.

## Actual boot and compiler proof

The complete 72,341-byte serial is `readable/serial.log`, SHA256 `e0845a2d34a0f3d16d7a753c50c94f30b1d3eacc1d7b1649811cfdc4f574cccd`. It includes:

```text
OSTD initialized. Preparing components.
TRILLIONNIUM_A01_INIT_BEGIN
TRILLIONNIUM_A01_CPU_COUNT=1
Successfully booted.
TRILLIONNIUM_A01_BOOT_OK
```

`readable/qemu.json` retains complete requested/executed argv, private BIOS/data selection, real QEMU version and executable SHA256, loaded snapshot hashes/stats, raw status and duration. The actual profile is q35, TCG, CPU max, 1 vCPU, 512M, fixed serial and debug-exit devices. The actual postrun `check-boot.py --live-artifacts` command and success log are preserved; packaging verifies archived bytes offline and does not rerun that live check.

All 369 rustc calls retain both incoming and effective argv. Each effective argv preserves every incoming argument in order and has the canonical map before any `--` delimiter. The map was already present in 130 calls and inserted in 239. The four key calls (`aster_core`, `ostd`, `component_macro`, `aster_virtio`) receive the canonical remap even though their OSDK/Cargo incoming argv lack it. All six complete original/mapped metadata pairs, binding receipts, component membership and stderr are preserved. `analysis/compiler-and-custody.json` binds every row and includes full selected calls. The offline verifier checks full metadata projection, not only selected path examples.

This is an explicit opt-in profile, schema `a01-component-path-projection/2`. It deliberately embeds synthetic builder `a01-repro@a01-fixed-profile`, fixed timestamp `Thu Jan  1 00:00:00 UTC 1970`, epoch 0, C locale and UTC. That synthetic identity is visible in the guest's Linux ABI `/proc/version` string and is preserved alongside the **actual host** `343e40cfefc1`, user root, uid 0, Linux 6.18.44. It is not claimed as the real build machine identity. Complete compiler/tool versions and installed toolchain components/targets remain in `readable/`. No offline-build or immutable-host claim is made.

## Preserved original inputs

The package contains all 44 A2 files, nine controller-A2 files, one frozen v2 controller and six read-only profile-v2 inputs: **60 original files**. The shared profile was captured without changing it or acquiring its build lock; all captured hashes and identities match A2's original prelaunch snapshot. The full owner, lock, Components and helper bytes remain recoverable. A2's source worktree and target were neither read, written nor cleaned by packaging. B2 results and future comparisons belong to separate phases.

| Content | Storage |
| --- | --- |
| Every nonbinary original file, including complete rustc argv and metadata | Deterministic `raw.tar.gz`, 56 regular members; `raw.manifest.json` |
| Three deduplicated exact boot inputs at four original paths | `artifacts/manifest.json` and gzip containers/chunks |
| 86 exact producer build/repro/OSDK/component controls, lockfiles and MPL license | `source/controls.tar.gz`, `source/members.json` |
| Offline commit → tree → path → Git blob proof | `source-binding.json` and 30 original objects in `source/tree-objects.json` |
| Complete serial, build/console logs, actual make command, QEMU/environment/policy/result/cleanup, pre/post source, status and installed components/targets | `readable/`, bound to original paths by its manifest |
| Stable read stats, scope and derived proof | `capture.json`, `report.json`, `analysis/` |

| Loaded QEMU input | Exact original bytes | SHA256 |
| --- | ---: | --- |
| Kernel ELF | 8,293,608 | `e89063b19e5895aa64695ba27c04d7d53fd5d65e23adeb0aab06983a1a33794d` |
| Minimal initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| BIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

The 2,569,961-byte kernel gzip is split into 2,097,152 and 472,809-byte chunks; every stored archive/binary chunk is at most 2 MiB. Initramfs storage wraps the original already-gzipped input, so one storage-wrapper decompression restores that exact `.cpio.gz`. The package preserves the real input snapshots and profile bytes; it does not duplicate the whole Git repository or complete host installation.

## Offline verification and reconstruction

From the repository root:

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-a2/verify.py
python3 -I -O support/build/evidence/2026-10-17-repro-kernel-a2/verify.py
```

The verifier checks complete SHA256 coverage, safe regular tar members/modes, chunks/gzip and original input reconstruction, all original/readable files, Git commit/tree/path/blob identity, private profile bytes and snapshot identities, source pre/post, recorded command log hashes, all actual incoming/effective compiler flags, full metadata projection and A2 boot acceptance. It starts no Cargo, make, host suite, VM, live check or captured controller and needs no network or Git executable.

To reconstruct all 60 original evidence/profile files plus the selected source controls into an explicitly selected fresh directory outside this phase:

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-a2/verify.py --restore /absolute/new-directory
```

Reconstruction only writes verified bytes into fresh files with normal creation permissions. Historical inodes, timestamps, ownership and host dependencies are not recreated, and no reconstructed script is executed.
