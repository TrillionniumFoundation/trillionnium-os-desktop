# Durable signed update owner

`platform/durable_update_owner.py` composes the actual S11 signature verifier,
private filesystem state store and regular-file image slot store into one
durable source transaction. It confirms a complete durable intent before any
possible slot publication. Restart after an unclean or unfinished session
requires external diagnosis and cannot replay an update.

This is a source and host mechanism candidate. Tests use disposable test-only
keys and actual private files. They establish no installed QEMU update,
bootloader effect, observed boot/health, hardware qualification, production key
custody, protected monotonic storage, trusted production clock or release
readiness. Default signature admission and production activation remain
disabled. The contract is `contracts/durable-update-owner.v1.json`; the frozen
underlying mechanisms remain documented in `S11_UPDATE_RECOVERY.md`.

## API and authority

`DurableUpdateOwner(state_root, slot_root, *, active_slot, current_version,
current_image_sha256, signature_verifier=None, protected_rollback_floor=None,
clock=None)` creates the exact bundled `AtomicStateStore` and `ImageSlotStore`
and acquires both leases. The two roots must be distinct externally provisioned
private directories. The slot root contains `slot-A.img` and `slot-B.img` as
private regular files. A missing explicit floor defaults to the current
version. A missing verifier disables admission. A missing clock uses system
Unix time and does not provision a trusted production clock.

The verifier must be the exact bundled `ExternalUpdateSignatureVerifier`,
configured with externally approved `UpdateTrustRoot` objects. The companion
module is available as `durable_update_owner.recovery`, retaining one bundled
concrete type identity without substituting Python's standard `platform`
module. No supplied verifier, store or persistence callback can issue a
substitute successful result. Clock and optional fault hooks are trusted,
nonreentrant in-process configuration.

| API | Actual behavior |
| --- | --- |
| `verify_manifest(payload, *, now_unix, signature=None, fault=None)` | Verify actual detached signature and S11 admission, persist `manifest_verified`, read back the complete chain, then issue `DurableUpdateOperation`. |
| `stage_image_file(operation, image_path, *, now_unix, state_fault=None, slot_fault=None)` | Verify the complete candidate, confirm durable `stage_intent`, publish the actual inactive regular file, confirm `stage_completed`, verify both actual images and the complete final chain, then issue `DurableUpdateResult`. |
| `arm_first_boot(operation, *, now_unix, fault=None)` | Confirm durable `arm_intent`, change the source coordinator's policy phase, confirm `boot_policy_armed`, then verify images, admission and history. This performs no bootloader effect. |
| `confirm_result(result)` | Reconfirm the same retained result against its actual event, complete current history, current admission and actual source/target image bytes. |
| `inspect()` | Read bounded actual diagnostic records. It issues no operation, result, resume or activation permit. |
| `phase` | Read this live owner's source phase on its creating process/thread. |
| `close()` | Write `owner_clean` only for idle sessions. An admitted, staged or armed unfinished update requires recovery. Always release descriptor copies. |

Operation authority carries `operation_id`, `manifest_sha256` and
`signature_sha256`. Result authority also carries the actual event sequence and
digest, phase, target slot, complete image digest and length, retained slot root
identity and false production/boot-effect flags. Both contain private issuer,
process, thread and seal bindings. Acceptance requires the actual object
retained by this owner. Copies, identical hash strings, other owners' objects,
caller statuses and reconstructed dataclasses grant no authority.

Authority is restricted to the creating process and thread. Checks precede
inherited store locks or effects. A fork child can release its descriptor
copies through `close()`, but cannot use inherited operations/results, write an
event, acknowledge a clean session or explicitly unlock the parent's lease.
Garbage collection and exception-context cleanup close descriptors only.

## Durable event chain

Every canonical JSON event stores its consecutive sequence, previous actual
SHA-256, random 256-bit owner ID, source phase, observed configured time,
complete configuration, complete operation and applicable staging receipt.
Every object has a closed field set. Configuration binds the current source,
protected floor, trust-policy digest and the actual retained state/slot
directory device and inode. Changing configuration cannot silently migrate
an existing chain. Owner IDs cannot repeat.

The allowed source transitions are:

```text
initial / owner_clean -> owner_open(idle)
owner_open            -> manifest_verified(verified) OR owner_clean(closed)
manifest_verified     -> stage_intent
stage_intent          -> stage_completed(staged)
stage_completed       -> arm_intent
arm_intent            -> boot_policy_armed(boot_pending)
```

There is no transition from `boot_policy_armed` or an unfinished update to a
clean owner. The wrapper exposes no boot observation, health assertion,
commit, operator rollback, reconciliation, history reset, marker clear or
resume method. The underlying coordinator's separate policy APIs are not
exposed as wrapper authority.

State events are `update-event-%06d.json`, at most 256 events of at most 64 KiB
each. The directory admits only those consecutive events,
`.coordinator.lock` and optional `update-recovery-required.json`: at most 258
entries. Unknown files, leftover evidence, gaps, unsafe modes, hard links,
symlinks, corrupt bytes and illegal transitions are retained and refused.
Capacity exhaustion requires external migration; this module never compacts
or deletes history.

`AtomicStateStore.write` performs complete temporary write, file sync, atomic
replacement and directory sync, retaining inode custody. The wrapper then
reads the actual published canonical bytes, syncs the retained leaf and
directory, and scans the entire chain. Each scan retains every event/marker FD
until all records have been read, then rechecks every retained and named
inode's device, inode, length and timestamps, the leased roots and the whole
inventory. A predecessor changed while a later record is read cannot authorize
the next effect. At most 257 record FDs are retained. Live readbacks also
reject same-byte replacement by a new inode. Descriptor cleanup uses one
shared owner per scanned FD, detaches ownership before actual close, and
attempts all owned closes even if one close raises after taking effect.

Each scan record is constructed empty before its actual file open. The retained
record receives the raw descriptor inside the protected read scope. Constructor
call, first-line and final-return interruptions therefore acquire no scan FD.
Descriptor-only garbage collection closes an acquired record that is discarded;
explicit cleanup detaches the integer before `os.close` and never retries that
number. GC does not adopt a record, acknowledge history or release a lease by an
explicit unlock.

An operation stores the complete signed manifest and actual signature
admission bindings: signer ID, pinned public-key digest, detached-signature
digest, domain-separated preimage digest, policy digest, minimum version and
verified time. The S11 signing domain and exact canonical preimage remain
unchanged. Detached signature/key bytes are not copied into this event chain.
Historical parsing checks bindings and legal transitions; it does not
reconstruct a cryptographic admission or ticket after restart. External
diagnosis needs the original authenticated update packet and independent
trusted configuration.

Configured clock observations cannot regress within a live owner or the
confirmed event history. Regression permanently refuses that owner, even if
the clock later advances. Signature policy, revocation, root validity,
manifest expiry and floor are revalidated for staging, publication, arming
and result confirmation. Caller `now_unix` must match the configured clock
within the underlying five-second bound; caller time is not authority.

## Actual staging and results

The candidate is opened through the existing absolute no-follow path walk.
The corrected S11 private acquisition helpers return a non-integer descriptor
owner. The wrapper closes those owners through their `close()` method in active
image verification, staged image verification and candidate prehashing. Actual
filesystem calls borrow their FD through `fileno()` or the integer-index
protocol; closing an owner disarms later GC before the kernel close, so reuse
of its number cannot authorize a second close. The scanned JSON records keep
their separate raw-descriptor ownership and cleanup protocol.
Actual complete digest and signed byte length are checked before durable
staging intent and before the core creates its image temporary file. Staging
uses the existing 1 MiB streaming copy, with a maximum 16 GiB image. It
verifies the actual running source image, inactive pathname, candidate and
retained temporary inode. Publication uses file sync, atomic replacement,
directory sync and complete bound readback. The wrapper checks its exact
durable operation around each core fault cutpoint and performs final complete
history readback after actual image verification. These repeated scans/hashes
use bounded memory; filesystem sync and device latency have no real-time
deadline claim.

The original core conservatively classifies any failure after attempting
replacement as potentially published, including an actual kernel replacement
followed by an interruption before the call returns. The wrapper preserves
the durable intent and enters recovery; no fresh stage call can replay it.
`stage_completed` results require actual full image bytes and complete durable
history readback. A source `boot_policy_armed` result reports
`bootloader_effect_performed=false` and `production_activation_enabled=false`.

Python cannot observe whether a caller received its final return value. If
complete local durable staging/policy confirmation is already known and result
construction then fails, `DurableResultUnavailable` preserves `staged` or
`boot_pending` knowledge. It claims no caller acknowledgment and grants no
stage/arm replay. If completion/readback remains unconfirmed,
`DurableRecoveryRequired` preserves the pending intent and recovery evidence.
Exceptions retain their original cause. After restart, neither case
reconstructs a replacement operation/result.

## Restart and retained evidence

Only an explicit idle clean close permits a later owner to append a new
`owner_open`. Otherwise startup confirms or attempts to persist the fixed
recovery marker and returns a quarantined owner. New admission/staging/arming
are refused. Corrupt, unknown or inconsistent history raises after attempting
recovery marking, without deleting or repairing the original evidence.

The marker binds the last confirmed complete prefix and operation, not an
unconfirmed suffix that may have reached disk during an interrupted append.
Existing markers, including malformed ones, are never overwritten. If marker
storage fails, the owner remains `recovery_required` and earlier actual
`owner_open`/operation/intent records still prevent a clean restart.
`inspect()` separates `recovery_required` from
`recovery_marker_confirmed`; it does not claim marker durability when the
write was unavailable. A subsequent owner must attempt marking again and
cannot resume the update.

This chain provides crash/restart refusal under the cooperating private-root
and lease model. It is not a sandbox against arbitrary Python code, root or an
account already allowed to rewrite all authority files. Its SHA-256 links are
not an independently protected monotonic anchor. Wholesale restoration or
forgery of a formerly clean private directory, externally supplied floor/time
rollback, trusted configuration compromise and policy migration require
separate protected facilities and authorized recovery design.

## Verification and remaining installation work

Run `python3 -m unittest discover -s tests -p test_durable_update_owner.py`.
The corpus requires actual OpenSSL rather than skipping crypto. Disposable
test-only keys exercise positive staging plus wrong signer, expiry,
revocation and floor negatives. Real private files exercise failed durable
intent, full-image mismatch, lease/inode substitution, predecessor drift
during actual sync, final-history drift, failed marker storage, unavailable
results and non-clean closure. Single-thread fork tests enforce inherited
authority refusal and the parent lease; real SIGKILL tests interrupt four
slot cutpoints and reopen the retained chain without replay. Line-trace
interruptions with actual close and FD reuse check descriptor ownership.
Actual private image consumer tests reuse the just-closed number before owner
GC and retain the foreign file. Scan constructor call/first-line/return faults
leave the prior FD inventory and history intact. Raw scan cleanup and GC tests
exercise ordinary and interrupted real close, including reuse for the same
inode, without a second close or leaked scan descriptor.

Installed service startup/wiring, safe external recovery operators, actual
bootloader/block-device adapters, authenticated installed boot and health,
durable commit/rollback, whole-directory rollback protection, protected floor
storage, trusted production time, production signing-root approval and real
installed QEMU/power-loss/hardware acceptance remain prerequisites. This
wrapper does not activate a product graph or change their qualification
status. Adding it to source CI/registry requires recording its actual source
and tests separately; a source check cannot promote installed or release
readiness.

The S11 dependency correction has been applied separately: path walks detach
each old owner before closing, attempt every owned cleanup, and preserve the
successor directory or image until transfer. Real close/reuse regressions now
preserve the foreign descriptor and close the successor. Private helper
`RETURN_VALUE` interruptions dispose undelivered owners, and each core owner is
constructed empty before its actual open or sealed-memfd creation. The wrapper
uses that protocol and adds its independent raw scan record cleanup above.

These tests establish the specific Python constructor, return and cleanup
windows exercised. They do not prove every asynchronous opcode window between
an original C `os.open`/`memfd_create` result and its assignment to a Python owner
field or raw record list. Python cannot prove delivery of a returned value to
the caller. The core and wrapper tests remain host mechanism evidence; none of
these cleanup corrections closes the installation prerequisites listed above.
