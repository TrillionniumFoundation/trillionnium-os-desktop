# hepta-browser-codec

**Work package:** S03 / D0C-03  
**Claim ceiling:** canonical Browser API v1 parsing, validation, encoding,
hashing, and effect classification only. No listener, principal mapping,
authorization, BrowserActor, Servo dispatch, network permission, or external
effect authority.

## Responsibilities

The codec is the first layer allowed to interpret authenticated payload bytes.
It owns:

- bounded UTF-8 JSON parsing;
- recursive duplicate-member rejection;
- signed 64-bit integer-only JSON;
- exact request and response shapes with unknown-field refusal;
- paired session identity and layered semantic-reference validation;
- typed navigation and action validation;
- deterministic canonical encoding and SHA-256 publication;
- effect classification without authorization.

## Canonical byte contract

Accepted input must already equal the codec's canonical re-encoding. The codec
does not normalize attacker-selected whitespace, key order, duplicate keys,
number spelling, escapes, or trailing bytes and then accept the normalized
result.

The public `JsonValue` encoder and the decoder apply the same maximum message,
nesting, aggregate-item, generic-string, and object-key budgets. Typed fields
apply their own narrower UTF-8 byte limits. The machine-readable limits live in
`contracts/browser-codec-resource-limits.v1.json`.

## URL boundary

The codec recognizes only two URL classes:

- external HTTPS-shaped targets;
- local HTTP fixtures whose host is `localhost`, `127.0.0.1`, or `::1`.

It rejects userinfo, control characters, backslashes, malformed bracketed IPv6,
zone identifiers, empty ports, ports above 65535, and ambiguous authorities.
This remains shape validation. DNS answers, redirects, TLS identity, connected
peer addresses, proxy bypass, credentials, and network policy belong to the
controlled-egress layer.

## Session and reference binding

All operations except `health` and `session_create` require paired `session_id`
and non-zero `session_generation`. An element reference additionally requires a
non-zero document generation and a published semantic snapshot revision of at
least one. `browser-wire.v1.schema.json` records the wire-envelope tightening;
the Rust codec remains the executable authority for canonical bytes and UTF-8
byte limits.

## Effect classification

Observation, local interaction, and potential external effect are mechanism
classes. Navigation, click, type, press, and select are potential effects.
Classification never grants permission and never makes retry safe. A caller
must preserve an indeterminate result and must not blindly replay an operation
that may already have executed.

## Dependencies and build boundary

The crate depends only on exact `sha2=0.10.9`. Cargo binary auto-discovery and
package build scripts are disabled. It must not depend on transport listeners,
AgentPort, BrowserActor, Servo, systemd, policy, storage, update, or release
code.

## Verification

```bash
python3 tools/browser_codec_reference.py --self-test \
  --contract contracts/browser-codec.v1.json
python3 tools/validate_rust_browser_codec.py
python3 -m unittest tests.test_validate_rust_browser_codec -v
cargo fmt --all --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
```

The Python reference is an independent standard-library implementation. Golden
wire examples must round-trip byte-for-byte. Tests cover malformed Unicode,
integers, nesting, item budgets, generic key/string budgets, URL authority
parity, session binding, stale references, error retry binding, and response
shape.

## Versioning

Canonical v1 bytes are stable. Adding a field or enum variant, changing a bound,
accepted URL grammar, number representation, error retry meaning, or operation
risk class requires a new compatible proof or a new protocol version. Unknown
fields and unknown variants are rejected; they are never mapped to a nearby
known value.

## Evidence status

The checked-in historical Rust host result remains provenance for its recorded
source only. A changed codec tree requires exact-head Rust and reference runs,
fresh independent review, protected merge, and exact-main rerun before its
machine state may be promoted. Source or hosted CI does not prove a listener,
browser runtime, installed image, hardware, signing custody, or release.
