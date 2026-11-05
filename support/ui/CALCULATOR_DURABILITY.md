# Calculator durability and original-owner recovery (Linux host)

This document describes the application store, its sole state worker and the
independent recovery helper. The [Calculator wire contract](../../ui/core/CALCULATOR_PROTOCOL.md)
defines identity, arithmetic, effect bytes, deadlines and FinalUse composition.
The [Root lifecycle](../../services/hepta-session-host/ROOT_LIFECYCLE.md) defines
the joint Notes/Calculator owner generations. These are separate boundaries.

## Implementation and ownership

| Component | Responsibility |
| --- | --- |
| [CalculatorDocument](../../ui/core/src/calculator.rs) | Validated arithmetic state, revision, one pending Applied receipt and one exact last retirement identity. |
| [Checkpoint codec](../../ui/core/src/calculator_checkpoint.rs) | Strict, bounded serialization and restoration for the exact original target. |
| [CalculatorStore](../../ui/core/src/calculator_store.rs) | Exclusive target lock, persisted state transitions, recovery-only reopening and failure freezing. |
| [Private checkpoint IO](../../ui/core/src/app_checkpoint_store.rs) | Directory-relative private file access, synchronized replacement and lock custody shared with Notes. |
| [Calculator worker](../../ui/app-window/src/calculator_worker.rs) | Serializes protocol requests and local revision-CAS edits; publishes the resulting renderer projection. |
| [Calculator transport](../../ui/app-window/src/calculator_organ.rs) | Original inherited lanes, bounded queues, original Session lifetime and cumulative BOOTTIME request budget. |
| [Recovery helper](../../ui/app-window/src/bin/trill-calculator-recovery.rs) | Reopens one explicitly selected old target on a private inherited datagram; no effect endpoint. |

The original Hepta writer retains operation intent, source history, terminality
and the durable record of actual retirement ACK. The application checkpoint
contains application data and bounded causal receipt metadata. It is not a
replacement operation journal, grant or permission to repeat an effect.

## Storage selection and target separation

TRILL_CALCULATOR_STATE_DIR selects the durable namespace. Ordinary explicitly
optional profiles can use the temporary in-memory document when this variable
is absent. Joint Root bootstrap marks Calculator storage durable_required in
the original Session lifetime metadata; Session and App then require the
configured existing, canonical, private directory. Missing storage is an error.

The Root namespace is u/calculator. Each validated target creates its own
session_instance-task_id-incarnation child directory. Fresh Application mode
requires mkdir to succeed; it never opens an existing target as a fresh one.
RecoveryOnly mode opens that exact existing child and never creates it. Both
modes hold its exclusive nonblocking flock. A live App and a recovery helper
cannot concurrently own the same target.

A successor can reuse the namespace because its Session/incarnation identity
creates another child. Its Calculator begins with a new document. There is no
automatic history or value migration into the successor. Old pending or retired
receipts stay with the old target. Notes has a separate explicit saved-text
copy path; that behavior must not be inferred for Calculator.

## Checkpoint format and persistence

The strict JSON checkpoint is at most 16 KiB and contains:

- format trill.calculator.checkpoint and schema_version 1;
- the complete Calculator target, current value state and revision;
- pending_receipt and retired_receipt, both required fields with explicit null
  when absent.

Restore validates the exact target, every wire/state field, revision-zero
invariants, pending receipt causality and exact retirement identity. Missing,
unknown, duplicate, malformed or mismatched data is refused. Current displayed
values never reconstruct a missing historical Applied response.

Private directory access uses retained directory FDs and openat with NOFOLLOW.
Directories belong to the actual account and have no group/other access. Files
also require one link, correct ownership, private mode and the size bound.
Checkpoint replacement writes a fresh exclusive next.json, synchronizes the
file, renames it to document.json and synchronizes the target directory.
An interrupted pre-rename temporary file is never treated as a committed result.

A storage transition is visible to the caller only after this sequence succeeds.
If synchronization or replacement fails, the store freezes. Later effects and
local edits refuse until an independent recovery reconciles the original
checkpoint. The process cannot infer that a failed save means no disk change.

## Worker, replies and local editing

The store is initialized before the worker is started, then moved into the
single calculator-document-owner thread. After initialization, protocol writes,
local edits and receipt metadata changes run there. Draw consumes a bounded
read-only projection; it does not synchronize the filesystem.

The command queue has capacity four. Local edits carry the projected revision
and a local edit ID. The worker applies an edit only if that revision is still
current, preserving any pending effect receipt. The UI distinguishes saving,
a revision conflict and a frozen store; it does not silently rebase a local edit.
Normal close waits for an outstanding local edit acknowledgement. Actual
Session loss still closes the owned App and does not promise queued drafts saved.

The worker checks the inherited Session lifetime before and after each command
and while idle. The transport's cumulative BOOTTIME deadline is not renewed
while queued or blocked. An Applied reply follows the durable checkpoint.
A deadline, Session exit or lost reply after a real commit leaves the source
outcome unknown until the original owner reconciles it.

## Recovery-only process

The original owner launches the hash-bound retained ELF with exactly these
selectors:

~~~text
trill-calculator-recovery
  --state-dir <original namespace>
  --calculator-session <old session_instance>
  --calculator-incarnation <old incarnation>
  --task-id <old task_id>
~~~

Stdin is an already connected, unnamed Unix datagram pair. No listener, path
discovery, arbitrary descriptor number, reconnect, signer or grant exists.
The fixed TRILL_CALCULATOR_RECOVERY_READY_V1 signal only confirms successful
reopening and locking; it does not confirm an effect or source terminal.

The helper accepts read_calculator, observe and exact acknowledge metadata.
It refuses evaluate. The original Hepta previous-operation factory is narrower:
it fixes one old target and original operation and permits only observe and
acknowledge. It cannot dispatch to the old target or register an old FinalUse
destination.

| Event | Durable meaning |
| --- | --- |
| Exact pending observation | Returns the original Applied bytes for that target and operation. |
| No exact pending receipt | Unknown; current arithmetic cannot prove historical execution. |
| Matching original-owner terminal ACK | Clears the pending slot and persists the exact last retirement identity before replying retired. |
| Lost retirement reply | Original metadata-only retry can return already_retired; no arithmetic is repeated. |
| Source ACK persistence failure | The app may already be retired, while the original writer still lacks durable retirement evidence. |
| Original writer retains the validated ACK and publishes Current | Its protected read API can prove that this historical target operation completed retirement. |

Committed source terminality alone is insufficient to skip an old target.
The original writer must retain the actual target ACK in its own journal.
A new target never absorbs an old unknown operation or gains an old receipt.

## Development and validation

Run the original workspace tests with locked dependencies:

~~~sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-ui-core --locked
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-app-window --locked
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-session --locked
~~~

Use offline mode only with the exact cached graph. Respect the existing
TargetLease when using a shared product target.

The [checkpoint tests](../../ui/core/src/calculator_checkpoint_tests.rs) check
strict restore and causal invariants; [store tests](../../ui/core/src/calculator_store_tests.rs)
check the real private files, lock and persistence behavior.
The [independent helper process test](../../ui/app-window/tests/calculator_recovery.rs)
opens persisted state through the actual ELF, rejects an effect and wrong ACK,
loses an actual retirement acknowledgement, terminates the helper and reopens
the original target to verify already_retired.

Those are host component/process tests. Final product acceptance additionally
requires the exact installed Desktop/Hepta source pair, original Chat turns,
Objective and FinalUse, both real App effects, protected source terminal/ACK
persistence and two actual successor cycles. Each original Core turn admits
at most one effect across both Apps, so Notes and Calculator need separate turns.
The protocol's original refusal and unknown cases remain required. Host tests
do not establish physical power-loss durability, Asterinas guest behavior,
Android control or a cross-version database upgrade.
