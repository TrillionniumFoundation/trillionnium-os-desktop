# Real upstream kernel-mode tests

These entry points run the fixed Asterinas `cargo osdk test` runner in real
QEMU guests. They do not run host unit tests or the userspace boot script.
They preserve the existing process, scheduler, OSTD and OSDK sources.

`CARGO_ENCODED_RUSTFLAGS` must be unset, including an explicitly empty value.
Cargo otherwise gives it priority over OSDK's required kernel `RUSTFLAGS`.
The entry refuses that environment before creating output, acquiring a
workspace lock or invoking tools; unset the variable and retry the same
command and output path.

After the host setup documented in `../README.md`, from the project root:

```sh
python3 -I support/build/ktest/prepare-locks.py
python3 -I support/build/ktest/run.py
```

Preparation is offline and uses `nightly-2026-07-21`. It mirrors the fixed
OSDK test-base manifest into an isolated temporary directory, seeds its lock
from the original root `Cargo.lock`, allows Cargo metadata to normalize that
lock, then checks it again with `--locked`. Every external package version,
source and checksum must belong to the original upstream lock. Separate
`locks/ostd.Cargo.lock` and `locks/aster-core.Cargo.lock` are committed; the
run-base lock is not used for tests. Preparation may fail if the pinned Cargo
dependencies have not been cached; it does not silently resolve newer versions.

The runner installs OSDK from the vendored source with `--locked`, then invokes
`cargo osdk test` from `kernel/asterinas/ostd/` and
`kernel/asterinas/kernel/core/`, respectively. `OSDK_CARGO_LOCK` selects the
corresponding fixed test-base lock. The installed downstream OSDK lock patch
copies it into the generated workspace and passes `--locked` to Cargo. The
runner checks the resulting generated lock against the selected input again.
Each run installs the patched OSDK from its actual upstream checkout into the
exclusive new output's `osdk/` directory using `cargo install --root`. Tests call
that absolute `osdk/bin/cargo-osdk` path with `osdk test` arguments. They do not
use Cargo's external-subcommand lookup or install into the global Cargo bin.
The environment receipt records the private executable, installation root,
source root and executable SHA256; the install/test command receipts retain the
actual arguments. Missing, linked or nonexecutable private SDKs and installation
failures stop the run without selecting a different SDK.

`--skip-osdk-install` is retained only to provide a clear error: it exits2 before
creating any output or acquiring the workspace lock. Remove the flag for a new
run. No global or previous-output SDK reuse is accepted. With `OSDK_LOCAL_DEV=1`,
OSDK binds local OSTD and helper paths through compile-time `CARGO_MANIFEST_DIR`;
runtime environment changes cannot rebind them. Even the same Git commit in a
different worktree therefore requires its own installation. Rust dependency and
kernel target caches retain their existing behavior.

`test_sdk_isolation_mock.py` checks prefix/argv/receipts, failure propagation and
the early deprecated-option guard entirely in-process with `unittest.mock`.
These tests execute no SDK/helper binary and no Rust or QEMU. The existing
process lifecycle fixture was statically adjusted to its new private install
location; its subprocess tests and real kernel-mode suites require separate
execution records and are not implied by passing the new mock tests.

No upstream OSDK manifest is rewritten. The original upstream manifest expands
its ordinary test arguments, and `record-qemu.py` records those requested
arguments, keeps only the OSDK-generated kernel/initramfs/command line, and
constructs the actual fixed q35/TCG/CPU max/1-vCPU/512-MiB/SeaBIOS/serial/debug-exit
invocation. Network, data disks, GRUB, OVMF, an ISO and Nix are unnecessary.
The kernel-test runner has its own entry point and needs no userspace initramfs.

For a prepared private QEMU installation, `A01_QEMU_BIOS` selects a nonempty
absolute regular firmware file and `A01_QEMU_DATA_DIR` selects a nonempty
absolute existing resource directory (passed as one `-L`). The recorder imports
the ordinary recorder's selectors by absolute source path; it does not maintain
a second validation policy. An explicit data directory conflicts with any
incoming OSDK `-L` and is rejected. Invalid selections fail before QEMU's version
probe or launch. Without these variables, the ordinary fixed system BIOS path
and fixed profile remain in effect.

Each guest retains the original OSDK arguments, the fixed arguments before
selection, selection provenance and actual argv. Firmware hashes bind the
selected file using the shared stable-FD capture. The runner's environment
input hashes include the ordinary selector source, and each guest identifies
that dependency too. This does not add immutable snapshots to the ktest path;
it preserves its existing source-artifact model and unchanged result checker.

The runner shares the persistent `support/build/out-kernel.lock` inode with
the ordinary boot wrapper. Output uses a fresh directory and every guest has
its own serial log and QEMU JSON record. `--output DIR` refuses an existing
directory. A busy workspace lock is rejected before creating the requested
output or its parent. `--crate ostd` or `--crate aster-core` runs just that crate.
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

The preparation reports include resolved feature sets. Disabling generated
base default features alone does not necessarily disable OSTD's defaults,
because the upstream test-kernel dependency also depends on OSTD.

No test result is claimed by adding these entry points. Consult actual saved
guest evidence for the completed, failed or filtered tests of each invocation.

The CLI cooperatively handles SIGINT and SIGTERM, retaining the first request
as status 130 or 143. Every subprocess, including source verification, compiler
and Git metadata, runs in an owned session. The runner holds the workspace lock
while sending TERM then KILL to the original process group and reaping its
direct leader. `waitid(WNOWAIT)` anchors that group until its final signal; an
externally reaped leader disarms group signals. Descendants must remain in the
original group. Their exit after KILL is asynchronous; the runner does not
adopt or claim to reap grandchildren.

Each subprocess log has a sibling `<log filename>.command.json` recording its
argv, cwd, raw child wait status (`raw_exit_code`), normalized effective
`exit_code`, and direct-leader cleanup. Cancellation keeps the actual raw
child status, such as -15 or -9, while its effective `exit_code` is 130 or 143. Cancelled invocations retain
`result.json` with `passed: false`, `interrupted_by`, `received_signals` and
`exit_code`. The aggregate result also records the runner SHA256, pinned
toolchain and relative command-receipt paths. Existing evidence directories
are never overwritten.

Host-only lifecycle regression (fixture commands, no Rust build or QEMU):

```sh
python3 -I support/build/ktest/test_runner_lifecycle.py -v
python3 -I -O support/build/ktest/test_runner_lifecycle.py -v
```
