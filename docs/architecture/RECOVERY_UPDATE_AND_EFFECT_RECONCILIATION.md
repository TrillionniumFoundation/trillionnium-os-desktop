# Recovery, effect reconciliation, and immutable A/B updates

## Status and boundary

This package is a D7 source candidate blocked by D6. The reference models do
not execute external effects, query providers, persist to the product journal,
write block devices, change a bootloader, update a secure rollback counter,
access production signing keys, or build recovery media.

## External-effect protocol

Every external-effect intent binds operation and idempotency identities, effect
kind, payload digest, permit digest, and subject digest. Its lifecycle is:

1. `requested` — no effect has been attempted;
2. `prepared` — local validation is complete, still no effect;
3. `dispatched` — the potential external-effect boundary has been crossed;
4. terminal success/failure, indeterminate, or reconciliation outcomes.

Only requested or prepared operations may be cancelled or separately
reprepared. A dispatched or indeterminate operation is **never automatically
replayed**. Recovery may perform a read-only reconciliation query using the
original identity. Provider outcomes are handled as follows:

- `applied`: record reconciled success;
- `not_applied`: record that a future retry needs a new explicit authorization;
- `unknown`: require manual action.

The journal has no execution or replay method.

## Effect journal

Each canonical JSON-line record binds sequence, previous record hash, event,
and record hash. Replay must reconstruct the same state machine. An incomplete
final record may be discarded as a torn tail. Corruption, removal, insertion,
reordering, or mutation of any complete record fails closed.

Crash recovery classifies requested/prepared operations as pre-effect,
dispatched/indeterminate operations as reconciliation-only, and completed
operations as terminal.

## Signed update manifest

An update manifest is Ed25519 signed and binds:

- release and issuer identities;
- monotonically increasing version and rollback index;
- exact hardware profile;
- exact image SHA-256 and byte length;
- source commit, SBOM digest, and provenance digest;
- minimum supported current version;
- recovery compatibility.

The updater receives a signed manifest and image through a separately mediated
input. It has no network authority and no signing key.

## Immutable A/B transaction

The active healthy slot is never written during staging. The transaction is:

1. validate signature, identity, anti-downgrade, hardware, image, SBOM, and
   provenance;
2. create a stage intent for the inactive slot;
3. write only the inactive slot;
4. seal its digest and metadata;
5. explicitly mark it pending;
6. make a bounded boot attempt;
7. commit the slot and secure rollback index only after health confirmation.

Before health confirmation, the previous slot remains active and the secure
rollback counter remains unchanged.

## Failure handling

- disk full before staging leaves all state unchanged;
- disk full or power loss during an inactive-slot write discards the partial
  slot;
- a sealed slot is never automatically activated;
- a pending sealed slot may resume a bounded boot attempt;
- power loss during boot consumes an attempt and returns to the previous healthy
  slot until an explicit retry;
- failed health or exhausted attempts marks the candidate failed and rolls back;
- a corrupt update journal enters recovery-media-required state rather than
  guessing which slot to boot.

## Offline recovery media

Recovery media has a separate Ed25519 issuer and binds hardware profile, image
digest, provenance, and minimum rollback index. It cannot be older than the
secure rollback state and cannot request automatic destructive recovery. The
normal runtime credential set is not part of the recovery claim.

Separate update and recovery fixture keys test role separation. They are not
production keys and provide no custody evidence.

## Required integration evidence

After D6 is independently integrated, D7 runtime work must prove:

- durable crash/session/watchdog storage under disk-full and power loss;
- provider-specific read-only reconciliation with no duplicate effects;
- actual immutable A/B image staging and bootloader selection;
- a hardware- or TPM-backed monotonic rollback counter;
- production update and recovery key custody under independent roles;
- signed offline recovery media and non-destructive operator confirmation;
- repeated failed boot, corrupt journal, partial image, and interrupted update
  behavior on the fixed hardware target;
- exact-main and release-candidate provenance.

Source-model success does not substitute for those image, hardware, key, or
operator-control gates.
