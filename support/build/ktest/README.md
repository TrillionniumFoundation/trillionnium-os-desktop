# Real upstream kernel-mode tests

These entry points run the fixed Asterinas `cargo osdk test` runner in real
QEMU guests. They do not run host unit tests or the userspace boot script.
They preserve the existing process, scheduler, OSTD and OSDK sources.

After the host setup documented in `../README.md`, from the project root:

```sh
python3 -I support/build/ktest/prepare-locks.py
python3 -I support/build/ktest/run.py
```

Preparation uses `nightly-2026-07-21`. It mirrors the fixed OSDK test-base
manifest into an isolated temporary directory, validates the committed derived
lock against the immutable upstream seed, and populates a cold cache with
`cargo fetch --locked`. It then replaces only that temporary lock with the
original root `Cargo.lock` read from the fixed upstream Git blob, normalizes
it with offline Cargo metadata, and
checks it again with `--offline --locked`. Every external package version,
source and checksum must belong to the original upstream lock. The only added
local packages are each OSDK test-base and, for `aster-core`, this checkout's
`os-control 0.1.0` with only `portable-spin`; `spin 0.9.9` is already pinned in
the original lock. This feature selection does not qualify portable-spin as a
kernel lock backend. The original Git seed is immutable; the working root lock
is a separately validated 235-package local derivative, not a new seed. Its
only changes from the 234-package seed are the core dependency edge and local
`os-control` package. Complete component-macro metadata uses `--locked`, so it
cannot implicitly update that working lock during compilation. Separate
`locks/ostd.Cargo.lock` and `locks/aster-core.Cargo.lock` are committed; the
run-base lock is not used for tests. A failed fetch or drift audit stops
preparation; it does not silently resolve newer versions. The G1-a derived
aster-core lock contains 200 packages; the unchanged OSTD test lock has 97.

The runner installs OSDK from the vendored source with `--locked`, then invokes
`cargo osdk test` from `kernel/asterinas/ostd/` and
`kernel/asterinas/kernel/core/`, respectively. `OSDK_CARGO_LOCK` selects the
corresponding fixed test-base lock. The installed downstream OSDK lock patch
copies it into the generated workspace and passes `--locked` to Cargo. The
runner checks the resulting generated lock against the selected input again.
`--skip-osdk-install` can reuse the already source-built patched OSDK.

No upstream OSDK manifest is rewritten. The original upstream manifest expands
its ordinary test arguments, and `record-qemu.py` records those requested
arguments, keeps only the OSDK-generated kernel/initramfs/command line, and
constructs the actual fixed q35/TCG/CPU max/1-vCPU/512-MiB/SeaBIOS/serial/debug-exit
invocation. Network, data disks, GRUB, OVMF, an ISO and Nix are unnecessary.
The kernel-test runner has its own entry point and needs no userspace initramfs.

The runner shares the persistent `support/build/out-kernel.lock` inode with
the ordinary boot wrapper. Output uses a fresh directory and every guest has
its own serial log and QEMU JSON record. `--output DIR` refuses an existing
directory. `--crate ostd` or `--crate aster-core` runs just that crate.
`A01_KTEST_TIMEOUT` sets each guest timeout (default 300 seconds). A failed
build, failed guest or rejected summary stops the command and retains evidence.

By default no positional test filter is used. OSDK's `TESTNAME` is a complete
test-path suffix, despite the CLI describing a substring. Passing a crate name
as `TESTNAME` can filter out every test. `--test-name SUFFIX` is available for
focused diagnostics; the checker still requires at least one exercised test.

The checker requires raw QEMU status 33 without timeout, the target crate's
serial bytes to match the recorded SHA256, its own nonempty consistent
summary, zero failures, zero filters in a full run,
and the final `All crates tested` marker. Expected-panic tests are valid and
do not use the boot smoke's panic-string filter. Upstream tests that print
`[skipped: ...]` yet return success are reported separately as soft skips;
in particular TCG does not establish VMX/EPT support. Runner pass counts must
not be presented as proof that those skipped hardware paths ran.

The preparation reports include the original seed tree/blob/SHA256, working
root-lock SHA256 and resolved feature sets. Disabling generated
base default features alone does not necessarily disable OSTD's defaults,
because the upstream test-kernel dependency also depends on OSTD.

No test result is claimed by adding these entry points. Consult actual saved
guest evidence for the completed, failed or filtered tests of each invocation.

## Complete g1c post-exec object regressions

After committing the reviewed candidate, the explicit one-CPU profile compiles
`aster-core` with `g1c-trusted-observe` and runs the complete core suite. Ordinary
`run.py` does not select that Cargo feature from `HEPTA_G1C_TRUSTED_OBSERVE`.
The profile rejects `--test-name`, other crates and `--permission-attr-smp`.
It also rejects changed tracked source or untracked Rust/build/test inputs, and
records the exact commit/tree before and after execution.

The feature has a compile-time `include_bytes!(env!("HEPTA_TRUSTED_INITIAL_ELF"))`
input. Compile the already tracked G1-c probe into a fresh directory outside the
source tree, using the same command as the existing native G1-c runner:

```sh
mkdir /absolute/fresh/g1c-ktest-input
cc -std=c11 -O2 -Wall -Wextra -Werror -pthread -static -no-pie \
  -Wl,-z,noexecstack,-z,separate-code \
  tests/kernel/control/g1c_init.c \
  -o /absolute/fresh/g1c-ktest-input/g1c-init

python3 -I support/build/ktest/run.py --crate aster-core \
  --g1c-postexec-observe \
  --trusted-initial-elf /absolute/fresh/g1c-ktest-input/g1c-init \
  --skip-osdk-install \
  --output /absolute/fresh/g1c-postexec-ktest-output
```

Use the existing prepared Cargo cache and fixed test-base lock. Set `CARGO_HOME`
to that cache and `VDSO_LIBRARY_DIR` to the existing directory containing
`vdso_x86_64.so` when they are outside this checkout. The pinned toolchain remains
`nightly-2026-07-21`; the wrapper selects it itself. `--skip-osdk-install` is valid
only for the original source-built OSDK carrying the existing explicit-lock
patch. Kernel/OSDK builds sharing a target or installed OSDK must be serialized.

The wrapper uses the unchanged `prepare-trusted-image.py` to freeze the input
into its fresh output as mode 0444, records its SHA-256, and passes that absolute
copy to rustc. The input must be a nonempty little-endian x86_64 static ET_EXEC
within the existing 8 MiB bound. The existing kernel remains responsible for
full ELF and mapping validation. Kernel tests have their own entry point: they
do not boot or authorize this probe, and need no userspace initramfs.

`check-g1c-postexec.py` first calls the unmodified `check.py::check_guest` with
`allow_filtered=False`. Thus the original complete-core lower bound, every
retained required test, serial digest, raw exit 33, no timeout, no failures,
and completion markers remain mandatory. It then requires all five external
fence and eleven recipient/transaction tests exactly once without soft skips,
and a minimum equal to the original bound plus these sixteen additions. It
also verifies the fixed recorded Cargo command, source/feature identity,
frozen ELF and actual QEMU profile. It never treats a filtered subset as full
core qualification.

The checker has synthetic host negative controls, which can be run without
QEMU. Their output is not kernel pass evidence:

```sh
python3 -I support/build/ktest/test-g1c-postexec-check.py
python3 -I -O support/build/ktest/test-g1c-postexec-check.py
```

The result explicitly states `qualification=kernel-object-tests-only`,
`native_sealed_launch_qualified=false`, and `g2_qualified=false`. A full pass
still does not establish a sealed original Supervisor launch, userspace fd
handoff, a production FinalUse authority, or an original CPU grant/read. Those
require a separate native integration gate under the original owners.
