# Experimental G1-c: trusted initial image and CPU observation

This profile is an explicit development candidate. Ordinary builds retain the
QueryAbi-only control device and all original A06 acceptance gates. Enabling
`g1c-trusted-observe` implements QueryAbi and ReadUsage for one manifest-bound
initial Process image; it does not enable native management or history.

## Build and authority contract

The build wrapper takes `HEPTA_G1C_TRUSTED_OBSERVE=1` and one absolute
`HEPTA_TRUSTED_INITIAL_ELF` input. It snapshots at most 8 MiB, records the exact
bytes and SHA256, and passes a read-only copy to the kernel's `include_bytes!`.
The profile is x86_64, one CPU, static ET_EXEC, no interpreter, no writable
executable LOAD segment and no overlapping LOAD pages. The normal loader is
unchanged for subsequent ordinary exec.

At initial load, the kernel obtains one bounded snapshot from the actual open
file and compares all bytes with its embedded input. Those same bytes initialize
private RAM VMOs. It checks the final mappings and entry, seals the image and
consumes a private loader result in the existing, stopped initial Process
transaction before its single first resume. A path, UID, PID, copied page, file
descriptor or userspace digest cannot construct that authority.

`AT_HEPTA_BOOT=240` locates an experimental read-only, non-executable 4096-byte
bootstrap page. Its first 32 bytes are `HOS2BOOT`, version 1, slot 1 and generation
1 (three little-endian u64 fields). All remaining bytes are zero. The page is
discovery data; the original Process image and live CPU owner hold authority.
The observe lease starts at the kernel's BOOTTIME sample and lasts 300 seconds.

Every process sees the same build capabilities: `supported_ops=6`,
`max_request_payload=0`, `max_response_payload=64`, `features=0`. A fresh session
in an ungranted image returns HOSR PermissionDenied for ReadUsage. An incorrect
nonzero slot or generation in the granted image returns StaleHandle. Fork and
SCM-transferred control descriptors fail with EPERM. Exec fences the old
descriptor with ESTALE and removes the grant; opening a new descriptor does not
restore it, even when exec loads identical ELF bytes.

## Real guest verification

Run in the project's disposable cloud build environment:

```bash
python3 -I -B tests/kernel/control/run_g1c_guest.py \
  --expected-source-head "$(git rev-parse HEAD)" \
  --expected-source-tree "$(git rev-parse HEAD^{tree})" \
  --target-dir /new/external/g1c-target \
  --output /new/external/g1c-evidence
```

The runner requires a clean, reviewed source commit and records every tracked
byte and mode before building and after all guests. It compiles `g1c_init.c`
statically, uses the original kernel/OSDK build path with the explicit feature,
checks the fixed 204-package lock, and retains the exact kernel and manifest.
QEMU uses the existing q35/TCG/max/512 MiB/one-CPU profile, pinned SeaBIOS, no host
network, no guest disk and no shared host directories. `rdinit=/test/g1c-init`
selects the C ELF directly as the initial process; it is not a child of a shell.

The positive guest verifies all of the following through real syscalls:

- The exact auxiliary page and uniform QueryAbi capabilities, real ReadUsage
  layout, monotonic counters, revision and fixed initial CPU budget.
- Nine VM restrictions, including adding write/execute permissions, creating
  executable mappings, replacing/unmapping/discarding the bootstrap page,
  remap aliases and sharing the VMAR with a different Process.
- Same-process thread and dup behavior, distinct fork identity, forged
  bootstrap-page denial, transferred control descriptor denial and retained
  parent authority after fork.
- Write-time rejection through an already open `/proc/self/mem` descriptor,
  including after SCM transfer to a child. The child cannot open `/proc/1/mem`.
- ReadUsage agreement with the actual owner's `cpu.max` and revision: a same
  value write, a 25 ms budget and restoration to 50 ms all go through the
  original Linux cgroup interface. Each accepted configuration write advances
  the original revision; observation itself does not advance it or refill a
  window. `cpu.stat` is also retained but its jiffy counters are not asserted
  equivalent to nanosecond native accounting.
- A failed exec preserves the current grant. A successful exec in the same
  granted PID removes it, rotates the CapSpace, removes AT240 and fences the
  old descriptor before a fresh session is denied observation.

Two rejection boots use exactly the same already-built kernel and embedded
manifest. Only the initramfs probe bytes change: one non-LOAD tail byte is
flipped, then one byte is truncated in a separate boot. A negative result
requires the specific manifest-byte-mismatch or truncated-snapshot marker, no
commit/activation/userspace record, the original init-load failure and QEMU's
failure exit 65. An arbitrary panic or timeout is not accepted.

The separate `G1-c trusted initial image and real CPU observation` workflow runs
these three boots and retains their raw inputs and logs. Host verifier tests,
including optimized Python, validate refusal of missing, duplicated and forged
records. They are checks of the evidence parser and do not count as guest
execution. Original A06 kernel, ordinary QueryAbi, Linux comparison, SCM_RIGHTS,
RLIMIT_NOFILE, full32 and CPU gates remain independently required.

## Remaining limits

This experiment does not isolate the legacy Linux root administrator from
changing cgroup configuration or membership. Its native target remains pinned
to the original CPU owner; it is not retargeted by an ordinary process move.
Owner replacement/deletion and inconsistent accounting must fail closed. The
loader seal protects this narrow static image; general dynamic executables,
JITs, inherited management grants and device control need separate contracts.

InstallBudget, QueryDelivery and RetireThrough stay disabled. This candidate is
not a proof of the original Hepta agentd runtime, ObjectiveAdmission durability,
crash/power-loss recovery, SMP native authority, desktop/mobile device drivers,
VMX/EPT hardware or production readiness. Passing the experimental profile
closes only the properties explicitly exercised and checked above.
