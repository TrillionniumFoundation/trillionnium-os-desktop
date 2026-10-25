# Process status for the original protected authority peer

The protected Hepta service verifies the registered process's four UIDs,
supplementary groups, five capability sets and NoNewPrivs before accepting its
pre-held pidfd. The kernel already implements the original credential state,
`setgroups`, capability operations and `PR_SET/GET_NO_NEW_PRIVS`, including the
per-thread and exec rules. Its procfs status file omitted `Groups` and
`NoNewPrivs`, so the unchanged host rejected every native registration.

`StatusFileOps` now reports the actual owner thread's no-new-privileges bit and
the actual supplementary group set, including an explicit empty `Groups:` line.
It creates no new credential state and cannot grant or clear privileges. Group
storage is reserved outside the preemption-disabling credential lock. Copying
uses already-reserved space; user-memory output starts after releasing the
guard. Four bounded attempts handle a concurrently growing group set; repeated
growth returns EAGAIN instead of blocking indefinitely. Reservation failure
returns ENOMEM. The existing procfs offset printer still handles partial reads.

The real C probe checks twelve observable contracts through procfs, pthreads,
fork, exec and the original syscalls. It checks a nonempty group set before
clearing it, so an implementation that always prints an empty group set fails.
A child drops all capability sets, groups and all four UID/GID values to60001;
the original parent independently reads its status before releasing it to exec.
The child verifies the same exact state after exec. A separate thread sets its
own NoNewPrivs without changing the main thread. The probe reaps its own child
and closes its descriptors. It must run as root in a disposable test environment;
it does not alter the calling shell's credentials or install a service.

Compile the Linux reference with `-std=c11 -O2 -Wall -Wextra -Werror -pthread
-static`, and make its executable accessible to UID60001. After a clean original
ordinary build, run `run_proc_process_privileges.py` with the actual kernel,
ordinary receipt and its SHA256, original initramfs and a new output directory,
using the same arguments documented by `run_proc_boot_identity.py`.

The native runner requires every exact case, setup/exec checks, original boot
completion and raw QEMU33 with the unchanged 512MiB/one-CPU/TCG profile and fixed
120-second deadline. `--expect-missing` accepts only the older kernel's missing
NoNewPrivs field before any cases, with a successful original boot and QEMU33;
its positive verdict stays false. The original and injected initrds, raw serial
and source/tool/ELF/receipt identities are retained. This ABI qualification does
not prove a protected root service, authenticated recovered writer, persistent
CPU effects or complete G2.
