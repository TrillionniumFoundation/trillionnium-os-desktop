# systemd AgentPort custody

**Checkpoint:** `TOS-D0C-05`

## Default state

The Debian package may install `hepta-browserd-agent.socket` and
`hepta-browserd-agent@.service`, but the socket preset is `disable` and the unit
also requires `/etc/hepta/enable-agent-port`. That marker is not shipped by the
repository or an install manifest. Unit presence therefore is not a listener or
product-availability claim.

The marker may be created only after the headed Servo lifecycle, BrowserActor
command bridge, receipt persistence and recovery gates explicitly authorize the
local AgentPort. Removing the marker and stopping the socket removes the runtime
socket path.

## Socket custody

The only address is `/run/hepta/browserd/agent.sock`. systemd owns creation and
removal. The socket is `0660`, owned by `hepta-browserd:hepta-agent`, and its
parent directory is `0750`. It is an `AF_UNIX/SOCK_STREAM`; the service network
namespace is private and its address-family allowlist contains only `AF_UNIX`.
No TCP, abstract namespace or public-network fallback exists.

`Accept=yes` starts one short-lived `hepta-browserd-agent@.service` per accepted
connection. The inherited stream is descriptor zero through
`StandardInput=socket`. The service verifies that the inherited socket's local
pathname is the locked path before reading any request.

## Runtime client identity

Group access to the path is necessary but not sufficient. The service resolves
the dedicated `hepta-agent` user and group, obtains kernel PID/UID/GID from
`SO_PEERCRED`, opens a pidfd, and reads the peer's bounded procfs status, stat
and cgroup records twice. It requires:

- uniform real/effective/saved/filesystem UID and GID;
- equality with the socket peer credentials and expected service account;
- a stable process start-time value;
- the exact unified cgroup-v2 path `/system.slice/hepta-agent.service`;
- the exact systemd unit `hepta-agent.service`;
- a live pidfd before and after attestation and after request service.

This closes the obvious “any process sharing the UID can connect” gap for the
locked system-service profile. It does not replace the kernel, systemd or LSM as
an authority source and does not prove the semantic identity of a model.

## Per-connection service

`hepta-agent-portd` performs one D0 request and exits. Until a Servo BrowserActor
is active, its handler returns the truthful typed error
`browser.runtime_unavailable`; it does not simulate navigation or success. The
wire binding, canonical request/response hashes and peer runtime evidence are
logged to the journal, while durable receipt persistence remains a later gate.

The service has no capabilities, no writable product filesystem, a private
network namespace, only `AF_UNIX`, no new privileges, a closed device policy,
strict system protection and a 25-second runtime ceiling. It cannot restart
itself.

## Qualification boundary

Host tests cover procfs parsing, identity drift, cgroup and unit mismatch,
pidfd liveness, account lookup and the complete connected-stream self-check.
Static custody validation covers the units, preset, sysusers, tmpfiles and
install map. Actual socket activation under Debian PID 1 is a D1/QEMU evidence
gate and is not claimed by this checkpoint.
