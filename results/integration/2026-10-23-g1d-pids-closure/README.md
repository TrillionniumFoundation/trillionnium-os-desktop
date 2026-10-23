# G1d pids negative-control deadline closure

The tested source is `458f9b1086ed7535658ae5e4e9392d3eb88f459d`, tree
`f67d00514eafbd03ed66a0877667b63f2804a94f`. The change separates the
30-second workload startup deadline from the recovery IPC deadline, which is
now 40 seconds. The strict root-workload negative oracle is unchanged.

The earlier failure was a probe-ordering problem: the deliberately unsafe
workload exited at its privilege boundary, recovery's old 20-second IPC
deadline expired, and only then did the manager report the expected missing
workload at 30 seconds. The extra `ipc_timeout` correctly made that run fail.
The previous failed CI receipt and artifact identity must remain in the
evidence history; this directory does not replace them.

## Reviewed outcomes

The original positive runner reports `passed: true`, `stage: complete`,
unchanged source inputs, and one kernel for its three controls. The exact
guest reports no unexpected records, no timeout, and QEMU exit 33. Its
byte-mismatch and truncated-input controls report the exact expected
rejection, no activation or guest execution, no timeout, and QEMU exit 65.
The native pids observations include task/thread/descendant admission,
retained zombie accounting, WNOWAIT non-refund, rollback, migration,
nonleader exec, and workload limit/membership protection.

The original root-workload negative runner reports `passed: true`. Its
mutation parent is the tested source above; the generated negative source is
`e3f6bbac81b4bbd3acd4d017f425990183f087b6`, tree
`cfabc0b67b5fb13db384f62355e56376c07aad13`. Only the declared
`kernel/asterinas/kernel/core/src/process/process/init_proc/trusted_roles.rs`
mutation is applied. The probe SHA-256 is unchanged between positive and
negative kernels. Both source-input checks pass.

The negative exact guest correctly fails the unchanged positive oracle,
with exactly these two failures and no `ipc_timeout`:

```
G1D_FAIL at=workload_privilege_boundary line=478 errno=0 pid=2 role=2
G1D_FAIL at=workload_really_running line=791 errno=2 pid=1 role=1
```

It observes the intentionally unsafe UID/GID zero credentials and capabilities,
and both non-destructive cross-role permission probes succeed. The negative
verdict confirms that no destructive signal was sent. This is a successful
negative control, not a successful unsafe workload. The negative exact guest
has `passed: false`, no timeout, and QEMU exit 33, as required by that control.

## Identities

| Item | SHA-256 |
| --- | --- |
| Shared initial probe | `c5d79aea455e5f38fa8c106f5372fc0a19b1d4cc31150f3936370e7bb47c92ab` |
| Positive kernel | `b8dd3f0816585c998c336e5405954f65a079e044b26fdac6a61ef55b42045088` |
| Negative kernel | `c5da27e3db91cd53dd1c307f1b71d0a5bcf798c79a38fdf1be8ca072ec9566ec` |
| Positive exact raw serial (1,058,123 bytes) | `3820e8f841885a7cda680171bd2516bdd8b31d4c393959a4af72a922b4f02cd0` |
| Negative exact raw serial (5,141,783 bytes) | `1cd165889c678f48b6c5a6f55b90d46732968ea98e184ce59cd7876f816fdaa2` |
| Negative mutation patch | `2443658d41f1b5f0ac7f46e344097bfd4ed960f075ad68bdec15937de8ec5eb9` |

`MANIFEST.json` indexes the original result JSON, serial logs, launch/build
commands, source snapshots, generated lockfiles, and mutation patch. Text
larger than 128 KiB is losslessly gzip-compressed with `mtime=0`; both raw and
stored hashes and byte lengths are recorded and verified after publication.
ELF and initramfs files remain in the original execution directories and are
identified by their receipts. This evidence-only descendant retains the tested
source head/tree above; it does not claim that its own head was executed.

## Qualification boundary

These receipts qualify the bounded native QEMU/TCG uniprocessor G1d profile.
They explicitly do not qualify a memory controller, physical memory reserves,
SMP, hardware devices, Hepta durability, or production readiness. Manager and
recovery task admission outside the workload's pids cap is not a physical
memory reserve. This closure adds two IPC-timeout rejection regression cases
without weakening the negative oracle; the host suite is 24 tests.

The final PR head still requires the repository's hosted CI gates. Local
native success is not a substitute for those gates. The review above uses
the original receipts and compact file index. Every stored archive member is
read back, decompressed when needed, and checked against its raw SHA-256.
