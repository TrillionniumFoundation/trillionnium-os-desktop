# Real QueryAbi guest entry points

`run_queryabi_guest.py` and `queryabi_guest.c` retain the historical A05 replay
and its original fixed kernel/initramfs hashes. The G1 candidate entry point
below builds a fresh ordinary product from a reviewed clean Git head/tree.
Adding this entry point does not establish a passing guest result.

## Ordinary G1 product, image lifecycle and four unsupported operations

Prepare the native toolchain, source-built OSDK, vDSO, QEMU and static BusyBox
as described in [the build manual](../../../support/build/README.md). From the
reviewed checkout, use the full approved source commit and tree identities:

```sh
python3 -I tests/kernel/control/run_queryabi_candidate_guest.py \
  --expected-source-head REVIEWED_40_HEX_COMMIT \
  --expected-source-tree REVIEWED_40_HEX_TREE \
  --output /absolute/fresh/g1-queryabi-candidate
```

This single command first invokes the existing `support/build/kernel.sh
run_kernel`, which compiles the ordinary `ActionChoice::Run` product and boots
its unmodified minimal init. That path does not enable `cfg(ktest)` or its
extreme-revision fixture. OSDK's `--check-cfg cfg(ktest)` declares a known cfg;
it does not enable it. The working source and generated run-base locks remain
explicit, and actual compilation uses `--locked`. The run-base lock must match
the committed minimal **204-package** lock byte for byte.

The runner checks the ordinary boot result and then uses the same product ELF
for a second guest. It reuses the original in-memory initramfs packer and the
original C probe via an include wrapper. The original seven process-lifetime
markers, the four new image-lifecycle markers, the four operation markers
below, both QueryAbi completion markers, and the final ordinary boot marker
must each occur once: **18 exact markers**. After the original completion,
the four lifecycle checks precede the four operation checks and candidate
completion. The exec child returns only the original epoch-check result and
cannot repeat them.

The candidate wrapper emits each marker and its newline in one bounded
`write` call. The included original probe uses unbuffered stdout, where libc
`puts` can split those bytes across two syscalls and let the kernel's trace
appear between the text and newline. The candidate handles `EINTR`, fails on
a short write, and keeps the exact-line acceptance rule. The historical A05
C source and replay runner remain byte for byte unchanged.

The static candidate is compiled with `-pthread`. Its added checks use the
actual ioctl and syscall paths in the ordinary product:

| Lifecycle case | Required observation | Exact marker |
| --- | --- | --- |
| Existing executable, unreadable argv pointer | Direct `execve` returns `EFAULT`; old fd and a fresh open still return the complete original 16-byte boot and space identities | `HEPTA_EXEC_EFAULT_SESSION_STABLE` |
| Absent executable | Direct `execve` returns `ENOENT`; the same old/fresh identity check passes | `HEPTA_EXEC_ENOENT_SESSION_STABLE` |
| Another pthread in the same Process | Different TID, same PID; inherited fd and fresh open return the same boot and space identities | `HEPTA_THREAD_SESSION_SHARED` |
| Non-last thread has exited and joined | The surviving thread's original fd and another fresh open remain valid in that image | `HEPTA_NONLAST_THREAD_EXIT_SESSION_STABLE` |

Both exec failures precede acceptance of irreversible replacement by the
original TaskSet. They do not test a post-boundary loader failure. Successful
exec, stale inherited descriptors and the new image's different CapSpace
remain covered by the unchanged original probe. An exited process cannot
issue its own ioctl; closure on group/last-thread exit and one-shot initial
startup require the actual core tests described in the
[G1-c development manual](PROCESS_IMAGE_G1C.md).

| Known operation | Valid request used in the real guest | Required result/marker |
| --- | --- | --- |
| ReadUsage (2) | 64-byte header; nonzero target slot/generation | `EOPNOTSUPP`; `HEPTA_DISABLED_READ_USAGE_OK` |
| InstallBudget (3) | 96 bytes; canonical sequence ID 1, expected revision 1, period 100 ms, cap 1 ms, reserved zero | `EOPNOTSUPP`; `HEPTA_DISABLED_INSTALL_BUDGET_OK` |
| QueryDelivery (4) | 104 bytes; nonzero target, actual QueryAbi boot/space identities, historical sequence 1 | `EOPNOTSUPP`; `HEPTA_DISABLED_QUERY_DELIVERY_OK` |
| RetireThrough (5) | Same valid 40-byte history payload with the known retire opcode | `EOPNOTSUPP`; `HEPTA_DISABLED_RETIRE_THROUGH_OK` |

The valid-shape requirements come from the unchanged
[HOS2 decoder](../../../libs/os-abi/src/lib.rs). The
[actual device](../../../kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs)
decodes these known requests before returning `EOPNOTSUPP`. Malformed framing,
bad capacity, protocol mismatch, or any successful effect fails this probe;
they cannot be counted as the required disabled-operation result. Before the
four requests the probe again requires the exact QueryAbi-only mask, no
features, revision zero, and nonzero real boot/space identities.

## Evidence and execution bounds

Both guests use x86_64 q35/TCG, CPU `max`, 1 vCPU, 512 MiB and the fixed SeaBIOS.
There are no data disks, network devices, KVM or physical device passthrough.
Success requires raw QEMU exit **33**, no timeout/panic/probe failure, and all
required serial markers. Default timeouts are 300 seconds for ordinary boot
and 60 seconds for the QueryAbi guest, with maxima 600 and 120 respectively.
Use `--boot-timeout` and `--timeout` only within those bounds.

The output directory must be new and outside the source checkout. It contains complete before/after snapshots
of tracked source bytes and Git modes, original product build/boot evidence,
the generated-lock hash, C compile log, copied product ELF/BIOS, injected
initramfs, exact QEMU argv, raw serial hashes and the final `result.json`.
Input limits are 256 MiB for the product ELF, 8 MiB for the compressed original
initramfs, 2 MiB for BIOS, and 16 MiB for the static guest probe; candidate serial
evidence is limited to 8 MiB. The x86_64 multiboot **boot** ELF has OSDK's converted
`EM_386` header; the original Cargo symbol ELF must not be substituted.

`--target-dir /absolute/cache` explicitly selects a reusable product target.
The default is `kernel/asterinas/target`; A06 CI uses its separate `a06-target`
before the later SMP=2 build. Do not run parallel kernel builds in the same
checkout; the original build wrapper retains its shared workspace lock.
Keep the source-built OSDK bound to this checkout path. A different worktree
must not reuse a locally embedded OSDK source path without preparing it again.

A06 CI generates preparation reports in `RUNNER_TEMP/a06-prepared-locks` and
compares both normalized test locks to the committed locks. It never overwrites
tracked reports with runner-specific paths or weakens the clean-source gate.
The new candidate step follows complete kernel tests and precedes the separate
SMP=2/quota probes; all of their evidence sets retain separate scope and counts.
The artifact also retains the actual OSTD and aster-core boot ELFs and the later
SMP=2 product boot ELF, in addition to the copied QueryAbi candidate ELF.

Host-only acceptance checks can be run with:

```sh
python3 -I -B -m unittest discover -s tests/kernel/control -p 'test_queryabi_candidate_runner.py' -v
```

Those use Git/filesystem and receipt fixtures, not a kernel or emulated ioctl.
Neither they nor this QueryAbi-only guest establish trusted-init, native
CapSpace grants, ReadUsage/InstallBudget/delivery effects, Hepta integration,
CPU timing/SMP qualification, physical hardware or mobile support.
