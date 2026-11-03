# 2026-11-03 organ source convergence and executed evidence

This checkpoint records actual source-bound executions. It is an evidence and
documentation successor of the frozen product; it does not change that product's
source identity or turn component checks into production qualification.

## Frozen sources

| Role | Commit | Tree |
| --- | --- | --- |
| Current Desktop product | `fd8d56c52b971c2d5d0e6430f296803b43ef60a3` | `347fbb7e9931006c749b5bef0e1550c54bc08f27` |
| First integration / native kernel execution | `e1f3898ff6c2181a6da27de9f9b0f5d1ec03123d` | `31f8eb04759aafd49a51084ce7ecb425b2d1f097` |
| Original Hepta owner, native UI and dependency patches | `a39a0871d9601ffccb5e0d95d8f39d54b3a63360` | `e03f9b3eca364222029298496d3e4f1f5e1bf5de` |

The Linux product uses Rust/Cargo **1.96.0**. The independently documented
standalone Web stable/packager profiles are not product compiler mistakes and
remain unchanged. All six product Cargo lock roots and 39 original source
declarations are checked by the existing dependency verifier. The original
`745c0731` implementation checkpoint remains in Git history; the moving branch
name is not a deployment identity. Integration PR:
[Desktop #279](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/279).

The PR includes the previously unmerged product implementation. Its entire
diff against old `main` is not the amount of code newly written on this date.

## Executed checks

| Evidence | Exact source and actual result | Qualification boundary |
| --- | --- | --- |
| [Session CI](session-host-ci/receipt.json) | `e1/a39`: 23 original tests, no failures/ignored/filtered; original writer, Unix socket, lost-reply and retained-history checks; strict Clippy and full source/critical dependency graph validation | Host composition tests, not a newly installed production Root or real Notes window |
| [Native UI CI](native-ui-ci-e1/receipt.json) | `e1/a39`: UI groups 370 passed / 3 ignored; native text 5 passed / 3 filtered; product Root 25 passed / 2 ignored. Prepared SDK text 35 and window 4 selected tests passed; their remaining tests were filtered | Build/test/Clippy and SDK component checks. Ignored/filtered cases are not passes. No installed window, IBus or AT-SPI claim |
| [Shared original UI core](shared-ui-core/result.json) | `a39`, Rust 1.96, original `hepta-control-core` 55/55 and `hepta-robrix-ui` 24/24; no ignored/filtered; unchanged source/lock | Original shared state libraries with the native product compiler; no Web/WASM/rendered-window qualification |
| [Linux Python contracts](python-contracts-fd/result.json) | `fd/a39`: UI 103; product 93 with 4 privilege-dependent cases skipped as user, then those 4 executed as actual UID 0. **196 distinct cases exercised** | Packaging/input/contracts; no model or device effects |
| [F1 original daemon](f1-native-ci/selected-evidence-index.json) | `e1/a39`: original FleetRegistry/Supervisor lifecycle inside Asterinas; starting/running, capabilities/events, same-process draining, original restart, old-spawn rejection and controlled stop; raw QEMU 33 | Read-only runtime fixture. Full F1, production authority, model/device effects and crash durability remain false |
| [Original CognitiveStore](original-store-a39/independent-replay.json) | `a39` original SQLx/Store binary; 10/10 host and 10/10 native checks. Native uses the same `e1` ordinary kernel, raw QEMU 33. Actual WAL, SIGKILL, reopen, two-process CAS, loser rollback and final persistence; original observers independently replayed | Legacy original Store API scope. No production writer lock, authenticated recovery, physical power loss or complete F1/G2 claim |
| [Kernel four-crate run](kernel-ci/00-result.json) | `e1`: core 377/377; OSTD reports 233 with 3 original TCG soft-skips, exercised lower bound 230; physical allocator 20/20; MLSDisk 15/15. Raw QEMU 33 per guest | The exact native suites; no full SMP or global recovery guarantee |
| [Partition parser](kernel-ci/05-result.json) | `e1`: 24/24 original native cases | In-memory parser qualification, not physical storage or power-loss qualification |
| [Android current host/build](android-host-fd/receipt-index.json) | `fd`: 257 normal and 257 optimized host tests; original Java/JNI/Linux ABI checks; SDK 35 unsigned APK and derived original helper | No signing, installation or phone effect. Binder unavailable in host scope; native Android kernel gates remain red |

The F1 ordinary kernel SHA-256 is
`be188450f0c67b5085a7d6c6a42d6dc959c39c83969bca2b5a2c2b8389ba923b`.
Store execution does not relabel it as a kernel built from `fd`.

The kernel allocator held **127093 ordinary frames** until the original
allocation paths denied further requests, while its previously withdrawn
**64-page** reserve remained usable and returned to the original allocator.
The original result explicitly keeps `global_recovery_guarantee=false`.
Kernel heap, production recovery admission, complete control/I/O resources and
trusted pause ingress remain separate work.

## Corrected failures and original records

The first `e1` CI set ended with 16 successes and one A08 failure. Its 14 missing
Pillow imports were an environment dependency failure. The `fd` workflow installs
`python3-pil` and checks the same interpreter before running the unmodified
contracts. [Current A08 run 41672755499](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/41672755499)
completed successfully. This does not alter the failed
[e1 run 41662601100](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/41662601100).

The current [fd G1-d run 41672755810](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/41672755810)
is **failed**. Its ordinary management/recovery profile completed, but its
historical negative-control episode produced an 8,596,814-byte serial log and
the original bounded evidence parser rejected it. QEMU returned 33 without a
timeout; that exit alone does not satisfy the failed oracle. The original
[outer failure](g1d-current-ci/04-result.json),
[inner failure](g1d-current-ci/05-result.json) and
[QEMU record](g1d-current-ci/06-qemu.json) are retained. No evidence bound or
pass criterion was relaxed and no prior green run replaces this red gate.

The Linux installation test fixture now sets its intended directory mode
explicitly, so a user's umask does not invalidate the fixture premise. The
runtime path checks remain unchanged. The Android source derivation records the
one reviewed live-helper difference (the legacy Enter key names the keyboard
source); the frozen original helper, live installation and old read-only pin
are preserved. Transport deadlines/output bounds and owned-process cleanup
remain fail-closed; stopping a transport is not proof of cancelling a phone
effect. The strict effect receiver remains disabled before device discovery.

## Remaining delivery gates

| User priority | Remaining acceptance |
| --- | --- |
| P0 Linux Notes | Final exact-source product build/package, real local login and original Root/authority, real model task, application effect, independent readback, original writer terminal, disconnection and restart reconciliation |
| P0 F1 / G2 | Compose original production runtime/writer/outbox and HOS2 in the same native execution; lost reply must not duplicate mutation and retirement must follow durable terminal acknowledgement. The separate daemon and Store executions do not prove this composition |
| P1 resource recovery | Covered process-family memory admission and original reserve/watchdog components have evidence; whole-kernel allocation containment, production recovery resources and trusted user-pause ingress remain open |
| P1 second target | Calculator has a separate development branch. It requires its own bounded target protocol, causal readback, original typed writer evidence and a new versioned original tool profile/thread; an ordinary local calculator UI is not an organ |
| P1 Android | Recover the original signing authority through its existing authorized channel, qualify exact installed peer/helper and original owner target, then actual Chinese text/focus/rotation/reconnect/cancel episodes |
| P1 shared UI | Shared Rust core contracts are tested. Final Makepad IBus/AT-SPI, workspace-switch input transactions and the independently pinned Web build/runtime need their own executions |
| P2 fixed hardware | [Actual X230 inventory and driver gaps](../../../support/hardware/X230_NATIVE_DESKTOP.md). No boot medium selected; no native boot or disk/firmware mutation. AHCI/e1000e and the complete device recovery path remain unqualified |

## Preservation and interpretation

Each raw selected receipt is retained without changing its false flags, test
counts, failed attempts or original source IDs. Selection indices record exact
file bytes and SHA-256. Native UI's complete 2,483,092-byte ZIP digest was
recomputed. A06 used bounded HTTP range extraction: selected entries passed ZIP
CRC and individual SHA-256 checks; its complete ZIP digest was **not** recomputed.
The artifact's published SHA-256 must not be presented as a local full-archive
verification. Large reproducible compiler caches are not evidence archives.

Issue [#33](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/33)
was closed using current successful CI evidence. Issues
[#28](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/28),
[#46](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/46)
and [#63](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/63)
retain their historical bodies and now name their still-open qualification work.
The Ubuntu 32-case run does not qualify the separate pinned Debian 13 profile.
