# hepta-browser-codec

Strict canonical Browser API request/response codec for D0C-03.

The codec rejects duplicate JSON object keys recursively, unknown fields,
non-canonical encodings, invalid session bindings, unsafe navigation schemes,
stale-shaped semantic references, invalid response result/error combinations,
and messages larger than the transport bound. It does not dispatch Servo or
open a listener.
