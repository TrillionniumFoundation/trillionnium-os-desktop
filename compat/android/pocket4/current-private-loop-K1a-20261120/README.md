# K1a: unpublished native loop allocation

This successor adds a real native loop/blk-mq allocator behind the unchanged K0c closed gates. It creates no control FD, block FD, device node, global loop index, major/minor allocation or userspace operation. The runtime issuer remains empty. K1 as a whole is still incomplete.

The exact parent is K0c commit `f83f52dde3594d7eef4a1e44785f940c824467d5` (PR #337). `K1a.patch` contains five new or changed postimages; the other sixteen source bodies in `candidate/` are byte-identical to that parent. This packet records an independent source review and three actual matching C-object/objtool checks. It contains no kernel execution evidence.

## Native ownership and retirement

The new internal realm retains the original controller and actor references, the corresponding held actor task, a bounded number of reserved slots, and a mutex-protected list of allocations. The constructor accepts retained kernel objects, not a numeric PID. The fixed policy is supplied by the kernel owner; the source ceiling is 256 devices and no production value is selected here.

Allocation reserves both a quota slot and a realm reference before sleeping in the native allocator. It creates a distinct K0c lease and generation, then uses the real `blk_mq_alloc_tag_set` and `blk_mq_alloc_disk` APIs with the original loop request operations. The loop object is unbound, its global index is deliberately absent, and its disk has zero capacity and no device number. `p4_private_loop_target_attach` applies the already reviewed closed target and BDI markers.

The final controller/actor/revocation bookend runs after native allocation. If that bookend fails, the return code is negative **and the caller still receives the exclusively owned cleanup handle**. The caller must retire it. Returning an error does not discard the actual resources or release the quota early. Revocation stops further construction and revokes retained leases without destroying live allocations.

Retirement is independent of whether the actor still exists. It requires the actual disk to remain unpublished, with no openers, partition users, capacity, device number, registered queue/BDI, cached pages, backing file or loop work. It marks the native loop deleting, releases the never-added disk and queue, frees the native tag set, then frees the loop object. A refusal retains the handle, slot and all references and revokes the realm.

This is the original native never-added lifetime order. In this exact kernel, `disk_release` drains and exits an owned blk-mq queue when `GD_ADDED` was never set; it calls the driver's `free_disk` callback only for added disks. The new path therefore calls a shared `loop_free_device` after `put_disk` and tag-set cleanup. The original `lo_free_disk` now delegates to the same cleanup statements. The complete original loop body can be reconstructed byte-for-byte by removing the addition and reversing that small extraction.

The original block file's `private_data` holder field is untouched. The new assignment to `disk->private_data` is the normal loop-driver assignment to its `loop_device`; these are different objects. No new module export or userspace constructor is introduced.

## Validation actually performed

`SOURCE-CONTROLS.json` records a real forward/reverse `git apply`, exact equality of all five postimages, equality of all sixteen inherited source bodies, and the complete inverse transformation of `drivers/block/loop.c`. Original loop allocation, removal, configuration, support-probe, worker, completion and release behavior is retained outside the documented same-body cleanup extraction. `ROOT-INDEPENDENT-SOURCE-REVIEW.json` records the separate full diff and native-lifetime review.

The ordinary Pocket4 owner ran `/home/alex/work/p4-private-loop-k1a-20261120-3b9d-r1/compile_objects.py` in isolated output directories. The original 6.18.64 source tree, GCC 15 executable, 43 generated headers, configuration, and objtool were held and fully hashed. The previous actual K0c receipt was also pinned. The operation used CPU 23, one compiler job, a 2 GiB memory/address-space bound, and the same bounded child PIDFD/reaper protocol as K0c.

| Mode | Actual C object | Result |
| --- | --- | --- |
| Actor, lease and realm feature macros enabled | `block/p4_private_loop_realm.o` | GCC and original objtool passed |
| Actor, lease and realm feature macros enabled | `drivers/block/loop.o` | GCC and original objtool passed |
| Features disabled | `drivers/block/loop.o` | GCC and original objtool passed; no private-loop symbol dependency |

All sixteen child commands were actually reaped. The actual compiler dependency scans and compile dependency files agreed: 692 unique C dependencies and 765 retained inputs passed complete-body SHA256 and F9 bookends. The 32 original stdout/stderr files were independently read back with their original whole hashes, sizes and exact immutable version strings; they total 27,340 bytes and are retained in `actual-logs/`. The outer job completed with exit 0, 299 stdout bytes and zero stderr bytes, without timeout, cancellation or truncation. `ACTUAL-LOGS.json` preserves the independent transport observations; `OBJECT-COMPILE.json` is the complete original receipt.

The feature macros were supplied to the isolated C compilation only. Kbuild configuration selection, full kernel linking, kernel loading, a VM, Android, and a private allocation at kernel runtime were not performed. The frozen `MANIFEST.json` remains the source-candidate input consumed by that actual compile; its initial false validation fields are not retroactively rewritten. The later receipts and `HANDOFF.json` contain the actual completed source/object results.

## Remaining K1–K3 work

K1 still needs authentic native control and S_IFBLK file objects, a private device lookup/index namespace, exact original ADD/GET_FREE/index behavior, and lifecycle rules for aliases, by-device opens and received or reopened FDs. The block core's native open, holder, LSM and release semantics must remain intact. A regular or anonymous file with a block-like name cannot satisfy this requirement.

K2 must connect the original unmodified support probe and configuration to retained source/geometry and actual loop state. K3 must bind real dm/AVB/mount users, asynchronous I/O completion and graph retirement. These need independent interfaces and qualification; the closed allocator does not authorize them. The original patched-kernel VM rejection remains in force. Nothing in this packet enables an issuer, changes `CURRENT`, touches original Android images, installs a kernel, or establishes production readiness.
