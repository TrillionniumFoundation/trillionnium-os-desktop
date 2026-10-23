# Original signal ownership syscall regression

The static `probe.c` exercises nine mandatory bounded cases on real syscalls:
SA_SIGINFO code/address for a PROT_NONE fault; kill, tgkill, process-group and
pidfd SIGKILL with actual wait/reap; denied sends between different UIDs; original
RT FIFO/value; signalfd number/code; and ptrace fault siginfo then delivery/reap.
Every child belongs to this probe. Parent-death signals, a 30-second process
alarm and child alarms bound cleanup. No global memory exhaustion, kernel panic
or allocator fault flag is used. PIDFD/raw siginfo and ordinary RT remain the
original dynamic paths and serve as compatibility controls.

A Linux reference run requires an explicit `--linux-reference` and UID 0 so the
cross-UID negative is real. It does not qualify Asterinas. The disposable guest
requires `--disposable-guest` and its private fixture marker. The runner embeds
that same probe into the original initramfs, uses the original isolated 512 MiB,
one-CPU TCG profile without host disks/network, and retains the original 120-second
guest deadline. All cases, ordered completion, actual probe exit zero, boot
completion, raw QEMU 33 and no panic/failure are required. A marker alone cannot
pass the checker. `test_check.py` preserves missing/duplicate/reordered, false
exit, timeout, panic and Linux-reference negative evidence cases.

Run the host checker with `python3 -B -m unittest discover -s
 tests/workloads/linux/inline_signal -v` (one command). After building a clean,
source-bound ordinary kernel, run:

```
python3 -I -B tests/workloads/linux/inline_signal/run_guest.py \
  --kernel /absolute/path/to/source-built-kernel.elf \
  --initramfs /absolute/path/to/original-initramfs.cpio.gz \
  --output /absolute/path/to/new-evidence-directory
```

The runner records input hashes; the integration caller must additionally bind
those hashes to the exact ordinary build receipt and unchanged full source.
This tests signal behavior and owner transfer, not a global low-memory guarantee.
The existing signalfd implementation does not populate all Linux siginfo fields;
this slice preserves its original contract rather than claiming those fields.
