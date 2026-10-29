# Actual datagram page-budget guest

This guest-only probe uses ordinary AF_UNIX SOCK_DGRAM socketpairs, real POSIX
senders/receivers, process migration, inherited descriptors and actual cgroup
attributes. See [the development and technical contract](../../../support/kernel-safety/DATAGRAM_MEMORY.md).
Source and C syntax checks are not a kernel qualification.

With the pinned nightly and an OSDK built from this exact checkout, run in an
exclusive build window:

```sh
python3 -I -B tests/kernel/datagram-memory/run.py --smp 2 --output /absolute/new/evidence
python3 -I -B tests/kernel/datagram-memory/run.py --smp 4 --output /absolute/another/new/evidence
```

The unchanged inherited safety runner uses the original 60-second static
compiler and 120-second QEMU limits. The C probe has a 45-second alarm. It retains
raw serial logs, source-before/after records and exact kernel/probe/firmware
hashes. No network or host block device is attached. Never execute the probe on
the host. Missing controls, failed setup and child failures are failures.

Checks require exact IPC-class physical deltas for multi-page and empty
datagrams; sender/ancestor ownership; peek and truncation; migration; leaf and
ancestor rejection with rollback; denial of a second empty message at a real
one-page ceiling; source and destination user-copy faults; complete retry;
queued lifetime after sender exit; receiver-close cleanup; and the original
64-KiB payload/message capacity. Every child must exit successfully before the
parent emits its completion marker. This does not verify heap/slab/ancillary
ownership, global OOM or Linux memory.max.

The original stream/pipe IPC probe remains separate and unchanged. Preserve the
pre-fix datagram failure independently; a legacy ELF with this new probe is a
negative comparison, never a same-source positive qualification.
