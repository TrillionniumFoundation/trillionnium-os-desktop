# FAIR runtime prerequisite (W1)

This probe runs actual forked POSIX children in an ordinary kernel. It compares
`CLOCK_PROCESS_CPUTIME_ID` with `CLOCK_MONOTONIC` under unlimited CPU and the
original `cpu.max=20000 100000`, verifies throttling and child cleanup, and
requires `cpu.weight` writes to remain rejected. It uses no trusted/native
management entry or production authority.

```sh
python3 -I -B tests/kernel/fair-runtime/run.py --smp 1 --output /new/evidence
```

The inherited runner supports SMP 1, 2 and 4, creates a fresh isolated guest,
retains raw serial/source/artifact hashes, and never runs the probe on the host.
Exact committed ordinary product evidence can be reused with `--product-evidence`.

The CPU-time bounds are a CPUmax regression, not a group-weight ratio test.
W1's controlled class-runqueue tests cover the missing FAIR handoff interval;
this ordinary workload verifies supported CPU limits still work. Neither lane
qualifies hierarchical group scheduling, migration, physical hardware or Hepta
production authority. See [the development and technical contract](../../../support/kernel-safety/FAIR_RUNTIME.md).
