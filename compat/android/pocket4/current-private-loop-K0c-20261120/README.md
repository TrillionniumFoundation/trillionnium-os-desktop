# K0c: closed private-loop lease and block-entry foundation

This source successor adds actual kernel reference objects and closed entry gates to the exact Linux 6.18.64 + K0b source. It does not grant access to a private loop device. The Rust issuer remains unavailable. Android, original apexd qualification, app runtime acceptance and production readiness remain false.

## Implemented source

The lease retains the exact K0b controller and actor objects. Its generation is allocated by a saturating atomic compare/exchange and is never zero or reused. A lease binds at most one target for its entire lifetime; a target binds at most one real original open-file description, including after that association is released. The only states are `FENCED` and `REVOKED`.

The authorization object takes its own `get_file()` reference and its own target reference. It checks the actual whole block mapping, native `def_blk_fops`, O_RDWR access and exact file pointer. It never replaces `file->private_data` or native holder bookkeeping. A successful custody observation does not make any operation gate succeed. Final puts remove the association under its spinlock and release file, target and actor references outside the lock.

A target can attach only during exclusive kernel ownership of a new unpublished, unopened, zero-capacity disk with no page cache, partitions, device number or registered queue/BDI. These are internal construction preconditions, not claims supplied through JSON, a PID or a path. The target marker is removed only at native final `disk_release`. BDI gets a one-way closed marker instead of a borrowed target pointer because native BDI references may outlive the disk.

All marked disk/file/BDI gates return denial. No ACTIVE state, UAPI, ioctl constructor, exported module symbol, allocator, permit or userspace issuer is introduced. The default Kconfig value is `n`; the implementation requires the original built-in loop driver and K0b actor support.

## Entry coverage and retained native behavior

| Entry family | Actual source boundary |
| --- | --- |
| Native file and kernel by-path/by-dev opens | Common `bdev_open`, before holder claims and driver effects |
| Read/write/seek/sync/mmap/fallocate | Actual block-file handlers, before cached access or mutation |
| Splice | Narrow wrappers before the original generic splice helpers, including cached reads |
| Native/compat ioctl and io_uring | Both common file entry points, direct compat forwarding, uring command entry and loop driver callbacks |
| BIO and loop request submission | `submit_bio_noacct`, nocheck resubmission, final submission and loop request admission |
| Global publication | Common disk registration, direct `bdev_add` inode hashing, independent queue and BDI registration |
| Partitions and geometry | Add/delete/resize/scan, direct partition reads and nonzero capacity changes; zero remains available to original invalidation |
| Queue sysfs and loop attributes | Central queue show/store dispatch and loop show dispatch |
| BDI mutation | All eight original store families, independently of queue read-ahead |
| Global loop discovery/removal | Marked targets cannot be returned by GET_FREE or mutated by the global remove path |

Completion polling, original driver release, native block-file release, holder release, request completion, queue drain and final BDI cleanup are preserved. An async worker is not reclassified as the original actor. The closed stage admits no private I/O. K2/K3 must add retained I/O/graph authority and real cancellation/drain before any admission gate is opened.

The source controls compare 28 original probe, cleanup and completion function bodies byte for byte. They also compare every original `private_data` assignment, all four inherited K0b files and exact forward/reverse patch application. These are finite preservation checks, not execution tests.

## Actual matching compilation

The isolated ordinary-owner Pocket4 R2 job compiled **24 C objects** with the actual matching GCC 15 recipe, all 43 original generated C headers and the original objtool. Fifteen objects exercised the enabled declarations and nine exercised the default-disabled gates. The two enabled P4 macros are explicit compile-only inputs; no original `.config`, generated header or source tree was changed. This is not a full Kbuild configuration selection or kernel link.

The actual record contains **121 commands**, **1,076 unique C dependencies** and **1,148 retained input descriptors**. Dependency lists from the preflight scan and actual compiler match. Complete SHA-256 and nine-field descriptor/path identities were rechecked. Every command exited zero, every child was reaped and every stderr was empty. All **242 original stdout/stderr bodies**, totaling 292,873 bytes, were independently read back and compared to their receipt pins and exact version identities.

- `OBJECT-COMPILE.json`: 1,616,986 bytes, SHA-256 `8e0e4ea16f225c0b531eea33fc8f74e781a5f3e80984ee1c1acf7ae6582f3204`.
- `ACTUAL-LOGS.json`: 382,919 bytes, SHA-256 `31e1b8c051f2b5e3fe755a22ec4e609dc6a8123eab6f7930506e9bb4a1a467e9`.
- `ROOT-INDEPENDENT-SOURCE-REVIEW.json`: 3,033 bytes, SHA-256 `34628254a219fda2d64de2003b47d154b25064cec887a2571cde099286a35d56`; independent review of the exact closed foundation, with runtime explicitly false.

The initial R1 compile stopped after nine objects when the runner incorrectly used `backing-dev` in the assembler module token. The complete R1 receipt and diagnostics are retained. The correction follows the actual `scripts/Makefile.lib` name-fix rule, replacing hyphens and commas only in module/basename tokens. The K0c C/header postimages did not change. R2 used a distinct create-only directory and completed all 24 objects.

## Limits and next source stage

This closes the source and matching-object part of K0c only. A coherent full kernel build is still required because `gendisk` and BDI internal layouts change. No kernel was linked, installed, loaded or executed; no VM or Android was started. The original apexd binary and original Android data/metadata were untouched.

K1 must construct a real private realm/control and private allocation without using the global loop IDR as authority or exposing aliases. Its unpublished block OFD constructor must preserve native open/release and holder accounting; controller and actor commit timing need another review. K2 must admit only the exact original same-OFD native probe and source configuration, then bind the real dm-verity/AVB/mount graph and I/O references. K3 must cover exit/revoke, unknown results, native unbind, completion drain and terminal generation retirement. The previously rejected kernel/VM execution remains outside this source/object work.

## Reproduction

`prepare.py` reproduces the 15 new/changed postimages from pinned original bodies and retains the four exact K0b sources. `check_source.py` performs the finite preservation checks. `prepare_compile.py` creates the complete source packet and bounded compile runner. Host evidence records the exact create-only execution roots and arguments. Historical receipts and their pins are not rewritten to claim a later stage.
