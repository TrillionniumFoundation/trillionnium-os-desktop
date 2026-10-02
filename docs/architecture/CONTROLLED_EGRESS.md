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
copied, stale and cross-client permits or sessions are refused. Successful
rebinding or closing invalidates pending permits and active operations. Budget
checks validate again after clock sampling, and concrete native I/O admission
serializes with cancellation and session revocation as described below.

Only the creating process may use this authority. The PID check precedes every
authority mutex, including active-operation validation and final cleanup.
Inherited cancellation is a no-op before its copied mutex. Native I/O gates
check the creator process and observing thread. Registered socket owners also
retire their copied descriptors after fork, including a fork after the last
socket PID guard. Threads in the creator process may execute, revoke and cancel operations.
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

One private native I/O gate holds the cancellation-token mutex and then the
client policy mutex in that fixed order. With both held, it checks the exact
active permit/session/epoch, cancellation, creator PID and the original
monotonic deadline, including revalidation after its guarded clock sample.
Only then does it perform one nonblocking `connect_ex`, TLS handshake, send or
receive on its retained socket. Private locked helpers never acquire the same
nonreentrant mutex twice. Gate acquisition waits at most 50 ms for each mutex
and at most the remaining original deadline; acquiring a gate never starts a
fresh timeout. Readiness waits occur outside these locks. Scheduling and native
TLS computation remain subject to the finite-work limitations above.

`close()`, session rebinding, permit issuance, observation preflight and guarded
clock access use a private bounded policy context. It checks the creator PID
before entering any mutex and waits at most 50 ms; an operation's validation
and clock accesses also respect its remaining original deadline. Busy or
reentrant access raises `EgressDenied` before changing the binding, epoch,
permit records or cleanup quarantine. Such a refusal does not acknowledge a
successful revocation. Private locked helpers let an admitted native gate
validate policy and sample its clock without reacquiring its held mutex.

`close()` and session rebinding use the same policy mutex. A completed revocation
before native gate admission prevents that call. A call already admitted while
holding the locks can finish before the revoker returns; bytes already sent
cannot be recalled. `CancellationToken.cancel()` first requests cancellation,
then waits at most 50 ms for the token gate barrier. A normal return in the
creator process acknowledges that this barrier completed. If the gate remains
busy, cancellation is still requested but `EgressDenied` reports that the barrier
did not complete; callers must not report successful cancellation from that
exception. A foreign-process cancel returns `None` without setting the flag or
touching an inherited mutex. These orderings do not promise interruption of an
already executing native call or absence of all check-to-C-call races.

An empty private socket owner is registered before opening a raw socket and
retains both raw and TLS socket objects through setup, operation and cleanup.
The private TLS helper returns that owner. An `os.register_at_fork` child hook
closes only those socket objects' descriptor copies, without `shutdown`, mutex
acquisition or release. It retains a close failure as a private diagnostic and
continues retiring other sockets; a failed close is not represented as success.
Socket objects own descriptor detachment, so explicit close and GC never guess
ownership from a saved descriptor number or close a later foreign reuse.
The parent retains its own live descriptor and can complete its request.

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
connection identity. Failures, cancellations, timeouts and interruptions within
the managed I/O and cleanup path, including `KeyboardInterrupt` and `SystemExit`, produce `EgressIndeterminate`
with the operation ID, attempted connection, completed hops and original cause.
An admitted complete response hop is recorded before closing its owned TLS
socket, so a socket-close interruption retains that actual hop. Cleanup retries
only the owned socket's idempotent close; it never sends the HTTP request again.
The consumed permit cannot run again. Earlier errors are bounded policy,
resolver, connect or certificate refusals. The client never retries or chooses
another address automatically. It has no persistent operation journal or API
that clears indeterminate outcomes; explicit later operation approval and
durable reconciliation belong to the installed mediator/effect owner.

Admission and final active-record cleanup use a retained private mutex lease
constructed before permit consumption. The protected admission helper checks
capacity and the exact pending permit under the actual mutex, then records its
private reservation before consuming or inserting records. That shared owner
survives admission helper-return interruptions. Only the caller that owns this
reservation can retire its matching pending/active permit; a competing caller
that loses admission cannot remove the winning request's active record.

The lease checks the creating PID before acquiring a mutex,
waits at most one 50 ms poll interval, and retires its logical ownership before
the actual release. Explicit cleanup and destructor cleanup never infer
ownership from whether the mutex is locked, so they cannot release a later
acquisition by another thread. A failure to confirm final cleanup permanently
quarantines this client before any subsequent authority mutex: pending permits
cannot dispatch and retained active records remain bounded by four. A cleanup
failure before any HTTP send is a chained `EgressDenied` quarantine refusal,
without an invented connection identity; after a send attempt it is
`EgressIndeterminate` carrying the actual attempted identity and known hops.
There is no repair, retry or quarantine-clearing API. Ordinary protocol refusals
whose cleanup completes do not quarantine the owner.
An admission interruption after reservation whose cleanup completes returns a
chained `EgressDenied` for the consumed permit; it leaves no active record or
socket, grants no connection facts and cannot restore that permit. Before any
reservation, an interruption leaves the pending permit unused. Fresh explicit
permit issuance after a completed refusal is a separate operation.

The regressions cover specific Python call, line and helper-return boundaries,
actual native mutex release, foreign reacquisition and fork. They do not prove
the absence of every asynchronous interruption between a native C call and
Python attribute storage, within the standard library's raw-to-TLS ownership
transition, or that a caller received an API's final return value. The fork hook
and socket ownership tests cover actually retained sockets at the documented
Python boundaries; they do not qualify every possible allocation/transfer cut.
A local response and receipt are not a durable caller-delivery acknowledgement.

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
send-return interruptions, session revocation, cleanup interruptions, real mutex
timeout/release/reacquisition, GC, actual descriptor inventories across admission
interruptions, competing same-permit callers and actual fork after a response are exercised.
Additional real-I/O regressions cover completed post-clock revocation with zero
GETs, an already admitted call completing before revocation returns, token/policy
gate contention and unchanged deadlines, cancellation-barrier timeout and
foreign-process no-op, wrong-thread refusal, empty socket-owner construction,
GC after descriptor reuse, and actual fork after the last socket PID guard in
raw-connect, TLS-handshake and HTTP-send stages. The child has closed descriptors
while the parent completes the real DNS/TLS/GET path.
Actual `SIGUSR1` callbacks at an admitted native GET exercise bounded reentrant
close, bind, issue, observation preflight and clock refusal without changing
authority; the original request then completes and both mutexes are released.
These are source/host regressions, not installed browser or hardware evidence.

Remaining G5 obligations include authenticated host/root/session provisioning
and a trusted approval UI; privileged namespace/socket confinement; causal
interception of every browser resource class; synthetic origin interception;
policy/root lifecycle and certificate revocation; external effect permits;
durable indeterminate reconciliation; and installed resolver/TLS/time/platform
qualification. Until those gates are complete, browser external mutation stays
disabled.
