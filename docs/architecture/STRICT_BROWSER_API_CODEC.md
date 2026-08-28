# Strict Browser API codec

**Checkpoint:** `TOS-D0C-03`

Transport payloads are decoded by `hepta-browser-codec` before any BrowserActor
dispatch. The decoder rejects duplicate object keys recursively, unknown fields,
oversized messages and any byte sequence that does not equal the canonical
serialization of its typed value. The canonical SHA-256, not attacker-selected
raw formatting, is the receipt input.

The request model binds protocol, request identity, optional session identity,
session generation, bounded timeout and a typed method payload. Every operation
except `session.create` requires a non-zero session generation. Navigation only
accepts credential-free HTTP(S) URLs; `javascript:`, `data:`, `file:` and other
schemes fail before dispatch. Element references carry document and semantic
snapshot revisions plus lowercase SHA-256 fingerprints.

Click, type, press and select are classified as `PotentialExternalEffect`; only
scroll remains `LocalInteraction`. This classification is a routing input, not
proof that a page action is harmless. External mutation remains disabled until
the network/effect boundary is active.

Responses require either an object result for success or a strict typed error
for failure, never both or neither. The codec does not start a listener, own a
Servo object or decide policy.
