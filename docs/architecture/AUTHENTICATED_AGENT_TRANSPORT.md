# Authenticated fail-stop Agent transport

**Work package:** S04 / D0C-02  
**Claim ceiling:** authenticated, bounded transport over an already-connected
local Unix stream only. No listener, semantic principal, BrowserActor, Servo,
capability, external effect, installed image, hardware, signing, publication, or
release claim follows from this boundary.

The S04 transport accepts an already-connected Unix stream. It does not bind a
path or own listener lifecycle. Kernel PID/UID/GID authentication precedes a fresh
256-bit challenge nonce. The only public server-admission function obtains that
nonce from operating-system entropy. Raw frames, nonce values, nonce-source traits,
and deterministic nonce fixtures remain in a private wire module.

Each 88-byte-header frame binds protocol version, kind, sequence, bounded length,
nonce, and SHA-256 payload digest. The public connection facade owns
synchronization. Oversized local payloads and zero local timeouts fail before I/O
and leave the stream usable. Any error after wire I/O begins permanently poisons
the public connection and drops the private carrier. Resynchronization is
forbidden.

A single absolute monotonic deadline covers header and payload. Repeated partial
progress cannot renew it. The carrier treats payloads as opaque; canonical Browser
semantics and effect classification belong to higher codec/AgentPort layers.

Mechanism identity fields are supplied to the dedicated attestation layer, but all
public transport `Debug`, `Display`, connection-state, unauthorized-peer, and
AgentPort handler-error formatting is redacted. Raw PID, UID, GID, nonce, payload,
page text, credentials and secrets are never transport log fields.

Passing source and host tests proves neither systemd activation nor semantic
principal, BrowserActor, Servo, installed image, or external-effect authority.
