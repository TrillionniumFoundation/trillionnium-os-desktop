# A01 blocker continuation — actual native evidence, 2026-10-20

**The corrected default UNIX matrix passed all 22 cases with 11 real QEMU guests exiting 33. Both corrected cold full-kernel builds C and D also booted successfully.** This draft preserves the exact producer and result of every earlier failure. The second cold run and independent pair qualification are reported from their actual terminal evidence below; CI and cross-owner blockers are separately tracked. No blanket all-blockers-closed claim is made.

The immutable kernel base remains full Asterinas **v0.19.0**, commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`, Rust `nightly-2026-07-21`. The single kernel root is `kernel/asterinas/`. Work is on [`agents/A01-asterinas-boot`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/agents/A01-asterinas-boot), [PR #22 → main](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22).

## What actually ran

| Producer / run | Actual result | Actual QEMU processes | Interpretation |
| --- | --- | ---: | --- |
| `e37df299075b49302b076ecda5fcce46e315d210`, explicit TCP/GDB coverage v2 | **22/22 cases passed**, 0 failed/blocked, 234.979 s | 11; all raw 33 | Complete selected OSDK tooling/example matrix passed |
| Same producer, original UNIX v1 | **21/22**, coverage failed, 228.815 s | 11; all raw 33 | Original post-exit coverage lifecycle failed despite successful guest exits |
| `cc8b72a2f3a4cd52f9c7c978307b5ca6f9e9f148`, cold full-kernel repro A | Rust compilation succeeded; make/launcher 2; **QEMU raw 65**, 449.758 s | 1 | Real full kernel panicked during component initialization; boot failed |
| `684c4c82bbe770d712da75a199b7f5757ee61191`, default UNIX v3, first attempt | **21/22**, coverage pre-spawn rejection, 225.197 s | 10; all raw 33 | Coverage recorder entry exists but that guest was never launched |
| `8769a3e224fb97ce6d06fbcb1512281a7427156e`, default UNIX v3, second attempt | **22/22 passed**, 225.818 s | 11; all raw 33 | Complete default matrix and actual UNIX coverage passed |
| `684c4c82bbe770d712da75a199b7f5757ee61191`, 684-cold-repro-c | make 0, QEMU **33**, 439.446 s | 1 full-kernel guest | passed |
| `684c4c82bbe770d712da75a199b7f5757ee61191`, 684-cold-repro-d | make 0, QEMU **33**, 473.830 s | 1 full-kernel guest | passed |

All four complete matrix attempts selected the full 22-case denominator. Each includes one upstream hypervisor-example **VMX-unavailable fallback**. That fallback is not exercised VMX support. OSDK examples are small test kernels and tooling; their passes are distinct from full Asterinas kernel acceptance.

Every completed run retained its exact commands, environment, original errors, source snapshots and available artifacts. Source snapshots before and after each completed run are byte-identical. [report.json](report.json) contains exact producer project trees, source snapshot hashes, per-case outcomes, actual guest counts, artifact hashes and serial hashes. [original-evidence-manifest.json](original-evidence-manifest.json) identifies the byte-original source records by logical locator and SHA256. The full original data remains separate from this public draft.

## The coverage failure and the successful TCP control

The successful TCP v2 coverage run used the exact unchanged symbol `ostd::arch::power::try_poweroff`. GDB observed PC `0xffffffff88109e30`, equal to the resolved address, saved the announced profile and detached; the real guest then exited 33. GDB exited 0. LLVM processed **5,691 functions**, with maximum function count **383,140**.

| TCP v2 artifact | Bytes | SHA256 |
| --- | ---: | --- |
| Original symbol ELF | 40,265,016 | `30a482786018f78d129c5efa7754d9dbc9c268989f0eaa5ba1a59ea934932302` |
| Actual loaded ELF | 40,265,016 | `effb7e23f2e6b6b31c6f8a129fdb83a17c6751dde37571a0f99994f8e007cd0b` |
| Raw coverage | 2,006,216 | `b6d41b14fbd5c2adc15ca20e6a25488b29ff0e6f84fce786db75bac3d6d1e09f` |
| Complete original coverage guest serial | 2,823 | `908602eb9720548a28e10fdb5b1801d837097197c7200dbbda4177a6eead45a9` |

The ELF identities are intentionally distinct: the pinned OSDK creates the QEMU-loadable form from the original symbol ELF. The evidence binds both to this actual guest.

The original UNIX v1 run also printed the coverage announcement and exited 33, but produced neither `coverage.profraw` nor `coverage.profdata`. Its harness failed with “Coverage file not found.” This remains a failed original lifecycle run; a different capture profile does not retroactively fix it.

The first new default UNIX v3 attempt failed earlier. Its coverage recorder reported:

```text
ValueError: coverage-owned UNIX GDB cannot reuse another debugger's readiness marker
```

The harness exited 101, OSDK exited 6, and the recorder exited 125 with `raw_exit_code: null`. There is no coverage guest serial or capture sidecar for that attempt. The current runner had set the readiness marker for every case; the protected UNIX capture path refused it. Producer 876 removes the readiness marker specifically for the UNIX capture-owned coverage case and preserves the guard for competing markers. Its new complete matrix passed 22/22. The failed 684 records and original error are unchanged.

## Full-kernel cold failure and the next verification

The `cc8` run began with absent kernel and OSDK targets, installed its own source-bound OSDK and compiled the complete Rust kernel. Real QEMU then reached component initialization and panicked with `NotIncludeAllComponent`; it did not complete the guest smoke test.

| Actual failed-run artifact | Bytes | SHA256 |
| --- | ---: | --- |
| Full kernel ELF | 8,406,032 | `c98ddd313152c7e10c99046dae9f288ff354667deefdc97a8708986293bf0001` |
| Small initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| SeaBIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| Complete original failed guest serial | 4,659 | `f721246782f3f40d0529a83b5fc36cc8fffc590981ef3de2125bce5d9cfd2d71` |

The current component macro invokes `cargo metadata --locked --format-version 1`; the old reproduction adapter recognized only the unlocked spelling. It therefore left component registry paths unprojected and emitted zero projection receipts. Commit `684c4c82` matches the exact current argv, preserves `--locked`, and requires complete metadata/Components binding receipts before launcher success. It changes the build adapter, not the component runtime or its validation rules.

The new `684` C/D checkouts each passed independent prelaunch verification: 3,131 actual tracked files matched Git bytes and modes; the absent sparse files were explicitly marked; both kernel and OSDK targets were absent. Their complete source inventory SHA256 is `2ebd59179552f055de8d15bb85926ab7f67c4131171d7f9350ffc57d8d78a21c`. Cold C completed successfully: its independent audit passed 415 checks, six actual metadata projections each bound 19 components, all source/profile/project-input custody checks passed, and real QEMU exited 33 after the complete initramfs smoke. Strict completed-producer provenance used one Cargo build job. Both cold runs have terminal native results. The independent pair audit passed **855/855 checks** and compared all bytes of the separately frozen kernel ELF, initramfs and BIOS: all three are identical. Audit SHA256: `4f4cf8697ec13a7f16fe676c12751356a735a20972e661e9085aa547f5221721`. This qualifies the same-host, same-installed-toolchain, fixed-profile cold pair; it does not qualify reproduction on an arbitrary host.

## New default UNIX result and source bridge

The independent audit of producer `8769a3e224fb97ce6d06fbcb1512281a7427156e` checked **389 files**, **114 locked Cargo requests**, 22 private generated workspaces, the original basic-debug UNIX path, the upstream VSCode TCP path, and the coverage-specific inherited AF_UNIX listener. It found no pending checks or errors. Audit SHA256: `8a2752e17c7f4c818a59d2f208eb23e4e5d158df24960bbe27c96d4abfab10b1`.

Actual coverage PC and resolved symbol address were both `0xffffffff88109e30`. GDB exited 0, detached, and the real guest subsequently exited 33. LLVM processed 5,691 functions with maximum count 383,140. The original symbol and loaded ELF, endpoint identity, serial, raw profile and LLVM output were bound to that same guest.

| Default UNIX v3 artifact | Bytes | SHA256 |
| --- | ---: | --- |
| Raw profile | 2,006,216 | `bde3df6f0f193f14b3b909af4359d4600d63e1a4a0a56de2346bf7f773a4f253` |
| Profdata | 1,245,456 | `4a4079c063172d095527a9c4efa5417580e99c0dec259f3839025c7520530909` |

The full-kernel producer remains **684**, while the successful default matrix producer is **876**. Their only Git differences are `support/build/osdk-integration/run.py` and `support/build/osdk-integration/test_unix_capture.py`. The complete imported kernel tree, core, OSTD, `kernel.sh`, all reproduction helpers, local dependencies and upstream lock are content-identical, as recorded in `source_bridge` in [report.json](report.json). This does not falsely claim another full-kernel rebuild at 876.

## Successful complete-kernel artifacts and serial

The real guest reached:

```text
OSTD initialized. Preparing components.
TRILLIONNIUM_A01_INIT_BEGIN
TRILLIONNIUM_A01_CPU_COUNT=1
Successfully booted.
TRILLIONNIUM_A01_BOOT_OK
```

| Completed cold run / artifact | Bytes | SHA256 |
| --- | ---: | --- |
| 684-cold-repro-c / full kernel ELF | 8,410,560 | `00f3bfb76164fac3890c68115f5347e758820aeeffd42bb9021261900acca508` |
| 684-cold-repro-c / small initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| 684-cold-repro-c / SeaBIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| 684-cold-repro-d / full kernel ELF | 8,410,560 | `00f3bfb76164fac3890c68115f5347e758820aeeffd42bb9021261900acca508` |
| 684-cold-repro-d / small initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| 684-cold-repro-d / SeaBIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

| Complete serial | Original SHA256 | Delivered SHA256 |
| --- | --- | --- |
| [684-cold-repro-c](serial/cold-c.redacted.log) | `7c029e5e809829a0d083454e667e009ed4f4c6a846f791d97ab6c3144bdbb3ba` | `84f068c34f37e7aebdc6bbf7dea6065b11943009b2390fd138258f499625ea94` |
| [684-cold-repro-d](serial/cold-d.redacted.log) | `c05681f00e58b16293c41597e3a31911db16b4ec85dbd6a09ec04ff36f84b15a` | `73c92335d8f49d1169774adc8e63b0c16a33a00576f474678fc7b83dc040bf05` |

The complete serial candidates replace only the declared private profile-prefix bytes. [serial/redaction-manifest.json](serial/redaction-manifest.json) records original and delivered sizes/SHA256, replacement class, token digest/length, replacement text and exact count. All other bytes and line counts are preserved; originals remain unchanged. The literal original tokens stay in a separate private map. Cold C replaces four profile-prefix occurrences. The deliberate constant `a01-repro@a01-fixed-profile` is retained; it is not the actual host name, which was separately checked and is absent.

This cold comparison uses different real checkouts on the same host with one owned immutable virtual-path profile and the selected runtime. It does not establish arbitrary-host bit reproducibility or independent toolchain installations.

## Initial ENOSPC failure remains incomplete

The first e37 TCP attempt exhausted tmpfs space. Its partial audit observed 18 passed cases, four failed cases and five actual guests. Final aggregate and after-source writes were incomplete. Its original outer JSON still says `running`; this preserved interrupted record is not evidence that a process still runs. The original files and hashes are retained separately, and this attempt is excluded from complete-matrix acceptance. The successful e37 retry has its own output, commands and evidence.

## A04 reference fixture and exact-head CI

The completed cc8 Linux reference run reported **31/32** while the same frozen probe ELF and recorded inputs had previously passed 32/32. Private mount namespace creation succeeded in both runs. The sole failed condition was the errno from `syscall(SYS_pivot_root, NULL, NULL)`: Linux `6.17.0-1022-azure` returned EPERM (1), whereas Linux `7.0.0-1017-azure` returned EFAULT (14). This asserts capability errno while supplying invalid pointers. It is an actual Linux reference-fixture failure, not an Asterinas guest failure or a namespace-creation failure.

An observed A04 candidate in [PR #215](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/215), head `233e1e998f8e05d51c132e42ca727c2f5c54db98`, uses existing searchable-directory pointers and preserves EPERM, all 32 cases and the independent Python oracle. It was observed open and unmerged. A01 did not apply the cross-owner change or independently qualify that candidate's native artifacts. See the [A00/A04 coordination record](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#issuecomment-6295094269). The inherited CodeQL issue remains separately tracked in [A00 coordination](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#issuecomment-6294838522).

At the parent GitHub API observation **2026-10-20 16:08:48 UTC**, main remained `0c1de23a3754bc3a6976fed53c7dfa0ec3778e57`. Exact-head 876 [CodeQL run 39452168434](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39452168434) had completed successfully (updated 16:06:59 UTC); [A06 39452173755](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39452173755), [G1c 39452174167](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39452174167) and [A01 39452174269](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39452174269) were still queued with null conclusions. This observation does not establish an all-green exact-head CI result or repair of the inherited CodeQL finding.

## Reproduction entry points

The ordinary complete-kernel build and launch remain:

```sh
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
```

These invoke the pinned upstream `make kernel` / `make run_kernel` through the A01 minimal build overlay. The fixed guest profile is x86_64, q35, TCG, CPU max, one vCPU, 512 MiB, SeaBIOS, fixed devices and serial logging; no NixOS ISO is required.

For the historical successful explicit TCP control, at exact producer `e37df299`:

```sh
python3 -B -I support/build/osdk-integration/run.py \
  --local-tcp --coverage-gdb --output <NEW_ABSOLUTE_OUTPUT>
```

The `e37` no-flags invocation selected original UNIX v1; the now-passing `876` no-flags invocation selects UNIX v3. Do not infer historical profile semantics from a later checkout. [commands.json](commands.json) provides the original option sequences with declared path substitutions for all actual guests and the failed full-kernel run. They are normalized records, not byte-original commands, and placeholders require replacement before execution.

## Scope, CI and publication

Commit `684c4c82` had **203 different host regression cases**: 121 UNIX/integration cases, 59 repro cases and 23 CI compatibility cases. These are host fixtures and do not stand in for native tests. The A06 legacy skip option now warns but still builds a fresh private SDK; G1c retains the private install root via its controlled environment while matching the existing actual-argv contract. Their real CI outcomes must be read from their exact producer, without borrowing an older successful run.

The inherited CodeQL validator issue is outside A01 ownership and remains an [A00 coordination item](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#issuecomment-6294838522). A newer CodeQL workflow success is not itself proof that the inherited finding was repaired. This draft has no authority to mark that item closed.

This public draft contains selected facts, hashes, normalized commands and complete explicitly redacted successful cold-boot serials. It includes **no copied raw host log, environment file, source snapshot or binary**. The separate private locator manifest is not part of the public allowlist. The previously rejected raw-archive upload has not been retried, split or transferred elsewhere. All originals remain unchanged; no replacement byte stream is labelled as an original log.

Earlier full-kernel acceptance at producer `a9271462` and its 468 reported crate-test passes are recorded in the [previous evidence report](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/92b6d33722352db8ffdcfb93b94b3c8f03261f43/support/build/evidence/2026-10-20-main0c1/REPORT.md). Those earlier results retain their producer identity and are not asserted as results of the new reproduction profile.

## Completed pair and bridge receipts

The pair audit read complete artifact bytes for both cold runs and passed 855 checks. Cold D ended at `2026-10-20T16:05:47.259839Z`, after 473.830 seconds, with launcher/make 0, actual QEMU 33, six actual locked metadata projections of 19 components each, and unchanged source/profile/input custody. Both separately frozen kernel ELFs are 8,410,560 bytes with SHA256 `00f3bfb76164fac3890c68115f5347e758820aeeffd42bb9021261900acca508`. The comparison and original receipt are identified in `report.json` and `original-evidence-manifest.json`.

The root independent 684→876 bridge receipt checked 10 Git objects for the complete kernel, core, OSTD, local control library, build entry, minimal initramfs inputs, QEMU recorder, repro helpers and upstream lock. They all match; the repository README is 0 bytes and the observed working tree was clean. Receipt SHA256: `88c61abee3424bdffb7b67ee0a8da4e29539df83ff4bbe32f90f8ad9f1ae6414`. This is content identity evidence, not a claim that the old native runs executed on a later Git commit.
