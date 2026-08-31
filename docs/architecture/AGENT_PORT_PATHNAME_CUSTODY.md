# AgentPort filesystem-path custody

The product and development AgentPort sockets are created by systemd and pass an
already-accepted `AF_UNIX/SOCK_STREAM` descriptor to a short-lived browser
mechanism process. The browser mechanism must not own or mutate the listener
pathname.

## Effective ownership

The effective product and development socket configuration is:

```text
directory: /run/hepta/browserd
owner:     root
group:     hepta-agent-socket
mode:      0750

socket owner: root
socket group: hepta-agent-socket
socket mode:  0660
```

`hepta-agent` is enrolled in the dedicated client group. `hepta-browserd` is
not. The browser mechanism receives the accepted descriptor through
`StandardInput=socket`; it does not need directory write access.

The product connection service has no writable path beneath
`/run/hepta/browserd`. The development service may write only
`/var/lib/hepta-browserd/development`; the socket directory and reviewed Agent
executable are read-only inside its mount namespace.

## Packaging boundary

The production package installs the product socket/service drop-ins. The
development socket, service, binaries, and their drop-ins remain outside the
production install map and require an explicitly selected development profile.

## Evidence and claim ceiling

`tools/validate_agent_port_path_custody.py` merges the base units with their
ordered drop-ins, checks list-reset semantics, verifies tmpfiles/sysusers and
the Debian install map, and emits bounded deterministic source-policy evidence.

A passing source gate proves only the checked-in effective unit policy. It does
not prove a booted PID 1 configuration, repository governance, independent
review, a live Agent connection, BrowserActor/Servo dispatch, external effects,
hardware qualification, signing, or release readiness. D1/D2I must exercise
the same effective units in the exact image.
