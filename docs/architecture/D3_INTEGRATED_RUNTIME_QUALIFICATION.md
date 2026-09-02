# D3 integrated runtime evidence qualification

## Status and claim ceiling

This package defines the fail-closed verifier for evidence produced by an
independent D3 exact-image runtime qualification. The source workflow exercises
the verifier and its hostile corpus only. It does not create a Servo adapter,
boot a qualifying image, protect or merge `main`, enable the production
AgentPort, execute an external effect, or authorize D4-D9 promotion.

A `PASS_SOURCE_VERIFIER_ONLY` result proves only that malformed, incomplete,
self-inconsistent, tampered, symlinked, under-signed, or authority-widening
evidence is rejected by the source verifier.

## Evidence identity

One evidence packet binds the exact repository, ref, source head, source tree,
tested object, base, integrated-main identity, image SHA-256, and pinned Servo
commit. Exact-main mode requires `refs/heads/main` and equality of the head,
tested, and integrated-main commit identities. Fixture evidence is forbidden in
that mode.

The artifact directory is a closed set. It must contain exactly the three files
declared by the contract, with matching byte lengths and SHA-256 values. Paths
are canonical repository-independent POSIX relative paths; traversal,
backslashes, aliases, symlinks, non-regular files, missing files, and extra
files fail closed.

## Principal continuity

Admission and dispatch snapshots bind PID, UID, GID, process start time,
systemd unit, unified cgroup-v2 path, executable SHA-256, and pidfd liveness.
The two snapshots must be identical and dispatch-time revalidation must be
explicit. The hostile corpus requires wrong UID/GID/unit/cgroup/executable,
dead pidfd, and PID-reuse attempts to be denied.

## Servo-owned semantic action

A promotable D3 packet must state and prove that the adapter is Servo-owned,
retains an engine node, resolves and acts inside one engine critical section,
searches the current frame only, obtains exactly one match, verifies role,
accessible-name digest, and structural fingerprint, then revalidates
immediately before one action. The mutation epoch must advance exactly once.
Coordinate, DOM-order, accessible-name-only, and cross-frame fallbacks are
forbidden.

The required negative corpus includes stale session, document, semantic and
mutation revisions; missing and ambiguous targets; cross-frame fallback;
role/name/structure drift; mutation races; cancellation; deadline expiry; and
browser/content crash recovery.

## Durable receipts

The verifier accepts two independent receipt chains: one completed operation
and one indeterminate operation. Each chain is canonical and hash-linked from a
zero predecessor, with contiguous sequence numbers, identical operation
identity, and `requested`, `dispatched`, then terminal ordering. Every record
must be fsync-committed. Requested durability precedes dispatch and terminal
durability precedes the response. Indeterminate work requires reconciliation
and is never automatically replayed.

## Independent attestations

Exact-main mode requires Ed25519 attestations from two distinct roles,
identities, and keys:

- `independent_runtime_operator`;
- `independent_security_reviewer`.

The supplied keyring binds each key to its role and identity. Exact-main mode
also requires the key records to be production-enrolled. The verifier validates
signatures over the canonical evidence packet with the attestation list removed.
Source-CI fixture keys or a copied boolean cannot satisfy this requirement.

## Product boundaries

Every accepted packet keeps production AgentPort activation, external effects,
external networking, ambient filesystem authority, hardware qualification,
signing-key custody, and release readiness false. The development profile must
be explicit. A successful exact-main verification is only promotion-eligible;
its result deliberately remains `promotion_authoritative=false` because
protected governance, independent review, and project-truth promotion are
separate actions.

## Commands

Source-only verifier self-test:

```bash
python3 tools/verify_d3_integrated_runtime_evidence.py --self-test
python3 -m unittest tests.d3.test_d3_integrated_runtime_evidence -v
```

Independent exact-main verification:

```bash
python3 tools/verify_d3_integrated_runtime_evidence.py \
  --evidence /evidence/d3-evidence.json \
  --artifact-root /evidence/artifacts \
  --keyring /protected/d3-keyring.json \
  --require-exact-main \
  --write-result /evidence/d3-verification-result.json
```

The exact-main command validates supplied evidence; it does not itself perform
the runtime qualification or change repository truth.
