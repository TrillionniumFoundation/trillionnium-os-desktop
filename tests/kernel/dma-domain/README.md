# Real device-domain regression

This opt-in test boots an OSTD hardware test, not a host memory model. Build the
source-local `cargo-osdk` with the pinned toolchain and explicit-lock patch (see
`support/build/ktest/README.md`), set `CARGO_HOME` and `VDSO_LIBRARY_DIR`, then run:

```
python3 tests/kernel/dma-domain/run.py --smp 2 --output /absolute/new/evidence
python3 tests/kernel/dma-domain/run.py --smp 4 --output /absolute/other/evidence
python3 -B tests/kernel/dma-domain/test_runner.py
python3 -B -O tests/kernel/dma-domain/test_runner.py
python3 -B tests/kernel/dma-domain/test_source_inputs.py
python3 -B -O tests/kernel/dma-domain/test_source_inputs.py
```

The positive fixture uses q35/TCG, 512 MiB, two EDU devices at 00:05.0/00:06.0,
Intel VT-d with caching mode and snoop control enabled. It has no host disks,
network or passthrough devices. The same captured ELF must also reject binding
without an IOMMU and with the required snoop capability absent. A negative
profile's successful rejection cannot satisfy the positive profile.

The guest checks each device's own DMA, cross-domain read/write denials with
matching hardware fault source IDs, revoked-buffer lifetime, queue wrap, and old
IOVA rejection after domain teardown/rebind. The host validates exact fixture
arguments, ELF/BIOS/serial hashes, exit status, named test result and unique
profile-specific marker. Source snapshots before/after, pinned generated lock,
compiler/OSDK/vDSO identities and raw failures are retained in a new directory.

`production_qualified` deliberately remains false. See
[`DMA_DOMAINS.md`](../../../support/kernel-safety/DMA_DOMAINS.md) for assumptions,
remaining legacy shared-domain drivers and recovery/authorization gaps. This
fixture is not physical-device or PCIe ACS qualification.
