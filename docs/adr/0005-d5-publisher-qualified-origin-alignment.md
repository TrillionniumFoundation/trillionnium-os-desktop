# ADR 0005: Align D5 identity with the accepted publisher-qualified origin

- Status: Source candidate; independent security review required
- Date: 2026-09-05
- Plan: 2026-08-29-d6
- Authority: no runtime, installation, publisher enrollment, or release promotion

## Decision

Preserve ADR 0004 and the integrated Rust `TrustedAppIdentity` definition.
The canonical tuple-origin serialization is
`https://<app-id>.<publisher-id>.apps.hepta.invalid`, without a trailing slash.
Each variable is a separate lowercase DNS label of 1..63 ASCII bytes. Dots,
uppercase, Unicode, leading/trailing hyphens, and normalization are rejected.
The shell origin remains independent and unchanged.

D5's prior app-only `.trusted.invalid` namespace could not represent publisher
isolation consistently with browser contracts and the docs manifest. Correct
the Python D5 verifier and compiled Rust D5 policy to use the integrated origin.
The Rust policy delegates to `TrustedAppIdentity`, rather than duplicating it.

## Compatibility

Bump the signed D5 manifest payload to `trillionnium.desktop.trusted-app-manifest.v2`
and the Rust publisher-evidence subject to `trusted-app-manifest.v2`. Reject old
v1 payloads and app-only origins; never accept them as aliases. Historical v1
fixtures and evidence remain interpretable only against their original pinned
source/contract. No installed v1 product or automated state migration is claimed.
New fixtures use DNS-label identities and are regenerated and signed as v2.

A publisher key rotation under one publisher ID does not change origin. A
publisher-ID change is a new app identity, not a key rotation; no implicit
storage transfer or service-worker reuse is authorized. Root URLs append `/`
only after canonical origin comparison; the serialized origin itself never does.

## Verification and invalidation

The shared `contracts/golden/trusted-app-origins.v1.tsv` vectors cover same-app
cross-publisher isolation, 63/64-byte boundaries, separators, control bytes,
Unicode/lookalikes, and invalid edges. They run in the Python D5 suite and both
Rust browser-contract and browserd policy integration tests. Signed hostile
fixtures reject foreign publishers, legacy namespaces, trailing slashes, and v1
schema identities even when the fixture signature is valid.

Changes invalidate D5 source evidence and downstream app/capability/effect
consumer evidence. Exact-head and post-merge exact-main remain separate. This
ADR does not claim internal DNS routing, TLS, CSP/storage/service-worker runtime,
production publisher keys, installed applications, hardware, or release closure.
