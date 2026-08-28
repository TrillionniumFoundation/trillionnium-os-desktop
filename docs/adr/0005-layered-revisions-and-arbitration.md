# ADR 0005: Layered revisions and explicit Agent/human arbitration

- Status: Accepted and implemented at the pure-core layer
- Date: 2026-08-28

## Decision

Session identity is split into session generation, document generation,
semantic snapshot revision, and mutation epoch. DOM mutation does not globally
invalidate every semantic reference.

Agent/human control uses explicit control states and session phases. Human focus
has a monotonic bounded lease, can interrupt Agent work, and IME composition
owns text input. The queue is bounded and fails closed.
