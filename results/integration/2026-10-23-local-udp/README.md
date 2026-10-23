# Ordinary UDP errors and original Agentd stop: fixed-source evidence

## Fixed product source
- Desktop implementation: `c8f0c88ecb640117686ff05f850a73e60688eac7`.
- Desktop tree: `641c6627ba9aaf79ca3506154831a6c51abe521f`.
- Kernel SHA-256: `6d7b67c7046a54c7dda7a9595794159235f3b4dad45dd2c4892a7868432a1524`.
- Original native regression ELF SHA-256: `90ace4da1f2a34200dc0952ea4419d7ad67c201a53994273b9f4a93d3f2ccc40`.

The archive commit only adds evidence. The ordinary product kernel was built from the implementation above without `--cfg ktest`. Its actual build command, exit, source identities, complete logs, QEMU boot/QueryAbi receipt, and the source-bound build adapter are retained.

## Actual results
1. The pre-fix reproducer distinguishes Linux from the ordinary guest: a connected loopback UDP socket targeting a missing port reports POLLERR and ECONNREFUSED on Linux, while the original guest times out and returns zero SO_ERROR. Distinct bound and destination ports exclude accidental self-delivery.
2. The repaired product kernel and Linux execute the same static regression ELF. All 6 groups / 43 checks pass: normal delivery, missing-port errors, error consumption, readiness, and reconnect/disconnect cases.
3. The original diagnostic Agentd lifecycle is replayed with only the ordinary kernel changed. The original payload, helper, environment, resolver absence and Supervisor 5-second stop budget remain fixed. Both starts reach ready; the original SQLite witness survives stop/restart; both stops complete with Exited(0), no KillRequested, and released writer locks. The recovered witness creates no automation run.

## Scope
The source fix handles local unicast UDP missing-port errors and their socket readiness/error consumption. It does not claim general remote ICMP/extended-error-queue coverage.

The Agentd run remains diagnostic causal evidence: the old diagnostic binary lacks the complete original build-exit receipt needed for formal F1 qualification. The new source-pinned production Agentd/helper build is a separate gate. These records do not establish production FinalUse inputs, post-exec G2 grants, a persistent user task, UI, real hardware, or phone OS qualification.

## Contents and reproduction
`manifest.json` binds every archived byte to its original execution path and SHA-256. The six `raw/` directories preserve the original baseline, Linux, product build, ordinary boot, native UDP regression and causal Agentd lifecycle outputs. Empty streams are preserved. `tools/` contains the exact executed wrappers.

Executable ELF files, compressed initramfs images and the mutable lifecycle disk remain at the recorded execution paths and are represented by exact size/hash identities in `binary-identities.json`; they are not replaced by reconstructed text or different builds. All complete textual receipts/logs and small guest byte streams are stored verbatim. Qualification must be rerun for a different product source or runtime pair.
