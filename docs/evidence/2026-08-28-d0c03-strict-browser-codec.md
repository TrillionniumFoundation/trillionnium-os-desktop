# D0C-03 strict Browser API codec evidence

**Date:** 2026-08-28  
**Claim:** source/host validation only

Implemented recursive duplicate-key rejection, typed deny-unknown-fields
decoding, canonical byte equality, canonical SHA-256, protocol/request/session
binding, bounded timeouts and collections, HTTP(S)-only navigation validation,
revision-bound semantic references, action effect classification, and strict
result/error response shapes.

The test corpus covers canonical round trips, duplicate keys at multiple depths,
whitespace/noncanonical encodings, unknown fields, unsafe URLs, invalid session
bindings, malformed semantic references, effect classification, response shape
and pre-decode size rejection. `hepta-browserd --self-check` invokes both the
transport and codec checks.

No payload is dispatched to Servo, no socket listener is enabled and no external
network or web effect occurs. BrowserActor command conversion and systemd
AgentPort activation remain later checkpoints.
