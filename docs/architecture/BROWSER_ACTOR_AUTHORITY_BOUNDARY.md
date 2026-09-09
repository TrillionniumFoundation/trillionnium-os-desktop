# BrowserActor authority boundary

## Purpose

S06 introduces the concrete product request owner that translates one validated
Browser API request into one bounded local-fixture runtime operation while
preserving session, cancellation, peer-custody, and receipt invariants. The weak
paths are absent from the product-facing type system rather than merely
conventionally discouraged.

## Product crate: `hepta-browser-actor`

The product API exposes one **non-generic** `BrowserActor`. Its
`from_attested` constructor accepts only:

1. a policy-selected `TaskFlowPrincipal`;
2. the kernel-derived `PeerIdentity` of the connected stream;
3. the `ProcfsPeerAttestor` or reviewed trusted-path source used at admission;
4. an opaque pidfd-backed `AttestedPeer` retaining the admitted process.

The constructor refreshes process start time, UID, GID, cgroup v2 path, systemd
unit, and executable digest, creates the private principal/mechanism binding, and
installs the bounded `DeterministicLocalRuntime` internally. It accepts no
`PageRuntime`, callback backend, thread handle, generic type parameter, or
caller-written mechanism identity.

The product crate does not export `PrincipalBinding`, `MechanismIdentity`,
`PageRuntime`, `RequestControl`, `RuntimeReply`, or a raw session event type. It
does not implement `BrowserRequestHandler`, expose an ordinary `handle`, create a
listener, or define an installable binary.

## Per-request authority

Every authority-changing product operation enters through `handle_attested`:

1. reject an expired absolute deadline before identity work;
2. refresh the same admitted identity source;
3. compare all mechanism facts to the private binding;
4. mint one non-cloneable request custody owner from the `AttestedPeer`;
5. propagate only its verifier through internal runtime controls and callbacks;
6. verify current custody at runtime/effect boundaries;
7. verify again before releasing a terminal success;
8. on post-dispatch revocation, retire the runtime and classify possible effects
   as indeterminate;
9. drop the custody owner on normal return or unwind.

A peer tuple, copied runtime snapshot, semantic principal, caller-written digest,
or ordinary `BrowserActor` holder cannot invoke an alternate dispatch path.

## State-ingress boundary

The product wrapper exports no `SessionEvent`, `TransitionError`, or
`apply_session_event`. This prevents an ordinary caller from synthesizing human
focus release, IME completion, navigation completion/failure, modal closure,
capability resolution, recovery, or session closure outside the attested request
path. Human and IME exclusion therefore cannot be cleared before a later
attested navigation by mutating the actor directly.

The public cancellation helpers are revocation-only: they may cancel or observe
one in-flight request but cannot grant Agent control or mark an operation
successful. `principal` and `page_owner` return bounded observations.
`receipt_observer` records lifecycle facts and never authorizes execution.

## Implementation crate: `hepta-browser-actor-simulation`

The unpublished implementation-internal crate retains the generic runtime,
state machine, callback bridge, deterministic fixtures, fault injection, and
hostile test corpus. Repository validation permits only the product wrapper to
depend on it directly. Its compatibility APIs and raw state-machine methods are
not product entry points and cannot be wired directly into AgentPort.

## Internal runtime and completion

The actor-owned local runtime receives an internal `RequestControl` carrying the
same absolute deadline, shared cancellation token, and request peer verifier.
Queue admission is not execution. Callback loss, panic, timeout, duplicate
completion, or peer revocation cannot be converted into success. Ambiguous
cleanup poisons and retires the runtime pair. Semantic page action remains a
single runtime-owned resolve-and-act hook and the local fixture defaults closed.

A later Servo product adapter must be introduced as a distinct concrete reviewed
type. It must preserve the same custody and completion invariants and must not
reopen a public generic runtime injection point.

## Receipt lifecycle

Requested, dispatched, and terminal facts may be written to the S05 durable
journal. Journal recovery and export do not authorize execution. Interrupted
potential external effects become indeterminate and are never automatically
replayed. Storage or publication uncertainty requires inspection/recovery before
reuse.

## Negative guarantees

The S06 gate rejects:

- a product actor parameterized by a caller runtime or constructor accepting a runtime value;
- public `PageRuntime`, `RequestControl`, `PrincipalBinding`, or mechanism facts;
- public raw session events or an unauthenticated session-state mutator;
- ordinary `BrowserRequestHandler` or `handle` dispatch;
- dependencies on the simulation crate outside the product wrapper;
- actor-owned TCP/Unix listeners, spawned product workers, or automatic binaries;
- optional attestation/custody or a receipt journal that authorizes work.

Compile-fail doctests prove that weak binding types, generic runtime injection,
ordinary handler use, and raw session-state synthesis are unavailable. Python
surface tests and the complete Rust simulation corpus enforce the same boundary.

## Rollback and claim ceiling

Revert the bounded S06 merge before any Servo/runtime successor. The slice adds
no listener, installed service, state migration, external HTTPS authority,
physical hardware evidence, signing, publication, or release authority. A green
exact-source and live prospective-merge gate proves only the reviewed source/test
API on its exact S05 parent.
