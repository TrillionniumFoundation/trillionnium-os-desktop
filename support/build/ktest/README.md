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
`locks/ostd.Cargo.lock`, `locks/aster-core.Cargo.lock`,
`locks/osdk-frame-allocator.Cargo.lock`, and `locks/aster-mlsdisk.Cargo.lock`
are committed; the
run-base lock is not used for tests. A failed fetch or drift audit stops
preparation; it does not silently resolve newer versions. The G1-a derived
aster-core lock contains 200 packages; the OSTD lock has 97 and the
frame-allocator lock has 88. The allocator test base does not forward OSTD's
optional `coverage` feature, so its lock excludes nine coverage/build-support
packages present in the OSTD test-base lock. It has its own
`osdk-frame-allocator-osdk-bin` test base; its lock cannot be substituted with
the OSTD lock. The first allocator lock report records actual offline metadata
and locked metadata only, using an existing cache without a fetch/install/build.

The runner installs OSDK from the vendored source with `--locked`, then invokes
`cargo osdk test` from `kernel/asterinas/ostd/`,
`kernel/asterinas/kernel/core/`, `kernel/asterinas/osdk/deps/frame-allocator/`, and
`kernel/asterinas/kernel/core/comps/mlsdisk/`, respectively. All four run by default.
`OSDK_CARGO_LOCK` selects the
corresponding fixed test-base lock. The installed downstream OSDK lock patch
copies it into the generated workspace and passes `--locked` to Cargo. The
runner checks the resulting generated lock against the selected input again.
`--skip-osdk-install` can reuse the already source-built patched OSDK.
Reuse is valid only when that OSDK was built from the same exact checkout path.
OSDK embeds local dependency paths at compilation; a binary from another
worktree can select incompatible path identities even at the same source
revision. Reinstall from the actual test checkout in a dedicated Cargo home
and retain its source path and binary digest before using this option.
The [retained failed and corrected runs](../../../results/integration/2026-10-24-asterinas-integration/kernel-unix-dontwait/README.md)
show this failure and the subsequent actual four-suite execution.

No upstream OSDK manifest is rewritten. The original upstream manifest expands
its ordinary test arguments, and `record-qemu.py` records those requested
arguments, keeps only the OSDK-generated kernel/initramfs/command line, and
constructs the actual fixed q35/TCG/CPU max/1-vCPU/512-MiB/SeaBIOS/serial/debug-exit
invocation. Network, data disks, GRUB, OVMF, an ISO and Nix are unnecessary.
The kernel-test runner has its own entry point and needs no userspace initramfs.

The runner shares the persistent `support/build/out-kernel.lock` inode with
the ordinary boot wrapper. Output uses a fresh directory and every guest has
its own serial log and QEMU JSON record. `--output DIR` refuses an existing
directory. `--crate ostd`, `--crate aster-core`, or
`--crate osdk-frame-allocator`, or `--crate aster-mlsdisk` runs just that crate.
`A01_KTEST_TIMEOUT` sets each guest timeout (default 300 seconds). A failed
build, failed guest or rejected summary stops the command and retains evidence.

By default no positional test filter is used. OSDK's `TESTNAME` is a complete
test-path suffix, despite the CLI describing a substring. Passing a crate name
as `TESTNAME` can filter out every test. `--test-name SUFFIX` is available for
focused diagnostics; the checker still requires at least one exercised test.
The frame-allocator and MLSDisk gates reject `--test-name` and `--allow-filtered`, including
when it is selected implicitly by the default four-crate run. Select OSTD or
core explicitly when running focused diagnostics for those crates.

The checker requires raw QEMU status 33 without timeout, the target crate's
serial bytes to match the recorded SHA256, its own nonempty consistent
summary, zero failures, zero filters in a full run,
and the final `All crates tested` marker. Expected-panic tests are valid and
do not use the boot smoke's panic-string filter. Upstream tests that print
`[skipped: ...]` yet return success are reported separately as soft skips;
in particular TCG does not establish VMX/EPT support. Runner pass counts must
not be presented as proof that those skipped hardware paths ran.

## Complete frame-allocator gate

Run the original allocator crate independently with its own fixed lock:

```sh
python3 -I support/build/ktest/prepare-locks.py --crate osdk-frame-allocator
python3 -I support/build/ktest/run.py --crate osdk-frame-allocator --output /path/to/new-evidence
```

This is an additional suite; it does not qualify or replace OSTD or aster-core.
It uses the original OSDK test generator and test runner, no replacement kernel
entry, no positional filter, no extra Cargo features, and the default N0 profile
(q35, TCG, CPU max, one vCPU, 512 MiB, SeaBIOS). `cfg(ktest)` compiles the reserve
mechanism in this crate. Normal builds without `physical-reserve` keep the
ordinary allocator path; the explicit G1-d feature forwards `physical-reserve`.
The source verifier derives only these two exact feature additions from the
original manifests; it still rejects other manifest changes.

The gate fixes all 20 test names: all nine original allocator tests, eight
initial reserve regressions and three callback-ownership regressions. Every
name must appear exactly once, terminate with
its own `ok`, and precede the single complete target summary. Filtering,
soft-skipping even one original test, replacing names while keeping a count,
or shrinking the denominator fails. It also verifies the recorder's actual
QEMU arguments against the fixed N0 profile, the serial hash, raw exit 33 with
no timeout, and ordered runner completion. Updating the suite requires an
explicit inventory review in `check.py` and its source-inventory test.

The exhaustion test must emit one `PHYSICAL_RESERVE_EXHAUSTION` receipt inside
its own successful test record, after restoring memory and all assertions.
The receipt records ordinary allocation failure, successful allocation from
the protected 64-page extent, and return to the original ordinary owner after
close. The checker rejects missing, duplicated, misplaced or contradictory
receipts. The original allocator may retain unusable cache fragments; the test
requires real allocation failures, not an approximate free counter of zero.
N0 concurrent-holder tests establish task interleavings, not simultaneous SMP
qualification.

`allocator_exhaustion.global_recovery_guarantee` remains **false** even after
these 20 tests pass. This mechanism gate does not establish production recovery
admission, VMAR/page-table/IPC budgets, or a complete Hepta recovery path.
The host tests under `support/build/tests/` mutate synthetic logs to test
rejection; their success is not a guest pass. Hashes and command records bind
captured artifacts and logs within a retained run; they are not cryptographic
attestation against a host able to rewrite all evidence.

The separate full OSTD run must also execute
`ostd::mm::frame::allocator::allocation_claim_rejects_busy_page_without_refunding_its_owner`
once without soft-skipping, while preserving the 222-test baseline. Together
with `ostd::user::fatal_pre_entry_returns_kernel_event_before_unmapped_user_code`,
the retained OSTD gate contains 224 tests. The five named explicit-reserve
page-table tests in `RECOVERY_PAGE_TABLE_TESTS` increase the full gate to 229;
all seven required OSTD names must execute once without soft-skipping. See
[recovery page tables](../../../docs/agents/RECOVERY_PAGE_TABLES.md). The first test checks failed preclaim of a real physical
extent: only acquired original owners are released; a busy page and unclaimed
tail retain their separate ownership. A successful allocator-only invocation
does not execute this OSTD test because the original OSDK crate whitelist is
preserved.

The full core gate also retains its actual 292-test baseline plus three named
zero-quota fatal-cleanup tests (295 total). These do not replace the real
SIGKILL/wait/reap and user-progress checks in the six-boot watchdog suite. See
[zero-CPU fatal cleanup](../../../docs/agents/ZERO_CPU_FATAL_CLEANUP.md) for the
ownership and execution boundary.

The preparation reports include the original seed tree/blob/SHA256, working
root-lock SHA256 and resolved feature sets. Disabling generated
base default features alone does not necessarily disable OSTD's defaults,
because the upstream test-kernel dependency also depends on OSTD.

No test result is claimed by adding these entry points. Consult actual saved
guest evidence for the completed, failed or filtered tests of each invocation.


## Complete MLSDisk gate

The experimental MLSDisk workspace component has a separate original-OSDK
suite. It is not assembled into the ordinary core image. Its native suite
retains the one original `write_sync_read` test and adds three device-flush
regressions, seven entropy/transaction regressions, and four delayed-I/O/owner/fixture
regressions, for **15** exact native tests. The 34 `#[test]` declarations in
old host-style modules are not additional executed kernel tests.

```sh
python3 -I support/build/ktest/prepare-locks.py --crate aster-mlsdisk
python3 -I support/build/ktest/run.py --crate aster-mlsdisk --output /path/to/new-evidence
```

The independent 161-package lock is normalized by real offline Cargo metadata
from the immutable original upstream root lock, then verified with
`--offline --locked`. It adds only `aster-mlsdisk-osdk-bin 0.1.0`; every external
package/source/checksum remains in the original seed. Its initial committed
report records metadata only, without fetch, install, build or guest execution.
The standard prepare command can subsequently prefetch this exact audited lock.
The real OSDK-generated test-base lock must match it byte for byte at execution.

The checker requires the original success test and all fourteen added exact names
once each, each with its own terminal `ok`, zero failures/filters/soft skips,
ordered runner completion, unchanged serial hash, and actual default N0
q35/TCG/one-CPU/512-MiB invocation with raw QEMU exit 33 and no timeout. Missing,
renamed, duplicate, filtered, skipped, hung or summary-only results fail. The
existing complete core/OSTD/frame-allocator gates remain independent.

These are real native Bio paths on the original Frame-backed MemoryDisk with
injected device errors; they do not establish physical-media durability or
power-loss recovery. The report explicitly retains
`mlsdisk_media_durability_qualified=false`. The fallible entropy API and transaction ordering are detailed in the
[entropy contract](../../../docs/agents/MLSDISK_ENTROPY_FAILURE.md). The [asynchronous I/O contract](../../../docs/agents/MLSDISK_ASYNC_OWNERS.md)
describes the sleeping-lock and callback-owner changes and their four additional
native tests. Native evidence is required separately; broader persistence/recovery
gaps remain open. The
[flush contract](../../../docs/agents/MLSDISK_FLUSH_PROPAGATION.md) records the
preceding four-test slice; its inventory is historical, not the current total.

## G2 initial Root Process-state gate

The separate `--g2-initial-root` option enables only the explicit
`g2-trusted-daemon` feature and preserves the complete original unfiltered
core suite, one-CPU N0 machine and fixed lock. `check-g2.py` first uses the
unchanged original core inventory (365 baseline, 126 required names), then
requires each of the three new Root Process-state tests to terminate once
with its own exercised success. A changed feature, filter, machine, missing
test, soft skip, mutable compile input or changed lock is rejected.

`HEPTA_TRUSTED_INITIAL_ELF` and `--trusted-initial-sha256` are both required.
This bounded static ELF is copied read-only into the run evidence only for
compiling the trusted profile. The ktests do not execute that userspace ELF
and do not qualify an original Hepta entry, durable CPU effect or recovery.
Use the complete original four-crate invocation separately for the ordinary
configuration; its inventories remain unchanged.

```sh
HEPTA_TRUSTED_INITIAL_ELF=/absolute/pinned/compile-input.elf \
python3 -I -B support/build/ktest/run.py --g2-initial-root \
  --crate aster-core --trusted-initial-sha256 FULL_SHA256 \
  --skip-osdk-install --output /absolute/new/g2-process-evidence
```
