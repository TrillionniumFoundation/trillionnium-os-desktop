# MLSDisk asynchronous I/O and callback ownership

## Concrete defects and source boundary

This independent slice follows `148de6fa` (fallible entropy and the 11-test
suite). The ordinary kernel still does not assemble `aster-mlsdisk`; no device
registration, media selection or key policy is added.

Original MLSDisk code held OSTD spin `RwLock` guards across disk operations.
The public write/sync region was only the outermost occurrence. CryptoLog's
MHT, the LSM SST manager, an immutable memtable used during compaction, and
TxProvider's callback/initializer registries also held spin read/write guards
across code that can wait for I/O. A synchronous MemoryDisk makes the wait
condition immediately true and therefore hides the invalid atomic context.
An actual delayed Bio must park and violates OSTD's atomic-mode contract there.

Separately, provider callbacks captured state, RawLogStore and ChunkAlloc with
strong Arcs. Those owners or their caches/lazy-delete closures owned the same
TxProvider. The cycles retained the disk and its physical frames after the
last external store owner was dropped. A shutdown after one test cannot prove
last-reference reclamation; repeated tests at fixed memory can expose the leak.

## Original 512-MiB fixture failure

The actual preceding `9dffb043` MLSDisk run completed all 11 names with 5 passing,
6 failing and raw QEMU status 65. Its first large fixture allocation failed before
store creation. The serial log gives free regions `0..0x8000`,
`0x9000..0x9f000`, `0x100000..0x8000000` and `0x8a7d000..0x1ffe0000`.
The original buddy allocator requires a 256-MiB-aligned chunk for a 256-MiB
segment: the candidate starting at zero crosses reserved memory, while the
candidate at `0x10000000` extends beyond the free end `0x1ffe0000`. The fixed
512-MiB layout therefore cannot satisfy this fixture's unnecessary physical
contiguity requirement even though its total free capacity exceeds the disk size.

MemoryDisk now owns 65,536 ordinary `Frame<()>` values for the same 256-MiB
logical capacity, each allocated/refunded by the original allocator. Bio copies
use the original DMA and Frame VmReaders/VmWriters, splitting only at logical
page boundaries. No allocator behavior, geometry, memory profile or prior test
is relaxed. The new small copy regression deliberately reverses physical frame
order, writes an offset range across several pages/BioSegments, reads it through
a different segmentation and checks payload plus untouched prefix/suffix bytes.
The old failed run remains evidence; it is not retroactively considered passed.

## Locks, callback dispatch and owner graph

The same protected objects now use the original OSTD `RwMutex` for the four
I/O-spanning domains: `DiskInner.write_sync_region`, `CryptoLog.mht`,
`TreeInner.sst_manager` and `MemTableManager.immutable`. The read/write exclusion
and transaction/data ownership are unchanged. These operations remain Task
context APIs; this is not permission to call them in IRQ/atomic context.

TxProvider keeps short spin locks for its registries. Registry entries hold an
Arc to each original callback or typed initializer. Dispatch snapshots only the
starting length, visits the original indices in reverse order, clones one Arc
under the lock, and releases the guard before calling it. Registration only
appends. Consequently a callback registered during dispatch is first included
in the next dispatch of that stage; existing callbacks cannot move or disappear.
A typed initializer is likewise cloned before invocation. No callback is invoked
under a registry lock, including precommit, commit and abort. Reentrant
registration is supported; recursively committing/aborting the same transaction
or recursively accessing its data remains outside the original internal
callback contract. All production registrations are construction-time handlers.

RawLogStore's commit closure captures its existing Weak<Self>. TxLogStore's
commit/abort closures capture weak state/raw-store references. An active
CurrentTx borrows the original store/provider, and open raw logs own their store;
these original owners must remain live during the callback. Upgrade failure is
an invariant violation, not an I/O error and not silently skipped work. The
journal's strong callback reference is acyclic because it does not own the
provider. ChunkAlloc's callbacks capture only its state, which also has no
back-reference. No new resource ledger, dispatcher, transaction owner, or
fallible commit stage is introduced.

The lock order remains write/sync scope → tree/MHT or immutable/SST scope →
original object Mutexes → original Bio wait. Callback registry locks cover only
lookup/clone and are absent throughout the rest of that chain. Short SpinLocks
for notification counters, join results, and test injection remain local and do
not perform disk I/O while held. This change does not establish arbitrary
concurrent compaction, IRQ or SMP device qualification.

## Four additional native cases, total 15

The original 11 tests remain in the strict unfiltered suite. The added names are:

- `aster_mlsdisk::test::delayed_bio_completes_after_original_task_parks`
- `aster_mlsdisk::test::transaction_callbacks_sleep_and_defer_reentrant_registration`
- `aster_mlsdisk::test::final_store_owner_releases_real_disk_between_full_runs`
- `aster_mlsdisk::test::frame_backed_disk_handles_noncontiguous_cross_page_bios`

The first uses the original Frame-backed MemoryDisk behind a deferred device.
For every submitted Bio a different original OSTD Task performs completion.
Before completing, it asserts Bio status is still Submit and that the submitting
Task has actually left the original FIFO runqueue to wait. The fixed standalone
N0 MLSDisk test base uses that original scheduler; yield does not clear its CPU
assignment, while park does. This tests actual waiting, not a fake wait flag or
immediate completion. Format, sync, data read, terminal flush error, retry and
reopen all run through this device.

The second reaches the original TxProvider callbacks and typed initialization.
It performs actually deferred flush I/O inside precommit, commit, abort and
initializer callbacks. A callback appends another callback to its own stage;
the first round must call 2,1 and the next 3,2,1. The new initializer can also be
registered from an initializer. Exactly 21 actual park/completion events are
required. Commit remains infallible; this does not convert failures in commit
into generic abort.

The owner-release case formats/writes/syncs a full 256-MiB Frame-backed disk, drops the
last MlsDisk owner, and checks the original disk Weak cannot be upgraded. It
then repeats the full allocation under the unchanged 512-MiB N0 profile. No
smaller disk, larger guest, test filter, reset or synthetic owner is used to hide
retained physical memory.

The audited 161-package lock remains unchanged. The gate requires all 15 exact
native names and terminal success, no filters/soft skips, full runner completion,
source/artifact/log identity, and raw QEMU exit 33 without timeout. The 34 old
host-style tests and host anti-forgery gate tests are separate counts.

## Validation and remaining work

Ordinary and `cfg(ktest)` Cargo/Clippy compilation, the original 118-input source
gate, rustfmt/diff checks and all 44 ktest-evidence host tests pass.
Native execution is pending; compilation and host evidence checks cannot be
reported as the above behavior passing. Capture the exact same-source full
suite, including any failures, before closing these two blockers. The preceding
11-test source remains separately auditable.

Persistent root-key/reopen policy, non-destructive component initialization,
arbitrary post-write rollback, asynchronous compaction under SMP, physical media
cache behavior and power-cut recovery remain separate qualification work. This
slice does not implicitly flush or commit an unfinished user transaction on drop;
the original explicit commit/abort contract still applies.
