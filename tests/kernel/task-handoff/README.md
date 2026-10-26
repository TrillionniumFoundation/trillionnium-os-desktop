# Real completed-wait CPU handoff (W3A)

This ordinary SMP 2/4 probe uses real forked POSIX Tasks, the existing affinity
syscall and direct `SYS_getcpu`. The same PID/TID must resume across all available
CPUs for 24 acknowledged waits. Each timed wait begins after the parent stored
the next mask, so an immediate pipe wake cannot accidentally substitute for a
completed blocking transition. Another 256 immediate pipe exchanges check Task
identity, exact sequence and cleanup without claiming forced current migration.

Two additional children execute eight 100ms CPU-time workloads while migrating
after waits. Unlimited CPU must progress; the original `cpu.max=20000 100000`
must reduce actual process CPU time relative to monotonic wall time. The bound
checks preserved quota/debt, not hierarchical shares. Leaf/parent removal and
`cpu.weight` rejection are mandatory. Every child is reaped.

```sh
python3 -I -B tests/kernel/task-handoff/run.py --smp 2 --output /new/evidence
python3 -I -B tests/kernel/task-handoff/run.py --smp 4 --output /new/evidence
```

The inherited runner builds a fresh ordinary kernel or reuses a verified exact
committed product with `--product-evidence`. It retains probe binaries, serial,
source/artifact hashes and QEMU status, with no host execution of the probe.
Neither lane admits trusted native management, physical hardware or mobile/GPU
claims. Running/queued/throttled affinity forcing and live non-root group routing
remain future work. See the [development and technical contract](../../../support/kernel-safety/TASK_SWITCH_HANDOFF.md).
