# Authenticated update journal and readback

`platform/authenticated_update_owner.py` and
`platform/authenticated_update_observer.py` add a source and host candidate to the
G6 / D7 / S11 update mechanisms. They close the restart diagnostic gap where a
v1 journal retained signature digests but could not verify the actual detached
signature after owner descriptors had closed. The contract is
`contracts/authenticated-update.v2.json`; the source index is
`manifests/authenticated-update.v2.json`. These documents describe real signed
regular-file staging and read-only authentication, not installed boot, health,
commit, rollback, hardware qualification or production signing.

## Exact custody and event compatibility

`AuthenticatedUpdateOwner` inherits the existing `DurableUpdateOwner` constructor,
operation/result objects, six methods and `phase` property. The concrete verifier
and both existing private leased stores remain unchanged. Default admission is
still disabled without separately approved external roots. All source activation
and bootloader effect flags remain false.

A new owner emits `trillionnium.desktop.durable-update-event.v2` records. The
closed v1 event envelope, transitions, configuration, admission and stage receipt
remain, while every admitted operation adds one closed `signature_capsule`
reference: `name`, `sha256`, `manifest_bytes_sha256` and `signature_sha256`.
Each subsequent phase must carry the identical full reference. The capsule uses
`trillionnium.desktop.update-signature-capsule.v2` and the deterministic basename
`update-signature-<operation_id>.json`. It contains the exact original manifest
and detached signature bytes as canonical padded base64, the complete issuing
owner and operation identities, configuration and original signature admission.
No public key or policy supplied by this capsule can approve a trust root.

The owner writes and confirms the capsule before `manifest_verified`, through the
same concrete `AtomicStateStore` retained-root, one-link private regular-file
publication and readback path. Capsule bytes and directory are synchronized;
all complete history scans retain its descriptor with the events and compare
both retained and current named custody before completion. A named capsule is
never overwritten. A capsule orphaned before an operation event is retained as
unknown evidence on restart; there is no adoption, repair, clearing or replay.
The current owner may hold only its own transient pre-event capsule while it
publishes the first admitted event.

Legacy v1 histories keep their existing structural interpretation. A new v2 owner
may follow a clean v1 owner; an unfinished v1 operation still requires recovery.
A profile cannot change within an owner operation. Neither v1 digests nor v2
capsule hashes reconstruct an original ticket or confer signature authority. The
unchanged v1 read-only observer refuses v2 records as unknown evidence.

## Authenticated read-only inspection

Call `inspect_authenticated_update(state_root, slot_root, *, signature_verifier,
clock, protected_rollback_floor)`. These three keyword inputs are trusted local
installation configuration: the exact bundled concrete verifier with separately
approved roots, a configured trusted clock and the currently protected version
floor. The inspector does not accept caller health, operation/status digests,
verifier callbacks, signing keys, replay commands or a boot activation permit.

The inspector uses the unchanged read-only reader to walk bounded absolute
paths without following components, open existing private roots and named leases,
and hold nonblocking shared locks. It constructs no writable state or image
store. It validates all consecutive actual canonical event digests, transitions,
configuration, root identities, operation/capsule references and any recovery
marker's confirmed prefix. All event and capsule descriptors survive until final
metadata and inventory checks.

For a v2 completed staging history, the inspector decodes the exact stored bytes,
checks their complete crossbinding and invokes actual `/usr/bin/openssl` using
the existing v1 domain-separated preimage and sealed memfd snapshots. The current
independently supplied policy must match the recorded policy; actual admission
signer, key, signature, preimage, policy and minimum version must match the original
admission. Current root revocation and validity, manifest expiry, nondecreasing
local time and the protected rollback floor are checked again. A rehashed journal
with a forged detached signature cannot become an authenticated diagnostic.

It then reads the complete current active slot digest and target slot digest and
length through retained private `0600` single-link regular-file descriptors.
Kernel boot ID, mount namespace, root device/inode and mount table are sampled
before and after the scan. Their equality establishes observation consistency;
it does not map the actual kernel root to either signed file slot. Final named
metadata and inventories are checked again after the trusted final clock callback.

Only this complete path sets `signatures_verified` and
`stored_slot_images_verified` to true. `AuthenticatedUpdateReadback` has no public
initializer, rejects dataclass reconstruction and checks the creating process and
thread before delivering its public or private bytes. The public object reports
closed status/reason codes and bounded flags without private paths or identity
hashes. Explicit private bytes include the actual capsule, event, policy, root,
clock, floor, image and kernel observations. This object is a diagnostic: no owner
or coordinator API accepts it as a ticket, boot proof, health result or permission.

A marker may coexist with authenticated stored bytes; status remains
`recovery_required`. A completed source stage without an armed source policy may
also authenticate stored bytes, but still grants no continuation. Unfinished
stage intent, v1 pending history, missing configuration, stale policy/time/floor,
crypto failure, image mismatch or unsafe/substituted custody cannot produce a
successful readback. An observation never deletes or clears evidence.

## Bounds and regression scope

V1 retains its existing 64 KiB record limit, 256-event limit, 258-directory-entry
limit and 257 retained history record descriptors. V2 keeps the same record and
event limits; exact original manifest and detached signature envelopes each have
a 16 KiB bound, so both fit in one 64 KiB capsule. At most one capsule raises the
v2 limits to 259 directory entries and 258 retained history record descriptors.
Images retain the existing 16 GiB limit and stream in at most 1 MiB chunks. Private
diagnostic output remains bounded by 64 KiB. These are bounded source interfaces,
not unbounded archival or compaction support.

Run `python3 -m unittest discover -s tests -p test_authenticated_update_readback.py`.
The corpus generates temporary test-only RSA keys and uses actual system OpenSSL;
unavailable Linux/OpenSSL/fork prerequisites fail instead of skipping. Cases cover
exact noncanonical original manifest bytes, full forged hash-chain signatures,
policy/time/floor changes, v1 refusal, private custody, missing/symbolic/hard-linked
or oversized capsules, inode substitutions during actual crypto, complete image
mismatches, interrupted publication/read cleanup, forked ownership, creator-thread
facts and final clock callback substitutions. These real host operations do not
simulate an installed boot or stand in for production roots.

The actual head and prospective-merge corpus workflow also reruns unchanged S11,
v1 owner and read-only observer tests. Fixed profiles and source APIs are checked
by `tools/validate_platform_mechanisms.py`; `--refresh-api` cannot rewrite the v2
contract or raise a qualification claim.

## Remaining installed obligations

Production readiness still requires provisioned production public roots, a
protected monotonic floor and trusted time; immutable signed-image-to-actual-root
and block-device mapping; installed bootloader root selection; measured monotonic
health with durable commit and rollback; separately authorized recovery; real
QEMU two-boot tests and physical power-cut/long-duration hardware qualification.
The writable host file slots and kernel observation do not provide these facts.
Whole-directory rollback protection and isolation from arbitrary privileged
in-process or filesystem writers remain outside this source mechanism. Signature
readback alone neither upgrades historical qualification nor enables production.
