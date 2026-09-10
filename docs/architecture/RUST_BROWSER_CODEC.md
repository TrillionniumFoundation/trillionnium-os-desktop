# Rust Browser API codec

**Checkpoint:** `TOS-D0C-03`  
**Product crate:** `crates/hepta-browser-codec`  
**Candidate status:** exact-head qualification required; no listener or dispatch.

## Boundary

Authenticated transport hands opaque payload bytes to this crate. No caller may
interpret or dispatch a Browser operation before `decode_request` succeeds.
The codec never binds a socket, selects a principal, grants a capability, calls
Servo, or authorizes an effect.

## Ordered validation

The decoder performs:

1. total byte, UTF-8, and BOM checks;
2. bounded integer-only JSON parsing;
3. recursive duplicate-member, depth, item, generic key, and string checks;
4. exact typed conversion with unknown-field refusal;
5. session, reference, URL, operation, and error-policy validation;
6. sorted-key compact canonical re-encoding;
7. byte-for-byte equality with the received payload;
8. canonical SHA-256 publication.

The encoder applies the same generic depth, item, key, string, and total-byte
budgets to programmatically constructed values. This prevents an internal
caller from bypassing parser resource limits by constructing a deep or wide
`JsonValue` directly.

## Contract layering

`browser-api.v1.schema.json` defines operation shapes. `browser-wire.v1.schema.json`
defines envelope/session rules and tightens semantic element references to a
published snapshot revision. `browser-codec-resource-limits.v1.json` records
UTF-8 byte budgets that standard JSON Schema cannot express directly.
`browser-codec.v1.json` binds the operation-schema Git blob identity and the
executable codec policy.

## URL parity

The Rust and Python implementations use deliberately isomorphic authority
rules. Tests cover canonical schemes, case-insensitive `localhost`, IPv4/IPv6
loopback, optional decimal ports, query/fragment forms, userinfo, backslashes,
empty or oversized ports, zone identifiers, malformed IPv6, and private-LAN
rejection.

These checks do not establish DNS, TLS, redirects, connected peer identity, or
network permission.

## Evidence and promotion

The current tree regenerates the independent 27-vector Python result and static
source audit deterministically. The historical Rust 1.93 host result remains
bound to its original source commit and is explicitly stale for changed source.
A candidate becomes eligible for review only after exact-head format, check,
Clippy, workspace tests, browserd self-check, reference regeneration, and static
audit pass. Protected merge and exact-main rerun remain separate requirements.

No source or hosted-CI result proves BrowserActor, Servo execution, an installed
image, hardware, signing custody, or release readiness.
