# hepta-browser-codec

Product Rust implementation of the TrillionniumOS Desktop Browser API v1
canonical message boundary.

The crate owns bounded UTF-8 JSON parsing, recursive duplicate-member
rejection, signed-64-bit integer enforcement, sorted-key canonical encoding,
strict request/response shapes, session-generation binding, typed navigation
and semantic-reference validation, effect classification, and canonical
SHA-256 evidence inputs.

It deliberately does **not** create a listener, dispatch a BrowserActor, start
Servo, grant a capability, or authorize an external effect. The current source
has passed the repository's static cross-contract audit, the 27-vector
independent reference, and the recorded Rust 1.93 host validation. Exact-head
CI must rerun after every source or contract change; no listener or dispatch
claim follows from these checks.
