# hepta-agent-portd

**Work package:** S04 / D0C-05  
**Claim ceiling:** default-disabled, one-connection systemd mechanism service;
no production BrowserActor, decoded request, external effect, installed-image,
hardware, signing, or release claim.

## Product binary

`hepta-agent-portd` accepts only an `AF_UNIX/SOCK_STREAM` inherited on standard
input from systemd. It verifies the filesystem socket path, peer credentials,
pidfd/procfs/cgroup/unit/executable identity, and then fails closed because no
product BrowserActor is connected. It does not call `bind` or `listen`, and it
does not substitute the fixture handler.

The product self-check redacts PID, UID, and GID and confirms no listener,
fixture, BrowserActor, or activation authority.

## Fixture separation

`hepta-agent-port-fixture` is built only with the non-default `fixture` feature.
It is absent from the Debian production install map. The default package graph
contains no BrowserActor, Servo, session store, development daemon, or public
network listener.

## Activation and path custody

The socket preset is disabled and the marker `/etc/hepta/enable-agent-port` is
not shipped. The parent directory is root-owned by the client traversal group;
the browser mechanism is not a member. systemd retains the accepted descriptor,
while the per-connection service receives only read-only path visibility and no
socket-path mutation authority.

## Local checks

```bash
cargo run --locked -p hepta-agent-portd --bin hepta-agent-portd -- --self-check
cargo run --locked -p hepta-agent-portd --features fixture \
  --bin hepta-agent-port-fixture -- --self-check
python3 tools/validate_s04_transport_custody.py
```
