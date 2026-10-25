# Limited Binder guest qualification

`run.py` compiles `binder_probe.c` as a static program and runs it only inside an
ordinary Asterinas QEMU guest. The inherited safety runner retains source bytes,
compiler output, exact kernel/initramfs/firmware hashes, raw serial output and a
fresh run nonce. It neither executes the probe on the host nor attaches host
storage or networking to the guest.

The implemented profile is described in
[the development and technical document](../../../support/android/BINDER_BYTES.md).
This gate is independent of the historical A08 primitive ioctl/layout checks.
A pass does not qualify Android boot, Binder objects, descriptor transfer,
thread pools, service registration, SELinux policy, or a Hepta device effect.

Run from this checkout with its own source-built OSDK, pinned toolchain, external
private build cache, the fixed vDSO directory, and at most two compiler jobs:

```sh
python3 -I -B tests/kernel/binder/run.py --smp 2 --output /absolute/new/evidence
```

The driver uses actual process and thread allocation identities, so the probe
opens a fresh endpoint in each process. It intentionally tries an inherited
parent endpoint and expects rejection. The server response is checked by the
other process using bytes read from the real receive mapping.

## Page-budget integration regression

The full probe also includes a receive-mapping admission failure. Its separate
`--budget-only` runner option selects this same case without the transaction
suite. A child enters a real capped cgroup, reserves all 16 receive frames, and
maps across a PML4 boundary with budget for only the first three new table pages.
The mapping must return ENOMEM, increment the denial event, release every receive
data frame after actual reference destruction, and permit the same endpoint and
address range to be mapped successfully after the ceiling is lifted. Charged
empty table nodes may remain; the probe does not pretend those nodes were freed.

This case actually reproduced an integration bug: the Binder caller ignored
`MapHandle::map_frame`'s newly fallible return value and reported mmap success.
The driver now propagates the error before publishing its receive area. The
existing VMAR error path removes its mapped prefix. The before-fix failure and
after-fix passing guest evidence are separate. Two earlier fixture failures
(missing parent controller activation and cold stderr/TLS COW at the ceiling)
are retained and are not counted as reproductions of the product bug.
