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
