# A01 full Rust kernel build, boot and handoff — 2026-10-20

**The complete fixed Asterinas-derived kernel was freshly built from source and booted twice in real QEMU.** This run freshly installed the pinned native dependencies, completed an absent-target `make kernel`, and ran `make run_kernel` twice successfully after correcting one private QEMU module-path failure. Both successful guests loaded the exact cold-built ELF. Complete OSTD and aster-core target-crate runs reported **468 passes, 0 failures and 0 filters**, including **3 OSTD capability soft skips**; the exercised-pass lower bound is **465**.

This is the ordinary default kernel profile. Dedicated G1-c trusted-initial behavior, full G1/G2 acceptance, the complete POSIX/userspace suite and cross-host bit reproducibility are outside this run. The subsequent publication commit contains reporting changes and is not claimed as a separately rebuilt producer.

## Source identity and ownership

| Item | Verified value |
| --- | --- |
| Branch / PR | `agents/A01-asterinas-boot`, [PR #22 → main](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22) |
| Actual source producer | [`a927146241a8622affd6172a1584c9555ba3cc6b`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/a927146241a8622affd6172a1584c9555ba3cc6b) |
| Producer project tree | `eb297ece2b8e067716d3da389bf342015c2ac2d3` |
| Producer kernel subtree | `4ad35974d248e38eb7abc62f2e2c498f39b84e2b` |
| Actual main, first parent | `0c1de23a3754bc3a6976fed53c7dfa0ec3778e57` |
| Prior A01, second parent | `1baefc7dd22f9250d0176e454a4e6aed3a3752ca` |
| Single full source root | `kernel/asterinas/` |
| Fixed upstream | Asterinas **v0.19.0**, commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b` |
| Fixed upstream tree | `96605cf64aeae2d34f29b97e85eff9315fe10a8e` |
| Fixed Rust | `nightly-2026-07-21` |
| Producer input aggregate SHA256 | `bf6ccef4423f4b778395165bd8350a8530490067f2ec238b4e5f5ba5888a50f2` |

The ordinary two-parent integration preserves A01 history without force pushing. The fixed upstream Git objects were fetched and checked. All **2,938 original upstream paths and modes** are retained; 2,831 contents are unchanged and 107 have existing downstream derivations. All **2,957 indexed kernel files** are materialized. Upstream `LICENSE-MPL`, `README.md` and `AGENTS.md` retain their pinned bytes; the project root `README.md` is **0 bytes**. No second OSTD/kernel implementation was introduced.

All **1,648 owner files** across kernel core, OSTD, `libs/os-abi` and `libs/os-control` equal the actual main snapshot. The 12 kernel differences against main are the 10 retained A01 OSDK implementation files and two OSDK documentation files, each equal to prior A01. The [retention summary](source-retention-summary.json) states the pre-commit audit boundary; the [complete 3,047-file producer input list](source-inputs.json) binds the resulting producer to every native stage. Twelve before/after snapshots agree, including all ten tracked os-control files. Each observed native boundary was clean, with no public temporary `kernel/OSDK.toml` left behind.

The source producer also fixes bounded cleanup when recorder evidence writing fails after QEMU spawn, and extends fixed-input verification to the approved current root-lock derivation and actual os-control inputs. The old cleanup hang was reproduced with a controlled host fixture and injected ENOSPC, then the fixed child was reaped. Targeted host suites passed 109 distinct tests: source inputs 21, recorder 31, kernel runner 42, supervisor 10 and G1-c build profile 5. The same 21 source-input tests also passed optimized Python. These host fixtures are separate from the real guests below.

## Fresh dependency installation and fixed locks

The private installation completed on **2026-10-20 at 12:45:00 UTC**, followed by 129 successful verification checks. Thirty Ubuntu packages were checked against signed snapshot indexes and package SHA256 values before extraction; 64 actual executable/library hashes and 48 resolved QEMU main-library inputs were checked. No host package database or production service was changed. The initial version/ldd checks did not exercise QEMU's dynamically loaded TCG module; that limitation was exposed by the first actual boot attempt and corrected below.

| Dependency | Actual version / source |
| --- | --- |
| rustc | `1.99.0-nightly`, commit `87e5904f5eb6398af6b22eac2802c78934260c48` |
| Cargo | `1.99.0-nightly`, commit `3efb1f477e99b42974b982d939fd100303cdf7db` |
| Rust extras | rust-src, rustc-dev, LLVM tools 22.1.8, all four upstream bare-metal targets |
| cargo-binutils | 0.4.0, actually installed with `--locked` |
| QEMU | 8.2.2, Ubuntu package `1:8.2.2+ds-0ubuntu1.18` |
| Firmware | SeaBIOS `1.16.3-2` |
| Static BusyBox | `1:1.36.1-6ubuntu3.1` |
| cpio / GDB | 2.15 / 15.1 |
| Existing host Clang / LLD | 18.1.3 / 18.1.3, versions and bytes recorded |
| Linux vDSO | commit `8af571775a3d3a1df3e84fc9709b9d6b160c771a`, tree `8e0a300d78c2a020ccc79f1253bc27a8301416e6` |

Docker, Nix and KVM were unavailable. The actual route uses native tools and **QEMU TCG**. No NixOS installation ISO was downloaded or required. The complete package names, versions, public download URLs, hashes and corrected module setting are in [dependencies.json](dependencies.json). The original installation commands, signatures, logs and verification receipts remain in the local installation archive identified below. This records the actual environment; it does not claim a complete immutable host closure.

| Lock/input | SHA256 |
| --- | --- |
| Original upstream root `Cargo.lock` seed | `6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316` |
| Approved working root `Cargo.lock` | `af94d71680ecf3b9631e21c958263d5e41229033214f88dcff858bb14765a666` |
| Original upstream OSDK lock seed | `99a21f72f6a9f1582553b34f06e80f86e539f38e62eab7a0847afd0906e75be3` |
| Approved working OSDK lock | `1011e26a7070708d37f2062a84b309d2c228c177a9e5434bfe63917203c17a18` |
| Rust toolchain file | `b2508d8c9cd57258fad2fc77737e07172846161f6a7dd726cbd8e974de69c6f7` |
| Minimal generated workspace lock | `e54bc99b3df5e21a1fdcd88d89b32ac478e73c7b4bf69ae0b1084f59d56fc506` |
| OSTD test-base lock | `bd2fa3a12577a44f4730de7228a7ceb1fb77cda68d45835825a219c62e2c5ec6` |
| aster-core test-base lock | `85ccdcd1283d42af82ee8dca2faac2ee5401631ff150b35e43be46e1fc9c2150` |

The original seed locks and approved working derivations are distinct. Current kernel dependencies include the actual os-control path dependency. Neither fixed upstream version nor external lock resolution was upgraded to make the build pass.

## Build and launch entry points

From the project root, with the dependencies above installed and the pinned vDSO available at `support/build/out/linux-vdso`:

```sh
unset CARGO_ENCODED_RUSTFLAGS CARGO_TARGET_DIR
export RUSTUP_TOOLCHAIN=nightly-2026-07-21
export CARGO_BUILD_JOBS=2
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
```

The wrapper selects the upstream developer `make kernel` / `make run_kernel` recipes, overlaid by `support/build/minimal.mk`. It creates a new evidence directory, fixes x86_64 / 1 vCPU / 512M, prepares a small static BusyBox initramfs, holds the workspace lock, installs source-bound OSDK into a fresh per-invocation prefix with `cargo install --locked`, and records real arguments and output. `A01_RUN_DIR=/absolute/new/directory` selects a particular new evidence path. See the [handoff](../../handoffs/A01-2026-10-20-main0c1.md) for private-install environment variables, including `QEMU_MODULE_DIR`.

The actual upstream command shape, with only the task's private prefix replaced by a declared placeholder, is:

```sh
make -C <A01_RUN_ROOT>/source/kernel/asterinas \
  -f Makefile -f <A01_RUN_ROOT>/source/support/build/minimal.mk kernel \
  CARGO_OSDK=<A01_RUN_ROOT>/native-boot/kernel/run/osdk/bin/cargo-osdk \
  A01_OSDK_INSTALL_ROOT=<A01_RUN_ROOT>/native-boot/kernel/run/osdk \
  A01_INITRAMFS=<A01_RUN_ROOT>/native-boot/kernel/run/initramfs.cpio.gz \
  A01_QEMU_WRAPPER=<A01_RUN_ROOT>/source/support/build/record-qemu.py \
  TARGET_ARCH=x86_64 SMP=1 MEM=512M ENABLE_KVM=0 \
  BOOT_PROTOCOL=multiboot INITRAMFS=on AUTO_TEST=none
```

This displayed command is a path-normalized record, not a directly executable shell line until placeholders are replaced. [commands.json](commands.json) retains four normalized make commands and the four successful guest QEMU argv arrays. The first failed QEMU argv, all original exact commands and the environment remain unchanged in the local raw archives.

## Actual native results

| Stage | UTC / duration | Actual result |
| --- | --- | --- |
| Cold `make kernel` | 13:15:39.473–13:20:28.549; 289.075541 s | exit 0; both kernel and OSDK target directories absent before launch |
| First QEMU attempt | Retained original failed pipeline | raw QEMU 1, make/wrapper 2, serial 0 bytes; failed before executing the kernel |
| Corrected boot | 13:22:06.855–13:22:21.631; stage 14.774188 s / QEMU 9.183 s | raw QEMU 33, wrapper 0, no timeout; 72,275 original serial bytes |
| Repeat boot | 13:22:21.984–13:22:36.203; stage 14.218180 s / QEMU 8.970 s | raw QEMU 33, wrapper 0, no timeout; 72,275 original serial bytes |
| Complete OSTD crate | 13:23:06.165–13:24:12.902; 66.736077 s | raw QEMU 33; 221 reported passed, 3 soft skips, 0 failed, 0 filtered |
| Complete aster-core crate | 13:24:13.270–13:26:27.216; 133.945554 s | raw QEMU 33; 247 passed, 0 soft skips, 0 failed, 0 filtered |

The first attempt's exact error was:

```text
qemu-system-x86_64: fatal: could not load module for type 'tcg-accel-ops'
```

The TCG module had been installed in the private runtime but QEMU's compiled module search prefix did not locate it. Setting `QEMU_MODULE_DIR` to the existing private `usr/lib/x86_64-linux-gnu/qemu` directory resolved the failure. The module's 22,768 bytes have SHA256 `bbaaf2a24df5546d87a4973e4c02e93eea4347b015db029ef6749e1a00fcf013`. The correction changed environment configuration only. Both later boots and both crate suites then actually passed. The original failed `native-boot/pipeline.json` stays `passed: false`; the successful retry does not overwrite its logs or status.

The ordinary guest profile is **x86_64, q35, TCG, CPU max, 1 vCPU, 512M, SeaBIOS**, with `-nodefaults`, `-no-user-config`, `-no-reboot`, no graphical display, no monitor, serial logging and `isa-debug-exit,iobase=0xf4,iosize=0x04`. Actual argv has no disk, ISO or network device. The guest ran the original upstream `test/initramfs/src/boot_hello.sh` in a **1,107,990-byte** initramfs and produced:

```text
OSTD initialized. Preparing components.
TRILLIONNIUM_A01_INIT_BEGIN
TRILLIONNIUM_A01_CPU_COUNT=1
Successfully booted.
TRILLIONNIUM_A01_BOOT_OK
```

### Loaded artifacts

| Artifact | Bytes | SHA256 |
| --- | ---: | --- |
| Cold-built full kernel ELF, loaded by both successful boots | 8,396,472 | `87e2d0cccdf2e2224e46bd2c0c4393921d296c66a1af9038d7b9f5aa7d570a98` |
| Minimal initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| SeaBIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| OSTD test ELF | 1,998,976 | `a62649352a5ff0c2e3afcbbf2992baee6c3010116a5e1eb272c9fd1d82f75039` |
| aster-core test ELF | 9,967,432 | `61ef6ea0ade9194e6c860e04310f2048587d5d41c6690956f46d3e80537d1fdf` |

The ordinary ELF was produced at `kernel/asterinas/target/osdk/asterinas/asterinas-osdk-bin.elf`. Independent readback verified the first-produced frozen ELF and both actual loaded recorder-private kernel copies byte for byte. Each boot also used exclusive prelaunch initramfs/BIOS copies. This source-to-ELF-to-QEMU binding, the Rust build log, OSTD initialization and upstream guest smoke establish that the project kernel ran; Linux-compatible `/proc/version` text alone is not treated as that proof.

The full target-crate commands were:

```sh
python3 -B -I support/build/ktest/run.py --crate ostd --output /absolute/new/ostd-evidence
python3 -B -I support/build/ktest/run.py --crate aster-core --output /absolute/new/core-evidence
```

There was no `--test-name` filter. OSTD's soft skips were VMX unavailable twice and VMX/EPT invalidation unavailable once. Registered tests from skipped dependency crates are not included in 221/247. Each ktest invocation installed OSDK into its own private prefix, reusing the same producer's compilation cache. Ktest QEMU loaded the exclusively held workspace target ELF directly; its prelaunch hash/stat agrees with the post-run frozen ELF. That evidence model is distinct from ordinary boot's private prelaunch kernel snapshot.

## Evidence available in this PR

- [Machine-readable results](report.json), [source inputs](source-inputs.json), [dependency identities](dependencies.json), [normalized commands](commands.json) and [source publication bridge](source-bridge.json).
- [First successful boot, explicitly redacted](serial/boot.redacted.log) and [repeat boot, explicitly redacted](serial/boot-repeat.redacted.log).
- [Complete original OSTD serial](serial/ostd.raw.log) and [complete original aster-core serial](serial/aster-core.raw.log).
- [First failed attempt's original empty serial](serial/first-boot-failed.raw.log).
- [Original/public serial SHA256 and exact replacement counts](serial/redaction-manifest.json).
- [A00 / A05 / A06 handoff](../../handoffs/A01-2026-10-20-main0c1.md).

Each ordinary boot public log replaces exactly one build-host identifier and four occurrences of this task's absolute root. All other bytes and line counts are retained. The original logs remain unchanged. The two ktest logs and empty first-attempt serial are byte-original. Public and original hashes are intentionally distinct:

| Serial | Original SHA256 | Public SHA256 |
| --- | --- | --- |
| Boot | `3debbcf50d4bd61459481bb0037ab651497aa88d99e7382538c8fc6846d8b814` | `b0796596e6508d92686e14ca8f586862943746b326f6ff24172d0b397eb771f1` |
| Repeat | `4720dafea55a640c71b7bc54f5fd04a8db9cbe9183c99addfe641e83a27c820f` | `5bb32a25bcd956d1d58808ff2255a0e5b996fcc7e7105a5788518831344dc46e` |
| OSTD | `b0be3ce301380360885f80d55ab6aeb4955213117c72ce7cce7fd267def9aa63` | same |
| aster-core | `1ed8da8ddbe14e218257b0cbe6a9c6e8dc4f7f44b7d56ab6f1b808219f86a86a` | same |

### Complete original archives retained as user downloads

Automatic approval review rejected public upload of the complete raw archive because its internal build logs, host paths and environment data could be sensitive and explicit authorization for public distribution of that bundle was absent. Local review confirmed host-identifying information in the original archive. It has not been uploaded, split, renamed for upload or sent to another service. This PR instead contains the specifically reviewed, reduced public material listed above. Full raw public publication remains pending explicit user approval.

| Local archive filename | Bytes | SHA256 |
| --- | ---: | --- |
| `native-evidence.tar.xz` | 14,742,708 | `2e6c410637a31b1bf69f05cf2065c9e9a69ac1a0d8b89fefa1ea09093abd6c7a` |
| `verification-evidence.tar.xz` | 350,384 | `73993db26b50a98f0b7f4e927b0f46a60240bc3c74b8f16a1bb8237d466ec2d6` |
| `runtime-installation-2026-10-20.tar.xz` | 236,988 | `15c57f31187b4a550e69b847e249a547d343ba8d071d83435bb180423f0901d6` |

The native archive retains complete original make/compiler/OSDK output, serial logs, argv, environments, first-failure evidence, source snapshots, loaded and frozen artifacts, private SDK binaries, file-operation traces and the harness. Verification retains source acquisition, host tests, independent source/evidence reviews and module-fix receipts. Installation retains real dependency commands and verification, not the entire roughly 2 GB toolchain. Archive creation read back every member and verified payload bytes and modes. Content-identical archive hardlinks express storage deduplication, not original inode identity.

## Manifest lifecycle, limits and remaining work

The cold build, failed first launch and two successful boots each created and removed their own temporary public manifest using the existing ownership rules. Controlled file-syscall traces and continuous directory inotify agree; ktests did not modify the public manifest. No current unexplained manifest reappearance was observed at native boundaries. Historical October 18/19 failures remain historical records with their original scope. The tracing does not prove global atomic snapshots or identify arbitrary external writers.

There is **no unresolved technical blocker for this tested minimal x86_64 / 1 vCPU / 512M build-and-boot path**. A05 and A06 can continue at the concrete Process, ioctl, scheduler and CPU-owner interfaces in the handoff; A01 changed none of their core files. Additional acceptance remains with its owners: VMX/EPT-capable execution, full userspace conformance, dedicated G1-c trusted-initial checks, G1/G2 workloads and complete immutable/cross-host reproduction.

GitHub's last pre-publication check observed main still at `0c1de23a…`, branch at the producer and PR #22 open with base ref `main`. Producer Actions jobs were **queued**, with no executed steps or success conclusion; local native passes are not a claim that GitHub CI passed. The final PR/branch and Actions state must be read back after the reporting commit is pushed. The complete raw-archive public-distribution approval remains a publication blocker separate from the successful native acceptance.
