# BrowserActor authority boundary

## Purpose

S06 introduces the request owner that translates a validated Browser API request into one bounded runtime operation while preserving session, cancellation, peer-custody, and receipt invariants. The security objective is not merely to offer a safer helper: the weaker dispatch path must be absent from the product-facing type system.

## Crate split

### `hepta-browser-actor`

This is the only product-facing API. It exports a narrow `BrowserActor<R>` wrapper, runtime data/traits needed by adapters, and non-authorizing state/cancellation/receipt helpers.

It does not export:

- `PrincipalBinding`;
- `MechanismIdentity`;
- an ordinary `BrowserRequestHandler` implementation;
- an ordinary `handle` method;
- a constructor accepting caller-written mechanism facts;
- a listener or installable binary.

### `hepta-browser-actor-simulation`

This unpublished implementation crate retains the complete mechanism and hostile regression corpus. It contains compatibility APIs needed by its internal tests, but repository policy permits only the product wrapper to depend on it directly. It is neither an application nor an authority that may be wired into AgentPort.

The split preserves deep testing without allowing a simulation convenience path to become the product call path.

## Construction protocol

`BrowserActor::from_attested` requires:

1. a `TaskFlowPrincipal` selected by higher policy;
2. the kernel-derived `PeerIdentity` for the connected stream;
3. an opaque `AttestedPeer` that owns the admitted process pidfd;
4. the `ProcfsPeerAttestor` or reviewed trusted-path source used at admission;
5. a bounded `PageRuntime` adapter.

The constructor refreshes the attested process and binds PID, UID, GID, process start time, cgroup v2 path, systemd unit, and executable digest. A mismatch or unreadable source fails construction. The binding stays private inside the wrapper.

## Per-request protocol

Every request enters through `handle_attested`:

1. reject an expired absolute deadline before identity work;
2. refresh the same admitted identity source;
3. compare all mechanism facts to the private binding;
4. mint one non-cloneable request custody owner from the `AttestedPeer`;
5. propagate only its verifier through `RequestControl` and engine callbacks;
6. verify current custody at runtime/effect boundaries;
7. verify again before releasing a terminal success;
8. on post-dispatch revocation, retire the runtime and classify possible effects as indeterminate;
9. drop the custody owner on normal return or unwind.

A peer tuple alone, a copied runtime snapshot, a caller-written executable digest, or a semantic principal cannot invoke the product actor.

## Session and human control

The actor owns one logical page and uses `hepta-session-core` for:

- Agent observation versus mutation control;
- human focus and bounded leases;
- IME composition exclusion;
- navigation/modal/capability/cancellation phases;
- generation and semantic-reference invalidation;
- fail-closed revision exhaustion.

State transitions occur before success effects are emitted. Cancellation does not claim rollback of an operation that may already have crossed an effect boundary.

## Engine-thread completion

A runtime adapter receives a `RequestControl` with the same absolute deadline, shared cancellation token, and peer verifier. Queue admission is not execution. Callback loss, panic, timeout, duplicate completion, or peer revocation cannot be converted into durable success. Ambiguous cleanup poisons and retires the runtime pair.

## Receipt lifecycle

A receipt observer may record requested, dispatched, and terminal facts. It cannot authorize execution. Interrupted potential external effects are reconciled to indeterminate and are never automatically replayed. Storage uncertainty requires recovery before reuse.

## Negative guarantees

The S06 gate rejects:

- any direct repository dependency on the simulation crate except the wrapper;
- reintroduction of `PrincipalBinding`, `MechanismIdentity`, `new`, ordinary `handle`, or `BrowserRequestHandler` on the product wrapper;
- workspace/source-state drift;
- actor-owned TCP/Unix listeners or automatic binaries;
- contract fields that make attestation/custody optional;
- a receipt journal that authorizes or automatically replays work.

Compile-fail doctests additionally prove that the weak binding types are not importable and that the wrapper does not satisfy `BrowserRequestHandler`.

## Rollback

Revert the bounded S06 commit before any Servo/runtime successor. The slice adds no listener, installed service, state migration, or external effect. Existing S05 receipt data remains readable because no receipt format is changed.

## Evidence and claim ceiling

Exact-source and prospective-merge jobs separately verify repository truth, the complete locked Rust graph, hostile Python tests, simulation unit tests, and product compile-fail documentation. Success proves only a source/test API in which attested request custody is structurally mandatory. It does not prove product activation, Servo execution, installed-image integration, physical hardware, HSM custody, publication, or release readiness.
