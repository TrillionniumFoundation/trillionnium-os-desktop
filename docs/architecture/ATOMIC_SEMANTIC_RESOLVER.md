# Atomic semantic resolver boundary

**Gate:** `D3-01`  
**Current evidence tier:** source contract and independent reference  
**Promotion authority:** none

## Threat model

A `page_act` request carries an element reference created from an earlier
semantic snapshot. Its frame identifier, semantic identifier, role, accessible
name, and structural fingerprint are untrusted claims supplied by the caller.
They are not proof that the same node is still present, unique, visible,
enabled, or safe to act on.

Forwarding those fields through the generic BrowserActor `Act` message creates a
time-of-check/time-of-use and retargeting boundary. A navigation, frame swap,
DOM mutation, accessibility-tree update, duplicate semantic identity, or role
change could otherwise redirect the operation to a materially different node.

## Required engine operation

The canonical contract is
[`contracts/semantic-resolver.v1.json`](../../contracts/semantic-resolver.v1.json).
A real engine adapter must execute all of the following as one bounded,
engine-owned operation without yielding to another document or semantic-tree
mutation:

1. bind the request to the current PageOwner session and all four revision
   layers;
2. search only the current frame and current semantic snapshot;
3. require exactly one current node for the semantic identity;
4. compare role, accessible name, and structural fingerprint;
5. retain the resolved engine node rather than retaining caller fields;
6. revalidate PageOwner revisions and retained-node identity immediately before
   action;
7. apply one role-authorized action at most once;
8. advance the mutation epoch and return a typed receipt;
9. return a typed fail-closed error on cancellation, deadline, ambiguity,
   absence, cross-frame fallback, drift, or mutation race.

The adapter must not retry by selecting another candidate and must not fall back
to coordinates, DOM order, accessible name alone, or a generic action path.

## Independent reference

`tools/semantic_resolver_reference.py` is a standard-library-only state model.
It exercises exact revision binding, current-frame uniqueness, structural and
semantic drift, role/action policy, cancellation, deadline, mutation races, and
exactly-once action cardinality. The adversarial corpus is in
`tests/d3/test_semantic_resolver_reference.py`.

The reference intentionally owns no Servo object and performs no external
effect. Its result must remain `PASS_SOURCE_REFERENCE_ONLY`; it cannot set a
BrowserActor, integrated-image, AgentPort, hardware, or release promotion flag.

## Servo promotion requirement

D3 remains blocked until a Servo-owned adapter maps an engine-retained DOM or
accessibility node into this contract and the exact integrated image proves:

- authorized and unauthorized TaskFlow principals;
- PageOwner session/revision binding;
- unique current-frame observation and action;
- ambiguity and drift rejection;
- cancellation and deadline cleanup;
- browser/content crash and recovery;
- requested, dispatched, terminal, indeterminate, and recovered receipt facts;
- production AgentPort still default-disabled.

A passing source/reference workflow is a prerequisite, not a substitute for
that runtime evidence or independent security review.
