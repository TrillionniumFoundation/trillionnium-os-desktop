# New owner candidate for descriptor-allocation EMFILE

This is a separate, unqualified source revision. Candidate05 and its active Go4 build are unchanged. The actual production owner source compiles locally, but its new positive path has not run under a qualified nonroot application context or Android.

## Change

The existing persistent worker still attempts `pidfd_open(caller_tid, O_EXCL)` and `pidfd_getfd` in its private file table. The request now records which of those two acquisition stages failed. Only `EMFILE` from one of those stages activates the new path. Errors from `fstat`, `fstatfs`, xattrs, seals, context checks or `O_PATH` reopening are preserved without retry.

Initialization reserves a second 128 KiB usable stack and its guard page alongside the existing stack. On the qualified allocation failure, the actual calling thread invokes the fixed raw clone trampoline with `CLONE_FILES`, `CLONE_FS` and `CLONE_SETTLS` absent. The kernel copies that calling thread's existing descriptor table. `InheritedWorker` reads the target through the same `ReadPinned` implementation, selecting the already inherited descriptor instead of allocating a pidfd and duplicate. Its file table is private, so caller close/reuse cannot replace the inherited open-file description.

The worker uses the existing context, root ownership, shape, xattr, seal and final-inode checks. It does not return the earlier unpinned TMPFS observation, infer provenance from a display name, or construct a raw ABI result from normalized libc data.

The caller holds the existing Gate and full signal-mask scope until the kernel clears the new thread ID. Only then are the request result and context status consumed. The original final caller-context checks, raw/host ABI conversion, output publication and errno restoration still run. Stop cannot pass the Gate while this request is active. Private-memory fork reset clears the copied second thread ID while retaining both private stack mappings. Shared-VM process rejection is unchanged.

## Authority preserved

The new path is reachable only from an already started and admitted owner generation. `ReadContext`, `SameContext`, `VerifyInitialUserNamespace`, the persistent worker's initial namespace verification and the final caller-context/publication code are retained. The exact source comparisons are recorded in `preserved-contracts.json`.

An initial Start under NOFILE=0 still cannot acquire its original namespace authority and remains unsupported. This revision does not replace that authority with `/proc` path matching or an old generation. It also does not reopen a quiesced generation, accept root or retained capabilities, or make context sampling a substitute for lifecycle transition gates.

## Validation performed

The candidate is derived from the raw owner file proven byte-identical between R21 and the actual candidate05 925-file source preparation. All four included protocol/API headers are bound to the current candidate05 inputs. The source changes are one implementation file and two documentation-only headers; `nofile-inherited-owner.patch` contains the complete diff.

Strict local GCC compilation succeeded with `-Wall -Wextra -Werror`, stack protection on ordinary code, and the raw-owner compile flag enabled. The new auditor retains the previous closure rules and requires exactly one persistent Worker and one InheritedWorker. The local final ELF closure audit found six reachable internal functions and no forbidden libc, TLS, stack-canary, out-of-line atomic or compiler-runtime edge from either worker. The trampoline still has exactly two syscall sites and one fixed stack-stored entry call.

The actual local machine-code call sites were also read: Start passes the persistent Worker and null context; Read's allocation-failure branch passes InheritedWorker and its retained stack request. Both pass the unchanged `0x350900` flags and distinct clear-tid addresses. InheritedWorker passes `true` to the common metadata implementation and exits through raw `SYS_exit`. This is author review, not an independent peer or Android audit.

The real source, with no context or identity seam, passed a negative control in the current UID-0 environment: stack preparation succeeds while preserving errno; Start remains `EPERM`; closed Read remains `ESHUTDOWN` and leaves output untouched; Enabled stays false; quiesce prevents restart; Stop succeeds; and the signal mask is preserved. This negative result does not execute the new metadata path.

The separate `nofile-snapshot-control-01` experiment supplies five positive local kernel-mechanism controls, including NOFILE=0 plus AS=1, close/reuse, output atomicity and 24 clear-tid restarts. Those controls use a smaller fixed worker and do not substitute for running this actual production owner.

## Required next controls

Run the exact source under a nonroot, zero-capability, initial-user-namespace context that independently passes the unchanged Start authority. The minimal positive cases are: existing ordinary TMPFS FD under NOFILE=0; the same with AS=1 after both stacks are prepared; NOFILE=1 to exercise exhaustion at `pidfd_getfd`; preserved successful errno and raw/libc 120-byte views; guest EFAULT and partial-copy behavior after successful metadata capture; concurrent caller close/dup; Stop while the inherited worker is active; and private fork with an in-flight parent request.

The actual Android ELF requires a new two-worker closure audit and both clone call sites must be reviewed again. The full earlier ordinary metadata, lifecycle and raw/host ABI controls remain required; a positive new case cannot erase earlier failures.

## Remaining limitations

- Startup under zero descriptor limit, including a private child that has not established fresh namespace authority, is still unsupported.
- A virtual `O_PATH` descriptor still needs the existing readable reopening for tag checks. That can fail under NOFILE=0; this revision preserves the error.
- A new kernel task and copied file table are required. `RLIMIT_NPROC`, task limits and kernel memory failure may still introduce errors compared with a native metadata syscall.
- Credential, capability, root, namespace, zygote, exec and final-thread retirement boundaries still need the paired platform lifecycle implementation. No raw worker is registered with Bionic pthread APIs.
- No full engine, service, Android or complete-app qualification follows from the local compile and controls. This revision is not deployed.
