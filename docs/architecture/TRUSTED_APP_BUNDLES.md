# Signed trusted applications and synthetic origins

## Status and claim boundary

This package is a D5 source candidate blocked by D4. It provides a deterministic
offline reference verifier. It does not create an HTTPS origin, launch a
browser, install a production publisher key, access a production signing key,
partition browser storage, run a service worker, distribute revocations, or
assert release readiness.

## Bundle identity

A trusted application is identified by:

- an application identifier;
- a monotonically increasing positive version;
- publisher and publisher-key identifiers;
- an exact signed content root;
- a synthetic origin derived as
  `https://<app-id>.<publisher-id>.apps.hepta.invalid`.

The `.invalid` suffix is deliberate: the origin must be resolved by the product
runtime and must never be resolved through external DNS.

The active payload is `trillionnium.desktop.trusted-app-manifest.v2`. Both
identity fields are distinct lowercase DNS labels of 1..63 ASCII bytes, matching
`DnsLabel` and `TrustedAppIdentity` in the Rust contract. A serialized origin has
no trailing slash; a root URL is constructed separately. Publisher IDs are not
omitted, concatenated into an ambiguous label, or normalized from dotted names.

The earlier app-only `.trusted.invalid` v1 prototype is rejected, not aliased.
No installed v1 product is claimed. Historical evidence remains bound to its
original source/contract; fixtures must be rebuilt and resigned as v2. Publisher
key rotation preserves the publisher ID and origin; publisher identity changes
require a separate application identity and storage authorization.

`contracts/golden/trusted-app-origins.v1.tsv` is consumed by the Python verifier,
Rust browser contracts, and Rust D5 policy tests. See ADR 0005 for migration and
claim ceilings. This correction does not install an origin or grant authority.

## Offline signature verification

The manifest is encoded as canonical UTF-8 JSON with sorted object keys,
compact separators, and one trailing newline. The `signature` member is removed
before Ed25519 verification. The reference verifier contains a dependency-free
RFC 8032 implementation and validates itself against the published RFC vector.

The fixture signing helper is test-only. Its existence is not evidence of
production key custody.

## Content root and path custody

Every signed file record binds path, byte length, SHA-256, and media type. The
content root is a domain-separated binary Merkle tree over entries sorted by
canonical path. The verifier rejects:

- absolute and non-canonical paths;
- `.` or `..` traversal;
- backslashes and NUL bytes;
- duplicate normalized paths;
- symbolic links and non-regular files;
- missing, extra, oversized, or digest-mismatched content.

The entrypoint must be signed HTML or XHTML content.

## Content Security Policy

D5 uses an exact, closed directive set. Scripts, styles, fonts, workers, and
manifest data are self-only; network connections, media, objects, frames, base
URL changes, and form submissions are disabled. Wildcards, external origins,
unsafe evaluation, and inline script authority are rejected even when the
bundle is correctly signed.

A valid publisher signature authenticates the publisher's bytes. It does not
make an unsafe policy acceptable.

## Storage and service workers

Storage is partitioned by application and publisher identity. A version upgrade
may preserve that partition, but an older version cannot reopen a state created
by a newer accepted version.

Service workers are disabled by default. When enabled by a signed manifest, the
script must itself be signed bundle content, the scope must remain within the
synthetic origin, network fetch is disabled, and the only update source is a
new signed bundle.

## Revocation and anti-downgrade

Verification requires an offline revocation snapshot whose generation and
expiry include the qualification time. Revocation epochs cannot move backward
relative to installed state. A revoked publisher key or exact manifest digest
is rejected.

The installed state records the highest accepted version and exact content
root. Lower versions are rejected. Re-verifying the same version is idempotent
only when content root and publisher key are unchanged.

## Publisher-key rotation

Changing publisher keys requires a canonical transition statement signed by
the currently installed, still-active predecessor key. The transition binds:

- predecessor and successor key identifiers;
- SHA-256 of the successor public key;
- minimum version authorized for the transition.

A revoked predecessor cannot authorize a new transition. The new bundle is
also signed by the successor key, so both continuity and possession are proven.

## Visible trust indicator

Successful offline verification creates a hash-bound indicator containing the
application, version, publisher, key, content root, synthetic origin,
revocation epoch, and trust state. Any change to the visible values invalidates
the indicator receipt.

The later product integration must render these values in compositor-owned
trusted chrome and bind them to the same PageOwner and exact loaded content.

## Required integration evidence

After D4 is independently merged and qualified, a D5 runtime package must
prove, on an exact integrated image:

- internal synthetic HTTPS origin routing without external DNS;
- compositor-owned trust indicators distinct from untrusted content;
- storage and service-worker partition enforcement;
- offline install, upgrade, rotation, revocation, and rollback behavior;
- malformed and malicious signed-bundle rejection;
- production signing and release custody through independent identities;
- exact-main and fixed-hardware evidence at the later required tiers.
