# TaskFlow proposals, external approval and single-use dispatch

Plan revision: `2026-08-29-d6`. Status: source enforcement candidate for G5.
Implementation: `platform/taskflow.py`; machine profile:
`contracts/taskflow-execution.v1.json`; regression corpus:
`tests/test_taskflow.py`. This document does not close G5 or activate a daemon.

## Trust and ownership

The trusted host creates `TaskPolicy` from one actual native `CurrentBinding`:
principal, session/incarnation, origin, retained resource identity, document
generation, semantic snapshot revision and mutation epoch. A page/model JSON
proposal cannot configure this policy, a trust root, a storage path or an approval
boolean. These Python APIs are a contract between trusted host components, not
a sandbox for hostile Python code running in the same interpreter.

`PinnedIssuerRoot` is protected configuration supplied by an external approved
provisioning authority. Its constructor checks canonical Ed25519 DER SPKI bytes
and their externally pinned SHA-256, key/issuer scope, audience, policy revision
and validity. Constructing a root does not approve the key or authenticate its
provisioning. The repository provides no production keys or signing method.
`ExternalPermitVerifier()` starts with no roots and refuses all permits. Trusted
revocation only adds key/permit IDs; removal is unsupported. Authenticated root
rotation and revocation delivery remain installation obligations.

The offline verifier invokes fixed `/usr/bin/openssl`, verifies executable owner
and mode, uses `pkeyutl -verify -rawin -pubin -keyform DER`, and supplies a sanitized
environment with `OPENSSL_CONF=/dev/null`. Key, signing preimage and detached
signature are immutable sealed memfds inherited by that subprocess and opened
through its own `/proc/self/fd` namespace. No filesystem pathname or caller
temporary-directory/OpenSSL/provider configuration can replace these inputs. No arbitrary verifier
command, crypto callback, caller approval flag or assertion of a valid hash is
accepted. Tests generate real temporary Ed25519 keys and signatures; absent
OpenSSL causes failure, with no skipped crypto case. The command profile follows
[OpenSSL's EdDSA raw-input contract](https://docs.openssl.org/3.0/man1/openssl-pkeyutl/).

## Wire and signing profile

All JSON is bounded to 32 KiB and depth eight. Every object has a closed field
set; duplicates, boolean-as-integer, floats, NaN/Infinity, non-UTF8 strings and
unpaired surrogates are refused. Canonical bytes are UTF-8 JSON with sorted keys,
comma/colon separators and `ensure_ascii=false`. Canonicalization normalizes
wire formatting and member order, but never discards a semantic field.

Proposal fields are exactly those listed in `proposal_fields` in the machine
profile. Operations are `page.observe` (semantic mode), `page.act` (native
semantic click), `page.navigate` (exact same-origin URL) and `page.extract`
(exact extraction schema). Unsupported operations, selectors, JavaScript and
extra arguments are refused. Resource fields are exactly `kind`, `target`,
`document_generation`, `semantic_snapshot_revision` and `mutation_epoch`.
`target` is an opaque native identity, not a selector, text search or coordinate.

`proposal_sha256(payload)` validates before hashing:

```
SHA256("trillionnium.desktop.taskflow-proposal-digest.v1\0" || canonical_proposal)
```

The permit uses the existing `capability-permit.v1.schema.json` envelope and a
narrower closed resource profile. `subject`, `audience`, `operation` and
`policy_revision` must exactly match the current proposal. The resource binds
task/action IDs, session/incarnation, origin, complete proposal digest, complete
native target tuple, canonical argument digest and original action budget. It
contains no approval boolean, ambient wildcard or caller-authored capability.

`permit_signing_bytes(payload)` validates the envelope and excludes only
`signature.value`. Signature algorithm and key ID remain signed:

```
"trillionnium.desktop.capability-permit-signature.v1\0" ||
canonical(permit with signature = {algorithm, key_id})
```

`signature.value` is canonical padded base64 of exactly 64 Ed25519 bytes. A signer
can use base64 of 64 zero bytes as the helper's placeholder. Domain separation
prevents an app/update signature from being interpreted as TaskFlow approval.
Changing a signed binding or even switching to another permitted key ID with
the same public key invalidates the signature.

Canonical origin spelling is credential-free lowercase HTTPS, including the
distinct synthetic HTTPS origins for trusted apps required by
[ADR0004](../adr/0004-trusted-app-origin-model.md),
without custom schemes, path/query/fragment or explicit default HTTPS port. The narrow navigation
profile admits only a literal URL under that exact origin. This comparison does
not prove actual DNS, connected peer, TLS, redirects or egress isolation; those
remain separately enforced native/network adapter requirements.

## Concrete APIs and lifecycle

| API | Precondition and result | Closed failure |
| --- | --- | --- |
| `TaskFlowCoordinator(verifier=None, store=None, monotonic_ns=..., unix_ms=...)` | Concrete offline verifier and optional concrete durable store; trusted clocks | No roots by default; no store means dispatch unavailable; generic verifier/store substitutions refused |
| `create_task(TaskPolicy)` | Fresh task ID, bounded count/budgets, current trusted binding and actual durable task reservation when a store is configured | A previously reserved task from reopened history cannot be resumed, including predispatch cancel/handoff/expiry |
| `propose(task_id, payload)` | Exact trusted task/resource binding and one unresolved action; returns `ActionView` | Reused action ID, expanded resource, unsupported arguments or exhausted budget refused |
| `approve(task_id, permit_payload)` | Current proposed action, actual external signature and exact bindings; returns approved view | Model self-signature, unknown/revoked issuer, expired or mismatched permit refused |
| `dispatch(task_id, CurrentBinding, adapter)` | Approved action, current exact native binding, root/permit/control validity and durable single-use consumption | Missing concrete store, replay, drift, cancellation, expiry or uncertain persistence prevents adapter invocation |
| `ActionControl.ensure_active(actual_native_binding)` | Current dispatched action and exact actual native resource; caller performs this beside retained-node action | Revocation, stale native revisions, cancellation/handoff and original deadline stop new action |
| `cancel(task_id)` / `handoff_to_human(task_id)` | Revocation only; returns current view | Neither operation can create approval or restore Agent authority |
| `close_task(task_id)` | No unresolved action | Indeterminate work cannot be hidden by closing the task |

Task creation fixes one monotonic task deadline. Proposal creation fixes the
earlier task/action deadline. Approval adds an earlier monotonic ceiling derived
from the original wall/monotonic sample and signed permit expiry; frozen wall
time and delayed approval cannot renew it. Backward/unavailable trusted time
permanently closes the coordinator pending separate recovery. Actions count from
proposal creation and cancelled/refused proposals do not replenish the budget.
The native resource tuple is pinned for this task; revision or target changes
require fresh independently authorized task policy, IDs and permit.

The action-count regression uses a two-second test task policy and advances its
injected monotonic clock past that original deadline after testing the count.
Approval still runs actual offline Ed25519 verification. This avoids requiring
a native OpenSSL process to finish within five milliseconds to reach a counter
assertion. A separate five-millisecond task-expiry case uses a real signed permit
and checks that expiry refuses approval and dispatch without durable consumption
or an adapter call. Production policy limits and verification timeouts are
unchanged; these tests do not qualify installed performance or a latency SLO.

Store, coordinator, action controls and verifier policy remain bound to their
creator process. Authority methods check the current PID before mutex use, so
forked snapshots cannot ignore later parent cancellation/revocation or reuse an
inherited flock lease. Worker threads within the owning process remain allowed.

After durable consumption and the final local authority check, the action becomes
`dispatched` before adapter entry. Concurrent dispatch has one irreversible
winner. The trusted native adapter must repeat `ensure_active` using its actual
current owner/retained target immediately before action. Python cannot forcibly
preempt an adapter that has already started; cancellation is cooperative and
possible execution cannot be rolled back by changing a state flag.

Typed `EffectOutcome.SUCCEEDED`/`REFUSED` before the original deadline moves the
action to terminal. Missing/untyped completion, exception, late result, changed
authority, cancellation or handoff after dispatch moves to indeterminate and
hands the task to the human. An indeterminate task has no resume/retry API. These
views do not issue a product durable terminal receipt; that installed integration
is still required. A callback return is not qualification evidence of an effect.

## Durable consumption and recovery

`DurableGrantStore(Path)` uses an already provisioned service-owned `0700`
directory; it does not create/repair ownership or permissions. It retains every
nofollow ancestor and root descriptor and holds an exclusive nonblocking lock
on a validated regular one-link `0600` `.taskflow.lock`. Unsafe preexisting lease
metadata, busy ownership, symlink ancestors or detached/replaced parents refuse
admission. The root namespace accepts only that lease and reviewed consumptions.

Before an accepted task can propose or approve, its configured store writes
`task-<SHA256(task_id)>.reserved` with a versioned task ID and complete canonical
trusted-policy digest. This immutable one-link `0600` O_EXCL reservation uses
the same retained descriptor, file/directory sync and readback rules as a grant
consumption. It is never deleted. Reserving at dispatch would forget a cancelled,
handed-off or expired approved task and let a service restart renew its budget;
reserving at task admission closes that gap. Without a store the API can model
proposals/approval, but actual dispatch remains unavailable.

One consumption record binds task/action, proposal digest, issuer/permit ID,
nonce and canonical verified permit digest. Before any adapter call, three
`O_EXCL` immutable `0600` one-link records claim:

1. `nonce-<nonce>.used`;
2. `permit-<SHA256(permit_id)>.used`;
3. `request-<SHA256(task_id || NUL || action_id)>.used`.

Complete writes and file fsync precede directory fsync. Created descriptors stay
retained through exact content/inode/name readback and ancestor/root/lease
revalidation. There is no deletion, truncation or retry of a consumption.
Claiming all three is intentionally not an atomic distributed transaction:
partial publication loses availability and preserves evidence rather than
permit duplicate execution. Disk full, sync failure, pathname substitution or
ambiguous custody poisons the instance and leaves dispatch closed. Historical
partial/corrupt sets refuse reopening; complete sets remain consumed after
restart. Substituting a fresh signed nonce cannot reuse the original action ID.

The store permits at most 1024 task reservations and 1024 consumptions and fails
closed at capacity. It retains complete deduplication history. Previously reserved task IDs cannot
be recreated after reopen, even if their in-memory completion had been known:
without a persisted authorized recovery/terminal protocol, source code cannot
infer that the task is safe to resume. Fresh tasks require fresh human intent,
policy, identifiers and signatures. Archival/pruning, durable recovery decisions
and whole-directory rollback protection require separate reviewed mechanisms;
an unprotected local directory supplies no anti-rollback anchor.

## Source evidence and remaining G5 work

Run `python3 -m unittest discover -s tests -p 'test_taskflow.py' -v`. The corpus
uses fixed real OpenSSL verification, temporary test-only keys, actual private
files, concurrent dispatch and injected sync/write/custody cutpoints. It covers
signature/key-ID substitution, all proposal binding dimensions, native revision
drift, cancellation/handoff, budgets, clock regressions, response/completion
uncertainty, cross-restart replay, consumed-nonce substitution, partial records,
hardlinks, unsafe modes/leases, ancestor links and detached parents.
It also reproduces predispatch closure across restart and real fork inheritance
with parent cancellation and revocation, then confirms both are refused.

Remaining work includes authenticated root/revocation provisioning, real trusted
approval UX and external signing custody, the installed native effect/retained
target adapter, actual egress enforcement, product receipt integration, durable
authorized recovery decisions and installed-image fault evidence. Default
activation and release authority are unchanged. Source tests and these policy
objects cannot be labeled approval UX, physical isolation or production readiness.
