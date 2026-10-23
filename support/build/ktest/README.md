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
`locks/ostd.Cargo.lock`, `locks/aster-core.Cargo.lock`, and
`locks/osdk-frame-allocator.Cargo.lock` are committed; the
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
`cargo osdk test` from `kernel/asterinas/ostd/` and
`kernel/asterinas/kernel/core/`, and `kernel/asterinas/osdk/deps/frame-allocator/`,
respectively. All three run by default. `OSDK_CARGO_LOCK` selects the
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
directory. `--crate ostd`, `--crate aster-core`, or
`--crate osdk-frame-allocator` runs just that crate.
`A01_KTEST_TIMEOUT` sets each guest timeout (default 300 seconds). A failed
build, failed guest or rejected summary stops the command and retains evidence.

By default no positional test filter is used. OSDK's `TESTNAME` is a complete
test-path suffix, despite the CLI describing a substring. Passing a crate name
as `TESTNAME` can filter out every test. `--test-name SUFFIX` is available for
focused diagnostics; the checker still requires at least one exercised test.
The frame-allocator gate rejects `--test-name` and `--allow-filtered`, including
when it is selected implicitly by the default three-crate run. Select OSTD or
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
once without soft-skipping, while preserving the 222-test baseline (223 total
with this regression). This test checks failed preclaim of a real physical
extent: only acquired original owners are released; a busy page and unclaimed
tail retain their separate ownership. A successful allocator-only invocation
does not execute this OSTD test because the original OSDK crate whitelist is
preserved.

The preparation reports include the original seed tree/blob/SHA256, working
root-lock SHA256 and resolved feature sets. Disabling generated
base default features alone does not necessarily disable OSTD's defaults,
because the upstream test-kernel dependency also depends on OSTD.

No test result is claimed by adding these entry points. Consult actual saved
guest evidence for the completed, failed or filtered tests of each invocation.
