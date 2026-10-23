# Original supplementary-group DAC probe

The C source, Linux transcript, old-kernel transcript and original build receipt
are retained unchanged. This suite uses only its own temporary files and two
sequential children. It keeps all six checks and both explicit reap records.
The old source 0252 incorrectly rejected two group-member reads/searches; Linux
passed. The original source and binary hashes are recorded in `result.json`.

```sh
python3 -I -B tests/workloads/linux/supplementary_dac/run_guest.py \
  --kernel /absolute/source-matched-kernel.elf \
  --initramfs /absolute/original-initramfs.cpio.gz \
  --probe /absolute/original-linux-referenced-supplementary-dac-probe \
  --output /absolute/new-evidence-directory
python3 -B tests/workloads/linux/supplementary_dac/test_check.py
```

The runner requires the exact original Linux-referenced binary, checks its static
ELF bounds and hashes, and keeps the original 512 MiB, KVM, one-vCPU, 120-second
profile and 8 MiB initramfs bound. It has no host disk or network. Its caller must
bind the kernel to a fresh ordinary-build receipt and unchanged source snapshot.
The original compiler command is retained so the binary can be reproduced; a
changed compiler/binary requires a new Linux reference rather than borrowing the
old qualification.

The oracle requires the exact ordered unprivileged group membership, six
operations, two successful reaps, final completion, one boot marker, raw QEMU 33
and no timeout. Host oracle tests reject the actual old failure even if only its
exit marker is altered; those synthetic wrappers are not native qualification.
New-source native qualification is pending. See
[the technical contract](../../../../docs/agents/SUPPLEMENTARY_GROUP_DAC.md).
