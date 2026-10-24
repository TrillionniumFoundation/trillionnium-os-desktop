# Unix per-call nonblocking regression

This probe exercises the ordinary AF_UNIX socket implementation with the same
static C ELF on Linux and the Asterinas-derived guest. It covers SOCK_STREAM,
SOCK_SEQPACKET and SOCK_DGRAM, independently of file-description O_NONBLOCK.

## Implementation boundary

The relevant original owners are `UnixDatagramSocket::do_send/recvmsg` and
`UnixStreamSocket::sendmsg/recvmsg`. A per-call MSG_DONTWAIT must choose the
existing `try_send`/`try_recv` path without changing shared file flags, socket
timeouts, queue ownership, sender notifications or the ordinary blocking path.
The stream receive path already supported this behavior before this increment.
This test does not grant full Linux socket, authority, daemon or persistent G2
qualification.

The probe creates private socket pairs and duplicates one endpoint. For each
socket type it checks empty nonblocking receive, unchanged shared flags, ordinary
receive timeout, a real child producer waking a blocked receive, full-queue
nonblocking send, unchanged shared flags, and a real child consumer waking a
blocked send. The consumer reads and validates exactly the original queued
bytes. The parent reads back the newly sent payload; both children are reaped.
All three types run the same 11 checks, for 33 required ordered records.

Filling uses temporary O_NONBLOCK with the original flags restored before the
per-call test. Fill, counterexample and wakeup sends all use 1024 bytes: a
smaller Linux datagram may fit accounting space left after the fill request
fails. Filling is bounded to 8 MiB. The 750 ms socket timeout bounds old
MSG_DONTWAIT behavior; success requires less than 250 ms. The ordinary timeout
must still take at least 375 ms and less than 2 seconds. The 20-second alarm and
outer runner deadlines are failures, never accepted bug evidence.

## Linux reference and host oracle

From the repository root, with GCC static libc support:

```sh
python3 -I -B tests/workloads/linux/unix_dontwait/run_linux.py \
  --output /absolute/new-linux-reference
python3 -I -B -m unittest discover \
  -s tests/workloads/linux/unix_dontwait -p 'test_*.py' -v
```

The reference runner compiles with `-O2 -std=c11 -Wall -Wextra -Werror -static`,
executes the actual probe and retains compiler/source/binary identities, raw
stdout/stderr, wait status and the strict oracle result. A failed run remains
in its new directory and cannot be used as a reference. The oracle tests use
explicit synthetic records and establish no native execution qualification.

## Actual guest and causal negative control

Use a clean, built ordinary kernel from the recorded source combination, the
original initramfs and the **same ELF** accepted by the Linux reference:

```sh
python3 -I -B tests/workloads/linux/unix_dontwait/run_guest.py \
  --kernel /absolute/ordinary-kernel.elf \
  --initramfs /absolute/original-initramfs.cpio.gz \
  --probe /absolute/new-linux-reference/probe.elf \
  --reference /absolute/new-linux-reference/result.json \
  --output /absolute/new-native-result
```

The runner reuses the existing `run_proc_boot_identity` newc packing and
`run_g1c_guest` static ELF validator. It preserves the original init entries and
boot marker, adds one probe, and runs the existing socket-credential guest
profile: q35, KVM/host CPU, 1 vCPU, 512 MiB, SeaBIOS, no network/share/monitor,
120-second outer deadline. It records the real QEMU invocation, raw serial,
binary/source/initramfs hashes and checker result. It requires 33 ordered
observations, one summary, one correct probe exit, the original boot marker
once, QEMU exit 33 and no timeout. This runner does not build the kernel or
authenticate a kernel source identity; the surrounding original build receipt
must bind its exact ELF and complete source tree separately.

For the causal negative control, rebuild the unchanged old implementation (or
revert only the three repaired entries in an isolated checkout) and invoke the
same command with a new output directory and `--expect-old-blocking`. This mode
requires exactly four measured delayed EAGAIN observations: stream send,
seqpacket send, datagram receive and datagram send. Each must take 375 ms to
2 seconds, with its C assertion false. All 29 other checks must pass and the
probe must exit 1 normally. SIGALRM, an outer timeout, EINVAL, an unreaped child,
an altered inventory, failed payload checks or a missing summary cannot pass.
The result distinguishes `counterexample_accepted` from `product_passed`;
successful detection never qualifies the broken kernel.

Retain negative and positive output directories separately. Do not rewrite
older socket-credential failures or reuse their success as this probe's result.
