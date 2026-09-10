# hepta-agent-transport

**Work package:** S04 / D0C-02  
**Claim ceiling:** authenticated, bounded transport over an already-connected
`AF_UNIX/SOCK_STREAM`; no listener, semantic principal, BrowserActor, Servo,
capability, external effect, installed-image, hardware, signing, or release claim.

## Boundary and production API

The public `ClientConnection` and `ServerConnection` facades own connection
synchronization. Raw framing, `Frame`, `FrameKind`, session-nonce values,
`NonceSource`, and deterministic nonce fixtures live in the private `wire` module
and are not re-exported. The only public server admission path obtains a fresh
256-bit nonce from the operating system entropy source.

The transport authenticates kernel PID/UID/GID, binds payload bytes with SHA-256,
enforces a fixed 88-byte header, limits payloads to 256 KiB, and requires strictly
increasing request sequences from one. Mechanism identity fields remain available
to the attestation layer, but all public `Debug`, `Display`, and unauthorized-peer
error text is redacted.

## Fail-stop semantics

Local preflight failures that emit and consume no bytes do not poison the
connection. Once any wire, digest, nonce, kind, sequence, EOF, or deadline error
occurs, the facade drops the private carrier. Every later operation fails locally
without additional I/O. The transport never scans for a new magic value and never
attempts stream resynchronization.

One absolute monotonic deadline covers the entire frame. Partial progress cannot
extend it. Sequence exhaustion is explicit and never wraps.

## Security and logging

Peer credentials are a mechanism identity only. Service/cgroup/executable custody
belongs to `hepta-peer-attestation`; semantic authority belongs to a later policy
layer. Logs must not contain payload bodies, secrets, credentials, page content,
raw nonces, PID, UID, or GID. Record only bounded error class and redacted
connection state.

## Verification

```bash
python3 tools/validate_s04_transport_custody.py
python3 -m unittest tests.test_s04_transport_custody -v
python3 -m unittest discover -s tests/transport -p 'test_*.py' -v
cargo test --locked -p hepta-agent-transport
cargo clippy --locked -p hepta-agent-transport --all-targets -- -D warnings
```

Changes to header layout, nonce, sequence, deadline, payload bound, digest, public
API, error formatting, or poison behavior require a protocol/security review and
new exact-head golden/reference evidence.
