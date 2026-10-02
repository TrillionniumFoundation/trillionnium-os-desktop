# Controlled HTTPS observation source candidate

`platform/controlled_egress.py` implements G5's actual resolver, socket, TLS,
peer and response path using the Python standard library. It performs real
DNS-over-TLS and HTTPS I/O through one permit-bound operation. The default
`ControlledEgress()` has no approved hosts, origins, resolver or roots and
refuses external I/O. No production trust policy is supplied in the repository.

The machine contract is [controlled-egress.v1.json](../../contracts/controlled-egress.v1.json).
The initiating origin follows [ADR 0004](../adr/0004-trusted-app-origin-model.md)
and external effects remain disabled under
[ADR 0006](../adr/0006-network-egress-and-effect-boundary.md). This source client
does not confine the installed browser, integrate its load paths, activate an
external task, or establish installed D6 qualification.

## Explicit authority and one operation

The trusted mediator owner supplies an exact frozen `EgressConfiguration`:
approved hostname/port pairs, approved initiating origins, an approved
`ApprovedResolver` with its numeric endpoint and TLS name, and immutable PEM CA
bytes for resolver and destination certificates. These are externally
authenticated policy inputs. Page content, model output, redirects and DNS
answers cannot add hosts, roots or permit scope. The constructor does not load
system roots, an ambient resolver, proxy environment variables or caller sockets.

An initiating origin is an exact HTTPS tuple without a trailing slash:
`https://shell.system.hepta.invalid` or
`https://<app-id>.<publisher>.apps.hepta.invalid`. Both identifiers occupy one
canonical lowercase ASCII DNS label. Custom schemes, explicit ports, external
origins, paths, queries and fragments are refused. The entire `hepta.invalid`
namespace is forbidden as an external destination or resolver TLS name, so a
synthetic local app origin cannot fall back to this client's public DNS path.

The owner binds an actual `SessionBinding` object, then issues one
`ObservationPermit` for a canonical HTTPS URL and optional exact redirect host
scope. A permit contains a random operation ID, URL, session object, current
epoch and issuer identity. The issuer retains that exact object. Reconstructed,
copied, stale and cross-client permits or sessions are refused. Rebinding or
closing the client invalidates pending permits and active operations; active I/O
checks the current binding between bounded steps.

Only the creating process may use this authority. The PID check precedes every
authority mutex, including active-operation validation, so a fork cannot reuse
a copied permit or an old cancellation snapshot, nor deadlock on an inherited
mutex. Threads in the creator process may execute, revoke and cancel operations.
This is a trusted Python process API, not an isolation boundary against code
that can modify the mediator's private memory.

`observe(permit, session, timeout_seconds=10, cancellation=None)` consumes the
permit before network I/O. Only exact `method="GET"` and
`resource_class="observation"` are supported. Caller headers, request bodies,
credentials and cookies are unavailable. Observation means returning inert,
bounded bytes from an approved endpoint; this client does not navigate a
browser, run returned HTML, or establish that an arbitrary server's GET has no
side effects. A trusted approval surface and external effect classification
remain separate requirements.

## Actual resolver, peer and TLS checks

The resolver endpoint is a canonical approved literal public IP, with an exact
port, DNS TLS hostname and explicit CA PEM bytes. Its numeric socket avoids
libc resolver calls that could outlive the operation deadline. The client checks
the actual connected peer before and after certificate/hostname verification.
It sends bounded A and AAAA questions through DNS-over-TLS and parses the
responses itself. It validates transaction ID, question, response flags, record
counts, classes, lengths, bounded backward compression and complete packet
consumption. DNS aliases and non-address answers are deliberately unsupported.

Every A/AAAA address in every response section must pass policy before a target
connection is attempted. Production accepts conservative public unicast IPv4
and IPv6 only. It additionally rejects explicit special-use IPv4 ranges and
IPv6 outside `2000::/3`, mapped IPv4, `2001::/23`, documentation including
`3fff::/20`, 6to4,
scoped, private, loopback, link-local, metadata and multicast addresses. A mixed
public/private answer set is refused in its entirety. Resolution is fresh for
every redirect hop; no DNS cache or automatic address fallback is present.
The explicit documentation ranges follow the
[IANA IPv6 special-purpose registry](https://www.iana.org/assignments/iana-ipv6-special-registry/),
including RFC 9637's range even on older Python address tables.

The client sorts the unique admitted addresses and attempts one exact address.
It checks `getpeername()` against that address and the approved port; IPv6 scope
must be zero. HTTPS uses TLS 1.2 or newer, `CERT_REQUIRED`, DNS hostname
verification and only the explicit CA bytes. ALPN may be absent or select
HTTP/1.1. There is no certificate-error bypass or redirect-to-HTTP exception.

Each of at most three redirects rechecks the owner, actual session, origin,
permit scope, configured host, fresh A/AAAA answers, actual TCP peer and TLS
certificate. A repeated canonical URL is refused. A redirect cannot grant a
new hostname or port, resolve a synthetic app origin, or extend the deadline.

## Bounded I/O and outcome

One finite monotonic deadline covers resolver connect/TLS, both DNS queries,
destination connect/TLS, request send, response read and every redirect. The
allowed duration is 0.01–30 seconds. Sockets are nonblocking and readiness waits
last at most 50 milliseconds before checking cancellation and authority again.
This is a bound on readiness polling; operating-system scheduling and finite
parser/TLS CPU work can add latency. Backward or nonfinite monotonic time
permanently revokes the client; a later clock sample does not repair its permit
authority.

Every hop permits at most 16 KiB of headers, 64 unique headers and 1 MiB of body.
Responses require one exact `Content-Length`, ASCII nonfolded headers, identity
encoding and HTTP/1.1. Transfer encoding, duplicate headers, cookies,
attachments, upgrades, compressed content and unbounded close-delimited bodies
are refused. The final response must be status 200 and `text/plain`, `text/html`
or `application/json`, optionally declaring UTF-8 or US-ASCII. Unsupported
resource classes, workers, service workers, iframes, prefetch, subresources,
downloads, WebSocket, QUIC and external effects have no dispatch path in this
client. This refusal does not prove that an installed browser cannot bypass it.

A successful `ObservationResponse` contains immutable bytes, their SHA256 and
per-hop receipts. Each receipt binds session ID/generation, initiating origin,
URL SHA256, exact hostname/port, all admitted addresses, actual peer, HTTPS
certificate digest, resolver peer/certificate digest and a digest of the
approved policy. The policy digest is SHA256 of ASCII canonical JSON produced
with sorted keys, compact separators and `ensure_ascii=true`; the contract
defines its exact fields. It identifies the policy used by this client, not a
signature, durable delivery receipt or independent approval proof.

Immediately before the first HTTP send attempt, the client records the actual
connection identity. Any later failure, cancellation, timeout or interruption,
including `KeyboardInterrupt` and `SystemExit`, produces `EgressIndeterminate`
with the operation ID, attempted connection, completed hops and original cause.
The consumed permit cannot run again. Earlier errors are bounded policy,
resolver, connect or certificate refusals. The client never retries or chooses
another address automatically. It has no persistent operation journal or API
that clears indeterminate outcomes; explicit later operation approval and
durable reconciliation belong to the installed mediator/effect owner.

## Real local qualification and remaining integration

`QualificationEgressClient` requires an explicit exact `QualificationProfile`.
Production `ControlledEgress` rejects that profile. Its only network-policy
exception is an explicit set containing `127.0.0.1` and/or `::1`; resolver and
destination traffic use the same real socket, TLS, peer, redirect, deadline and
response code. Receipts set `qualification_only=true` and always leave
`browser_namespace_enforced=false` and `external_mutation_enabled=false`.

Run the source regression with:

```sh
python3 -m unittest discover -s tests -p test_controlled_egress.py -v
```

The tests create disposable test-only CA/server certificates using system
OpenSSL, then run actual local DNS-over-TLS and HTTPS endpoints, including IPv6.
Missing OpenSSL or an unavailable required IPv6 loopback listener fails the
suite rather than skipping qualification. Positive requests, wrong CA/name,
actual peer substitution, mixed/private/mapped answers, rebinding, redirects,
proxy/root environment poisoning, framing/size violations, deadline, cancel,
send-return interruptions, session revocation and actual fork are exercised.
These are source/host regressions, not installed browser or hardware evidence.

Remaining G5 obligations include authenticated host/root/session provisioning
and a trusted approval UI; privileged namespace/socket confinement; causal
interception of every browser resource class; synthetic origin interception;
policy/root lifecycle and certificate revocation; external effect permits;
durable indeterminate reconciliation; and installed resolver/TLS/time/platform
qualification. Until those gates are complete, browser external mutation stays
disabled.
