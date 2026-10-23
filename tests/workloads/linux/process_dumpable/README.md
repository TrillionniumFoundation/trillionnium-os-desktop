# Bounded process dumpability regression

These probes operate only on their own child processes and public sentinels. Root
sets up credential fixtures; sensitive observations run with actual UID/GID 60001,
no effective or permitted capabilities, and no-new-privileges. No system settings
are changed. No unsupported ptrace attach or process_vm_readv result is accepted
as evidence that those operations are protected.

| Suite | Exact observation contract | Lifecycle |
| --- | --- | --- |
| `lifecycle` | 164 on Asterinas; 165 only when the actual read-only reset-policy sysctl is present and compared | 14 credential fixtures and one unprivileged fixture; at most two simultaneous owned children; explicit reap |
| `stat` | 54 | One owned child, dumpability 0/1/0, ten protected address fields plus ordinary public fields and reap |
| `traceme` | 15 | One consenting child, original TRACEME, dumpability 0/1/0, public-sentinel PEEK only, CONT and reap |

The lifecycle suite covers failed and ordinary exec, fork versus pthread/CLONE_VM,
no-op/query/denied and actual credential transitions, capability reduction,
self-FD introspection, eight sensitive proc/pidfd paths, and old descriptors after
image replacement. The guest's fixed reset policy is 0. The recorded Linux host
has policy 2, so the reference explicitly observes its actual configuration; it
does not change it. Old auxv may return its original snapshot or empty bytes;
it must never follow the new image. The recorded Linux run retained 368 bytes.

The stat suite keeps starttime, vsize and RSS readable while checking protected
address masking. It parses exactly the original 52 fields, including a zero live
exit code. The TRACEME suite never writes tracee memory and never accesses an
unrelated process. Its two non-dumpable reads require EIO; its dumpable read must
return the exact public sentinel.

Run each suite against a source-matched ordinary kernel:

```sh
python3 -I -B tests/workloads/linux/process_dumpable/run_guest.py \
  --suite lifecycle --kernel /absolute/product-kernel.elf \
  --initramfs /absolute/initramfs.cpio.gz --output /absolute/new-output
```

Use `--suite stat` and `--suite traceme` for the other two boots. Each uses the
existing 512 MiB, one-vCPU TCG, 120-second guest bound, no host disks/network,
strict static compilation and raw QEMU exit 33. A successful marker alone is
insufficient: exact ordered observations, permissions, completion and reap must
all match. Reports bind kernel, initramfs, BIOS, probe sources, binary, checker,
runner and serial hashes. Kernel source/build provenance remains the invoking
ordinary-build receipt's responsibility.

`reference-fixtures.json` identifies the unchanged C and original transcripts
used by checker tests. The stored Linux lifecycle/stat/TRACEME references passed.
The stored old-kernel lifecycle and stat negatives failed; the old TRACEME guest
timed out before any PEEK because the parent mutex was acquired again by the Yama
ancestry walk. That timeout is not a dynamically demonstrated memory-read bypass.
All remain negative fixtures, even when a host test rewrites a completion marker.
Host oracle tests are synthetic acceptance/rejection checks, never guest evidence:

```sh
python3 -B tests/workloads/linux/process_dumpable/test_lifecycle_checker.py
python3 -B tests/workloads/linux/process_dumpable/test_traceme_checker.py
```

Source `4d32d94f0a3647155245d0a1b1dbe0d3caec8e7f` passed all three suites
against the same freshly built ordinary ELF after the full original kernel suites.
[The exact receipt](../../../../results/integration/2026-10-23-audit-closure/process-dumpable-4d32.json)
records the source and artifact identities. This bounded component regression
does not certify complete Linux ptrace compatibility, general process isolation,
core-dump writing, user namespaces, or production Hepta authority.
