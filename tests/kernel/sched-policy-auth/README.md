# Scheduling policy target authorization

This probe uses actual separate Linux-ABI processes in an owned ordinary guest.
It exercises `sched_setscheduler`, `sched_setattr` and `sched_setparam` against a
live target. A different effective UID and UID 0 without effective capabilities
must be refused before any scheduling attribute changes. Matching target real or
effective UID and the original target-namespace `SYS_NICE` permission remain the
authorization routes. Read-only getters remain reachable across these UIDs.
Target-process lifetime is retained through permission checking and mutation;
a reaped target returns `ESRCH`, and negative identifiers return `EINVAL`.

Run `python3 -I -B tests/kernel/sched-policy-auth/run.py --output /new/external/path
--smp 4` with this checkout's source-built OSDK and VDSO. The runner never runs the
probe on the host or attaches host disks or network. A clean exact-source
ordinary product receipt can be supplied through `--product-evidence`.

The test-only before commit leaves kernel bytes unchanged and retains the
original unauthorized success as failure evidence. A passing guest is a bounded
permission result, not complete Linux scheduling compatibility. In particular,
self-service real-time/nice escalation and resource-limit policy require their
own subsequent checks; this stage does not claim them fixed, enable `cpu.weight`
or implement physical migration. The policy-state and namespace checks must
remain independent of future writer-administration serialization.

Linux API permission reference: [sched(7)](https://man7.org/linux/man-pages/man7/sched.7.html).
