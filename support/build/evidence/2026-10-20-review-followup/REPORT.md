# A01 review follow-up: capture fixtures and ktest timeout preparation

## Result and source boundary

The three issues in [PR #22 review](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#issuecomment-6295476669) were reproduced against `aeb1784735aff9673d0524ff2c382ba97b02bd61` and fixed in four A01-owned files. No upstream kernel, A05/A06 core, ABI, workflow, permission-probe owner file or pinned version changes are included. Root `README.md` remains 0 bytes.

The machine-readable [results](results.json) bind the exact changed blobs, tested bytes, commands, original log hashes, failure observations and native recorder results. Raw private-environment evidence remains available in the continuation supplement; hashes here refer to those original bytes.

## Fixes and preserved negative evidence

1. The fake coverage capture CLI now requires `--profile-id osdk-native-local-tcp-gdb-capture-v2` and `--transport tcp`, each exactly once. Both receipt and sidecar are checked against these values. The original source-replacement, EM62, frozen-copy, read-only and digest assertions remain. Before the fix, two of eleven input-snapshot tests failed because the helper rejected these two real production arguments.
2. The private-tools rejection test now compares the complete current message, `ValueError: GDB coverage capture requires an explicit v2 TCP or v3 UNIX profile`. The refusal still occurs before version probing or guest execution. Before the fix, one of six tests failed solely on its stale TCP-only diagnostic.
3. `A01_KTEST_TIMEOUT` is parsed and checked inside artifact preparation, before QEMU discovery/version probing or guest execution. The record preserves the requested string and the selected positive finite integer. Invalid input produces `artifact_preparation_failed`, wrapper exit 1 and a null raw guest exit. Default 300 and valid explicit values retain their behavior; there is no arbitrary upper limit or fallback. Before the fix, invalid input raised an uncaught exception after recording `qemu_running` even though no guest had started.

Six invalid timeout cases (invalid, empty, zero, negative, fractional and a 1000-digit integer) are rejected before either helper runs. Default 300, explicit 2 and explicit 90000 retain exit 33 and artifact provenance. A real controlled Python sleeper verifies the existing one-second timeout exit 124, process reaping and serial digest. These host fixtures are not counted as QEMU guests.

## Host validation and its denominators

| Group | Distinct test methods | Actual successful executions |
| --- | ---: | ---: |
| Existing workflow suites: boot evidence 31, kernel runner 43, archive 28; normal and `-O` | 102 | 204 |
| Related OSDK suites, normal mode | 142 | 142 |
| Patched input snapshots 11, private tools 6, ktest private inputs 8; normal and `-O` on the canonical worktree | 25 | 50 |
| **Total without duplicate draft runs** | **269** | **396** |

The first two boot-evidence invocations each encountered 27 missing-file errors among 31 methods because the sparse checkout omitted the tracked historical serial fixture. Both original failures are retained. A new private four-file closure restored the exact original Git blobs, including `support/build/evidence/2026-10-16/acceptance/boot/serial.log` (blob `3d46545cef6a30067f0ee437334dd07cf6fc76a0`, SHA256 `919269f73caca7f4b6a715f5ece8f189bc26487a844dc98e247af5fd60720016`). The two modes then passed 31/31 without assertion or production changes. The other workflow gates used unchanged canonical source. The baseline and final snapshot over 5,390 tracked entries was byte-identical.

`test_capture_lifecycle.py` invokes native GDB and is excluded from this host-only sweep. Its existing native matrix evidence is separately documented. The workflow itself does not currently schedule all three changed test modules; the explicit local invocations in `results.json` close that validation gap without an A00-owned workflow change. Independent read-only reviews found no weakened oracle or blocking issue in either patch.

## Actual QEMU validation of the changed recorder

The changed recorder was also used for two new real QEMU invocations against the previously frozen complete-crate test ELFs produced from `a927146241a8622affd6172a1584c9555ba3cc6b`. This is a replay of retained build outputs, not a new Cargo build. The source and artifact hashes were checked before and after. The fixed profile is x86_64, q35, TCG, `max`, 1 vCPU, 512 MiB, serial logging, ISA debug-exit and the private recorded SeaBIOS.

| Actual guest | Frozen ELF SHA256 | Raw QEMU exit | Reported pass | Soft skips | Exercised lower bound |
| --- | --- | ---: | ---: | ---: | ---: |
| OSTD | `a62649352a5ff0c2e3afcbbf2992baee6c3010116a5e1eb272c9fd1d82f75039` | 33 | 221 | 3 VMX/EPT unavailable | 218 |
| aster-core | `61ef6ea0ade9194e6c860e04310f2048587d5d41c6690956f46d3e80537d1fdf` | 33 | 247 | 0 | 247 |

Both records reached `complete`, requested/selected the default 300 seconds, retained the original ELF and BIOS hashes, and passed the existing crate checker with no filter. Their 468 reported passes include the three explicitly identified soft skips, leaving 465 as the exercised lower bound. No kernel-source regression or new build claim is inferred from the replay.

The earlier [full cold-build/boot and default UNIX matrix evidence](../2026-10-20-blocker-closure/REPORT.md) remains bound to producers `684c4c82bbe770d712da75a199b7f5757ee61191` and `8769a3e224fb97ce6d06fbcb1512281a7427156e`. This follow-up does not relabel those producers.

## Remaining integration boundary

At the observed `aeb1784` A06 run `39456758126`, the permission-probe Linux comparison failed before the Rust and QEMU steps. This remains an A04/A00 owner handoff documented in the [closure handoff](../../handoffs/A01-2026-10-20-blocker-closure.md); the minimal reviewed candidate is retained there. This report makes no claim that current-head GitHub CI, the outside-owner publication scanner, or the complete project G1/G2 gates have passed. Latest remote states belong to the PR's timestamped update.
