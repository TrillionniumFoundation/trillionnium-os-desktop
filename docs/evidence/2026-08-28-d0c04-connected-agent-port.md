# D0C-04 connected AgentPort bridge evidence

**Date:** 2026-08-28  
**Claim:** source/host validation on `UnixStream::pair()` only

Implemented one authenticated, canonical request-to-handler-to-response path.
Host tests prove exact request/session response binding, canonical request and
response digests, one dispatch, typed refusal of a potential external effect,
duplicate-key rejection before handler invocation, and refusal to commit a
handler result after the effective deadline.

No filesystem socket, systemd unit, production service identity, multi-request
loop, Servo runtime, window, network navigation or external effect exists in
this checkpoint. The next D0C slice owns socket activation, unit/cgroup binding,
backpressure, cancellation and BrowserActor command conversion.
