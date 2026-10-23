# MLSDisk entropy failures and transaction publication

## Source and public contract

This slice follows `cd515fbc9c4e60ea02b1f984753aaf0fd9934a22` (the original
flush fix and independent native-suite gate). It changes the experimental
`aster-mlsdisk` workspace component; it does not add it to the ordinary kernel
assembly, choose a persistent root key, or format any real device.

Previously `os::Rng::fill_bytes` converted `ostd::arch::read_random()` returning
`None` into zero bytes and returned success; `RandomInit::random` then discarded
any error. Missing entropy could silently become an all-zero or partially zero
key/IV. Now the original hardware entropy function remains the only production
source. Each failed word returns `Errno::OsSpecUnknown`. The filler requests
exactly ceil(length / 8) words, including zero requests for an empty slice.
Legitimate zero-valued random words remain valid; zero substitution is removed.
A failed fill may have partially changed its destination and callers must discard
that value.

The public `RandomInit::random` signature is now `Result<Self>` for all generated
AEAD and stream-cipher key/IV/MAC types. External users must handle this API change.
`CryptoChain::new` is likewise fallible. Every production random key/IV call uses
`?`; component initialization translates failure to `ComponentInitError::Unknown`.
No default key, retry, weak PRNG, public injection control, or new unsafe code is
introduced. Default values used for the first chain's predecessor MAC or a
version-based IV remain protocol fields, not fallback entropy.

## Original state owners and error order

- `CryptoBlob::create` and `CryptoChain::{new,append}` fail before publishing
  their object or appending the affected encrypted block.
- `DiskInner::write_blocks_from_data_buf` obtains all keys before its original
  allocation table reserves HBA slots. A failure here preserves buffered data
  and makes no device write. This does not establish rollback for later I/O
  errors or all LSM failure phases.
- `MhtStorage::append_mht_nodes` only publishes node-cache entries after every
  key and the original block-log append succeed. Other MHT operations propagate
  failure; this slice does not promise that an arbitrary failed CryptoLog flush
  is independently retryable after partially writing earlier nodes.
- `TxLogStore::create_log` obtains its key before creating the original raw log
  or inserting a cache. Its abort handler removes caches for the transaction's
  created logs using the original `TxLogStoreEdit`; the original ChunkAlloc
  abort handler retains block rollback ownership.
- `EditJournal::commit` is fallible. When older buffered records cannot be
  appended, the current EditGroup is not applied to journal state. The old
  buffered records remain available for a later flush. Journal write/flush/
  compaction now propagate their errors instead of the former I/O expects.
- The journal handler is registered first among **precommit** handlers. The
  original TxProvider invokes them in reverse order, making the journal the
  final fallible step before the original non-failing commit handlers publish
  state. This preserves the original transaction owner and abort mechanism.
  Both format and recovery register in this order. Listener callbacks also
  propagate allocation-log failures instead of unwrapping them.

This does not make journal media writes transactional at the device level.
Snapshots or earlier successful writes may already exist when a later error is
returned. No power-cut, write-ordering, replay-resistance, or physical-media
qualification is inferred from error propagation.

## Exact native regression inventory

The previous four native tests remain. Seven new native cases make **11**, and
the original 34 host-style `#[test]` declarations remain a separate inventory:

| Native suffix (crate `aster_mlsdisk`) | Behavior exercised |
| --- | --- |
| `os::entropy_test::entropy_fill_reports_partial_failure_and_exact_word_count` | Exact 0/1/8/9/16/17-byte requests, valid zero entropy, first-word and partial failures without zero substitution |
| `os::entropy_test::entropy_cut_is_task_scoped_and_restored_on_drop` | Original Task identity, another real spawned Task unaffected, all generated types denied, RAII restores the real source |
| `test::entropy_failure_prevents_blob_and_chain_publication` | Frame-backed real Bio storage, key and partial IV failure, no unintended append/range change, subsequent actual append/read |
| `test::entropy_failure_keeps_buffered_disk_data_for_retry` | Real encrypted disk with two pending blocks, cuts at words 0/1/2/3, zero extra device writes, data remains readable, later sync/read |
| `test::entropy_failure_aborts_original_log_transaction` | Failed creation and original precommit abort, no new visible log, later successful transaction |
| `test::entropy_failure_does_not_apply_current_journal_edit` | Actual full journal buffer, failure leaves earlier committed state, flush and recover excludes the rejected edit |
| `layers::log::tx_log::entropy_tests::journal_entropy_failure_aborts_before_log_publication` | Original log transaction reaches journal entropy failure after data/root preparation; persistent state, journal state and cache exclude the aborted log |

The cut exists only under `cfg(ktest)`. An opaque, non-Send/non-Sync RAII guard
holds an Arc to the exact original current Task; identity is not a truncated
pointer, PID or caller-supplied label. The cut only returns failure after a
bounded count of successful word requests; it never supplies bytes. IRQ context
bypasses its lock and does not consume the interrupted Task's counter. Another
Task cannot consume the selected Task's counter. The guard is not nested and
clears the cut on drop. Ordinary builds contain no injection module or control.
These are **deterministic entropy cuts**, not proof of a hardware entropy failure.

The strict original unfiltered OSDK entry remains:

```sh
python3 -I support/build/ktest/run.py --crate aster-mlsdisk --output /path/to/new-evidence
```

It retains the same audited 161-package lock and N0 q35/TCG/one-CPU/512-MiB
profile. All 11 exact names require terminal success, no filtering or soft skips,
complete runner output and actual raw QEMU exit 33 without timeout. The gate's
host anti-forgery tests do not execute those native cases. Existing core/OSTD/
frame-allocator suites and their denominators are unchanged.

## Validation status and independent blockers

Ordinary and `cfg(ktest)` Cargo check, `cfg(ktest)` Clippy with `-D warnings`,
the original 118-input source gate, rustfmt/diff checks, and all 44 ktest-evidence
host tests pass for this patch. These are recorded separately from native execution.
At this patch revision, no same-source MLSDisk guest result is claimed. Run and
retain the exact source/ELF/log identity before marking these regressions passed.

The cross-I/O lock issue remains open: public `write_sync_region`,
`CryptoLog.mht`, TxProvider handler vectors, and deeper LSM paths use spin RwLocks
across callbacks or I/O. Immediate MemoryDisk completion cannot qualify delayed
Bio behavior. A separate lock-chain change and actually delayed-I/O native
regression are required. Original strong-Arc callback/provider cycles also require a separate owner
lifecycle audit and actual last-reference release test; a single shutdown-after-
test run cannot establish that disks are reclaimed between tests.
Persistent root-key/reopen policy, non-destructive
component initialization, arbitrary post-write failure recovery and real-media
power-loss durability also remain open. See the preceding
[flush contract](MLSDISK_FLUSH_PROPAGATION.md) and the kernel module handbook.
