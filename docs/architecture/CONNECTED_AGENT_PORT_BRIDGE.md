# Connected AgentPort bridge

Status: **D0C-04 executable reference complete; Rust bridge pending**

## Boundary

```text
one already-connected AF_UNIX stream
  -> peer credential and nonce-bound transport
  -> one canonical Browser API request
  -> one typed handler invocation
  -> request-bound canonical response
  -> one transport response frame
```

This layer does not create a filesystem socket, accept a second request,
identify a TaskFlow principal, grant a capability or call a BrowserActor. Its
input is an already-connected stream supplied by a later custody layer.

## Exactly-one dispatch

Each connection carries at most one request frame. The bridge validates peer
credentials, nonce, sequence, digest and canonical Browser API semantics before
calling the handler. Duplicate members, noncanonical bytes and malformed
session bindings fail before the invocation counter is incremented.

The dispatch context contains only mechanism facts:

- peer PID/UID/GID;
- transport sequence;
- canonical request SHA-256;
- operation effect class;
- acceptance monotonic timestamp;
- effective monotonic deadline.

## Response authority

The handler may author only an object result or a normative typed error. It may
not author protocol, request ID, session ID, session generation, transport
sequence or connection nonce. Those fields are copied from the validated
request and connection state, then passed through the canonical response
codec.

## Deadline and interruption

The effective deadline is the earlier of the server ceiling and the request's
wall-clock deadline converted once at connection acceptance. A handler result
that returns after this deadline is discarded and never committed to the
wire. The bridge does not infer success from a late or missing response.

## Effect ceiling

The reference fixture returns `policy_denied` for every
`potential_external_effect`. It never grants authority or automatically retries.
The effect class is evidence passed to a future policy/TaskFlow boundary; it is
not a browser-side permission decision.

## Current claim ceiling

A standard-library socketpair reference exercises the complete connected path
and thirteen fault/identity/binding assertions. This is not a Rust product
bridge, listener, BrowserActor, Servo integration or external-effect proof.
