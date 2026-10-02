# Read-only pending-update and kernel boot observations

This source candidate reads the existing G6 regular-file journal and current
Linux kernel observations. It produces a bounded diagnostic. It gives no
permission to resume, commit, roll back or activate an update. Its source index
is `manifests/update-observation.v1.json`; the exact public API and closed output
profile are in `contracts/update-boot-observer.v1.json`. The Cargo module inventory
and the six platform authority mechanisms are unchanged.

## Status and claim ceiling

`platform/update_boot_observer.py` is a Linux source mechanism tested against real
procfs, private regular files, flock, fork and disposable OpenSSL signatures.
The signatures create test journals through the existing concrete durable owner;
the observer itself neither constructs a verifier nor verifies a signature.
Its output always says `signature_authority: unavailable` and
`signed_boot_image_mapping: unknown`. All continuation, activation and bootloader
effect claims are false. A structurally valid journal is a local observation,
not an approved signing authority or a proof of what image booted.

Current journal operations retain manifests and admission digests, but no actual
detached signature bytes. This observer cannot reconstruct crypto authority from
those hashes. Approved roots remain empty by default. Production public-root
provisioning, protected version/time anchors and any signing/HSM resources stay
outside this module. No test root is installed or treated as a production root.

## Responsibilities

The observer opens both externally provisioned state and slot roots by a bounded
absolute nofollow component walk. It requires their existing private
`.coordinator.lock` files and takes nonblocking shared flock leases. The concrete
coordinator uses an exclusive flock on those same named inodes. An exclusive
owner yields `owner_busy`; the observer does not create a replacement lease,
repair permissions, clear a recovery marker or invoke a store constructor.

It reads the entire bounded canonical journal. It checks closed field sets,
exact integer/boolean types, consecutive sequence and digest links, transitions,
original directory identities, unchanged operation and staging receipt bindings,
unique owner sessions and a recovery marker's confirmed prefix. It retains every
opened record until the final named-leaf/FD checks and inventory comparison.
Each slot is checked as a private 0600 single-link regular file with a positive
bounded size. Slot bytes are neither read nor hashed; device, inode, size,
mtime and ctime are explicitly current-file metadata only.

## Non-responsibilities

No bootloader, filesystem, image slot, lease or journal is written. There is no
network/download/signing path, update recovery, replay, health callback,
60-second health qualification, rollback permit or activation switch. No caller
can supply a boot ID, mount table, active slot, root digest, observed health or
replacement kernel source to the public API. A writable ext4 root after boot is
not equivalent to the original signed image. Root device observations cannot
establish a signed-image mapping, even if some caller reports an equal digest.

The source wrapper does not resolve the separately documented S11 core
pathwalk interruption windows. This reader owns its own descriptors and does not
call the core pathwalk or state/slot constructors. Its finite tests do not prove
every C-to-Python-store or asynchronous interruption boundary is covered.

## Dependency and call direction

The observer uses stdlib plus the bundled S11 manifest parser and literal signing
preimage function for historical structural binding. It does not call
`ExternalUpdateSignatureVerifier`, `AtomicStateStore`, `ImageSlotStore` or
`DurableUpdateOwner` constructors. The CLI calls only the observer and explicit
diagnostic output helper. No product startup, systemd service, bootloader or
browser actor currently calls this module. The separate source index registers
these paths without adding an authority mechanism or a Cargo application.

## Public API and binaries

`inspect_pending_update(state_root: Path, slot_root: Path) -> BootObservation`
returns diagnostic bytes and typed `ObservationStatus`/`ObservationReason`
values. `public_json()` has a closed identity-free object of enums and false
claims. `private_json()` adds measured kernel and journal/slot metadata; neither
object is sealed permission, a durable completion receipt or a trusted boot fact.
No update permission API accepting this diagnostic object is added.

`python3 tools/inspect_pending_update.py --state-root /private/state --slot-root
/private/slots` prints the public object. No raw PID, UID/GID, boot ID, pathname,
manifest/image digest or inode is logged publicly. Only an explicit `--output
/private/diagnostics/new.json` can write raw observations, to an exclusive new
0600 file beneath an existing private retained parent outside the state/slot
ancestry. Existing leaves, symlinks, FIFOs and hardlinks are refused; no directory
is recursively created. The output is synced and read back through the same FD.
Failure can leave the explicit new output incomplete; it is not a receipt or
authority, and automatic retry/overwrite is absent. Arguments and output errors
use static redacted messages. Exit 0 means the scan observed no pending records;
exit 2 covers unknown/recovery/unavailable and CLI refusals. Neither is readiness.

## Configuration and features

There are two externally provisioned absolute directory paths and one optional
explicit output path. There is no approved-root parameter, policy injection,
clock callback, kernel-source override, production feature or enablement flag.
An absent state/slot root or lease returns a typed unavailable diagnostic without
creating any authority path. The observer requires Linux procfs and nsfs. Ordinary
journal files with size zero remain invalid, while fixed proc pseudo-files are
read with explicit byte bounds despite their reported zero size.

## State, concurrency, and failure semantics

Every scan method checks actual creator PID and thread before reading or acquiring
a descriptor. Shared observers may run together; an update writer's exclusive
lease blocks them. Flock protects cooperating owners, not privileged filesystem
mutation or whole-directory rollback. All opened component/record/lease/slot FDs
remain owned through the scan. End checks compare retained metadata to each
named nofollow leaf and compare both inventories; substitutions refuse the scan.

Boot ID, actual mount namespace device/inode, actual `/` device/inode and bounded
mountinfo bytes are sampled before and after. Proc/nsfs filesystem magic is
checked on the actual opened fixed-source FDs. The root mount must be unique and
match `/`'s actual major/minor device. The fixed `/proc/self` magic link must name
the actual creator PID before numeric process paths are read; a procfs mount from
a mismatching PID namespace is refused instead of measuring another process.
Any sampling drift gives typed unknown,
with no boot proof. Mountinfo's source string and filesystem options stay private
observations, not resolved devices or image identity. There is no claim that a
finite scan observes every intervening kernel change.

Descriptor cleanup detaches each integer before closing it, attempts remaining
descriptors after a close error and never retries a number that may have been
reused. Fork children and GC only close their local descriptor copies; they do
not use inherited scan authority, acquire a mutex, explicitly `LOCK_UN` the
parent's open-file description, write a clean receipt or repair evidence.
Cleanup failures propagate; loss of a diagnostic response grants no operation.

## Security invariants

All source records retain the existing schema and false claim ceiling. Exact
canonical bytes distinguish boolean and integer aliases. A pending source
`boot_policy_armed` tail reports `pending_identity_unknown`; a marker or other
unfinished tail reports recovery. Empty/clean history reports only no pending
records in the observed inventory. Bad chains, custody, limits or unknown files
never yield continuation authority. No event or marker is silently replaced.

Read-only means no create, write, fsync or permission repair in the authority
roots; flock and descriptor close are the only lease operations. The optional
private output is a distinct user-requested diagnostic file and cannot be placed
inside either retained authority ancestry. Output permission/custody is checked
without an automatic approval or provisioning workflow.

## Testing and evidence

The dedicated workflow runs this actual Linux corpus on the exact PR head and
current prospective merge, with zero skipped tests. It binds the live head/base
and ordered merge parents. Tests compare authority inventories, metadata and
bytes before/after, read actual proc sources, create real signed pending history,
hold actual exclusive leases, replace opened files and ancestors, and exercise
real kernel symlinks, hardlinks, FIFOs, fork and descriptor-number reuse. A
post-read epoch mutation separately tests the kernel drift refusal branch; it
does not pretend to be a real namespace switch. Contract/API/source-index fields
and enum/limit correspondence are strict regression checks.

Count and byte bounds limit retained evidence and memory. Local filesystem and
proc syscalls are synchronous; this API does not claim a preemptible wall-clock
deadline for a stalled kernel or filesystem. The workflow's process timeout is
a test-run bound, not a product health or update deadline.

Original S11 and durable-owner tests and implementation bytes remain unchanged.
The source workflow runs their actual crypto/private-file regressions too.
Passing these tests supplies no installed boot evidence, no signed-image root
mapping and no hardware result. D1/D2I runtime image qualification is a separate
product; its pass is not a G6 update/recovery pass.

## Operations and troubleshooting

Provision state/slots through the existing owner before using this diagnostic.
If `owner_busy`, wait for that owner to finish or retain the failure evidence; do
not substitute a lease. If unavailable or recovery, retain the existing files
and use external authorized diagnosis. The reader cannot clear recovery or
resubmit an update. Inspect raw output only from the explicitly requested private
file, whose snapshots are observations rather than authority. A missing output
or interrupted delivery does not imply an update effect.

## Compatibility and change protocol

This adds a separate read-only API, contract, source index, CLI and workflow.
Existing frame, nonce, update and durable-owner APIs, six-mechanism profiles,
default roots, production flags and Cargo module inventories are unchanged. The
source inventory guard additionally checks the entire independent observer
index/contract and exact public signatures, then counts its implementation in
the top-level source set. Its original six authority registrations are preserved;
`--refresh-api` cannot refresh the reviewed observer profile. Changes to
the public output require the closed contract and correspondence tests together.
Any future effect adapter must separately authenticate production roots, preserve
real signature bytes, map an immutable signed image to the actual boot root,
measure health with a trusted elapsed clock and durably persist effect outcomes.
Actual QEMU two-boot update/failure/recovery tests and hardware power-cut
qualification must be supplied by their own installed adapter; this source
diagnostic cannot stand in for them.
