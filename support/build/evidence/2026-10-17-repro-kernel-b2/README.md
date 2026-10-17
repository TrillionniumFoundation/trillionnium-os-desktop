# B2 cold source build and real QEMU boot: passed

This phase independently freezes **B2's actual successful source build and real project-kernel boot** at `bdf7a08dcc0980fa85c0ba5abdf365b7d2c42e80`, complete tree `eff51eb940d1f415aedb84555752ecbc97d58faa`, derived kernel tree `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. Fixed upstream remains Asterinas v0.19.0, commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, nightly `nightly-2026-07-21`.

| Recorded result | Evidence |
| --- | --- |
| Actual checkout | `/tmp/trillionnium-a01-normalized-B2` |
| Cold target precondition | Original policy records `target_absent_at_prelaunch=true`, exact runner guard preserved |
| Compilation | 279 `Compiling` lines and both completed release stages, then actual QEMU |
| All eight controller commands | Exit 0: worktree, source, build/boot, live artifacts, post-source, status, installed components, installed targets |
| Worktree status | Empty output, exit 0 |
| Source before/after | Identical successful 118-file verification receipts |
| Profile/source/code custody | All three original postrun checks true; captured profile inputs match prelaunch hashes/identities |
| Cleanup | Original receipt `owned_removed`, passed true |
| Actual QEMU | Raw 33, recorder 33, no timeout, complete stage, 1.319 seconds |

The entire 72,341-byte serial is preserved, SHA256 `e429eae97a05c5fe47e0fc4c09bb5cbf3911e86eea80598dbf22cbf5c5c0c123`. It contains OSTD initialization, `TRILLIONNIUM_A01_INIT_BEGIN`, `TRILLIONNIUM_A01_CPU_COUNT=1`, `Successfully booted.` and `TRILLIONNIUM_A01_BOOT_OK`, followed by poweroff. Exact real QEMU argv, executable version/hash, input snapshots and postrun `check-boot.py --live-artifacts` success remain available. This is q35/TCG/CPU max, one CPU and 512M with fixed serial and debug-exit devices.

This accepts B2 boot only. The separately attempted **A2/B2 complete kernel-byte comparison failed**; equal boot outcomes do not establish equal ELF bytes. Cross-path, independent-host and immutable-host reproduction are not accepted here. A2's published directory is unchanged and its result is preserved separately.

The explicit v2 same-host path-projection profile deliberately embeds synthetic builder `a01-repro@a01-fixed-profile` and fixed epoch/timestamp metadata. Actual host `343e40cfefc1`, user root and uid 0 remain separately recorded. It is an opt-in profile, not a claim about the real builder identity or an offline/immutable environment. Full toolchain versions and installed components/targets are preserved.

All 369 compiler calls retain incoming/effective argv. The canonical mapping already existed in 130 calls and was inserted in 239, preserving every other argument in order before any `--` delimiter. All six original/mapped metadata pairs, bindings and stderr remain intact. `analysis/compiler-and-custody.json` binds every call and complete selected core/OSTD/component-macro/virtio calls.

The raw controller includes exact arguments, environment, timestamps, statuses and log hashes. Root supplied outer session 87857/exit 0 from its actual tool-result retained summary; no separate outer raw log is fabricated. The v2 controller SHA256 is `fe9b1180aaa1316075701553f82b5b129c1f541bf3a0f4513ae1ff2e234043e8`. The real `run_kernel` action cold-built then booted with combined make/action 0; no additional standalone `make kernel` invocation is inferred.

## Preserved bytes and sources

All 60 original files are recoverable: B2's 44 files, nine controller files, v2 controller and six shared read-only profile inputs. The deterministic raw archive contains 56 nonbinary regular members. The package also holds 86 exact producer source controls and 30 original Git tree objects, permitting offline commit/tree/path/blob membership verification. Source-control bytes were reused unchanged from the frozen A2 package because both actual source producers are identical; no A2 directory was modified. Packaging did not inspect, write or clean the original B2 target/worktree.

| Actual loaded input | Exact bytes | SHA256 |
| --- | ---: | --- |
| Kernel ELF | 8,292,192 | `b5fda2500d15c250d022f81bf2d30c0778244faea021a5db34aa68665d68f763` |
| Initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| BIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

Three binary inputs are deduplicated over four original logical paths. The kernel gzip is 2,569,906 bytes, split into 2,097,152 and 472,754-byte chunks. Every archive/binary chunk is at most 2 MiB. One storage-wrapper decompression restores each exact original input; initramfs remains its original `.cpio.gz`.

`raw.manifest.json`, `artifacts/manifest.json`, `capture.json`, `source/`, `readable/manifest.json` and `report.json` bind the raw archives, original stats, complete significant logs, exact commands, pre/post checks, scope and input bytes. The entire repository and host dependency installation are not duplicated.

## Offline checks and reconstruction

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-b2/verify.py
python3 -I -O support/build/evidence/2026-10-17-repro-kernel-b2/verify.py
```

The verifier needs no Git executable or network. It checks SHA coverage, safe tar members/modes, gzip chunks and exact original inputs, full inventory, readable copies, Git membership, profile identities, source pre/post, log bindings, every actual compiler argv, full metadata projection and B2 boot acceptance. It invokes no build, test suite, live checker, captured controller or VM.

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-b2/verify.py --restore /absolute/new-directory
```

Optional reconstruction creates fresh verified files and never executes them. Historical inodes, timestamps, permissions and host dependencies are not recreated. Cross-path comparison belongs to its separate failed evidence phase.
