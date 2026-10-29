# Unix signal and partial-write QA

This probe runs only in an owned ordinary Asterinas guest with an explicit
argument and a private fixture marker. Its 42 fixed cases contrast six send or
write APIs under default SIGPIPE disposition, a local handler, healthy byte
transmission and the Linux SEQPACKET exception. Four flag-bearing APIs also
check MSG_NOSIGNAL suppression and a subsequent unflagged call in the same
child, proving suppression does not change the process-wide disposition.

Owned parents inspect only their own children's wait status and witness pipes.
The probe uses no procfs or MAC interface. A default-disposition child is
expected to terminate by SIGPIPE; the probe parent remains alive. Handler
observations use lock-free atomics.

O_NONBLOCK tests fill an owned socket, verify EAGAIN, drain half the recorded
capacity and require positive partial progress without SIGPIPE. A subsequent
SHUT_WR must return EPIPE and invoke the installed handler exactly once. A
separate blocking writev case runs eight owned reader threads which drain the
first vector before shutting down reading. At least one partial return is
required, and no positive writev return may also deliver SIGPIPE. Each reader
has a two-second receive timeout. Empty vectors, invalid later user buffers
after successful progress and offset pwritev/ESPIPE remain separate assertions.

The C program reports observations as well as pass/fail cases. The host oracle
checks the exact inventory, observation types and actual values independently.
Missing, duplicate or additional cases, a spurious positive-return signal,
misleading NOSIGNAL warnings, a failed original runner, timeout or abnormal
QEMU exit cannot pass. Synthetic host tests do not qualify real guest behavior.

Build and verify an ordinary QueryAbi product from the same clean source
identity, then run:

```sh
python3 -I -B tests/kernel/unix-signal/run.py \
  --product-evidence /new/exact-source/product --smp 1 --cc gcc-13 \
  --qemu qemu-system-x86_64 --timeout 120 --output /new/unix-signal-evidence
```

Before a production repair, commit the QA-only source and preserve its actual
red guest receipt, C/runner hashes, ordinary kernel ELF and source snapshots.
Run the identical test bytes after the repair under its own source identity.
Do not change older global-SIG_IGN tests, fixed Unix source profiles, existing
oracles, Native Hepta's 500ms window or any original guest settings to obtain a
pass. TCP and vsock SIGPIPE behavior require separate qualification.

Linux references: [send(2)](https://man7.org/linux/man-pages/man2/send.2.html)
and the stable [Unix socket implementation](https://github.com/gregkh/linux/blob/v6.2.10/net/unix/af_unix.c).
Warnings add synchronous console work; their removal alone does not establish
the cause or resolution of a Native Hepta request timeout.
