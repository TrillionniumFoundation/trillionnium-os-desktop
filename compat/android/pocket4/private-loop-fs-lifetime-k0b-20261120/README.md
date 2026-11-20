# K0b: independent `fs_struct` lifetime references

This is a source successor to the exact K0a commit `0bf19546e570a80247a5982d292de463cf0f4496` in [PR #326](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/326). The four-file kernel patch fixes a concrete defect in K0a: retaining an observation must not increment the `users` count that Linux uses for shared-filesystem, exec, unshare and namespace-entry decisions.

**Five actual C objects and the original objtool checks passed on Pocket4. This is not a complete kernel build or an enabled private-loop implementation.** The `fs_struct` layout changes, so these objects must never be mixed with a kernel or modules built against the previous layout. No kernel was linked, installed or loaded. No VM, Android process, loop device, issuer or grant was started or issued.

## Exact source boundary

| File | Change |
| --- | --- |
| `include/linux/fs_struct.h` | Adds a separate `refcount_t refs` and internal lifetime-only get/put declarations. |
| `fs/fs_struct.c` | Initializes one aggregate ownership reference in `init_fs` and the only allocator, `copy_fs_struct`; final lifetime put performs the existing path releases and slab free. |
| `block/p4_private_loop_actor.c` | Acquires/releases only an independent lifetime reference; compensates the original observation test for removal of its extra `users` slot. |
| `include/linux/p4_private_loop_actor.h` | Documents the corrected ownership and its remaining limits. |

`K0b.patch` is **5,959 bytes**, SHA-256 `94e4927b9669b7f7cfd19c1ce3e0c2c37ef85a5db51a1418e608a91aa9f7d6bd`. `MANIFEST.json` contains every exact preimage and postimage pin. Local forward application and independent forward/reverse application reproduce those bytes exactly.

The fixed source is Linux **6.18.64**, the original reviewed 66-file candidate patch, and K0a. The complete original source audit is `FIXED-FS-LIFETIME-AUDIT.json`, **89,735 bytes**, SHA-256 `3e50402974edc061da06e8eff21dc0f8a12b648d8b5b384c06ed0da182586f82`. It records a real complete-tree C/header search and full-body, nine-field identity bookends for the 19 files containing allocation, ownership or relevant access predicates. All 66 candidate postimages and all four K0a postimages were also rechecked.

The original `kernel/p4_guest_mntns.c` remains **11,777 bytes**, SHA-256 `9807e3b53684b59796e73c33bcac78bdb9e81a3f5ea886d2b6c39866e6f4efcc`. That existing grant deliberately holds a counted `users` slot: mint requires one, a live grant requires two, and its consumption/release retires the extra slot. Converting it to an ordinary observer reference would change its exclusivity rule. K0b leaves that source and its `users`, `in_exec`, credential, namespace and capability predicates byte-for-byte unchanged.

## Lifetime and concurrency

The new count contains **one aggregate ownership reference for the existing `users` discipline, plus independent observers**. It is not the count of tasks. Existing clone, exit, exec, unshare and grant decisions continue to consult their original `users` value. Neither new get nor new put reads or writes `users` or `in_exec`.

| Existing path | Aggregate ownership and observer behavior |
| --- | --- |
| `init_fs` | Starts with `users = 1` and `refs = REFCOUNT_INIT(1)`. |
| `copy_fs_struct` | Initializes `users = 1` and `refs = 1` before publication; path references are acquired exactly as before. |
| `CLONE_FS` | The existing `users++` remains unchanged; the aggregate reference stays one. |
| Last-user `exit_fs` or `unshare_fs_struct` | Original locking, decrement and zero test remain unchanged. `free_fs_struct` drops the aggregate reference after the original locks are released. |
| `ksys_unshare` cleanup | The existing call drops either the retired old aggregate or a never-published new copy, exactly once. |
| Temporary `nsset` copy or failed grant copy | Original cleanup retires the unpublished copy's initial reference. |
| Existing mount grant | Its counted slot and last-slot free remain unchanged; observers no longer interfere with the grant's one/two-slot rules. |
| K0a capture | Under the existing `task_lock` then `fs->seq`, a positively counted task fs keeps the aggregate alive while `get_fs_struct_ref` takes an independent reference. |
| K0a final destruction | `put_fs_struct_ref` runs outside those spinlocks. The allocation and original fs paths are freed only when the last aggregate/observer reference is gone. |

Capture cannot race the task's detach while it holds `task_lock`. An independent observer that already owns a reference may take another; no operation resurrects an unowned or zero-count pointer. If the last counted owner exits first, its aggregate put leaves any observer reference alive. If observers leave first, the aggregate keeps the allocation alive. Concurrent final drops use the kernel's `refcount_dec_and_test`; exactly the final drop executes the original destructor.

The unchanged original task and fs identity checks still reject a detached or changed context. The observation's old `users >= 2` test becomes `users >= 1` because capture no longer contributes a slot. The original `INT_MAX` rejection, `in_exec`, sequence, umask, root/pwd, exact thread, credentials, mm and namespace checks remain in place. The observer can still delay allocation/path destruction. It does not establish a durable access decision, serialize credential replacement, prove mount-graph stability or give a private block-device identity.

The independent review, `INDEPENDENT-SOURCE-REVIEW.json`, is **5,684 bytes**, SHA-256 `484dd7f33e4e451d7513658d1f390406788234d9830898f47bea479ad08f467d`. It additionally read the complete original fork/exec/exit/nsproxy/user-namespace and grant sources and checked the cleanup chains. This is a source review, not a runtime race test.

## Actual bounded compilation

The existing K0a source tree and configuration were read only. A new overlay contains exactly the four reviewed postimages. A new output directory contains exact copies of all **43 actual generated C headers** and the original configuration. All objects were compiled serially using CPU **23**, a **2 GiB address-space limit**, and one **220-second** total internal deadline. The actual host job was `1a1f93abfe7-ffbe-18f4`; it exited zero with complete, durable stdout and empty stderr.

The compiler is the same `/usr/bin/x86_64-linux-gnu-gcc-15` used for K0a. The recorded original compile recipe retains its architecture, hardening, instrumentation and diagnostic flags, with explicit per-translation-unit path/name substitutions and the two-header overlay include directory. The actual source Makefiles were pinned and contain no special per-object flags for these selected units. The original objtool binary and argument set were used for each resulting object. This was direct translation-unit compilation, not Kbuild configuration selection or a full link.

| Actual object after objtool | Bytes | SHA-256 |
| --- | ---: | --- |
| `fs/fs_struct.o` | 261,216 | `94386ddc76758ce6d67f03b066ea9fcb5ad487b93c769db3770ab7df2542dab4` |
| `block/p4_private_loop_actor.o` | 192,408 | `73c49dec9e39fa17b6913a0e3fe5732bf40ecf19db94f240980fc773695b265a` |
| `kernel/fork.o` | 1,133,128 | `ed0ec88a9387c858b755597b06bfeed0cb10c963381638b7cd91db61064e09ca` |
| `fs/exec.o` | 729,704 | `fa0df830523d084bd841c67733a3d2bbde140bae4a5792bf6ff8bf342ca7465b` |
| `kernel/p4_guest_mntns.o` | 418,528 | `86048ad01d744157fd2091c55901e4dc719bf2c97bc45b42c36c182cfe86d0e0` |

There were **27 actual commands**, **951 unique C dependencies** and **1,076 retained original input descriptors**. Each translation unit used the new `fs_struct.h`, and the original version was absent from its actual dependency closure. Compiler-produced dependency lists matched the preflight lists. All full-body SHA-256 and nine-field descriptor/path identities were rechecked. Every compiler and objtool stderr was empty. The real symbol tables show the new fs definitions and the actor's calls to those definitions; the actor no longer calls `free_fs_struct`.

Complete evidence is retained without substituting a summary for the originals:

- `OBJECT-COMPILE.json`: **1,037,582 bytes**, SHA-256 `85262fa4a4fa8ad9a31d6f68fc70115429a14c17131c542cc560a5edd128e803`; the complete original host receipt, including commands, flags, dependencies, retained references and object pins.
- `ACTUAL-LOGS.json`: every original stdout and stderr body for all 27 commands, matched to the receipt's full file identity and hash.
- `HOST-JOBS.json`: actual launch, terminal state, whole original terminal bytes and independent receipt file information.
- `SOURCE-PACKET.json` and `compile_objects.py`: exact inputs and runner used on Pocket4.
- `OBJECT-COMPILE-SUMMARY.json`: a navigation summary of the original evidence, with all kernel/runtime qualification flags false.

The actual object files remain in `/home/alex/work/p4-private-loop-k0b-20261120-3b9d-r1/out`. Their hashes are preserved; they are not deployable kernel replacements.

## Remaining implementation and acceptance

This closes K0a's specific observer-count source defect and its matching-object compile requirement. It does not close the original APEX blocker. The design in [PR #319](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/319) still requires a real isolated block-device subsystem, complete access/lifetime coverage, original actor and mount-graph binding, and a genuine target issuer. No ordinary host unconfigured loop is exposed, no errno is synthesized, and the original apexd/init or production gates are not changed.

Before any activation, the complete kernel and all relevant modules must be rebuilt consistently against this layout. Real lifetime/concurrency acceptance must cover last-user exit with retained observers, all observer-first/owner-first release orders, clone/unshare/exec transitions, failed unpublished copies, and unchanged existing-grant exclusivity. Such runtime tests have not been executed here. They require a separately permitted test environment; the previously rejected privileged patched-kernel VM fixture must not be retried through a different tool, key, agent or equivalent action.

Subsequent work must continue from these exact source and object evidence pins. It must preserve the empty private-loop issuer until the actual isolation API and all original positive and negative runtime checks are implemented and passed.
