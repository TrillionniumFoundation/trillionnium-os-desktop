# Child-zygote capability mechanism probe — source-only revision 01

This is a new, isolated mechanism probe. It is not part of candidate07, the native bridge, ART, the factory, or either compiled updater. No production guard is relaxed.

## Question

The current AOSP reference requests `CAP_SETUID`, `CAP_SETGID`, and `CAP_SETPCAP` for a child zygote, and later intersects requested capabilities with the caller's effective set. Existing native metadata startup and the factory client correctly require zero effective, permitted, and inheritable capabilities. The current bridge hook also loses the real child-zygote role before starting the owner. These are source findings; the installed child-zygote capability values have not been measured.

This probe asks one narrower kernel question: can a raw worker in the same thread group, after clearing its own E/P/I capabilities, obtain a kernel pin to the caller's file descriptor while the caller retains exactly those three capabilities? A separate thread group with the same zero-capability worker is the negative control. Upstream ptrace's same-thread-group exception motivates the experiment; it is not evidence that the deployed Pocket4 kernel or Android policy will permit it.

## Two fixed arms

| Arm | Caller | Worker | Required result |
| --- | --- | --- | --- |
| `same_tgid_zero_cap_worker` | UID/GID 61171, E/P/I low word 448, high word 0 | Same TGID, different TID, E/P/I all zero | `pidfd_open(caller_tid, PIDFD_THREAD)` and `pidfd_getfd` succeed; raw `fstat` and raw `fstatfs` equal the caller's complete initialized structures. |
| `different_tgid_must_reject` | Same exact caller | Different TGID, E/P/I all zero | Target thread pidfd opens, but `pidfd_getfd` returns exactly `-EPERM`; no metadata is accepted. |

Each arm verifies that the caller's E/P/I values are unchanged and its original FD remains open with the same device and inode. The JSON includes both caller and worker capability words. This checks raw kernel metadata only; it is not a test of the Bionic host-libc `fstatfs` normalization or the ARM64 guest adapter.

## Authority and lifecycle in this source

The default invocation only prints a plan. Execution requires the exact `--execute-owned` argument, a root caller in the initial user namespace, and default waitable SIGCHLD semantics. Initial-user-namespace proof uses a thread pidfd and the kernel user-namespace ioctl, then checks the held namespace FD's type, filesystem, device and inode. It does not trust a replaceable `/proc` symlink. Those initial-namespace constants are deliberately the Pocket4 qualification target; other hosts may refuse setup.

The standalone parent forks one direct child. Only that child changes UID/GID/groups and capabilities. It owns the memfd and guarded 128 KiB worker stack, requires a 4096-byte page size, and blocks/restores its signal mask around both arms. Both raw clone variants omit `CLONE_FILES` and `CLONE_SETTLS`; the worker closes only its copied FD table. Its first syscall is `capset` of its own E/P/I to zero. It reaches only fixed raw syscalls and inline helpers, then calls raw `exit`; it never calls a Bionic or glibc thread API.

The same-TGID worker is joined through the kernel clear-TID word before its stack can be reused. The different-TGID worker is also reaped by its exact returned child PID. The direct child waits at most two seconds per clear-TID join; the root parent applies an eight-second direct-child watchdog. The root parent is a subreaper and performs a one-second bounded collection of this standalone program's adopted descendants. An adopted child, timeout, remaining child, or failed wait makes the result fail. Cleanup after an abnormal orphan is not converted to a mechanism pass. A future outer controller must retain a finite owned cgroup and retire it if a descendant remains.

No existing process, Android package, service, namespace, Main file, or global policy is changed. No existing child is adopted from another application: the program is intended to start as a standalone executable with no pre-existing children. The future controller must attest that launch condition, the fixed unused UID/GID range, and exact executable/input identity.

## Evidence and unperformed gates

`syntax-result.json` records the only completed verification: local `g++ -fsyntax-only -Wall -Wextra -Werror` succeeded on this exact source. It did not create or execute an ELF. No host mechanism arm, Android arm, factory operation, ART transition, or root deployment has run.

Before execution, the matching build must retain source/tool/dependency pins and audit the actual final ELF. The worker closure must have no libc, TLS, stack-protector, libatomic, or indirect callback edge; its first syscall must be `capset`. The raw clone trampoline must have the fixed worker entry and must preserve the parent/child TID pointer while using no shared FD table. This freeze does not contain an admitted run request or an outer resource controller.

Suggested execution envelope for later review is one standalone owned unit, at most 0.5 CPU, 128 MiB RAM, zero swap, 16 tasks, and 15 seconds, with held unit/cgroup identity and before/after memory event checks. These are proposed bounds, not an executed resource claim. The root orchestrator must independently review and bind the actual ELF before granting an execution window.

Even if both arms pass, child-zygote support remains incomplete: explicit role propagation, paired ABI/version enforcement, caller/worker context validation, privileged-caller snapshot creation, pre-fork stop, parent reactivation, child specialization, and host-native credential/root/mount/last-thread transitions still require separate implementation and qualification. The ordinary zero-capability gates remain mandatory.

## References

The local source investigation is frozen separately in `art-enabled-call-chain-review01/report.json` (SHA256 `31e103de4890eae53ae8ae3ec7c0c9c1f204fba7dbf3c4811f95e59c436f9edf`). It identifies the exact current AOSP and candidate source hashes, and expressly does not bind those AOSP sources to the installed ART binary.

Upstream mechanism references, used only as motivation:

- `kernel/pid.c`, `__pidfd_fget`: <https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/bfe8eb3b85c571f7e94e1039f59b462505b8e0fc/kernel/pid.c>
- `kernel/ptrace.c`, `__ptrace_may_access`: <https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/cdb3033e191fd03da2d7da23b9cd448dfa180a8e/kernel/ptrace.c>
