# Connected AgentPort bridge

**Checkpoint:** `TOS-D0C-04`

`hepta-browser-agent-port` composes the authenticated AF_UNIX carrier and the
strict canonical Browser API codec. It accepts an already-connected stream and
serves exactly one request. It does not bind a path, create a listener, own a
Servo object, or decide whether an external effect is allowed.

The bridge verifies peer credentials, completes the per-connection nonce
exchange, receives one bounded sequence-bound frame and decodes one canonical
typed request. A `DispatchContext` exposes the kernel peer identity, transport
sequence, canonical request digest, effect class and effective deadline to a
typed handler. The handler returns only a JSON object or a typed Browser API
error; it cannot author protocol, request ID or session binding fields. The
bridge copies those fields from the validated request and hashes the canonical
response for later receipt persistence.

The effective deadline is the earlier of the server ceiling and the request
window measured from connection acceptance. A synchronous handler cannot yet be
preempted, but a result returned after the deadline is not committed to the
wire. Process isolation and cancellation remain BrowserActor/runtime work.

Malformed or noncanonical requests close the connected stream before dispatch.
The D0 fixture handler refuses `PotentialExternalEffect`; the bridge itself only
classifies and transports this fact so that policy remains outside the carrier.
