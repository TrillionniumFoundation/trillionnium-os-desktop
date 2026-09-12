# S11 transactional A/B update and recovery

## Scope and claim ceiling

S11 defines a fail-closed source and host-mechanism candidate for transactional A/B image updates. It admits one exact manifest, verifies one complete target image, stages only the inactive slot, requires an exact boot identity and a durable health receipt before commit, and enters recovery rather than guessing when state is ambiguous.

The claim ceiling is deliberately narrow: source behavior and host filesystem mechanics only. This branch does not prove an installed QEMU update, raw power loss, a physical device, production signing-key custody, publication, or release readiness.

## Threat and authority boundary

Update metadata, downloaded bytes, durable state, process restarts and caller-supplied recovery assertions are untrusted. A manifest is data, not authority. A checksum match does not authorize installation, a staged image does not authorize activation, and a journal fact does not authorize replay.

The coordinator owns transition authority through sealed, transaction-local tickets. Callers cannot construct a valid manifest ticket, health permit or reconciliation fact directly. One exclusive nonblocking filesystem lease prevents two coordinators from publishing state concurrently. No function performs DNS, HTTP, TLS, package download, signature creation, process execution or external publication.

## Manifest admission

The manifest is one strict UTF-8 JSON object with an exact field set. Duplicate members, a UTF-8 BOM, `NaN`, infinities, unknown fields, malformed identifiers and unbounded values are rejected. It binds:

- the repository identity;
- the exact running source version and source whole-image digest;
- a strictly newer target version;
- the inactive slot;
- one target whole-image digest and exact byte length;
- a rollback floor and bounded expiry;
- signer identity and detached-signature digest metadata.

S11 source validation does not itself authenticate a production signature. Installed qualification must supply a signature verifier rooted outside the update payload and repository checkout.

## Durable A/B state

The state machine is:

```text
idle -> verified -> staged -> boot_pending -> health_pending -> committed
                                  |                 |
                                  +---- failure ----+-> rollback_pending -> idle
                                                     -> recovery_required
```

The target bytes must match the complete manifest length and whole-image digest before staging completes. The booted slot and digest must equal the staged target. Commit requires a sealed health permit bound to the same manifest digest and sequence after at least 60 stable seconds.

State storage retains a private directory descriptor, rejects symlink traversal, requires a `0700`-style root and `0600` files, takes an exclusive coordinator lease, and publishes through exclusive temporary creation, complete write, file `fsync`, atomic replacement and directory `fsync`. A failure after replacement is `PublicationIndeterminate`; callers must read and reconcile the durable destination before retrying.

## Failure and replay semantics

A missing slot, substituted image, malformed state, changed active image, exhausted sequence, wrong phase, stale ticket, unrelated health permit or unrelated journal fact fails closed. Two failed first boots open rollback. Rollback must restore the exact source image digest; otherwise the state becomes `recovery_required`.

A possible effect dispatch latches reconciliation. There is no automatic replay. The latch can be cleared only by a sealed durable reconciliation fact for the same manifest digest and sequence whose journal status is terminal or indeterminate. Clearing the latch moves to rollback; it never repeats the update operation.

## Installed-image qualification

Closing S11 requires a separate immutable installed-image packet derived from the exact accepted S10 image lineage. At minimum, the installed QEMU gate must run normal update, downgrade, expiry, wrong-source, payload substitution, slot substitution, first-boot failure, health failure, rollback and restart reconciliation cases.

Every durable cutpoint must be exercised before and after temporary creation, complete write, file sync, atomic replacement and directory sync. The installed gate must also interrupt first-boot health and rollback. Host exception injection is useful source evidence but is not raw power loss evidence.

The installed packet must bind source commit/tree, source image digest, target image digest, manifest digest, booted slot, journal/receipt identities, QEMU command line, firmware/kernel/package locks and every terminal result. A source push, base movement or image rebuild invalidates it.

## Evidence invalidation

S11 source evidence invalidates on changes to this contract, implementation, tests, workflow, S10 base, image manifests, receipt/journal logic, package inputs or toolchain locks. Installed evidence additionally invalidates on any source/target image digest, QEMU substrate, boot firmware, kernel, update signer trust root, systemd unit or durable-state format change.

Exact-head and live prospective-merge jobs must be terminal-success on the final immutable object. Historical S10/D1/D2I artifacts and predecessor update experiments are provenance only and do not transfer.

## Non-claims

This source candidate does not claim that an update was installed in QEMU, that a machine survived raw power loss, that physical hardware passed, that a production signature was verified, or that a release was published. Those facts must be produced by the corresponding independent facility and accepted without administrator bypass or self-approval.

## State-store custody and operator reconciliation

The executable additive contract is
`contracts/s11-state-store-custody.v1.json`; its actual-filesystem regression
suite is `tests/test_s11_state_custody.py`. This section tightens the existing
`descriptor_pinned_no_follow` requirement without promoting an installed update.

`AtomicStateStore` opens every absolute canonical path component relative to a
retained directory descriptor with `O_DIRECTORY|O_NOFOLLOW`. Paths are bounded
to 4096 UTF-8 bytes and 64 components. Ancestors must belong to root or the
effective service UID and may not be group/other writable, except for a
root-owned sticky temporary directory used by host tests. The final directory
must be exactly `0700`. Operations rewalk the name and compare it to the retained
inode; replacement, ownership/permission failure or lease identity loss permanently
invalidates the handle. Restoring an old name or mode does not revive it.

The coordinator lock is a private `0600`, regular, empty, single-link inode.
Nonblocking open prevents FIFO stalls; nonblocking flock enforces cooperation.
Existing permissions are never repaired. Both the retained descriptor and the
current `.coordinator.lock` name must identify the original inode. State names
are canonical ASCII basenames beginning with a letter or digit, at most 128
characters; hidden lock/staging names, dot aliases, traversal and normalization
are refused. A caller cannot overwrite the active lock through `write` and
thereby admit a second coordinator. Root or deliberately hostile same-UID code
is outside this cooperative lease's isolation claim.

State leaves must also be private regular single-link files. Reads reject
symlinks, FIFOs, foreign/multi-link/public files, inode replacement and concurrent
metadata changes. Both constructed and decoded state use the same 64 KiB, depth
32, 4096-item (including keys), 4096-byte string, and signed-integer-magnitude
limits. Floats, non-JSON values, duplicate keys, invalid UTF-8, malformed/deep
state and unsupported types are typed refusals. Container length is checked
before extending the validation worklist.

Exclusive staging collisions preserve the pre-existing file. Cleanup removes
only the inode created by the failed call, never a substituted name. The
staging descriptor stays open through atomic replacement and file/directory
barriers. Once replacement may have begun, syscall failure, interpreter
interruption, sync failure or later identity ambiguity produces
`PublicationIndeterminate` and blocks all further writes on that handle.

`read` is diagnostic and does not clear this latch. The explicit
`reconcile_publication(name, expected_sha256=...)` method requires the pending
name and digest, re-reads the exact bytes, synchronizes file and directory,
rechecks identities and validates the state before clearing the local latch.
It never rewrites state, changes a slot, retries an update or invents a receipt.
Missing/mismatched state or a failed sync keeps the latch. Preserve the store
and escalate instead of deleting a collision or repeatedly calling `write`.

This latch covers **only the current live storage handle**. Persistent update
transaction reconstruction, authenticated signatures, bootloader integration,
operator authorization and installed-image/power-loss qualification remain
separate unresolved gates. Reopening a store is not proof that any of those
protocols ran. Exception injection and local child-process tests are not actual
power interruption. Existing S11 acceptance tests remain required alongside the
new hostile corpus, both on the immutable head and the live prospective merge.
