# Pinned libc and vDSO CPU identity

Run only in the runner's owned ordinary QEMU guest:

```sh
python3 -I -B tests/kernel/vdso-cpu/run.py --smp 1 --output /new/evidence/smp1
python3 -I -B tests/kernel/vdso-cpu/run.py --smp 2 --output /new/evidence/smp2
python3 -I -B tests/kernel/vdso-cpu/run.py --smp 4 --output /new/evidence/smp4
```

`--product-evidence /exact/product` reuses only a successful ordinary product
receipt from the exact clean source. It does not rebuild or substitute a kernel.
The original safety runner retains its source/ELF/firmware/serial guards, while
`cpu-identity.json` independently requires the full case and sample inventories.
Both the original result and CPU-identity result must pass, with CLI exit zero.

The probe runs libc `sched_getcpu`, the mapped original `__vdso_getcpu`, direct
`SYS_getcpu` and LSL on the Linux CPUNODE selector. Every sample runs after its
own TID has bound to one CPU and before that mask is restored; a later unbound
sample cannot be used to infer a migration discrepancy. The main thread and one
joined worker visit every configured CPU in both directions. TLS, existing user
selectors, mask restoration and monotonic time remain mandatory.

There are exactly **34 / 58 / 106 cases** and **4 / 8 / 16 pinned samples** for
one / two / four CPUs. Missing, duplicated or extra cases/samples are rejected.
The original `9957` kernel's CPUNODE gap produced exactly **12 / 24 / 48 failed
cases** with this frozen probe; all actual syscall/mask/TLS/cleanup cases passed.
Those failed receipts remain failed. The corrected candidate needs its own
build, complete OSTD/core results and the same unchanged probe on all three CPU
counts. See the [technical and development contract](../../../support/kernel-safety/VDSO_CPU_IDENTITY.md).

The probe checks an explicit guest argument, a private nonce marker in the new
initramfs and the expected Rust-built kernel version before changing its own
affinity. It is never executed on the host. No host disk, network, service or
other process is configured. These checks do not grant production authority,
physical-hardware, general SMP, RSEQ, CPU-hotplug or NUMA qualification.
