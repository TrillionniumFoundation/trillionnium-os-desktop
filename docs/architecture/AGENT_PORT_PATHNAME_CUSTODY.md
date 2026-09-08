# AgentPort filesystem-path custody

The product and development AgentPort sockets are created by systemd and pass an
already-accepted `AF_UNIX/SOCK_STREAM` descriptor to a short-lived browser
mechanism process. The browser mechanism must not be able to resolve or mutate
the listener pathname.

## Effective ownership

```text
directory: /run/hepta/browserd
owner:     root
group:     hepta-agent-socket
mode:      0750

socket inode owner: hepta-browserd
socket inode group: hepta-agent
socket mode:        0660
```

The existing socket inode identity is retained for D1 evidence compatibility.
Pathname custody is established by the parent directory: `hepta-agent` is
explicitly enrolled in the dedicated `hepta-agent-socket` traversal group,
while `hepta-browserd` is not. Owning the inner socket inode does not grant
search or write authority over its root-owned parent path.

The product service also clears inherited `ReadWritePaths` and mounts the
socket directory read-only. The development service may write only
`/var/lib/hepta-browserd/development`; the socket directory and reviewed Agent
executable are read-only inside its mount namespace.

## Packaging boundary

The production package installs the product socket/service drop-ins. The
development socket, service, binaries, and their drop-ins remain outside the
production install map and require an explicitly selected development profile.

## Evidence and claim ceiling

`tools/validate_agent_port_path_custody.py` merges the base units with ordered
drop-ins, checks list-reset semantics, verifies tmpfiles/sysusers and the Debian
install map, and emits bounded deterministic source-policy evidence.

A passing source gate proves only the checked-in effective unit policy. It does
not prove a booted PID 1 configuration, repository governance, independent
review, a live Agent connection, BrowserActor/Servo dispatch, external effects,
hardware qualification, signing, or release readiness. D1/D2I must exercise
the same parent-directory custody in the exact image.
