# Canonical Browser API codec boundary

Status: **D0C-03 executable reference and current source audit; recorded Rust
host evidence is stale; no dispatch**

## Position in the request path

```text
bounded authenticated transport frame
  -> canonical Browser API decoder
  -> typed, session-bound request
  -> effect classification
  -> later BrowserActor dispatch
```

The transport treats the payload as opaque bytes. This boundary is the first
layer allowed to interpret Browser API semantics. It does not open a socket,
select an Agent principal, authorize an effect or call Servo.

## Canonical wire

The decoder accepts only UTF-8 JSON that is already in canonical form:

- no BOM or trailing newline;
- no insignificant whitespace outside strings;
- recursively unique object members;
- lexicographically sorted object keys;
- compact `,` and `:` separators;
- integers only, with booleans never accepted as integers;
- no floating-point or non-finite values;
- maximum 256 KiB, nesting depth 32 and aggregate container item count 20,000;
- input bytes must equal the typed value's canonical re-encoding.

The canonical byte string, not attacker-selected formatting, is the input to
SHA-256 receipt binding.

## Session and generation binding

`health` and `session_create` are unbound. Every other operation carries both
`session_id` and a non-zero `session_generation`; either both fields are
present or neither is present. Response session fields obey the same paired
rule.

Semantic element references additionally require a non-zero document
generation and a published semantic snapshot revision of at least one. The
original broad schema remains the operation-shape source, while
`browser-wire.v1.schema.json` and `browser-codec.v1.json` add these product
wire invariants.

## Effect classification

The codec reports mechanism classes; it does not authorize them:

- observation: health, snapshot, observe, wait and extract;
- local interaction: session create/close and scroll;
- potential external effect: every navigation and click/type/press/select.

Navigation is deliberately not described as read-only. It can make network
requests, carry cookies, trigger redirects and change remote state.

## URL boundary

External navigation is credential-free HTTPS at the codec boundary. URL
userinfo and control characters are rejected. The local fixture target is
limited to loopback HTTP hosts. Network namespaces, resolver/redirect/peer-IP
checks and the external-effect barrier remain later layers.

## Response integrity

A successful response contains exactly one object result and no error. A failed
response contains exactly one typed error and no result. Error retry text must
match the normative code in `contracts/error-codes.v1.json`; an intermediary
cannot weaken `never_automatic` or invent a retry policy.

## Current implementation ceiling

The checked-in Python standard-library reference and 27-vector corpus provide
an executable second implementation of the contract. A recorded Rust 1.93
host-validation baseline passed format, Clippy, workspace tests and browserd
self-check, but it is bound to the historical source commit
`4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb` and is marked `STALE_EVIDENCE` for
the current candidate. The generated source audit is refreshed for each tree;
an exact-head CI run and independent promotion are required before merge
readiness can be claimed. This remains a no-listener, no-transport-dispatch
checkpoint: BrowserActor conversion, Servo dispatch and external effects are
not demonstrated here.
