# 2026-11-03 organ source convergence and executed evidence

This checkpoint records actual source-bound executions. It is an evidence,
documentation and build-supervision successor of the frozen product; it does not change that product's
source identity or turn component checks into production qualification.

The [follow-up evidence](../2026-11-03-organ-followup/README.md) records the
completed nine-workflow `bf15a519` repair CI, Calculator component and original
owner selections, the retained Memory failure and private Xvfb diagnosis. Each
keeps its actual source identity; none is an installed-product completion claim.

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

The complete `fd/a39` product CI set has now finished: **16 successful workflows
and one retained failed G1-d historical negative-control gate**. Its current
[Session 23-case result](session-host-ci-fd/receipt.json),
[full dependency verification](session-host-ci-fd/dependency-verification-summary.json),
[native UI groups and SDK selections](native-ui-ci-fd/receipt.json),
[native four-crate result](kernel-ci-fd/00-result.json), and
[original Agentd lifecycle with independent observer replay](f1-native-ci-fd/independent-review.json)
are separately retained. [The complete final CI snapshot](ci-status-fd-final.json)
does not overwrite the earlier in-progress snapshot.

Current `fd` native counts remain core 377, OSTD 233 reported / 230 exercised
lower bound, allocator 20 and MLSDisk 15; no new skip is introduced. The exact
`fd` ordinary kernel is
`2d13b752c241391f218a14af23f834920e2ba8d582c21fdf3e3c754b117892e4`.
The original daemon's eight observations include PID 26 / spawn 1 changing to
PID 162 / spawn 5. Full F1/G2 and production flags remain false. The separate
original Store run below continues to use its explicitly recorded `e1` kernel.

The dedicated original timer-watchdog workflow also completed on evidence
source `22a94f7d6cd9f77eb4e27c30dfc2befc00dbdb20`, tree
`e9615b923eb4611124c295482bcaf3303b16055c`: **six original boots, each raw QEMU 33**.
The [independent replay](watchdog-native-22a94/independent-review.json) checks all
six raw serial streams against the original observer. Restore, healthy, zero,
thread-directed zero cleanup, stopped and already-recovered cases all pass.
`independent_timer_qualified=true`; trusted user-pause intent, complete physical
reserve, SMP, physical clock faults, hardware and Hepta durability remain false.
This additional gate does not replace the original failed G1-d gate.

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

The original CPU-control builder's timeout/interruption cleanup has a separate
reviewed successor from `22e55ede`: it observes its own unreaped child with
`WNOWAIT`, stops numeric process-group signalling before any wait can reap,
preserves the exclusive Cargo lease through collection, and rejects a conflicting
SIGCHLD owner before spawn. [Fourteen normal tests and six optimized supervision
tests](builder-supervision-22e55/receipt.json) use ordinary owned children. They do
not change the original entry, pins, features, locks or ELF/LOAD limits. The
earlier `e1` build keeps its actual original source and is not relabelled
as a run of the corrected supervisor.

That [original G2 build](g2-original-build-v2/g2-owner-v2-result.json) completed
Cargo's unchanged default release command in 5,554.231 seconds. Its subsequent
original packaging command failed because the builder had frozen its private
product copy to mode `0555` before invoking the original in-place strip script.
The [original error](g2-original-build-v2/g2-owner-v2-original-packaging.log)
is retained. The 102,836,712-byte unstripped ELF is not a passed static profile;
packaging, the unchanged 8 MiB ELF / 16 MiB LOAD checks and G2 execution remained
false. No binary was executed by that failed build.

The reviewed packaging successor makes only this private copy writable for the
original script, then restores mode `0555` on success or failure. The existing
task-private `RUNNER_TEMP` already isolates the script's symbol directory.
[Two ordinary packaging regressions](packaging-nonroot-bde8/result.json) passed
as actual main-host UID/EUID 1000, with source hashes independently checked.
They qualify the copy/strip component only. The new original G2 attempt freezes
Desktop `4dcd02d8058005b92b75b4e997ec4de08833e01d`, tree
`504d5850df75de8697dfb56572cc8745dcc59f13`, with the same original Hepta `a39`;
the original packaging script now succeeds and preserves the same unstripped
ELF digest. Its actual stripped ELF is 20,138,584 bytes, with a page-aligned
LOAD total of 20,168,704 bytes. The original kernel/host 8 MiB file and 16 MiB
LOAD profile correctly rejects it. No native G2 execution or static pass is
claimed. A new owner resource profile would require separate source, budget
review and qualification rather than relabelling this failure.

The [first fixed-nightly download failure](g2-original-build-v2/nightly-range-v1-result.json)
retains its TLS timeout/reset and expected official whole-archive digest. A
partial download is not a usable pinned toolchain and does not permit a version
substitution.

The installed-product attempt also exposed Notes tests parsing libtest's human
stdout as a readiness protocol. A [small Rust 1.95 presentation diagnostic](notes-readiness-diagnostic-1.95/observation.json)
shows that single-threaded libtest prefixes the marker with the test name;
the exact-line parser misses it. This diagnostic is not a Rust 1.96 original
product execution. The successor's real persistence/recovery fixtures now send
their post-commit readiness through their private datagram and explicitly run
their child with one test thread. The original ten-second deadline, SIGKILL,
independent readback, no-replay and retirement checks remain. The standalone
recovery binary's actual readiness protocol and all product code are unchanged.
Exact-source Rust 1.96 CI on `bf15a519e9192b063071e8b9b61ef3319bed416e` now
passes the complete original native UI, Root and prepared SDK workflow.
All nine workflows on that repair head succeeded. The separately retained
Calculator 5a Core/App/Session executions also exercise the corrected fixtures.

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
| P1 second target | Calculator's bounded App/Session target and independent readback have actual component evidence, and the original owner has passed scoped protocol/profile selections. The new paired Root/Core version, installed two-application windows and real task/reconnect/cancel loop remain open |
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
