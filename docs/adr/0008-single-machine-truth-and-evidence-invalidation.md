# ADR 0008: Single machine project truth and evidence invalidation

**Status:** Accepted by plan revision `2026-08-29-d6`

## Context

Plan indexes, README, current-state text, build constants, documentation
manifests, and repository manifests previously carried independent status
claims. Candidate, squash-merged, and exact-main evidence could therefore drift
or be interpreted as equivalent.

## Decision

`manifests/project-state.v1.json` is the primary project-status source and
`manifests/gates.v1.json` is the primary package/evidence registry. Human
summaries and build-info constants are validated against them.

Every gate declares invalidation paths and exact evidence identities. Candidate
head, tested merge, base, and integrated-main commits are distinct.

## Consequences

- truth changes require atomic machine and human updates;
- CI fails on cross-file drift or mutable action refs;
- evidence can become stale after transitive input changes;
- a source manifest does not attempt to contain its own commit SHA; CI evidence
  binds source/tree/workflow/input/output identities;
- historical evidence remains provenance but cannot silently promote current
  main.
