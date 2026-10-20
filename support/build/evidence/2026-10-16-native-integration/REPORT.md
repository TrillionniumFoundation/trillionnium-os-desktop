# A01: fresh kernel tests and native OSDK integration

The full Asterinas boot passed in the immediately preceding
`2026-10-16-boot-binding/` phase. This follow-up reruns the real OSTD and
aster-core kernel tests with the source-built fixed OSDK, and expands the
previously selected host-only integration subset to all **22** original OSDK
integration test names under an explicit native profile.

The latest per-case integration outcomes are **20 passed, 2 failed**. This is
an aggregate of the complete 22-case run and retained exact-case retries,
not a single clean 22/22 run. The complete run originally recorded 19 passed,
3 failed. Both remaining failures attempt actual QEMU UNIX sockets and fail
with host `Operation not permitted`; they remain in the denominator. The
suite returns nonzero. No permission, namespace or transport change was used
to turn those failures into passes.

## Actual results

| Scope | Result |
| --- | --- |
| Real OSTD kernel guest | 221 reported passed, 0 failed/filtered, 3 explicit VMX/EPT soft skips; exercised lower bound 218; raw33 |
| Real aster-core kernel guest | 141 passed, 0 failed/filtered/skipped; raw33 |
| Both real kernel test guests | 362 reported, exercised lower bound **359**, no timeout; OSDK/top-level exit0 |
| Native adapted OSDK integration, latest per-case results | **20/22 passed**, 2 failed due to host UNIX socket EPERM; one passing hypervisor case explicitly takes its VMX-unavailable fallback |
| Real TCP GDB/VSC-config case | Loaded the actual Cargo symbol ELF, attached, read RIP and detached; guest Hello and raw33; actual VSCode LLDB application not run |
| Default UNIX GDB case | Actual QEMU raw1, UNIX socket creation EPERM; failed |
| Coverage case | Fixed-toolchain kernel builds, actual QEMU monitor UNIX socket EPERM, no valid profraw; failed |
| Original kernel-in-100-lines case | First registry/path lock mismatch retained; explicit fixed vendored dependency adaptation followed by actual raw33 and passing original assertion |

The two kernel-test guests use the complete fixed upstream crates, not host
models or boot script tests. `kernel-tests/` preserves their unmodified output,
exact argv, raw serial, generated locks, binary references and source
provenance. Its independent archive script reconstructs the pinned checker
and validates both guests in four Python modes. These eight archive checks
are not eight additional boots. The ELF bytes match the already retained
artifacts and are referenced rather than duplicated.

## Native integration profile

Production OSDK is built from the unique `kernel/asterinas/osdk` source with
its original lock. Only the isolated test harness is adapted:

1. Fixed `/tmp` strings become a newly owned short scratch root, preserving
   existing host paths. Per-case temporary directories also use a short path.
2. The helper's local OSTD anchor points back to the vendored source.
3. The kernel-in-100-lines example's `align_ext` 0.1.0 dependency uses the
   fixed vendored path already represented by the root lock. The original
   registry identity was rejected; this is an explicit source adaptation.

Original assertions and production test source files remain unchanged. Exact
patches and original/adapted hashes are recorded. The isolated harness is not
a second kernel implementation. Its generated workspaces are disposable.

Generated dependency resolution normalizes the complete original root lock
offline and rejects any external name/version/source/checksum drift, then
builds with `--locked --offline`. Every real Cargo invocation is pinned to
`nightly-2026-07-21`, including absolute rustc/rustdoc paths and disabled
toolchain auto-install. The OSDK adapter selects direct multiboot; QEMU uses
q35/TCG/max, 1 vCPU, 512 MiB and explicit SeaBIOS. It preserves GDB, startup
pause, monitor and coverage behavior, with TCP debug endpoints on loopback.
It rejects network/data disks, keeps raw statuses and requires expected guest
counts and nonempty hash-matched serial logs.

Earlier preparation failures are retained. They include missing fixed cached
dependencies, isolated harness setup errors, a generated `nightly` template
selecting a different compiler before the absolute pin was added, and the
registry/path dependency mismatch. That compiler selection attempt failed;
it was not a passed kernel test or an upstream toolchain upgrade. The
vendored toolchain and source pins never changed. Per-attempt hashes preserve
the distinction between earlier runner versions and the final support code.

## Reproduce and handoff

With the native host dependencies and the exact Rust toolchain available:

```sh
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -I support/build/ktest/run.py --output NEW_KERNEL_TEST_DIR
python3 -I support/build/osdk-integration/run.py --output NEW_INTEGRATION_DIR
```

Use a new output directory on every invocation. The integration command will
remain nonzero on this host while UNIX socket creation is denied. Read
`osdk/REPORT.md` for individual attempts, latest-case aggregation, source
hashes and the complete retained failures. `support/build/osdk-integration/`
contains the maintainable runner, adapters, archive command and pure tests.

A00/A05/A06 continue from the unique `kernel/asterinas/` root and the concrete
Process/exec/sys_ioctl and ClassScheduler/PerCpuClassRqSet/LocalRunQueue paths
in `support/build/README.md`. This phase changes only A01 support/build files
and verification metadata. The existing production OSDK fixes are in
`4ae1a80e6b87fd55913bd01e6aadd28a20e6c322`; A05/A06 core files are untouched.

The default upstream GRUB/container/firmware matrix, KVM, nested VMX/EPT,
controlled SMP, physical devices, all userspace workloads and HOS2 kernel
enforcement remain outside these results. The full-kernel boot's unexplained
temporary-profile replacement and initial overwritten host failure log remain
explicit limitations in the preceding phase; these later tests do not erase
them. Root README stays 0 bytes. No active disk, firmware, driver or production
service was changed.
