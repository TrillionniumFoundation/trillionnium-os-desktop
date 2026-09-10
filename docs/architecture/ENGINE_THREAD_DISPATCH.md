# Engine-thread dispatch boundary

Status: **S06 source/test candidate; no native Servo or installed runtime**

## Purpose

The internal simulation crate models one bounded in-process request/reply pair
between BrowserActor ownership and an engine-thread owner. It exists to prove
queue, deadline, cancellation, callback, cleanup, and custody semantics before a
real engine adapter is admitted.

## Ownership and limits

`engine_thread_pair` creates one non-cloneable client and one non-`Send`,
non-`Sync` owner. The queue and reply capacity are one. A preflight failure does
not enqueue. Queue-full, abandonment, endpoint loss, deadline, cancellation, or
identity revocation permanently closes the affected pair; a late result cannot
be reused by another request.

## Custody

The product wrapper does not expose this transport or its `PageRuntime` trait.
S06 constructs only an actor-owned deterministic local runtime. Internal
`RequestControl` checks deadline, cancellation and request-scoped peer custody at
bounded points. Future Servo integration must use a distinct concrete reviewed
adapter and preserve the same original request authority across engine entry,
callback completion and terminal response classification.

## Failure and effect semantics

Generic page action is unsupported. Semantic resolve-and-act remains one
runtime-owned atomic hook. A crash or post-dispatch uncertainty cannot be
converted to empty success and a potentially started effect is never
automatically replayed.

## Evidence and claim ceiling

Required source paths are recorded in
`contracts/engine-thread-dispatch.v1.json` and mechanically resolved by
`tests/test_s06_contract_paths.py`. Host tests do not establish Servo, native
event-loop latency, process IPC, installed-image behavior, hardware, signing or
release authority.
