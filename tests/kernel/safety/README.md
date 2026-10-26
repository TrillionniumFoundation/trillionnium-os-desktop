# Owned kernel safety regressions

The suite runs five bounded programs inside an isolated QEMU guest. The kernel
baseline is Desktop #267 (`bee137ed`); the credential probes and ordinary-product
reuse gate are adapted from #268 (`ca0b5592`). See
[the implementation and scope note](../../../support/kernel-safety/README.md).

| Probe | Required observations |
| --- | --- |
| `commoncap_probe.c` | A same-ID, dumpable child with an extra permitted capability denies maps access, then allows it after dropping that capability. |
| `socket_snapshot_probe.c` | Existing SO_PEERCRED/SO_PEERGROUPS stay unchanged after credentials change; new sockets capture the replacement values. |
| `lifecycle/*.c` | Actual dumpability, credential/exec/fork/CLONE_VM lifecycle and sensitive proc paths; old file descriptors cannot follow a replacement image. |
| `ptrace_dumpable_probe.c` | An unprivileged parent with an owned TRACEME child observes peek denial/allowance/denial across dumpability 0→1→0. |
| `frame_budget_probe.c` | Existing selected-frame `memory.*` admission, private faults/COW, deferred refunds, pressure denial/events, a recovery sibling, and four concurrent allocators with limit updates; all valid `cpu.weight` writes remain unsupported. |

The frame probe uses the #267 physical-frame owner. It does **not** install the
older `hepta.anon.*` controller or claim full Linux memory-controller coverage.
Before forking the measured worker, the observer touches 128 KiB of its inherited
initial stack. The worker retains its original 64 KiB private-stack warmup and
all allocation, COW, pressure and zero-refund checks. This setup matters because
the initial stack's VMO is shared across fork: a zero base page first committed
by the worker remains charged while the observer still holds that VMO. A process
exit cannot refund a physical frame whose last shared reference is still alive.
The setup changes no budget, zero ceiling or bounded-wait limit; see the scope
note for the physical-owner lifetime contract.

Do not run these credential/cgroup programs on a production host. The runner
compiles them on the build host and executes them only in a transient guest with
512 MiB RAM, no host disk and no network. Every probe must return zero; exit 77 is
setup unavailable and fails qualification.

## Run against one committed product

First produce the ordinary QueryAbi receipt for the exact clean head/tree using
`tests/kernel/control/run_queryabi_candidate_guest.py`. Reuse that same receipt
for both SMP configurations:

```sh
python3 -I -B tests/kernel/safety/run.py \
  --product-evidence /absolute/evidence/queryabi-candidate \
  --cc gcc --qemu qemu-system-x86_64 --smp 2 --timeout 300 \
  --output /absolute/new/evidence/safety-smp2
python3 -I -B tests/kernel/safety/run.py \
  --product-evidence /absolute/evidence/queryabi-candidate \
  --cc gcc --qemu qemu-system-x86_64 --smp 4 --timeout 300 \
  --output /absolute/new/evidence/safety-smp4
```

The reuse gate validates a completed successful receipt, all source snapshots,
clean head/tree, boot artifacts, original QueryAbi serial/exit and the QEMU
binary before reuse. The kernel is not rebuilt in this mode. Each output contains
its raw guest log, nonce-bound exact ordered completion records, source hashes,
kernel/firmware/initramfs/probe hashes and raw QEMU exit. Missing, repeated,
malformed, stale or nonzero completion records fail; success also needs the final
boot marker, exit 33, unchanged source/artifacts and no timeout or false assertion.

Without `--product-evidence`, the runner builds and boots current working bytes.
This mode records a dirty tree explicitly as development evidence. Set
`VDSO_LIBRARY_DIR` to the pinned vDSO location required by `support/build/kernel.sh`.
It cannot be used as a committed release attestation. These commands are proposed
CI integration points; their presence is not evidence that CI has executed them.

## Host-side runner regression

```sh
python3 -I -B tests/kernel/safety/test_runner.py
python3 -I -B -O tests/kernel/safety/test_runner.py
```

These check receipt/artifact/source tampering, guest assembly and exact verdict
handling. They execute neither the probes nor QEMU. Successful host tests and C
compilation do not establish that the kernel guest suite passed.
