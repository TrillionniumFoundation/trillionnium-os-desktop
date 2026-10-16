# Native OSDK integration profile

This runner executes all 22 real tests from the pinned OSDK integration suite.
These tests exercise OSDK tooling and small OSTD example kernels. They do not
establish acceptance of the complete Asterinas kernel, HOS ABI, Linux userspace,
VMX virtualization, or desktop workloads.

```sh
python3 -I support/build/osdk-integration/run.py \
  --output "$PWD/support/build/out/osdk-integration-new"
```

The output directory must be new. The runner uses an independent Cargo target
directory and a persistent integration runner lock, so it can run alongside a
complete-kernel build. It starts the live GDB and VS Code cases first, then runs
the other 20 cases sequentially. `--case EXACT_NAME` can select individual cases;
the original list is retained in `upstream-test-list.txt`. Each case has a
900-second bound, and each guest has a 300-second bound. Native QEMU, SeaBIOS,
GCC, GDB and the pinned Rust toolchain must be available. `--target-dir` can
reuse a previous runner's independent Cargo cache after validating its origin.

The production OSDK binary is built directly from `kernel/asterinas/osdk` with
its original `Cargo.lock` and `--locked`. A separate test-only package copies
the upstream tests into the run directory. Its three harness substitutions are:

1. Fixed `/tmp` string prefixes point to a newly created short `/tmp/a01oi-*`
   root. The short path preserves Linux UNIX socket path limits. Its device and
   inode are recorded; only that owned root can be removed after the run.
2. The local OSTD helper's manifest anchor points to the original OSDK directory.
3. The kernel100 example's added `align_ext = "0.1.0"` dependency points to
   `kernel/asterinas/ostd/libs/align_ext`, still version 0.1.0. The fixed root lock
   contains that path identity, not the registry copy. This preserves a single
   fixed source implementation without permitting a new external identity.

The exact patch and original/adapted source hashes are retained. Assertions are
unchanged. The helper's original relative toolchain include is supported by an
exact copy of the pinned toolchain file. Existing host `/tmp/myos`,
`/tmp/myworkspace`, and similar paths are untouched.

The test package's lock is normalized offline from the original OSDK lock.
For generated kernel/library workspaces, the Cargo shim normalizes the original
root Asterinas lock offline, verifies every external package's name, version,
source and checksum against that seed, then executes the real Cargo command
with `--locked --offline`. It only writes locks under the run's generated
directories. Every normalization, lock and command is recorded. A dependency
outside the pinned seed is a failure, including a newer cached version.
OSDK's new-project template uses the unqualified `nightly` channel and its build
command removes `RUSTUP_TOOLCHAIN`. The Cargo adapter therefore restores the
fixed channel and absolute `RUSTC`/`RUSTDOC` paths before every real subprocess,
and disables automatic toolchain installation. The runner checks the compiler
commit; command records include actual executable paths, versions and hashes.
The `metadata --no-deps` path only reads manifests before upstream adds local
OSTD. Actual dependency normalization always restarts from the complete seed.

The OSDK adapter changes only `build/run/test` boot options to direct multiboot
and the recording QEMU executable. The QEMU profile fixes q35, TCG, CPU `max`,
one vCPU, 512 MiB and explicit SeaBIOS. It preserves real GDB sockets, wait-for-
client, monitor sockets, coverage's no-shutdown behavior and original log path.
Network and data disks are rejected. Firmware pflash is replaced with SeaBIOS.
Coverage can legitimately exit through monitor quit with raw QEMU status 0;
other examples commonly exit with 33. Raw statuses are retained without being
replaced by a blanket success status. The hypervisor example's upstream VMX-
unavailable fallback is reported as a soft skip, never as a VMX success.

Each case retains the upstream harness output, exact commands, OSDK adapter
requests, Cargo identities/locks, and complete guest serial logs with hashes.
Top-level `result.json` reports passed, failed, blocked and soft skips separately.
An existing generated path blocks its case; cleanup only removes paths that
were absent before that exact case. Failed commands and timeouts remain in the
output for diagnosis.

The current host rejects AF_UNIX socket creation with EPERM. The original UNIX
GDB and coverage monitor transports are retained and their failures remain in
the 22-case denominator. A separate TCP VS Code/GDB case can pass on this host;
it does not establish UNIX socket support or usable coverage. Earlier failed
attempts, including a rejected registry `align_ext` identity, remain archived.
Coverage is accepted only with a nonempty saved raw profile, successful pinned
`llvm-profdata merge/show`, nonzero function count and nonzero execution count.

`archive.py SOURCE DESTINATION` saves logs, command/guest records, hashes, the
adaptation patch and locks, with deterministic gzip for large logs. It omits
generated example source, Cargo targets and tool binaries.

Pure profile checks (no VM):

```sh
python3 -I -m unittest discover -s support/build/osdk-integration -p 'test*.py' -v
```
