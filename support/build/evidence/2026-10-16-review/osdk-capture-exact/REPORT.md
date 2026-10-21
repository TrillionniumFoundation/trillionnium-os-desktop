# Post-capture-fix exact coverage retry

This is a new **1/1 exact coverage pass**, with zero failed, blocked or soft-skipped cases. It is **not a repeat of the full 22-case matrix**. The earlier complete matrix in `../osdk/` remains frozen on its earlier source. This retry uses the explicit `osdk-native-local-tcp-gdb-capture-v2` profile after the capture lifecycle fix; it exercises an OSTD example kernel, not complete Asterinas kernel acceptance.

`invocation.json` is the original record written **before launch**. The actual command selected only `commands::run::coverage_feature::basic_coverage`:

```sh
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb \
  --case commands::run::coverage_feature::basic_coverage \
  --output "$PWD/support/build/out/next5-osdk-capture-exact-01" \
  --target-dir "$PWD/support/build/out/osdk-capture-v2-02/target"
```

The parent observed actual tool session **72394 exit 0**; `completion.json` preserves that observation separately. No exit status is inferred from the console summary. No new guest was started for archival.

## Runtime and publication binding

The runtime environment's HEAD is `8e5187ffd274df3ae1003905fc7928e2ddd9edb3`; its tree **`a58098875a9affc51d409d3aa52ea34fccd7cd6f`** exactly matches code publication **`349a28ff9f78319e497d3fd7b58fe73b6e6e44b5`**. The environment also honestly records dirty documentation and concurrent changes. Its actual integration README bytes match later docs publication **`5f59dbb7baa34cf7c69e8730bc4642f061b36fa1`**, tree **`8d68627ba24aa38344f116f9a5662f0086d247dc`**, which equals local docs commit `fd9035d8854fde915096619422c603fafe4644f8`.

All **90** recorded source hashes match their explicit publication commits: the README is bound to the docs commit, while the other **15** support files, production OSDK, original tests and fixed local `align_ext` bytes match the code commit. `provenance/source-bindings.json` gives every comparison. The original environment/HEAD/dirty status is unchanged. This is a post-execution byte binding, not a claim that the dirty execution worktree equalled its clean HEAD tree.

Asterinas remains v0.19.0 commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`. The environment retains the actual compiler and Cargo paths, SHA256 and verbose versions for `nightly-2026-07-21`, plus fixed dependency lock hashes, original/adapted test hashes and exact harness patch. The reused isolated target is not copied into this archive.

## Actual guest and coverage

| Evidence | Actual value |
| --- | --- |
| Guest count / QEMU PID | 1 / 560 |
| QEMU / OSDK / GDB exit | 33 / 0 / 0 |
| Hardware breakpoint PC | `0xffffffff880edfc0`, equals resolved `ostd::arch::power::try_poweroff` |
| Raw profile size | 2,094,456 bytes, exactly this guest's announcement |
| Raw SHA256 | `a6a60289f3e9fed6c3f6ad17f1108e1a44aac61cac313e8ebc3b1611288eb9a1` |
| Pinned LLVM merge/show | Both exit 0; 5696 functions, maximum count 383731 |

The original OSTD shutdown and ISA debug-exit remain. GDB stops before the original poweroff, reads the same complete serial coverage announcement, saves fresh memory, removes its breakpoint and detaches; the guest resumes and exits with raw 33. The finalized capture sidecar binds symbol ELF, boot ELF, exact PC, announcement, paused/final serial and raw profile. No stale or preexisting raw file was accepted.

The actual OSDK-managed monitor is a private connected inherited **FD 64**, not a listening endpoint. QEMU argv retains the named `osdk-managed-monitor` descriptor and its metadata binds actual QEMU PID 560, connected loopback local/peer addresses, and closed parent copy. The separately owned GDB loopback listener is inherited as FD 3 without a bind/close/rebind gap. QEMU uses x86_64 q35/TCG, CPU `max`, one vCPU, 512 MiB, explicit SeaBIOS and direct multiboot. Exact raw argv, PIDs, serial bytes and capture command remain archived.

## Archive integrity

The frozen hardened `archive.py` actually processed this completed run into a new scratch destination, selecting **60 files**. Its original **61-entry** checksum file and original index are retained under `provenance/`. Every source/helper size and digest was checked; `helper-compatibility.json` maps the historical helper names to the original raw tar content or separately compressed coverage artifact. The original helper checksum file describes that scratch output; `SHA256SUMS` describes the committed files here.

`logs.tar.gz` contains **60 original members**, including complete serial, debugger/nm/LLVM/console output, command metadata, locks and exact adaptation patch. It was finalized by atomic replacement, reopened, and every member's size/SHA checked against `members.json`. The actual source serial, helper snapshot, tar bytes and QEMU expected size/SHA all agree. Two `.profraw`/`.profdata` gzip artifacts have both compressed and original digests in `artifacts.json`. Key JSON is also readable as byte-identical copies. Target trees, generated example implementations and tool binaries are excluded. `SHA256SUMS` covers all final files except itself.
