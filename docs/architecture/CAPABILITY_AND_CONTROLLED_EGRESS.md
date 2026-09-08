# Audience-bound capabilities and controlled egress

## Status and authority boundary

This package is a D6 source candidate blocked by D5. The reference engine owns
no network namespace, resolver, proxy, socket, filesystem portal, notification
service, audio service, credential, or external-effect authority. All DNS,
proxy, TLS, and connected-peer observations are explicit test inputs.

A reference pass proves policy behavior only. It does not prove that the
operating system has applied those controls.

## Capability permit

The source-candidate wire contract is
`contracts/capability-permit.v2.schema.json`, with schema identifier
`trillionnium.desktop.capability-permit.v2`. The retained v1 string-subject and
Unix-millisecond format is not an alias for this structured-subject,
second-based contract; v1 objects are rejected. See ADR 0006 for migration and
claim boundaries. A schema-valid object still needs signature, runtime-subject,
portal-resource, current-time, DNS/peer, and replay validation.

Every permit is an Ed25519-signed canonical object binding:

- permit, issuer, and issuer-key identities;
- the complete semantic and mechanism subject;
- exact portal audience;
- exact resource scope;
- allowed actions;
- issue, not-before, and expiry times;
- nonce and maximum use count;
- operation-specific constraints.

The subject includes TaskFlow principal, mechanism UID, systemd unit, session,
and PageOwner. Every field must equal the runtime identity; wildcards and
partial matches are rejected. Unknown permit fields are rejected.

Issuer keys have independent validity and revocation state. Permit lifetime and
use count are bounded. A valid signature cannot override audience, subject,
resource, action, time, replay, or portal policy.

## Portals

### File

File authority uses an opaque handle, never an ambient host path. The permit
binds handle, actions, and maximum byte count. Supplying a raw path or exceeding
the byte limit fails closed.

### Notification and audio

Notification authority is bound to one channel and a text-size limit. Audio
authority is bound to one stream, maximum duration, and maximum gain. Neither
portal implies device enumeration or ambient access.

### Network

A network permit contains an exact canonical origin set, controlled resolver
identity, egress-proxy identity, request-context set, method set, redirect
budget, DNS TTL bound, and request/response byte bounds.

Only `https` and `wss` are accepted by this source package. Plain HTTP,
filesystem and other external schemes, QUIC, and WebTransport remain disabled.

## URL and origin handling

URLs reject user information, fragments, malformed ports, trailing-dot hosts,
non-canonical IP literals, localhost names, and schemes outside the permit.
Origins are canonicalized to an explicit port and compared exactly with the
signed origin set.

Each redirect is a new authorization decision. The source and destination
origins must both be permitted, the redirect count must remain within the
permit, and secure schemes cannot downgrade.

## Controlled DNS

The policy consumes a bounded resolver receipt containing resolver ID, query
name, addresses, TTL, observation time, and CNAME chain. It rejects:

- wrong resolver or query identity;
- future or expired observations;
- TTL above the permit bound;
- excessive addresses or CNAME depth;
- CNAME loops;
- duplicate addresses;
- non-global addresses.

Address rejection covers private, loopback, link-local, metadata, multicast,
unspecified, reserved, IPv4-mapped IPv6, 6to4, and Teredo cases. DNS names do
not become trusted merely because they are public-looking.

## Proxy and connected-peer binding

Direct transport is forbidden. The transport receipt must name the exact
signed egress proxy, record verified TLS, reject interception, and bind the
certificate host. The upstream peer IP observed by the trusted proxy must be a
member of the previously approved DNS set. A different connected peer is a DNS
rebinding or routing mismatch and is rejected.

A captive-portal signal, TLS interception, proxy mismatch, or unapproved
response redirect fails closed.

## Request contexts

Top-level pages, iframes, workers, service workers, prefetch, WebSockets, and
downloads require explicit context authorization. No worker or subframe
inherits ambient network authority. A download requires both a network permit
and an independent opaque file-handle permit.

## Decision receipts

A successful reference decision produces a hash-chained receipt containing the
exact permit and request digests, peer/DNS/proxy decision data, and an explicit
`external_effect_executed=false` statement. Tampering with any decision field
breaks the receipt chain.

## Required runtime integration

After D5 is independently integrated, a later D6 package must prove on an exact
image and then fixed hardware:

- separate network namespaces;
- a controlled resolver and pinned egress proxy;
- kernel/proxy observation of the connected upstream peer;
- redirect reauthorization and TLS verification;
- real HTTP(S), DNS, WebSocket, worker, service-worker, iframe, prefetch, and
  download behavior;
- file, notification, and audio portal isolation;
- SSRF, rebinding, metadata, private/link-local, proxy bypass, captive portal,
  and protocol-bypass attack corpora;
- absence of ambient filesystem, device, secret, and credential authority;
- durable PageOwner/permit/operation receipts.

No source-model result may be promoted as that runtime evidence.

## Input and decision transaction hardening

Integer fields accept actual integers, never booleans or floating-point values.
JSON readers reject duplicate members recursively, non-finite numbers, malformed
UTF-8, excessive nesting, and inputs beyond the fixed byte bound. Raw URL control
characters, whitespace, backslashes, empty fragments, and noncanonical authority
spellings are rejected before a parser can silently normalize them. A connected
peer observation cannot predate the DNS evidence it is asserted to bind.

The in-memory decision ledger serializes commits. It rechecks availability,
rejects duplicate permit IDs and unused extra permits, prepares all canonical
hashes and a detached result, and publishes use counts plus receipt only after
all preparation succeeds. Encoding failure or exhaustion of any required permit
leaves both counters and receipts unchanged. Concurrent single-use requests
admit at most one commit. These are reference-model guarantees, not durable
multi-process storage, real portal execution, or external exactly-once claims.

`tests/d6/test_capability_boundary_hardening.py` covers the public authorization
facade, validly signed malformed permits, URL variants, typed bounds, duplicate
JSON, serialization fault injection, concurrent commits, result aliasing, legacy
schema rejection, and schema field-set agreement. Rust's verifier subject is
versioned in the source candidate; exact-head Rust/CI and independent review are
still required before accepting this compatibility change.
