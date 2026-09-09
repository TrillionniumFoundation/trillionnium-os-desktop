# Authenticated fail-stop Agent transport

The S04 transport accepts an already-connected Unix stream. It does not bind a
path or own listener lifecycle. Kernel PID/UID/GID authentication precedes a fresh
256-bit challenge nonce. Each 88-byte-header frame binds protocol version, kind,
sequence, bounded length, nonce, and SHA-256 payload digest.

The public connection facade owns synchronization. Oversized local payloads and
zero local timeouts fail before I/O and leave the stream usable. Any error after
wire I/O begins permanently poisons the public connection and drops the private
carrier. Resynchronization is forbidden.

A single absolute monotonic deadline covers header and payload. Repeated partial
progress cannot renew it. The carrier treats payloads as opaque; canonical Browser
semantics and effect classification belong to the higher codec/AgentPort layers.

Passing source and host tests proves neither systemd activation nor semantic
principal, BrowserActor, Servo, installed image, or external-effect authority.
