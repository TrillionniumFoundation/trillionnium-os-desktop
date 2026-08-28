# ADR 0001: This repository is the full product repository

- Status: Accepted
- Date: 2026-08-28
- Plan: `2026-08-28-d5`

## Decision

`TrillionniumFoundation/trillionnium-os-desktop` contains the canonical product
code, contracts, manifests, tests, packaging, documentation, and evidence.
There is no separately named implementation checkout and no local absolute path
that acts as a second source of truth.

## Consequences

Plan and implementation changes are reviewed and versioned together. Build and
release identities use repository commit and artifact digests. Historical local
staging paths are provenance only.
