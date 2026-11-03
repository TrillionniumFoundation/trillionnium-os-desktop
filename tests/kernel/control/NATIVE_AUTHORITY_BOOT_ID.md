# Native boot identity for the original protected clock

The original Hepta host clock reads `/proc/sys/kernel/random/boot_id` before
publishing a BOOTTIME mapping. The IPC-fixed kernel provided pidfd open, poll,
`/proc/self/fdinfo` and the HOS2 boot identity, but did not provide this procfs
file. A native protected-clock service therefore could not start unchanged.

Linux specifies a boot UUID that stays constant after its first retrieval:
[kernel sysctl documentation](https://docs.kernel.org/admin-guide/sysctl/kernel.html#random).
The implementation keeps one `spin::Once<[u8; 16]>` in
`kernel/core/src/util/boot_identity.rs`, uses the existing random owner, and
sets UUID v4/variant bits. HOS2 and procfs read that same owner. The HOS2 wire
continues to contain the exact 16 bytes; procfs prints their lowercase UUID and
newline. No second identity, grant, monotonic counter or recovery witness is
created. It is initialized at the same original HOS2 device initialization
boundary, and remains safe if the first access comes through procfs instead.

The procfs directory enumerates only the implemented `boot_id` entry. Unknown
entries return ENOENT. The 0444 file uses the original procfs offset printer,
so one-byte reads, pread, EOF and reopening preserve the same value. It has no
write implementation; the original procfs default rejects writes with EPERM.
Root cannot mutate the UUID through this interface. No unsafe Rust is added.

The original kernel RNG policy is unchanged. Its documented timestamp fallback
on platforms without a hardware/device-tree seed is not promoted to a secure
entropy guarantee. This public boot identifier grants no authority. Two observed
different boots do not prove collision freedom, hostile hypervisor protection,
whole-host rollback resistance or storage power-loss recovery.

## Development and acceptance

Keep the original HOS2 QueryAbi codec unchanged. Core tests cover stable UUID
layout, partial procfs reads and rejected mutation. The original unfiltered
core gate retains all 303 earlier tests and requires the three new complete
names (minimum306/67 required names); allocator/OSTD and all prior negative
controls are unchanged.

`proc_boot_identity.c` includes the original strict QueryAbi consumer. Its
normal Linux reference performs eleven checks: UUID format/reopen/partial/EOF,
write refusal and unchanged state, fork identity, real pidfd type/fdinfo,
unreadable-live/readable-exit lifetime, and monotonic CLOCK_BOOTTIME. The native
mode adds a twelfth check comparing the UUID bytes with the actual HOS2 reply.
It reaps its own child and closes its descriptors.

After a clean original ordinary build, run:

```sh
python3 -I -B tests/kernel/control/run_proc_boot_identity.py \
  --kernel /absolute/path/kernel.elf \
  --ordinary-receipt /absolute/path/ordinary/result.json \
  --expected-receipt-sha256 ACTUAL_ORIGINAL_RECEIPT_SHA256 \
  --initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --output /absolute/new/directory
```

The runner checks the actual original receipt/source/ELF identities, compiles
with strict warnings, injects only the probe into the original initrd, and
boots twice under the existing 512MiB/one-CPU/TCG profile. Every boot has a fixed
120-second deadline and must exit QEMU33 with twelve exact successful records,
one completion and no panic. Boot IDs must differ between the two boots.

The dedicated `--expect-missing` negative runs an older ordinary ELF once.
It accepts only ENOENT before any case, with original boot completion and
QEMU33. Its positive `passed` field stays false. It cannot turn a different
ABI/lifecycle failure into a successful negative control. Results retain raw
serial, source/tool/ELF/receipt identities and both original/injected initrds.

This closes only the boot identity ABI prerequisite after actual tests pass.
The canonical root service, private three-lane transport, authenticated writer,
durable CPU K↔D, native graphics and complete F1/G2 still require their own
same-source execution. No unexecuted result is claimed here.
