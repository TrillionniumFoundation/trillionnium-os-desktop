# Actual boot identity guest checks

The probe reads the real procfs boot ID and sends an actual HOS2 QueryAbi
request, then compares the complete original 16-byte identities.
It checks canonical UUID formatting, offsets and EOF, read-only content even
after a root metadata change, and stability across reopen, fork, exec and an
unprivileged reader.
The negative profile requires `EOPNOTSUPP` when the CPU has no hardware random
source; it does not accept timestamp-derived identity as a substitute.

From this checkout, use the source-built OSDK, pinned toolchain and vDSO
specified in the [build manual](../../../support/build/README.md):

```sh
OSDK_LOCAL_DEV=1 CARGO_BUILD_JOBS=2 \
  python3 -I -B tests/kernel/boot-id/run.py --cross-boot \
  --output /absolute/new/boot-id-evidence
```

`CARGO_HOME` must select an OSDK built from this worktree with
`OSDK_LOCAL_DEV=1` during installation as well as execution.
`VDSO_LIBRARY_DIR` selects the verified vDSO; `TMPDIR` may select a private
physical-disk scratch directory.
Do not share the generated kernel target or run another kernel build in the
same checkout concurrently.

The fixed cross-boot profile runs two positive fresh guests and one missing
RDRAND guest.
It requires equal source snapshots and kernel ELF hashes, different positive
boot IDs, and a successful negative refusal.
Each child retains the complete source snapshot, raw serial output, kernel,
initramfs, BIOS and result; the parent retains a report even if child evidence
is incomplete.
The ordinary safety runner's bounded timeout is unchanged.

For an individual positive run, omit `--cross-boot`.
For the fixed negative CPU profile, use `--expect-unavailable`.
These are development evidence, not production approval.
See [the technical contract](../../../support/kernel-safety/BOOT_ID.md) for
entropy assumptions, trusted-page layout and explicit limits.
