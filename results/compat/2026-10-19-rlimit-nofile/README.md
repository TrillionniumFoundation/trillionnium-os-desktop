# RLIMIT_NOFILE: original Linux reference and ordinary-kernel RED

This archive freezes the **real Linux success and real old-kernel failure**
used to review the allocation/receiver fix. It contains no new RLIMIT kernel
GREEN. At this snapshot, compilation and same-ELF execution of the repaired
kernel are the next integration gate. This additional 37-case profile does not
replace the fixed Debian 13 rootfs/ELFs, the complete OSTD/core kernel tests,
sender-side in-flight SCM_RIGHTS accounting, Hepta qualification or device tests.

## Fixed inputs and observed results

| Input | Exact identity |
| --- | --- |
| Final C probe source | `7e86277f3e55da43328ad8da980d23709a84adf6c6543268a3a4699493b75317` |
| Same static ELF on Linux and both guest attempts | `c3533e3b343ffb719e22d736aba4f9bc9c3040826547530f24e0556292b1ea3e` |
| Ordinary kernel source head | `dafa1eba79cb1e17f880b5f0c5d57a80510d5d68` |
| Ordinary kernel source tree | `354adb549b064c78477932ca943309694eb54356` |
| Ordinary kernel ELF | `1145311a1335b866196019dfeea5937a86d4cbc4ff1efb222e8a229137b3737b` |
| Fixed original initramfs, already in the repository | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| Actual diagnostic initramfs in both attempts | `6583c4d507b57332772419e581924a2d9de3c543a852ebd17a62fbe0499daec8` |
| Actual BIOS | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

The ordinary kernel came from the passing A06 product/QueryAbi build and boot
gate for the CLOEXEC candidate in PR #198. Its original receipt and all three
byte-identical source snapshots are preserved. Its source already contains
CLOEXEC, but predates the RLIMIT allocation fix. The source head above is the
actual original build identity, rather than a later merge commit.

| Execution | Complete result | Actual exit and scope |
| --- | --- | --- |
| Final ELF on Linux 6.18.55 x86_64 | 37 PASS / 0 FAIL | Probe 0; empty stderr. Ten further complete runs also passed. |
| Maintained reference 01 | 37 PASS / 0 FAIL | Probe 0; pinned inputs unchanged; anchored group cleanup completed. |
| Guest RED01, runner `b433aaf` | Raw stream contains 0 PASS / 37 FAIL and probe exit 1 | Failed runner receipt: the 14,761,415-byte log exceeded its former 8 MiB parser limit. The receipt did not retain QEMU's exit, so this attempt makes no QEMU-exit claim. |
| Maintained reference 02 | 37 PASS / 0 FAIL | Probe 0; unchanged ELF and helpers; group cleanup completed. |
| Guest RED02, runner `f7658e5` | 0 PASS / 37 FAIL; all fixed cases and consistent summary | Probe 1, QEMU 33, no timeout or kernel panic; 16.11 seconds; all guest/reference/runner inputs unchanged. |

RED02's complete serial stream is 14,001,009 bytes with SHA256
`2bb9e45dd29f9f334bee143032299604fe90becffba444bcede7d2117f0229d4`.
Most failures stop immediately when the old allocator returns a descriptor at
or above the selected limit. The three bounded reservation observers instead
reach their deadline. Every failure remains in the 37-case denominator. Normal
QEMU shutdown never converts the probe's exit 1 into compatibility success.

## Earlier failures are retained

`linux-history.tar.gz` includes the original compile/run commands, compiler
version, raw stdout/stderr, exit records, source snapshots and ELF bytes for
the earlier probe revisions:

- The first 36-case revision returned 31 PASS / 5 FAIL under sandbox socket
  restrictions, then 33 PASS / 3 FAIL on unrestricted Linux. The latter failures
  exposed the probe's incorrect assumption that accept would reserve a
  preselected descriptor while an observer was competing for it.
- The corrected observer identifies a real reservation through `dup2` returning
  `EBUSY`. That 36-case revision passed before the separate `CLONE_FILES` case
  was added. Its original source and different ELF are preserved.
- The final 37-case ELF passed the initial reference and ten additional runs.
  Its expected behavior and bytes were frozen before either guest execution.

The first runner commit passed 17 normal and 17 optimized Python regressions.
After the actual large-log failure, the follow-up passed 18 in each mode.
The additional regression requires an over-limit log to preserve the real
QEMU exit/timeout facts while retaining a failed verdict. Verdict/CPIO fixtures
are parser tests. The owned-child cleanup checks use actual Linux processes;
neither kind of test is represented as guest compatibility execution.

## Archive layout and deduplication

`MANIFEST.json` binds every payload's size and SHA256, decompressed bytes, and
all tar members. Large repeated ELF copies are represented by explicit
`shared_archive_members` references to the single `probe.elf.gz`. To restore a
Linux reference directory, unpack its tar archive and place those decompressed
ELF bytes at `probe.elf`; the original `probe.sha256` then checks that copy.
The historical directory similarly restores `rlimit-nofile-probe` from it.

The three original product source snapshots were compared byte for byte and
stored once as `ordinary-source-snapshot.json.gz`. The manifest retains each
original filename and its digest. Restoring an ordinary product directory
copies these same bytes to `source-before.json`, `source-after-boot.json` and
`source-after-guest.json`, alongside `ordinary-product-receipt.json` renamed to
`result.json` and the decompressed `kernel.elf.gz` as `product-kernel.elf`.

`initramfs.cpio.gz`, `bios.bin.gz` and the QEMU launcher preserve the actual
boot inputs. The QEMU binary and libraries are not bundled; the runtime report
records the observed QEMU 8.2.2 version and launcher digest. Both full raw
serial streams are compressed without filtering. `harness-sources.tar.gz`
contains the two runner versions, final tests, and the exact shared
product/CPIO/process-group helper sources whose digests appear in the receipts.

The source fix was frozen locally as
`b4ae089ccec35bc4cdd414c4c58fc2ebb2780912`; its exact patch is retained.
The runner commits were
`b433aafbbad6a89032cfc6359361595062796d77` and
`f7658e5507bfe1e127d85dd005a864d1259808b8`. Later integration may cherry-pick
these changes onto a different parent; content hashes and original runtime
identities in this archive remain unchanged.

Verify archive integrity without executing any archived program:

```sh
python3 -I -B results/compat/2026-10-19-rlimit-nofile/verify_archive.py
```

The verifier checks stored and decompressed bytes, archive members, and shared
content references. It reports byte integrity only. See the
[RLIMIT design and runner instructions](../../../tests/workloads/linux/RLIMIT_NOFILE.md)
for the actual Linux and guest acceptance commands and remaining qualification.
