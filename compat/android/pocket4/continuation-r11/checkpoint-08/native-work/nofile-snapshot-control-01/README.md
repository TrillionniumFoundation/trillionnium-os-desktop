# NOFILE=0: inherited file-table snapshot mechanism

This is a new standalone mechanism experiment. It does not change candidate05 or implement the production generation, provenance, virtual-file tag or guest-memory-copy contracts. No Main, Android or remote action was performed.

## Observed production defect

The R21 Android control had an existing descriptor and an owner started before lowering `RLIMIT_NOFILE` to zero. Native `fstat` / `fstatfs` succeeded, while projected metadata returned `EMFILE`. The owner stopped, its kernel clear-tid completed and the owned child was reaped. The raw guest representation control separately observed the same error with untouched output. This is not evidence of a startup or child-reaping failure.

The raw owner and FD owner sources used by R21 are byte-identical to the files in the actual candidate05 preparation. Candidate05's provenance file differs, so the whole file is not equated to R21. Its three `Fstatfs`, `FstatfsKernel` and `FstatfsForGuest` entry functions are independently compared in `source-binding.json`.

In `ReadPinned`, after descriptor-free context checks, the first new descriptor is `pidfd_open(caller_tid, O_EXCL)`, followed by `pidfd_getfd`. The first failure is directly returned. Later virtual-file `O_PATH` classification may require further directory/readable descriptors. These are new descriptor requirements that an ordinary native metadata syscall does not have. The actual R21 result did not include a per-syscall trace; the source identifies the allocation path rather than claiming such a trace exists.

## A mechanism that does not consume new FD slots

The calling thread performs a fixed raw clone on an already allocated stack, omitting `CLONE_FILES`. The kernel copies that calling thread's current file table, so the child inherits the existing open-file descriptions without assigning new descriptor numbers. The fixed worker directly calls `SYS_fstat` and `SYS_fstatfs` on the inherited descriptor and exits through `SYS_exit`. It does not create a pidfd, duplicate a descriptor, raise limits, or operate on another thread's descriptor number.

The copied file table supplies a concrete capture point during the metadata operation. A later close or same-number reuse in the caller does not replace the inherited open-file description. The caller retains the request and stack until the kernel clears the thread ID. The fixed worker calls no libc functions and has no TLS, stack-canary or out-of-line atomic references in the inspected local ELF.

This is an actual implementation of the mechanism in `owned_snapshot.cc`, with a complete local control in `probe.cc`. It is not a production fallback yet. In particular, the experiment deliberately does not pretend that an unverified generation is a verified application generation.

## Actual local results

Strict GCC compilation (`-Wall -Wextra -Werror`, with stack protection enabled for ordinary code and disabled only for the fixed raw worker) succeeded. The final local ELF was inspected before executing it. `out-01/binary-audit.json` binds its SHA, objdump tool and relevant disassembly. The fixed Spawn entry supplies only `OwnedFdSnapshotWorker`, the exact clone flags are `0x350900`, and the cloned child reaches raw exit through the copied R21 trampoline instruction sequence.

All five independent owned-process cases passed:

| Control | Actual observation |
| --- | --- |
| NOFILE=0 before clone | Native metadata and the inherited snapshot succeeded; a newly requested pidfd failed with `EMFILE`. |
| NOFILE=0 plus AS=1 before clone | The already allocated stack permitted raw clone and snapshot completion; all 120 raw statfs bytes matched the oracle. |
| Close / reuse after clone, then NOFILE=0 | The caller read the replacement inode; the fixed worker read the original inode and original size. |
| Bad FD under NOFILE=0 | Native and worker results were `EBADF`; the caller's published output remained untouched. |
| 24 restarts under NOFILE=0 | Every worker completed and reached kernel clear-tid before stack reuse; the caller's FD survived. |

The baseline thread pidfd succeeded before lowering the limit (returned FD 5) and then failed with raw `-24`. Thus the local probe also observes the specific new-descriptor failure, rather than attributing an unrelated permission error to NOFILE. All five outer children were reaped, no watchdog fired, and the parent retained its own limits. The raw-worker protocol creates 28 threads across these five cases, including the 24 sequential restart case; their lifecycle is checked by kernel clear-tid, not by `waitpid` on threads.

These are local host results, not Pocket4 or Bionic results. The local process is UID 0 in the managed execution namespace and would not satisfy the production owner's nonroot initial-user-namespace gate. The experiment does not relax that gate.

## Minimal production integration still required

A subsequent independent revision can add a second preallocated stack and a separately tracked clear-tid to the already validated production generation. On an explicitly classified descriptor-allocation failure in the existing pidfd acquisition path, the calling thread could run a fixed inherited-table worker. Both workers must remain covered by the existing admission/Stop gate, raw-private-fork reset and generation transition rules. The new worker must reuse the actual metadata and tag-validation code rather than replacing it with the two-syscall experimental body.

The error stage must be explicit: an arbitrary filesystem error that happens to equal `EMFILE` is not authority to substitute another path. All outputs must remain unpublished until metadata, provenance, context and lifecycle checks succeed. No fallback may return the first unpinned TMPFS statfs observation; that would revive the FD-reuse ambiguity.

Several boundaries remain open:

- A production `Start` occurring for the first time under NOFILE=0 still needs initial namespace authority; the existing startup verification allocates descriptors. The proposed fallback assumes an already validated generation. Raw-private-fork initialization under the combined zero limit requires its own explicit solution.
- A virtual root-owned `O_PATH` snapshot still needs a readable object to check its tag with the current implementation. The experimental direct stat/statfs worker does not solve that branch.
- Clone still needs a kernel task and copied file-table storage. `RLIMIT_NPROC`, task limits and kernel memory failure can cause an error even when native metadata would succeed. These controls do not claim universal resource equivalence.
- Raw workers are not registered with Bionic pthread machinery. Credential, capability, root, namespace, zygote and final-thread-exit boundaries must remain enforced by the production lifecycle design. Context sampling alone is not a transition guarantee.
- A real Android build, final Android ELF closure audit and owned application controls are required before integrating the mechanism into any engine candidate. Provenance-positive, raw/host ABI and guest EFAULT/partial-copy controls remain required.

The original R21 NOFILE red results remain unchanged. This experiment supplies a tested next mechanism, not a declaration that the defect or all applications are production ready.
