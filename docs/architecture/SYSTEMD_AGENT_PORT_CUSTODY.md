# systemd AgentPort custody

**Checkpoint:** `D0C-05`  
**Status:** source candidate; product activation remains closed

## Boundary

`hepta-agent-portd` is a one-connection mechanism service. It never calls
`bind(2)` or `listen(2)`. systemd owns the only allowed socket:

```text
/run/hepta/browserd/agent.sock
AF_UNIX / SOCK_STREAM
hepta-browserd:hepta-agent / 0660
```

The socket uses `Accept=yes`; each accepted stream starts one short-lived
`hepta-browserd-agent@.service`. The process authenticates and dispatches one
request through the already host-validated D0C-02/D0C-03/D0C-04 stack, emits a
request-bound mechanism result, and exits. There is no multi-request hidden
control channel.

## Default-disabled activation

Two independent gates prevent package installation from becoming a listener:

1. the system preset is exactly `disable hepta-browserd-agent.socket`;
2. the socket unit requires `/etc/hepta/enable-agent-port`.

The marker is not present in the repository, tmpfiles definitions, Debian
install map, image inputs, or any generated product artifact in this stage.
Creating it is an explicit later product decision that requires D1 QEMU/PID 1
evidence and a current threat review.

## Peer identity

The socket group is only the first admission boundary. For every accepted
connection the service verifies:

- kernel `SO_PEERCRED` PID, UID, and GID;
- a pidfd held through the complete request;
- uniform real/effective/saved/filesystem UID and GID in bounded procfs data;
- the process start-time field before and after policy evaluation;
- exactly one safe unified cgroup-v2 entry;
- exact unit `hepta-agent.service` and cgroup path
  `/system.slice/hepta-agent.service`.

UID/GID numbers are resolved from the package-created account names at runtime;
no distribution-specific numeric allocation is embedded in the protocol.

## Service sandbox

The connection service runs as `hepta-browserd`, with only the `hepta-agent`
supplementary group needed to receive the stream. It has:

- no ambient or bounding capabilities;
- `NoNewPrivileges=yes`;
- a private network namespace and only `AF_UNIX`;
- strict filesystem, device, namespace, kernel, personality, and W^X controls;
- a 25-second process lifetime ceiling;
- `Restart=no`.

Procfs remains visible because the service must compare the peer process to
its kernel socket identity. Access is read-only and each procfs file has a
strict byte limit.

## Current claim ceiling

This checkpoint does not provide:

- an enabled listener;
- an Agent semantic principal or TaskFlow mapping;
- BrowserActor dispatch;
- Servo or a visible page;
- capability permits;
- external navigation or effect authority.

D0C-05 is complete at source/host level only after the exact branch passes the
static custody audit, systemd unit verification, Rust 1.93 formatting, Clippy,
workspace tests, and both daemon self-checks. Actual socket activation is a D1
QEMU gate, not a host-source gate.
