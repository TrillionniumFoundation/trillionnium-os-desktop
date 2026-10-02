# Durable signed-app storage source v1

`platform/app_storage.py` supplies concrete private disk storage for the G5
signed-app lifecycle. It stores complete verified asset snapshots, strictly
increasing version floors, install/uninstall records and partitioned opaque app
data. Its [machine contract](../../contracts/app-storage.v1.json) is a source
candidate. Installed native origin interception, engine storage enforcement,
CSP, app activation and trusted approval remain open G5 obligations in the
[closure plan](../plan/IMPLEMENTATION_CLOSURE_PLAN.md).

The store reuses the real [signed-bundle admission](TRUSTED_APP_BUNDLES.md)
implementation. A default store creates an admission owner with no publisher
roots and refuses installation. The trusted host supplies an externally
authenticated policy, trusted Unix time and the concrete admission owner.
Host Python code is trusted; these APIs are not a sandbox for arbitrary Python.
A principal identifier supplied to the API does not authenticate a native
request by itself.

## API and ownership

The module exposes its concrete admission dependency as `trusted_apps` under a
stable module identity, `hepta_trusted_apps_v1`; this avoids the stdlib `platform`
module and duplicate verifier class identities. Hosts construct their
`PublisherTrustRoot`, `PublisherTrustPolicy` and `TrustedAppAdmission` from that
dependency. A different independently loaded admission class, a duck verifier,
an approval boolean or a caller digest cannot replace the owner.

All operations require the creating process and Python thread and refuse
reentrancy. A forked copy cannot use store authority or unlock the parent's
retained lease when closing its own descriptors. Instances should be closed
explicitly; a clean close is part of the durable protocol. Constructor failures
release acquired descriptors and never remove artifacts.
Garbage collection closes the abandoned object's descriptor copies without
issuing `LOCK_UN`, checking thread authority, publishing a clean receipt or
deleting history. Its unresolved open record still blocks a subsequent owner.
GC cleanup prevents a forgotten object retaining a lease until process exit;
it does not implement successful shutdown or recovery.
Cleanup detaches the complete lease/ancestor/root descriptor ownership before
any close, attempts every detached descriptor even if another close raises, and
propagates the first error from explicit close. An ambiguous close return is
never retried by integer; GC cannot later close an unrelated reused descriptor.
Physical errors before a close takes effect may leave an unowned descriptor
until process exit; retrying that number would risk closing unrelated resources.

| API | Concrete semantics |
| --- | --- |
| `AppStorage(root, admission=None, shell_version="1.0.0")` | Acquire an existing private directory and exclusive lease, validate retained history, fsync a new owner-open record; default admission has no roots |
| `synchronize_policy(now_unix=...)` | Persist the actual admission owner's current revision, root pins, cumulative revocations and remembered key identities |
| `prepare_install(principal, verified_bundle, now_unix=...)` | Revalidate this owner's admitted bundle; build bounded immutable canonical ZIP; return store-issued `InstallTransaction` tied to current policy/event sequence |
| `commit_install(transaction, operation_id=..., now_unix=...)` | Consume an exact current plan, publish intent/package/commit, redo real verification on the protected package, return `InstalledApp` |
| `open_app(principal, exact_origin, now_unix=...)` | Require active partition, read its protected archive and redo complete current real signature admission before issuing an incarnation handle |
| `asset_response(handle, exact_url, now_unix=...)` | Validate active incarnation, package custody, exact local URL and current publisher policy; return admitted immutable bytes and restrictive headers |
| `put_data(handle, key, immutable_bytes, operation_id=..., now_unix=...)` | Publish a bounded immutable data artifact and durable logical replacement |
| `read_data(handle, key, now_unix=...)` | Read exact current partition data with custody, recorded length/hash and current policy checks |
| `delete_data(handle, key, operation_id=..., now_unix=...)` | Publish a logical deletion tombstone while retaining prior bytes and key identity |
| `uninstall(handle, operation_id=..., now_unix=...)` | Publish an uninstall tombstone; invalidate active handles, preserve version floor and all data/assets |
| `close()` | Publish a clean owner receipt only for an unpoisoned successful owner; release descriptors; poisoned owners leave unresolved history |

Public `InstalledApp` and `InstallTransaction` constructors refuse. Plans are
bound to their issuing store and current event sequence; an intervening data,
policy, lifecycle or other event invalidates a plan. Consumed plans and operation
IDs cannot be reused. IDs are 1–128 ASCII characters from `[A-Za-z0-9._:-]`.
`policy:` is reserved for durable operator-policy records. Failures raise
`AppStorageError`; custody, publication and unresolved history raise
`RecoveryRequired`. Process interrupts propagate and leave recovery required
when they interrupt a publication. No exception grants partial authority.

## Partition, version and migration rules

Each partition binds a trusted principal identifier and the exact origin
`https://<app_id>.<publisher>.apps.hepta.invalid`, as required by
[ADR 0004](../adr/0004-trusted-app-origin-model.md). HTTP, custom schemes,
credentials, ports, paths, queries, fragments and alternative spelling refuse.
The internal partition identifier is
`SHA256(UTF8("trillionnium.desktop.app-storage-partition.v1\0") ||
canonical_ascii_json([principal, exact_origin]))`; callers never supply that
hash as proof. Source data handles cannot cross principals or app origins.

Storage accepts stable canonical uint32 SemVer triples and compares them
numerically. `1.10.0` is greater than `1.9.0`. Every later installation in a
partition must be strictly higher, even after uninstall. The same version with
changed signed content refuses. The bundle verifier permits prereleases, but
this narrower storage lifecycle explicitly rejects them. It does not implement
prerelease precedence.

Updates require a concrete prepared transaction from the real store and verified
bundle owner. The signed optional `data_schema_version` must remain exactly the
same, including whether it is absent. Any addition, removal or change refuses;
there is no caller migration callback or boolean assertion. Supported schema
migration needs a separate trusted transactional protocol and is not claimed.
Updates invalidate previous incarnation handles while retaining data in the
same schema and partition. Uninstall immediately blocks source access through
old handles and future `open_app`. It retains all histories and bytes. A strictly
newer reinstall with the same schema can see retained partition data. This is
logical uninstall, not secure erasure or native context termination.

## Real file custody and immutable content

The trusted operator provisions the directory beforehand, with exact mode 0700
and the service UID. The store walks the whole absolute ancestor chain using
`O_DIRECTORY|O_NOFOLLOW`, retains every descriptor and checks each named and
retained inode, owner and mode again through a fresh absolute walk. Renaming an
ancestor or replacing the current root cannot redirect a publication to a
detached directory. Its reserved `.app-storage.lock` is a zero-byte one-link
regular file, service-owned mode 0600, held by an exclusive nonblocking `flock`.
Preexisting symlink, hardlink, writable/group-readable, nonempty or replaced
leases refuse. Lease identity is rechecked alongside directory custody.

All artifacts use derived flat numeric names; archive paths and data keys never
become filesystem paths. Files are mode 0600, service-owned regular files with
one link, created with `O_EXCL|O_NOFOLLOW`. The writing descriptor stays open
through file fsync, directory fsync, complete readback, named-inode checks and
final ancestor/lease checks. Reads are bounded, nonblocking and nofollow, checking
size, timestamps, inode, owner, mode and link count before/after and against the
named leaf. Substitution preserves every candidate and foreign inode and
requires recovery; no cleanup deletes an ambiguous artifact.

The canonical asset snapshot is classic `ZIP_STORED`, regular-file metadata,
fixed timestamps, the original admitted signed manifest and every indexed asset
obtained from the owner's current local-response API. All included extensions
must be supported by that API. Its archive must fit 32 MiB even when the original
compressed bundle was smaller. A full current real Ed25519 admission of the
published package runs before and after commit; reopening an active app repeats
real signature verification. Historical ZIP/index parsing binds retained floor
metadata to complete actual assets without granting a revoked historical key
execution authority. Assets are immutable through this API; a privileged host
process with direct filesystem access can mutate mode-0600 files, which this
store detects at its reads and custody barriers. No filesystem immutable flag
or protection from arbitrary service-UID code is claimed.

Data values are immutable `bytes` up to 1 MiB. Keys are one canonical portable
ASCII path segment, interpreted as exact case-sensitive opaque identities.
Traversal, slash, backslash, percent encoding, hidden names, trailing dots,
Unicode aliases and Windows device basenames refuse. A replacement adds a new
immutable artifact; deletion adds a tombstone and never unlinks previous bytes.
Per partition, live values total at most 4 MiB and at most 128 retained key
identities are allowed, including tombstoned keys. This API supplies an opaque
byte namespace; it does not implement IndexedDB, cookies or a Servo storage
backend.

## Policy floors and durable refusal

The actual admission owner's policy snapshot is persisted before use, augmented
with the store's retained historical key pins. These pins do not reactivate old
roots; they prevent key-ID rebinding after a legitimate rotation removes an old
root and a new admission process has forgotten its former in-memory history. A clean
restart refuses a lower revision, changed contents at the same revision,
removed cumulative revocation, removed remembered key pin or rebound key ID.
The store reads the immutable policy state from the frozen admission
implementation after requiring the concrete owner; callers cannot replace it
with a claimed policy hash. Active app operations revalidate the owner's current
key, issuer, validity and revocation. `synchronize_policy` also persists policy
changes that revoke all roots. Historical records grant no app authority.
Authentic policy provisioning and time remain external trusted inputs.
Synchronization precedes target-key refusal, so a read refused by a new
revocation still retains that policy floor. If a validated new snapshot cannot
be recorded, even because capacity is exhausted before its intent, the owner
stays unresolved and restart refuses; it cannot silently discard the observed
revocation and reopen an old floor.

`now_unix` is supplied by that authenticated host clock on each call. This source
profile configures no clock, monotonic expiry clock or permanent backward-time
latch. A page-selected value, frozen clock or replayed timestamp cannot establish
current validity; an installed owner must supply a fresh authenticated sample
and define rollback/clock-loss refusal. No production clock or roots are
provisioned by this repository.

Before any mutation, construction fsyncs an immutable owner-open record. Each
operation then publishes and separately syncs an immutable intent, optional
asset/data artifact and commit. A commit binds the exact intent hash and event.
Only an orderly owner whose effects and checks all succeeded publishes a clean
session receipt. A publication failure or observed in-operation interrupt leaves
the prior durable open record unresolved, even when complete commit bytes exist.
The tests cover interruptions after append, before handle issuance and during
owner cleanup. A callee cannot prove that its caller received a returned value:
CPython's final return trace callback can interrupt after its exception region.
In that case the already fully durable local commit remains terminal and a clean
restart may inspect it; its consumed operation ID, version and transaction still
cannot replay or broaden authority. No caller acknowledgement boolean clears
an uncertain effect, and no all-possible-interruption-window guarantee is made.
Any unresolved owner, missing commit, gap, duplicate operation, orphan record,
malformed record, or artifact mismatch makes a new owner refuse permanently.
There is no automatic retry, history deletion, truncation or reconciliation API.
An independently specified authenticated operator recovery protocol is required
before recovering that directory.

If the clean-close barrier itself fails, a clean candidate may already exist.
The source preserves it and attempts to leave a distinct refusal artifact; any
such artifact blocks restart even if incomplete. All effect barriers already
succeeded before a clean close began. Storage failure preventing creation or
persistence of the refusal artifact cannot be solved by a Python store alone.
Likewise, restoring the whole directory to an earlier internally consistent
snapshot defeats its internal version/policy floor. An external rollback anchor,
durable storage guarantees and authenticated recovery remain required; neither
whole-directory rollback protection nor crash recovery availability is claimed.

Limits are 256 durable events, 256 owner sessions, 64 retained partitions, 2,048
root entries and 128 MiB retained total bytes. Record size is at most 1 MiB.
Policy roots/revocations/pins keep the admission module's bounds. Every retained
record and old artifact counts toward capacity. Capacity refuses before an
operation intent and reserves room for normal closing when the operator-policy
floor is unchanged; an unrecordable new compatible policy instead preserves an
unresolved owner as described above. Capacity never deletes history.
These deliberately finite source bounds require an installed retention and
external archival policy before long-running production use.

## Verification and remaining installed work

The corpus uses actual private directories, Unix locks, fork/thread checks,
real OpenSSL Ed25519 keys and signatures, complete ZIP bytes, interrupted
publication, injected disk-full/fsync errors, candidate substitution, restart
replay, version and policy rollback, current revocation, origin/principal
isolation, path aliases, symlink/hardlink refusal and retained uninstall/data
tombstones. Crypto cannot be skipped or replaced by a fake verifier.

```sh
python3 -m unittest discover -s tests -p test_app_storage.py -v
```

G5 still requires authenticated roots and time, native request-principal binding,
installed origin interception and storage-engine integration, revocation of
already running contexts, trusted installation/approval/uninstall UX, migration,
operator recovery, retention and external antirollback custody. Source local
response headers and files alone do not enforce native CSP or stop a direct
socket, cached load or unrelated storage path. Production activation remains
disabled until those installed boundaries have independent acceptance evidence.
