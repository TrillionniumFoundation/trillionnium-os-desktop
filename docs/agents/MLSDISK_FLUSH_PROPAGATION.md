# MLSDisk flush completion and error propagation

This change fixes a concrete persistence-reporting defect in the experimental
`aster-mlsdisk` crate. In source `10dae5ea4ae5c2f81e2e530b1eb74bd41a5c29cd`,
`RawDisk::flush` returned `Ok(())` without asking its underlying block device to
flush its volatile cache. Public `MlsDisk::sync` and `TxLogStore::sync` also
unwrapped legitimate downstream I/O failures. A caller could therefore receive
false success, or panic once actual device errors were exposed.

## Original owner and changed behavior

The original `RawDisk` still owns its `Arc<dyn BlockDevice>` and region. A flush
now submits the original `BioType::Flush` with an empty segment list, and uses
`Bio::submit_and_wait` to observe the original device completion. Only
`BioStatus::Complete` returns success. Submission refusal/full/too-big and
terminal unsupported/no-space/I/O errors return the crate's `Errno::IoFailed`.
There is no retry, replacement queue, extra durability ledger or synthetic
completion. Flushing a subregion flushes the same underlying device cache.

The existing chain remains:

`BlockDevice::enqueue(Flush)` → `MlsDisk::sync` → `DiskInner::sync` →
`TxLogStore` / `BlockSet::flush` → `RawDisk` → original `BlockDevice`.

`MlsDisk::sync` and the two fallible operations in `TxLogStore::sync` now use
`?`. The original outer Bio completion translates a returned sync error to
`BioStatus::IoError`; it no longer requires a panic at those three sites.
Other append/compaction paths still have separate error-handling limitations.
This slice does not claim all MLSDisk I/O failures are recoverable.

## Exact native regression scope

The original crate has **one native `#[ktest]`**, `write_sync_read`. The other
34 source test attributes are under the old `#[cfg(test)]` host-style modules;
they are not 34 additional executed OSDK tests. Preserve that distinction.

The native suite retains `aster_mlsdisk::test::write_sync_read` and adds:

- `aster_mlsdisk::test::raw_disk_flush_submits_and_reports_terminal_failure`
- `aster_mlsdisk::test::mlsdisk_sync_returns_device_flush_error`
- `aster_mlsdisk::test::mlsdisk_flush_bio_completes_with_io_error`

The existing success test now checks that sync reaches the underlying device.
The new low-level case invokes the real Bio submission/completion API and
checks all six submission/terminal failure modes, with exactly one request per
call. The two upper-layer cases format the original encrypted/logged MlsDisk
on the original Frame-backed MemoryDisk, buffer a real data write, inject a
device flush completion error or enqueue refusal, and require a returned error
or completed error Bio, without panic or retry. The fixed geometry preserves
the journal's original snapshot-capacity requirement.

These are native failure-injection tests with an in-memory block device. They
do not establish real-media durability, power-loss recovery, hardware cache
behavior or asynchronous device completion. The unfiltered original execution
entry is, from `kernel/asterinas/kernel/core/comps/mlsdisk`:

```sh
cargo +nightly-2026-07-21 osdk test
```

Do not supply a test-name filter or count old host attributes as native tests.
A complete result must contain all four exact native names and their own
terminal `ok`, zero failure/filter/soft skip, runner completion, and actual raw
QEMU exit 33 without timeout. The [project wrapper](../../support/build/ktest/README.md#complete-mlsdisk-gate)
now has a separate fourth crate/test-base lock and supports
`--crate aster-mlsdisk`; the existing core/OSTD/frame-allocator suites remain
independent and complete. Its host anti-forgery tests do not execute the guest.

## Remaining blockers and qualification

The crate is a workspace **default-member**, but the ordinary assembler and
`aster-core` manifests at the audited source do not depend on it. This patch
does not add default device registration or expose a new production disk.
The public library/optional component still needs correct errors regardless of
that current assembly boundary.

Known independent blockers remain:

- Component initialization selects device 255:0, creates a new random root key
  and calls `MlsDisk::create`. It is not a non-destructive device-selection or
  persistent-key/reopen policy.
- `os::Rng::fill_bytes` currently substitutes zero when `read_random` fails,
  and the infallible RandomInit chain hides failure. This is a separate
  fail-closed entropy/key-generation defect, not fixed here.
- The public write/sync region uses OSTD's spin `RwLock` with preemption
  disabled across I/O. An actually delayed Bio may need to sleep, which is
  invalid in atomic mode. Synchronous MemoryDisk completion does not exercise
  this path. The cross-I/O locks and deeper journal/LSM locks require an
  independent sleeping-lock/async-completion audit and native tests.
- Journal append/compaction still contain I/O `expect` paths. This change
  removes the sync-specific unwraps above, not all storage failure panics.
- Physical-media flush/power-cut recovery and durable key management are
  unverified; passing the four native cases cannot close those blockers.

At this documentation revision, only source inspection, ordinary and
`cfg(ktest)` Cargo check, and `cfg(ktest)` Clippy `-D warnings` are local static
validation. Actual same-source guest execution is pending and must be recorded
separately, with its source identity and artifacts.
