# Real process stop guest regression

`run.py` builds and runs the six-thread `probe.c` only in an ordinary Asterinas
guest. It reuses the shared safety runner's exact-source product admission,
bounded execution and raw evidence. No test process is executed on the host.

The [group-stop contract](../../../support/kernel-safety/GROUP_STOP.md) describes
the original failure, all-task stop boundary, 88 assertions and remaining
job-control limitations. Run `python3 -B tests/kernel/group-stop/run.py --help`
for the exact-product and CPU options.
