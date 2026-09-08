# Session incarnation and frame-reference isolation

## Scope and non-claims

D3 source candidate. This change prevents accidental reuse of a PageOwner and
WebView identity when an actor is reconstructed, including in either development
service. It also namespaces the current atomic fixture's local frame key so an
old target cannot accidentally match a new WebView after a caller replaces only
the outer session envelope. It is not a real Servo adapter, kernel identity
proof, installed service, exact-image result, production activation, capability
or signed release. No canonical gate is promoted.

## Reproduced failure and authority boundary

Previously every new actor started its counters at zero and emitted
`session-<uid>-1` and `webview-1`. Its new SessionMachine also started local
revision counters at the same values. An old session envelope with a fresh
request ID could therefore pass binding after reconstruction. Separately, the
fixture emitted the same `frame-main` and node coordinates across owners; an
old reference could be copied under the new outer session and accepted after a
new observation. These are independent of duplicate-request rejection in the
journal: the regression deliberately uses a new request ID.

The fix allocates identities on the trusted actor side. No caller session,
request ID, profile name, timestamp, PID, connection nonce, receipt digest or
persisted old PageOwner is accepted as an incarnation source. Session IDs and
frame IDs remain public opaque identities, not secrets and not capabilities.
Knowledge or fabrication of current reference fields does not authorize work.
Principal, current-node, revision, visibility and action-policy checks remain
independently necessary.

## Identity allocation and failure sequence

BrowserActor::new keeps its existing API and performs no entropy I/O. The first
valid SessionCreate checks both ordinal successors, checks the original deadline,
then obtains one 32-byte sample through the existing OsNonceSource. The namespace
is the lowercase SHA-256 of the domain
`trillionnium.desktop.actor-incarnation.v1\0` followed by those bytes. The
transport handshake uses a separate sample; its nonce is not reused.

After the entropy read, the actor checks the original deadline again, builds and
validates both opaque tokens, commits the reserved ordinals, and only then calls
the backend. Maximum tokens stay inside the existing 128-byte bounds. A dispatched
create consumes its ordinals even if refused or interrupted; a pre-allocation
counter failure or entropy/deadline failure does not advance them. An allocated
but unexposed namespace may be retained after deadline failure. The entropy I/O
itself cannot be forcibly interrupted by this synchronous mechanism.

Entropy errors or an all-zero sample latch identity allocation failure in that
actor. No predictable timestamp, counter-only, UID/PID or fixed-value fallback
exists. Repeated creation attempts cannot revive the allocator; a new actor is
required. Existing health behavior is not promoted into a successful creation.
A live actor keeps its namespace across close/create cycles, and checked ordinal
increments prevent reuse inside that actor. Reconstructed actors obtain new
samples. There is no new public constructor accepting a chosen namespace,
configuration flag, environment override or installed fault injector. Unit-test
sources are private and compiled only under cfg(test).

## Scoped frame identity API

`scoped_frame_id(session_id, webview_token, local_frame_key)` is a pure adapter
helper. It accepts three bounded ASCII identity tokens (1..128 bytes each), then
hashes the domain `trillionnium.desktop.scoped-frame.v1\0` followed by each
UTF-8 byte length as four big-endian bytes and the bytes themselves. The result
is exactly 64 lowercase hexadecimal characters, without a prefix, fitting the
existing Browser API frame_id limit. Length delimiters prevent concatenation
aliases. Invalid values fail before publication; no normalization or truncation
is used.

The atomic fixture invokes this helper with its current owner and its local
`main` frame key before storing a semantic snapshot. Equality checks of the
complete target and RuntimeCoordinates remain. A rejected reparented target does
not consume the fresh snapshot or increment its action count. Numeric session
and document revisions are still scoped by the opaque session/frame identities;
they are not advertised as globally monotonic across process restarts.

A future Servo adapter must derive its local key from its own actual current
frame, use equivalent owner scoping, resolve unique live nodes and retain them
atomically through an authorized action. Merely hashing caller target fields or
copying an expected PageOwner is not current DOM proof.

## Durable receipts and service reconstruction

Neither daemon needs a new profile, dependency, listener or configuration field.
Both already construct BrowserActor through its standard constructor. The
persistent service continues reopening its existing full journal, restoring old
receipt IDs and reconciling unresolved operations. It does not restore an old
PageOwner identity or replay a recorded action. The next create gets a fresh
namespace even when the authorized agent process and UID are unchanged.

The host integration reconstructs the actual service runner twice in one test
process, reopens the same managed disk journal and runs eight separate socket
requests. It checks 24 lifecycle records, response digests and dispatch ordering.
The old outer session is refused before backend entry; an old reference under the
new envelope is refused by the atomic fixture; the current target then executes
once. The fixture's unit/cgroup facts are synthetic. This is not process reboot,
systemd activation, QEMU, hardware or production-browser evidence.

## Compatibility and operational diagnosis

Existing Browser API v1 token and frame bounds are unchanged. Clients must read
opaque IDs from successful creation and observation, never parse numeric suffixes
or rebuild a session from UID. Old numeric-looking IDs remain interpretable in
historical receipts but receive no compatibility alias to a new actor. There is
no migration, automatic session resumption, journal reset or new replay authority.

On identity allocation failure, preserve the error and existing journal; diagnose
OS entropy availability without injecting a fixed source or reusing an old ID.
On StaleSession, discard the stale envelope and obtain a newly created session;
on rejected stale target, observe the current owner instead of changing target
fields or silently retrying another node.

## Tests and evidence

The actor tests cover reconstruction, pre-dispatch stale rejection, lazy allocation,
latched errors and all-zero entropy, deadline exhaustion, checked counters, maximum
wire tokens, failed-create consumption, domain separation and scoped-frame bounds.
Fixture tests cover cross-WebView and cross-session reparenting, no mutation on
rejection and invalid-owner publication failure. The service test above exercises
actual socket/codec/actor/thread/journal paths. Test-source overrides are not
production API. Structural Python checks supplement, not replace, executable
behavior. Removal of a security invariant must make the relevant negative test
fail; a passing source audit alone is not runtime proof.

## Residual risks and remaining gates

Uniqueness is probabilistic and relies on fresh, correctly functioning trusted OS
entropy and SHA-256, not a proved globally unique allocator. A malicious entropy
provider or a whole-process/VM memory snapshot rollback can defeat freshness.
This is not an external monotonic anchor, credential, attestation or durable
anti-rollback mechanism. Same-process actor reconstruction tests do not prove an
actual system boot path. Current reference fabrication still requires rejection
by principal/policy and the real engine; identities are not MACs.

Publication, new-head CI, independent review, protected-main merge and exact-main
reruns remain required. D2I/D3 actual Servo and image evidence, D4-D7 native
services and permissions, D8 hardware and D9 signing/release remain separate.
