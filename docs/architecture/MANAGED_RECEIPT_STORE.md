# Managed receipt store: head selection and atomic rotation

## Status and claim ceiling

This is an opt-in **source candidate** for the d6 D0C-06/D3 storage boundary.
It owns local receipt files, not browser operations. It does not qualify Servo,
production AgentPort, installed images, physical power loss, authenticated
anti-rollback storage, external effects, hardware or release authority.

The explicit-path `ReceiptJournal::open_chain` API remains available for legacy
unmanaged journals. It requires a trusted caller to identify the authoritative
head. The new managed API eliminates that mutable caller-supplied path list
**only for a newly initialized managed directory**. It does not silently migrate
or reset an existing directory, journal or receipt namespace.

## Public API and ownership

The implementation is
`crates/hepta-session-core/src/receipt_journal/managed.rs`.

```rust
ReceiptJournal::create_managed(root, journal_id, created_wall_clock_unix_ms)
ReceiptJournal::open_managed(root, journal_id, ManagedOpenPolicy::STRICT)
ReceiptJournal::open_managed(root, journal_id, ManagedOpenPolicy::RECOVER_CRASH)
journal.is_managed()
journal.managed_rotation_due()
journal.rotate_managed(created_wall_clock_unix_ms)
```

Creation requires a new directory. Opening requires an existing valid marker
and a complete chain. `rotate_managed` consumes the writer and returns its old
seal plus the new writer. On error no writer is returned; the caller must stop
admission and reopen/inspect durable state. An I/O error is not evidence that
publication did not occur. Never retry by choosing the previous segment.

`ManagedOpenPolicy` has two independent fields: the existing journal tail/lease
policy and `complete_pending_rotation`. `STRICT` permits no pending completion
or tail repair. `RECOVER_CRASH` allows completion of a fully validated empty
pending header, or repair of the current segment's torn record tail when no
pending rotation exists. It never repairs a predecessor during publication.

`ReceiptLifecycleObserver` preserves its PageOwner shared object, principal,
image identity and logical clock when it consumes an idle journal for managed
rotation. An in-flight request prevents observer rotation before file changes.

## Directory layout and exact encoding

The root is an absolute canonical UTF-8 path of at most 4,000 bytes. Empty,
relative, repeated-separator, dot, parent, whitespace and control-character
paths are rejected, not normalized. Existing ancestor symlinks and unprotected
writable parents are rejected using the existing journal parent checks. The
root itself must be a real private directory with no group/other permissions.
Creation uses 0700; files use 0600 subject to the process umask.

The only allowed entries are:

```text
store.v1
segment-0000000000000001.journal
segment-0000000000000002.journal
...
next.pending                         # optional interrupted preparation only
```

`store.v1` is exactly 56 bytes: ASCII `HPTSTR01` (8), the expected nonzero journal
ID (16), then SHA-256 of the preceding 24 bytes (32). It contains no host path,
command or externally supplied active filename. The caller must provide the
expected journal ID; a matching checksum alone is not sufficient.

Segment names use exactly sixteen zero-padded decimal digits, starting at one.
The closed inventory must be contiguous and match the decoded header chain.
Unknown names, directories, symlinks, multi-link files, unsafe permissions,
missing segments and duplicate/noncanonical numbers are hard failures. Directory
enumeration stops at 66 entries (64 segments, marker, optional preparation).

The existing **v1 segment and record byte formats are unchanged**. Every prior
segment is validated and retained. The complete-chain limits remain 64 segments,
128 MiB and 131,072 records, with the existing 64 MiB per-segment ceiling.
Limits do not grant permission to delete old receipts or forget their IDs.

## Writer and path custody

The managed writer holds an exclusive nonblocking advisory lock on the actual
directory inode for its entire lifetime, plus the existing inode locks on every
segment. It does not create per-segment PID lease sidecars. A terminated process
releases the managed directory lock through the operating system; a stale
sidecar is not used to select or authorize a new head.

The directory and marker descriptors are pinned. Marker inode, length, exact
bytes, root identity and the complete inventory are checked on live operations.
The active and predecessor paths/inodes retain the existing checks. Path or
inventory drift poisons append/inspection/sealing; it cannot redirect the live
handle onto a replacement directory.

All public **unmanaged writer** entrypoints (`create`, `open`, `open_chain`,
explicit-path `rotate`) reject a directory containing the managed marker. This
prevents accidentally reopening just segment one after a committed rotation.
Read-only legacy inspection is still diagnostic only, not proof of the managed
head or permission to acquire a partial writer.

These are cooperation and local crash-consistency guarantees. Advisory locks
are not protection against root or a same-UID actor intentionally ignoring
locks. Standard-library path operations do not provide a fully dirfd-relative
adversarial filesystem sandbox; the private directory and trusted writer
assumption must hold. The marker/hash chain cannot detect an attacker restoring
a whole consistent old directory or deleting a final suffix offline. Strong
anti-rollback needs a separately protected monotonic anchor, outside this work.

## Commit protocol

A canonical segment filename is the append-only chain-head commit record;
there is no independently mutable `HEAD` file.

1. Hold directory and all predecessor locks. Validate the current inventory,
   quiescent lifecycle state, cursor/seal consistency and all resource bounds.
2. Create `next.pending` exclusively. Write one full linked successor header
   and sync it. The header binds the journal ID, next contiguous segment and
   sequence, exact predecessor file digest and last-record digest.
3. Revalidate the pending file and all predecessors. Require the pending file
   to contain **only one complete header and zero receipt records**.
4. Confirm the next canonical destination is absent. Atomically rename the
   pending file to that exact canonical name inside the locked private root.
5. Sync the directory. Revalidate root, marker, inventory and pinned inode.
   Only then return a writer that may append to the new segment.

This protocol assumes a local filesystem supporting same-directory atomic
rename and file/directory sync semantics. Tests on a host filesystem do not
qualify the device firmware, filesystem mount configuration or power supply.
The consumed handle and error semantics prevent an uncertain publication from
being retried on a guessed prior head.

## Recovery and failure matrix

| Durable state | STRICT | RECOVER_CRASH | Mutation allowed |
| --- | --- | --- | --- |
| Complete canonical chain, no pending | Open latest | Open latest | No recovery mutation |
| Valid active tail incomplete, no pending | Reject | Validate full chain, then truncate active tail | Active torn suffix only |
| Full empty pending header with exact links | Reject | Strictly validate all committed predecessors and publish pending | Rename plus directory sync |
| Initial marker plus valid empty first pending header | Reject | Validate and publish segment one | Rename plus directory sync |
| Pending header partial, malformed or wrong identity | Reject | Reject and preserve | None |
| Pending contains any receipt records | Reject | Reject and preserve | None |
| Pending plus torn/corrupt/unresolved predecessor | Reject | Reject and preserve | None |
| Missing/corrupt marker, gap or unknown entry | Reject | Reject and preserve | None |
| Marker without segment or complete pending header | Reject | Reject and preserve | None |
| File/directory sync error during publication | No writer returned | Reopen to determine durable state | No blind retry |
| Chain capacity exhausted | Reject rotation/growth | Same limits | No pruning |

Initialization creates and syncs the new directory and marker before the first
header. Interrupted initialization is not automatically reset. A malformed
pending file or partial marker requires a separate reviewed recovery decision;
do not delete evidence and recreate an empty namespace merely to restart.

Reopening imports all historical terminal receipt IDs and the highest stored
logical time. Unresolved current facts remain unresolved until the caller uses
the existing reconciliation API. Dispatched potential external effects retain
`NeverAutomatic`; this component never calls a provider, reexecutes an action,
creates an outcome, or reports an indeterminate effect as failed/succeeded.

## D3 development integration

The development service still requires its existing explicit profile, marker,
systemd socket and peer attestation. This feature grants none of those gates.
`storage::open_configured` selects the new mode only when the reviewed development
configuration supplies, for example:

```text
HEPTA_D3_RECEIPT_STORE=/var/lib/hepta-browserd/development/managed-v1
```

When `HEPTA_D3_RECEIPT_STORE` is present, either legacy variable
`HEPTA_D3_RECEIPT_JOURNAL` or `HEPTA_D3_RECEIPT_PREDECESSORS` being present is a
configuration error, even if its value is empty. The store must remain under
the existing development state root. No variable defaults to managed mode.
No production unit or enable marker is changed. Existing directories must
already be valid stores; legacy files are not adopted.

After each connection finishes, the service checks for an idle observer and a
quiescent journal at or above 4 MiB. Only then does it rotate. The threshold is
a fixed source constant, not an unbounded environment input. New segments start
below the threshold. Rotation errors exit the service with `Restart=no` still
in force; neither the actor nor a lost writer is silently replaced. Reopening
and reconciliation follow the configured startup path. Capacity limits still
stop service operation rather than pruning receipt identities.

## Validation, diagnosis and change protocol

Run with the locked Rust 1.93.0 toolchain:

```sh
cargo test --locked -p hepta-session-core --test journal_managed_store
cargo test --locked -p hepta-session-core --test journal_managed_process_recovery
cargo test --locked -p hepta-browser-actor managed_observer
cargo test --locked -p hepta-d3-development --all-features --all-targets
python3 tools/verify_receipt_journal.py
python3 -m unittest tests.test_managed_receipt_store tests.test_verify_receipt_journal
```

The disk corpus covers creation, closed inventory, identity/permission drift,
legacy downgrade, capacity, initial/pending publication, record-tail versus
header corruption, global receipt IDs, exact sequences and rotation thresholds.
Service-loop tests additionally verify idle automatic rotation keeps its session
and failed rotation returns an error with no reusable writer.
The original isolated process target uses SIGKILL after acknowledged rotation
and after durable dispatch. The additional private persistence-cut target now
tests userspace boundaries around write, file sync, rename, directory sync and
record-tail repair. Neither is physical power loss or interruption inside a
kernel syscall. See [`RECEIPT_PERSISTENCE_FAULT_MODEL.md`](RECEIPT_PERSISTENCE_FAULT_MODEL.md). Stored pre-publication cases are constructed from real linked headers
and must be described as durable-state tests, not physical power-loss runs.

Audit mutation tests remove individual call-site guards, locks, sync/rename
steps, strict pending policy, service/observer wiring and executable regressions.
Checks are function-scoped so another occurrence cannot satisfy a removed guard.
The structural audit is not a formal proof; Rust tests and independently bound
exact-image evidence remain separately required.

On failure preserve the marker, all numbered segments and `next.pending`; do not
publish receipt content into generic diagnostics. Report the exact failing
invariant and bounded metadata. Required follow-up work includes safe archival
checkpoints/pruning, reviewed legacy migration, authenticated anti-rollback,
malformed-initialization repair tooling and real installed-image/power-loss tests.
A storage format, authority or contract change must update this document,
`contracts/receipt-journal.v1.json`, module registries, explicit audit inputs,
negative tests and gate invalidation paths together. Historical evidence is not
rewritten or promoted by these source changes.

## Reopen durability barrier

A visible canonical head after a process crash is not a synchronization receipt.
Before returning an existing managed writer, the store now validates its full
chain and pinned identities, synchronizes the active file and directory, and
revalidates inventory and identities. Any error returns no writer; complete
unacknowledged facts remain present. This ordering is exercised by the private
fault corpus described in `RECEIPT_PERSISTENCE_FAULT_MODEL.md`. Disk formats,
legacy APIs, bounds and production activation defaults are unchanged.

## Explicit legacy-copy entry point

The separately documented `ReceiptJournal::copy_legacy_chain_to_managed` API stages a validated byte-preserving copy and publishes `store.v1` only after data sync. `migration.pending` is not a rotation head and is never accepted by automatic recovery. Legacy writers also refuse a parent containing it. See [Legacy receipt migration](LEGACY_RECEIPT_MIGRATION.md). Default service selection, automatic migration and pruning remain disabled.
