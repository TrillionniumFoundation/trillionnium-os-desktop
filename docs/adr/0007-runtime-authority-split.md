# ADR 0007: Session, capability, build, and update authority are split

- Status: Accepted
- Date: 2026-08-28

## Decision

The d4 concept of one `hepta-osd` owning lifecycle, capability brokering, image
generation, update, and recovery is decomposed. Runtime session supervision,
per-capability services, build-time image generation, and privileged update
transactions are separate components with minimal interfaces and credentials.
