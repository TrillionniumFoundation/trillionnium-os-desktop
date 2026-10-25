# Owned-child commoncap regression

The C source, Linux result and original native failure are immutable inputs from
`commoncap-owned-audit-01`. The target is an owned child with permitted CAP_CHOWN,
effective zero, UID/GID 60001, NNP and dumpability 1. The actual observer has zero
capabilities. Eight sensitive operations must fail with a permission error;
after the child drops CAP_CHOWN, the same eight operations must succeed.

Build with the original static compiler arguments, retaining the resulting hash:

```sh
x86_64-linux-gnu-gcc-13 -static -O2 -std=c11 -Wall -Wextra -Werror commoncap_probe.c -o commoncap-probe
python3 -B test_check.py
python3 -I -B run_guest.py --kernel /absolute/source-qualified/kernel.elf --initramfs /absolute/original/initramfs.cpio.gz --probe /absolute/commoncap-probe --output /absolute/new-output
```

The runner requires the exact Linux-referenced binary hash and keeps the original
512 MiB, one CPU, 120-second guest deadline, 8 MiB archive and 16 MiB image bounds.
It retains kernel/probe/serial hashes and demands raw QEMU 33 plus exact probe
exit 0, all 16 operations and actual child reap. Host checker tests qualify the
oracle, not native behavior. Original native probe exit 42/raw 33 is a failure.

The probe reads only a public four-byte sentinel from its child, small controlled
proc metadata, and copies only its child's `/dev/null` FD. No arbitrary process
is attached or modified. This covers the selected access paths, not full Linux
ptrace, namespaces, general security or production OS authority.
