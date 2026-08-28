# D0C-02 authenticated UDS carrier evidence

**Date:** 2026-08-28  
**Claim:** source/host validation only

Implemented:

- kernel peer-credential extraction and exact/UID peer policies;
- fresh 256-bit server challenge nonce;
- fixed, versioned, length-bounded binary framing;
- SHA-256 payload binding;
- strict request sequence and replay rejection;
- one absolute operation deadline across header and payload;
- browserd self-check integration without creating a listener.

Validated by workspace unit tests and `hepta-browserd --self-check`. Tests use
only local `UnixStream::pair()` channels. No socket path, systemd unit, Servo
engine, external URL, credential or web side effect is created.

Remaining before `AgentPort` activation: dedicated service UIDs, socket
activation/path custody, unit/cgroup identity binding, strict browser-message
codec, TaskFlow principal mapping and crash/reconnect integration.
