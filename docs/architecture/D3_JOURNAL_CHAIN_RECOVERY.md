# D3 complete-chain journal recovery

**Plan:** `2026-08-29-d6`
**Status:** local source candidate, awaiting independent review and exact-image evidence
**Scope:** disk-backed receipt namespace restoration and recovery classification only

## Problem and compatibility

The old standalone `ReceiptJournal::open` reconstructed only the named segment.
After rotation it lost terminal IDs and logical timestamps in predecessors.
Read-only `inspect_chain` could detect an already-written replay, but inspecting
and then reopening only the active path did not import the global namespace.
The development daemons therefore refused rotated stores. A second defect
allowed crash recovery to truncate a torn successor tail before the application
noticed its wrong journal identity or incomplete chain.

`open` now accepts segment one only. `open_chain(paths, expected_journal_id,
policy)` is the new writer API. It requires every segment in ascending order,
beginning at one, with the active head last. This deliberately tightens writer
admission without changing the HPTJRNL1/HPTREC01 on-disk format. Existing clean
single-segment stores remain readable. A solitary successor is never appendable.
The older one-connection development daemon still has no predecessor-list input
and continues to reject rotated stores, before any tail repair.

## Open transaction and ownership

The core first consumes at most 65 supplied paths and enforces a maximum of 64
segments, 128 MiB total encoded bytes, 64 MiB per segment, and 131072 records.
It checks canonical/no-follow paths, captures device/inode identity, rejects
repeated inodes (including hard-link aliases), opens every descriptor and takes
nonblocking exclusive inode locks. It keeps all predecessor descriptors locked
until the active writer is dropped; live rotation transfers these guards.

Before acquiring or rewriting the active pathname lease, the core validates:

- expected journal ID on every segment, sequence continuity, both predecessor
  hashes, clean predecessors, and quiescent predecessor receipt lifecycles;
- global receipt ID transitions and immutable admission identity, request digest,
  effect and privacy consistency across all segments;
- all input and decoded-record bounds, pinned path identities and file lengths.

It then imports the complete receipt-progress map and greatest recorded logical
timestamp. Only after validation and active lease acquisition may RECOVER_CRASH
truncate the final segment's incomplete record to the validated prefix and sync
it. Reordered/missing/duplicate/foreign/corrupt predecessors are not repaired.
STRICT refuses every torn tail. Complete-record corruption remains a hard error.
Append and rotation enforce the same aggregate bounds and recheck predecessor
path/inode/length custody; a custody error poisons the writer before new bytes.

The locks are Linux advisory locks. They exclude cooperating journal writers,
not a malicious process that ignores locks or an administrator. Hash linkage is
not a signature, an external authenticity anchor, or proof against malicious
same-length rewriting. The application/operator must provide the authoritative
head: the core cannot discover an omitted successor or prove that an offline
snapshot is the latest. No automatic segment deletion or retention checkpoint
is introduced. Full-chain users must retain all predecessors; reaching a bound
requires an explicit reviewed archival/checkpoint design, not dropping old IDs.

## Persistent development service configuration

Only `hepta-agent-port-development-sessiond` accepts the new optional
`HEPTA_D3_RECEIPT_PREDECESSORS` environment value. It is an ordered colon-separated
list of absolute UTF-8 paths under `/var/lib/hepta-browserd/development`, excluding
the active path supplied by `HEPTA_D3_RECEIPT_JOURNAL`. Omit the variable for a
single-segment store. An explicitly empty list, overlong input, duplicate/active
path, traversal, ambiguous separators, whitespace/control characters, backslash,
non-UTF-8 path, symlink, or wrong order is rejected, never normalized or sorted.

Example administrator configuration for a stopped development service:

```ini
Environment=HEPTA_D3_RECEIPT_PREDECESSORS=/var/lib/hepta-browserd/development/segment-1.journal:/var/lib/hepta-browserd/development/segment-2.journal
Environment=HEPTA_D3_RECEIPT_JOURNAL=/var/lib/hepta-browserd/development/segment-3.journal
```

This is a path list, not a command or a directory-discovery pattern. It grants no
new listener, namespace, network, credentials or production activation. Existing
marker, profile, systemd socket, executable and peer identity requirements remain.
A missing active file with configured predecessors is fatal; the service never
creates a fresh empty journal to replace a missing chain head. No auto-rotation,
crash-safe head-selector update, or image qualification is claimed by this work.

## Recovery facts and privacy

The service classifies only unresolved records in the active segment (all
predecessors must be terminal). Dispatched potential external effects become
Indeterminate, with no outcome or response digest. Requested or other interrupted
operations become Interrupted. It does not query an effect provider, execute an
action, or replay a request. Calling classification again creates no additional
records. Logical ordering starts above the maximum across the full chain; it is
not elapsed-time measurement. Clock exhaustion is a refusal.

SecretRedacted entries retain `detail=None`, including recovery annotation.
Previously an unconditional detail string made recovery reject otherwise valid
secret-redacted receipts. Other privacy classes receive a bounded generic restart
annotation, not page content or a fabricated external result.

## Tests and promotion

`crates/hepta-session-core/tests/journal_chain_reopen.rs` exercises real private
files, rotation/reopen, cross-segment replay refusal, wrong identity, corrupt/torn
predecessors, active-tail repair, path replacement, hard links, symlinks, resource
bounds and descriptor-lock lifetime. `journal_chain_process_recovery.rs` is a
separate integration-test executable: a bounded child commits a dispatch, is
killed by its parent, and the parent proves stale-lease handling and
NeverAutomatic recovery without adding any action or result. Keeping spawn in
a separate executable prevents transient fork-inherited descriptors from
interfering with concurrent same-process lock-release assertions. Neither the
assertions nor default test parallelism are disabled. Both use the shared
`tests/support/journal_chain_fixture.rs` private-directory fixture.

`crates/hepta-d3-development/src/sessiond/storage_tests.rs` invokes the actual
persistent service storage functions on private temporary stores, including
complete-chain startup, missing-active denial, privacy, repeat recovery and
configuration rejection. Neither suite starts an AgentPort listener or calls
Servo. The full default/all-feature Rust matrix and repository/Python validators
are required. CI, independent review, governed merge, exact-main and the D3
integrated-image corpus remain separate requirements; this source candidate does
not promote D0C-06, D3, D7 or any product/release flag.

The stricter per-receipt admission commitment is detailed in
[RECEIPT_ADMISSION_IDENTITY.md](RECEIPT_ADMISSION_IDENTITY.md). It is reconstructed
from unchanged v1 records and never substitutes for authoritative head selection.

## Optional managed directory successor

The explicit-path API described above still requires trusted selection of the
latest head and has no automatic discovery. New development stores may instead
use the opt-in [managed receipt directory](MANAGED_RECEIPT_STORE.md), which
selects the complete closed inventory and provides atomic pending-header
publication. It is not a migration of the legacy API, an archival checkpoint,
an offline anti-rollback anchor or installed-image evidence.

## Offline copy is separate from recovery

[Explicit legacy copy](LEGACY_RECEIPT_MIGRATION.md) can prepare a new managed store from a strictly valid operator-selected complete legacy chain. It never repairs original bytes, classifies unresolved effects, deletes originals or changes D3 configuration. Source quiescence and single-writer service cutover remain operator responsibilities.
