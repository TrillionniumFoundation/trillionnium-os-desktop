# ADR 0006 — Distinct D6 permit v2 and transactional source decisions

Status: proposed source-candidate decision; independent review and exact-head
validation required. Plan: `2026-08-29-d6`. No product gate is promoted.

## Context

The retained `capability-permit.v1.schema.json` defines a string subject, issuer,
single operation, Unix-millisecond timestamps, policy revision, and a different
signature shape. The D6 reference used the same schema identifier for an object
with issuer/key IDs, a structured mechanism/semantic subject, actions, second-
based timestamps, use counts, constraints, and a distinct signature object.
Those are different wire protocols, not interchangeable examples.

## Decision and compatibility

Give D6 the explicit `trillionnium.desktop.capability-permit.v2` identifier and
`contracts/capability-permit.v2.schema.json`. Keep the v1 schema unchanged for
historical interpretation. Update the source reference and Rust verifier subject
in the same candidate. Reject v1 rather than auto-converting subjects, time units,
or signatures. No installed product migration or production credentials exist
in this package, and no historical evidence is relabeled as v2 evidence.

The schema specifies exact top-level/subject/signature fields and portal resource
shapes. Runtime identity, byte bounds, canonicalization, signature verification,
expiry, revocation, DNS/proxy/connected-peer policy and use accounting remain
semantic checks. A schema or signature alone never grants authority.

## Failure semantics

Reject boolean-as-integer and silent URL parser normalization. Parse source JSON
under fixed byte limits with recursive duplicate-member and non-finite rejection.
Commit source decisions under one lock, compute all receipt hashes/copies before
publishing counters, reject duplicate/unused authorities, and leave the ledger
unchanged on failure. Source receipt verification refuses an external-effect
claim even if its hash has been recomputed.

## Validation and residual work

Run the full Python discovery, the D6 suite, schema consistency tests, repository
and truth validators, and locked Rust default/all-feature checks. The local
source tests cannot prove installed networking, durable permit consumption,
real peer observations, issuer custody, or cross-language runtime interoperability.
Those remain D6 integration and independent-review requirements.
