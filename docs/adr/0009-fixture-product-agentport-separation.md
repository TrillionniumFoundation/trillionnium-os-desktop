# ADR 0009: Physical separation of fixture and product AgentPort handlers

**Status:** Accepted direction; implementation required before D3

## Context

The D0 AgentPort mechanism uses a fail-closed fixture handler for health and
contract testing. A packaged product daemon must not appear operational while
silently substituting that fixture for BrowserActor.

## Decision

Fixture and product activation paths are separate binaries or compile-time
graphs:

- fixture handlers are available only to tests and qualification images;
- the production daemon refuses readiness without a real reviewed BrowserActor
  binding;
- release validation rejects fixture handler symbols/dependencies and test
  activation markers;
- development and qualification profiles are explicit and machine recorded;
- production remains default-disabled until its own gate.

## Consequences

D0 host tests may continue to use connected pairs and fixture binaries, but D3
cannot promote an AgentPort product claim until fixture/product separation and
semantic-principal binding pass.
