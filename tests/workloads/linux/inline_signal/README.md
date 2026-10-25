# Original signal ownership syscall regression

The static `probe.c` exercises twenty-two mandatory bounded cases on real syscalls:
SA_SIGINFO code/address for a PROT_NONE fault and a genuinely unmapped address; kill, tgkill, process-group and
pidfd SIGKILL with actual wait/reap; denied sends between different UIDs; original
RT FIFO/value; signalfd number/code; and ptrace fault siginfo then delivery/reap.
Four additional rt_sigqueueinfo cases preserve copy/code/target/signal error
ordering, permission-only signal zero, payload fields with argument-derived
signo, actual cross-UID denial despite forged metadata, and a real nonleader
pthread TID delivering to the shared process queue. The original ten cases and
their assertions remain mandatory. Eight further cases cover the full signed
integer boundary of kill/tkill/tgkill/pidfd_send_signal; target, flags, fd and
copy error ordering; an isolated one-child process group; real pidfd reap;
actual credential checks; valid signal delivery; and nonleader kill delivery.
No test sends to the host-wide kill(-1) broadcast target. Raw register high bits
follow the Linux int ABI (1 << 32 becomes zero), while 256 and 266 cannot become
zero or SIGUSR1. Valid delivery reads original kernel siginfo with the raw
rt_sigtimedwait syscall because glibc folds SI_TKILL into SI_USER.
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
