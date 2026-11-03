# Native family user-data memory budget qualification — 2026-10-23

This evidence closes the bounded user-data frame-accounting slice of the resource work. It does not close the entire resource, recovery, F1, G2, or hardware milestone.

## Qualified source and results

The executed product source is `5768423844c4258e4c9cb5ffaa4046896a9709a0`, tree `745f305fdee487b9e717f8b3a0f63ff55f2d9666`. The archive commit is an evidence-only descendant; it is not the source used to build these kernels.

| Gate | Actual result |
| --- | --- |
| Complete aster-core guest suite | 281 passed, 0 failed, 0 filtered, 0 soft skips, 281 observed test starts; raw QEMU exit 33 |
| Original 64 MiB family budget | Positive oracle passed; family sharing across fork/exec, anonymous/shared/COW/file-backed faults, file writes, independent recovery effect/readback, and retry after physical-page refund all observed |
| Counterfactual, only 64 MiB → 128 MiB | The same probe reaches the exact `memory_aggregate_limit` failure; positive oracle is false, strict counterfactual oracle is true, raw QEMU exit 33, no timeout |
| Host oracle regression | The retained original host-oracle result/log records the 9-case parser regression run; it is not native evidence |

The positive result SHA256 is `8dfc206f3e9c8b358b0d6326fc23362305fbee0a2341ce4422da1981e3ef363d`. The strict counterfactual result SHA256 is `ecd22977180d751c9da5e364568058a8b9eed4ab95e10bdedb8adda6743855a7`. The complete core result SHA256 is `7a59b6d06cd5150ea89065e73c4f78c4671495c2ecf9a2110b69de3cc02a57a6`.

The counterfactual source is `778d061c584470a6419b08874a757981426f78f2`, tree `09f1fc8b95f310188a1abf052f1c259aca9dbcfa`. Its exact diff and source identities are retained. It is a test control only and must not be merged as the product implementation.

Both native runs used the identical static probe SHA256 `f216bfef106fb3c6d27a90ba2fbbc2a58d738eb7298c1973879450e4f3e61521`, identical initramfs SHA256 `cbd49f64a52e1766548fb3bec40cfded18f03b77ce6bbbcfa2acf9a82304490d`, the g1d-trusted-control ActionChoice::Run profile (without --cfg ktest), one emulated x86_64 CPU and 512 MiB RAM. The original fixed dependency lock remained unchanged.

## What the native positive run establishes

The sealed workload family receives one immutable 16,384-page account before resume. Fork and exec preserve the account identity. Physical user-data frames are precharged before allocation and refunded only when the last physical-frame reference is released; mapping the same frame again does not charge a second frame. Anonymous, backed-VMO, copy-on-write, file-I/O, contiguous-allocation and DRM-shmem allocation paths use the account.

Two real 18 MiB holders (one fork, one fork/exec) share the third process's allowance. The third process cannot fill its own 64 MiB allocation. The probe requires quota provenance at the expected PIDs/addresses for the four fault paths and bounded file writes; an unrelated allocation failure does not pass. An independent original recovery role then performs a real recovery operation and reads the result. After the held physical pages are released, the failed mappings can be retried, COW contents remain intact, and all children are reaped.

The negative changes only the page limit to 128 MiB. It admits the same two holders and complete third allocation, so the unchanged positive acceptance boundary is violated at the expected check. A generic crash, build failure, unrelated guest error, timeout, missing marker or truncated log is not accepted as that negative.

## Limits that remain open

This is user-data physical-page accounting for the sealed g1d workload family. Ordinary init/F1 processes do not acquire this account merely by running. General kernel heap/slab, page tables, networking metadata, reclaim and OOM selection are not covered. This is not a Linux memory.max controller.

The manager and recovery roles have separate accounting identities, but these receipts do not establish a global physical reserve, preallocated recovery metadata, an active watchdog, recovery under global kernel-heap exhaustion, or SMP qualification. Hepta writer durability, post-exec role authority, native F1/F2, physical x86 hardware and mobile qualification remain separate gates. The machine-readable receipts retain all corresponding flags as false.

## Preserved failed attempts

Earlier rejected attempts are retained beside the successful run. They include stale source-embedded OSDK/align_ext selection, a preflight source-cleanliness rejection caused by generated Python cache, and an OSDK built without compile-time OSDK_LOCAL_DEV=1 whose generated dependency graph was rejected by the unchanged --locked gate. No one of these failures is counted as a negative guest pass. The successful runs use the existing install_osdk target, correct source-local OSDK and the original lock.

## Evidence layout and reproduction

`manifest.json` records the original absolute path, exact raw SHA256 and byte count of every captured file. Text larger than 64 KiB is losslessly gzip-compressed with mtime=0; both stored and raw identities are recorded. Complete serial streams, build logs, invocation/exit receipts, source snapshots, generated locks and failed attempts are included. Large executable, initramfs and Python cache files are recorded by identity rather than duplicated in Git. Every copied/compressed artifact was decoded and compared to the source bytes before commit.

Reproduction commands and acceptance rules are in [G1D_USER_MEMORY.md](../../../tests/kernel/control/G1D_USER_MEMORY.md). Use a fresh output directory, the pinned compiler, the original lock and the exact source head/tree. Build the supplied counterfactual patch only in a separate disposable worktree. The original runtime receipt paths and hashes are retained for direct comparison.
