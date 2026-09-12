# Explicit legacy receipt copy to a managed store

**Work package:** D0C-06 / D3 storage prerequisite
**Evidence ceiling:** source candidate and local host tests only
**Automatic migration, service cutover, pruning, and replay:** none

## API and ownership

`ReceiptJournal::copy_legacy_chain_to_managed(paths, expected_journal_id, destination)`
returns `Result<ReceiptMigrationReport, JournalError>`. It accepts 1–64 explicit,
ordered, canonical absolute UTF-8 source paths starting at segment one, the
expected nonzero `JournalId`, and a NEW canonical absolute destination directory.
No environment variable, service default, package activation, listener, key or
network capability is added. The implementation lives in
`crates/hepta-session-core/src/receipt_journal/migration.rs`.

This is an offline **verified copy**, not an atomic switch of running services.
An operator must first stop the source service and obtain its authoritative
complete chain from trusted configuration. Passing an internally consistent
prefix cannot reveal an unknown omitted successor. The operation neither
searches an arbitrary directory for likely files nor invents a trusted chain head.
The old service must remain stopped through subsequent configuration cutover;
the copy function does not permanently lock out another legacy writer after it
returns. No CLI or automatic startup migration is introduced by this change.

`ReceiptMigrationReport` contains the journal ID, original/copy paths, per-segment
byte counts and SHA-256 digests, record count, unresolved receipt count, next
sequence, and final record digest. It has no receipt payload or execution method.
It is NOT a signed attestation, a deletion permit, or an anti-rollback checkpoint.

## Source custody and strict admission

All original segment descriptors are opened **read-only** and nonblockingly
locked before decoding. No `ReceiptJournal::open` writer, `WriterLease`,
`.writer-lock` update, tail repair, truncate, rename or deletion is performed on
sources. Reading may update filesystem access times; byte content, source
permissions and lease payload are not intentionally changed.

Input paths and every ancestor obey the existing path-custody rules. Symlinks,
hard-link aliases, duplicate inodes, dangerous permissions, and a managed or
already-migrating parent are refused. A cooperating active writer yields
`WriterBusy`, before creation of any destination entry.

The actual v1 record decoder and `chain::validate_reports` are reused in STRICT
mode: journal identity, continuous segment/record sequences, both predecessor
links, terminal predecessors, immutable receipt admission coordinates and global
receipt lifecycles must agree. A torn active tail is rejected without repair.
Historical accepted d5 receipts remain byte-identical; invalid historical
records are not rewritten into apparent validity.

Bounds remain 64 segments, 64 MiB per segment, 128 MiB total and 131072 records.
Source iterators are consumed only through the 65th entry to reject overflow.
There are at most two segment-descriptor sets plus directory and marker handles.
Copies read one bounded segment at a time, not an unbounded filesystem stream;
decoded admission data is separately bounded by the existing record limits.
Allocation failure, filesystem stalls and OS scheduling are not real-time bounded.

## Destination transaction and commit boundary

The destination is reserved with create-new directory semantics and mode 0700.
Existing files, directories and symlinks are not adopted, cleared or overwritten.
A directory inode lock serializes cooperating managed readers and writers.

1. Strictly validate all sources before creating the destination.
2. Create and sync the new directory's parent entry. Open and lock the directory.
3. Write canonical `store.v1` marker bytes to `migration.pending`, sync that file,
   then sync the directory. Both managed and unmanaged writer paths refuse this
   staging state: the former lacks a committed marker; the latter explicitly
   rejects the migration marker name.
4. Independently create each `segment-{number:016}.journal` as mode 0600. Copy
   original bytes, sync each file, and retain its separate inode lock. No hard
   links, re-encoding, lifecycle classification or synthetic terminal record.
5. Re-read every locked source against its original digest. Verify the complete
   closed staging inventory, pinned directory/marker/file identity, and each
   copied digest. Sync the staging directory before publication.
6. Rename `migration.pending` to `store.v1` in that same new directory, then sync
   the directory. The pre-existing managed v1 layout is now complete; no new
   permanent file type or record version is introduced.
7. Recheck the final inventory and source/copy digests before returning a report.

The rename is a commit point, not proof that the caller received success. An I/O
failure or process death after it may leave a complete valid copy. Error is never
interpreted as “destination absent.” Do not retry over an existing destination.
A normal managed reopen can re-establish the directory durability barrier when
all bytes and identities validate. Partial `migration.pending` directories remain
rejected even under `RECOVER_CRASH`; they are never auto-completed or discarded.

The new directory is private and initially absent. Its lock and closed inventory
prevent cooperating writers from inserting a competing marker. `std::fs::rename`
can replace a target inserted by an uncooperative same-UID/root process between
checks. This mechanism does not claim hostile-local-writer authenticity or
atomicity against such an actor. Do not reuse it as a general privileged importer.

## Failure and cutover matrix

| Stage | Source | Destination | Next action |
|---|---|---|---|
| Invalid source or active writer | Preserved | Absent | Correct source selection or quiesce the writer |
| Directory/marker/segment write failure | Preserved | Absent or incomplete | Preserve and inspect; no auto-adoption |
| Complete copied data, marker still staged | Preserved | Writer admission refused | No automatic migration resume |
| Marker renamed, result lost or sync failed | Preserved | May be a complete copy | Inspect strictly; do not infer absence |
| Success report | Preserved | Complete managed v1 store | Independent verification and controlled service cutover |

Service configuration remains a separate operation. After independent verification,
select the managed directory using the existing explicit development configuration
only in its approved profile. Do not run the old and new writers as two authorities
for the same journal. Keep originals under the applicable retention policy; this
API does not authorize deleting them. Unresolved `Dispatched` potential effects
remain `NeverAutomatic`; only the existing independent recovery path may append
an honest `Indeterminate` classification, never execute the effect.

## Verification and limits

The Rust tests exercise byte/header/privacy preservation, old receipt-ID refusal,
retained unresolved state, source read-only descriptors, unchanged source sidecars,
active writers, malformed chains, links/permissions, existing destinations, sparse
oversized inputs and the 64-segment boundary. Same-length mutation and source-path
replacement tests exercise post-admission revalidation under held advisory locks.

A dedicated custom test harness compiles the exact journal source and pauses at
16 specified migration boundaries before real SIGKILL. The unit fault matrix
injects EIO and ENOSPC at the same boundaries (32 combinations), including actual
partial prefix writes. Sources and lease bytes are compared after every failure;
only post-publication states may reopen. Existing partial destinations cannot be
adopted by rerunning the copy. These are userspace file/process tests, not physical
power loss, torn-sector, filesystem-journal-replay or device-cache qualification.

`contracts/legacy-receipt-migration.v1.json` and
`tools/audit_receipt_migration.py` bind the source boundaries, fault inventory and
non-claims into the existing receipt source audit. Structural auditing is not
formal verification and does not independently attest a running deployment.

Repository publication, exact-head CI, independent review, exact-main regression,
installed-service cutover, archive deletion, partial-initialization repair, trusted
anti-rollback storage and D8/D9 qualifications remain independent gates.
