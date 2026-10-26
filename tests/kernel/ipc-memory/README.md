# Actual IPC buffer-budget guest

This probe runs only inside an ordinary Asterinas QEMU guest. It uses real
AF_UNIX streams/seqpackets, anonymous/named pipes, cgroups and file descriptors.
It attaches no host storage or network and must not be executed on the host.
See `support/kernel-safety/IPC_BUFFER_MEMORY.md` for the development and technical
contract and its remaining isolation limits.

From this checkout, with its own pinned source-built OSDK and external build
cache, run:

```sh
python3 -I -B tests/kernel/ipc-memory/run.py --smp 2 --output /absolute/new/evidence
python3 -I -B tests/kernel/ipc-memory/run.py --smp 4 --output /absolute/another/new/evidence
```

The inherited safety runner compiles the static C probe, builds the actual
ordinary kernel, injects only the owned probe and checks fresh completion
markers. It retains compiler output, raw serial logs, source-before/after
snapshots and exact artifact hashes. A failure is not an unavailable skip.

Checks cover exact 64-KiB pipe and 128-KiB connected-socket deltas, one-end and
inherited-descriptor retention, migration without transferring original charge,
leaf/ancestor denial and second-ring rollback, unchanged output arrays and FD
slots on failed creation, bad user output and second-FD EMFILE cleanup, FIFO
open retry, and failed connect leaving the original backlog empty before retry.
The inheritance ordering uses an actual eventfd release barrier. Each child
must exit successfully; a final parent marker alone cannot hide its failure.

These checks cover the `ipc` class only. They do not turn `memory.max`, global
recovery reserves, datagram/TTY/object/slab allocation or Android IPC support
into completed features. The receiving integration must run its own evidence.

The existing original socket/descriptor witness runner has a separate explicit
`--source-profile ipc-memory-v1` for this reviewed allocation stage. Run it with
the exact committed head/tree, then separately select `shutdown_race` for the
64-iteration production stress witness. Its legacy source/mutation fingerprints
and historical controls remain unchanged. The new profile accepts only the
production-positive variant and pins the IPC allocator/ring/pipe/stream sources;
missing or drifting sources cannot qualify. Synthetic host gate tests establish
only this admission behavior, never an executed kernel witness.
