# Actual forced affinity migration

Run only inside a fresh ordinary SMP2/4 guest. The runner compiles static guest
probes; it never runs them on the host and exposes no host disks or network.

```sh
python3 -I -B tests/kernel/forced-affinity/run.py --smp 2 --output /new/evidence
```

`--product-evidence /exact/ordinary/product` reuses only a successful ordinary
non-ktest product receipt from the exact clean checkout. Raw serial, original
kernel/bios hashes, transformed initramfs, probe executables and source snapshots
are retained. See the [development and technical contract](../../../support/kernel-safety/FORCED_AFFINITY.md).

`probe.c` is the immutable frozen W3A before oracle (SHA256
`f61caacac44ea15ef8b7bfbcc81c1da57e03b011053f4b7a723ab82fe80bc67c`).
Its static ELF is
`395f69ec76aa2153d0e7d542f70d767eb6aeea5bf923c91a266f12f3c6e2aed9`.
SMP2 and SMP4 must pass all 24 JSON checks. It establishes each actual source
state, migrates current/queued/throttled Tasks, directly observes destination
CPU or CPU tag, verifies no quota grant, legitimate original-owner recovery,
child joins and cgroup cleanup. No fork-affinity or libc-vDSO assumption is used.

`rt_admin_probe.c` adds ten checks: actual FIFO source and destination, a second
CPU's successful management write/readback while the target runs FIFO, no watchdog
kill, and all children joined. The timing of the original controller's syscall
return is only diagnostic. It is not a deterministic test of pre-return RT
preemption, group shares, physical hardware, trusted N0 multi-CPU execution,
production Hepta authority or all kernel OOM paths.
