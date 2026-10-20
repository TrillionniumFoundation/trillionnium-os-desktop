# Explicit local TCP and GDB coverage evidence

The explicit GDB capture profile completed one real **22/22** OSDK integration run, with **one VMX-unavailable soft skip**. These are tooling and small OSTD example kernels. Complete Asterinas kernel boot/debug evidence belongs to the parent phase, not this matrix.

| Evidence directory | Profile | Selected | Passed | Failed | Source binding |
| --- | --- | ---: | ---: | ---: | --- |
| `v1-pilot-01` | `osdk-native-local-tcp-v1` | 3 | 2 | 1 | Initial TCP implementation; recorded differences retained |
| `v1-pilot-02` | `osdk-native-local-tcp-v1` | 3 | 2 | 1 | All 11 support files match `c3c80f9a1aac63ca33b6a168deb20d74ca6763b1` |
| `v2-exact-01` | `osdk-native-local-tcp-gdb-capture-v2` | 1 | 1 | 0 | v2 code; README still from v1 |
| `v2-full-22` | `osdk-native-local-tcp-gdb-capture-v2` | 22 | 22 | 0 | All 13 support files match `fa9b6cd6be310155b10fa36aafcb8896444e0f6e` |
| `v2-guard-exact-01` | `osdk-native-local-tcp-gdb-capture-v2` | 1 | 1 | 0 | All 13 support files match `1cc76b90dfd162e18a946a01e0bcaa31b8e03b4f` |

Every historical result is retained independently. No results are combined into a synthetic full run. The original Unix profile's 20/22 and two AF_UNIX failures remain in the previous `2026-10-16-native-integration/osdk` archive unchanged. This phase has no automatic transport fallback.

## What ran

The source remains Asterinas v0.19.0 commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, with Rust `nightly-2026-07-21` (rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48`). Each environment record includes actual Cargo/rustc executable paths, SHA256 and verbose versions. Cargo is locked to the original OSDK/root external package identities; the adapters restore the fixed compiler and disable automatic Rust installation.

The full matrix started with actual GDB basic and VS Code cases, then executed the remaining 20 cases sequentially. All **11 actual QEMU guests** exited with raw status **33**. The hypervisor example printed the upstream VMX-unavailable fallback; accepting that case does not establish working VMX virtualization. QEMU uses x86_64 q35, TCG, CPU `max`, one vCPU, 512 MiB, explicit SeaBIOS and direct multiboot. Raw QEMU/OSDK/GDB statuses, actual arguments, kernel and serial hashes remain in the records.

Reproduce the explicit complete profile from the repository root with native host tools and the fixed toolchain available:

```sh
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb \
  --output "$PWD/support/build/out/osdk-gdb-capture-new"
```

`invocation.json` records each actual selection, output and cache path; these top-level command records were transcribed after execution and are labelled as such. Each case's harness/OSDK/Cargo/QEMU command records were produced during execution. Each output must be new; the runner holds a persistent shared-cache lock. The short owned `/tmp/a01oi-*` scratch roots and their inode-bound cleanup records are retained. No preexisting host `/tmp/myos` or similar project paths were deleted.

The isolated test harness retains its exact adaptation patch: owned scratch paths, the fixed original OSTD anchor, local fixed `align_ext` 0.1.0, and the explicit TCP debugger/readiness adaptation. Original debugger/guest assertions remain. Production OSDK TCP monitor support is published at `54356654b0c88c1b0bec85cfdb4d7911839c6a3e`: OSDK owns an ephemeral loopback listener and QEMU connects as a monitor client. The recorder passes its separately owned GDB listener FD directly to QEMU, avoiding release/rebind races. No public GDB or monitor listener is used.

## Failed transport-only coverage and explicit debugger capture

Both v1 pilots really passed basic GDB and VS Code, then failed coverage. The monitor TCP connection worked, the guest announced `0xffff800010400000` and **2,094,456 bytes**, and original ISA debug-exit ended QEMU with raw **33** before the monitor obtained a dump. No profile file was accepted. The second pilot records actual OSDK exit **0**, while the coverage harness returned **101** for the missing dump. The first pilot predates the added source-OSDK-exit field/guard; its missing field is not retrospectively invented. v1 requires a genuine monitor dump/quit with raw QEMU **0** and remains a failure.

v2 explicitly collects coverage under GDB while preserving original OSTD and ISA debug-exit. Real `nm` resolves the original EM_X86_64 symbol ELF's `ostd::arch::power::try_poweroff`. Real GDB installs a hardware breakpoint and proves actual PC **`0xffffffff880edfc0`** equals the resolved address. At this point the original OSTD has completed its coverage announcement. GDB reads the same live serial stream, saves exactly the announced bytes through HMP to a fresh absolute path, removes its breakpoint and detaches. The guest then resumes its original shutdown and exits QEMU with raw **33**. OSDK and GDB must both exit **0**.

| Run | Raw profile SHA256 | Bytes | LLVM functions | Maximum function count |
| --- | --- | ---: | ---: | ---: |
| v2 exact | `39af13905ca147db1d5dbaf3ff5c986513edb46f9b4ffac24165cbf52d05d33e` | 2094456 | 5696 | 383731 |
| v2 full 22 | `9d564c13b2747da71c8353ff53214961d199726a1c4a7a9fb97d532a2e5d5764` | 2094456 | 5696 | 383731 |
| v2 guard exact | `da25dd71ac3710e00cf116f408c71c124218f30fa1a35f58bd61e145ecad7d57` | 2094456 | 5696 | 383731 |

The finalized capture sidecar binds the symbol ELF, wrapped boot ELF, exact breakpoint/PC, announcement, paused serial prefix, final serial log and raw profile. The pinned nightly `llvm-profdata merge/show` actually succeeded with nonzero functions and counts. Missing, stale, altered, timed-out, abnormal-exit or inconsistent capture evidence fails acceptance.

The final guard adds rejection of fatal-panic serial markers specifically to v2 coverage. Negative tests include plain and ANSI CSI/OSC-hidden panic markers even after an adversary updates all serial/sidecar digests. It does not change expected-panic kernel tests or the default/v1 profile. The guard received **16 related pure tests** and **one new real exact coverage pass**. The complete **58 pure tests** and **22-case matrix** were run on the preceding `fa9b6cd` source, not rerun after this guard.

## Host evidence and source provenance

`provenance/monitor-transport-source-ready.json` records the production transport's first full **34 passed / 1 failed** host suite, an isolated listener pass, the final full **35/35** pass, and integration compilation. All four original logs are in `monitor-transport-logs.tar.gz`, indexed by `monitor-transport-members.json`. The initial immediate-rebind assertion was changed to allow bounded release; no transient holder was identified, so its cause is not invented. The final production change after the pilots only corrects misleading shutdown log wording; its exact inverse-replacement hash is recorded.

`provenance/pure-test-invocations.json` binds the actual **40**, **58**, and **16** pure-test logs, counts, commands and publication commits. `next4-osdk*-source-hashes.json` retains the frozen source hash records. `published-source-bindings.json` compares every execution-recorded support and production source digest against the published Git blobs, including historical differences. Original execution `git_head` and dirty status remain unchanged: later publication commits are source-byte bindings, not rewritten execution histories.

Each run's `logs.tar.gz` contains selected complete logs, actual failed/successful commands, dependency locks, metadata, exact harness patch and real GDB script. `members.json` lists every member's original size and SHA256 plus the archive hash. Key JSON is also readable beside the archive. `artifacts.json` binds compressed `.profraw`/`.profdata` to their original bytes and hashes. The archives exclude target trees, generated example implementations and tool binaries. `SHA256SUMS` covers every final file except itself.
