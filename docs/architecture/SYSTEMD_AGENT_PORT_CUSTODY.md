# systemd AgentPort custody

The product socket is disabled by preset and additionally requires the absent
marker `/etc/hepta/enable-agent-port`. It uses a bounded backlog and connection
count with `Accept=yes`, launching one short-lived process per inherited stream.

The service has no capabilities, a private network namespace, `AF_UNIX` only,
strict filesystem/device/kernel restrictions, W^X enforcement, a 25-second
lifetime ceiling, and no restart. It authenticates the peer mechanism and then
fails closed because BrowserActor is not connected.

Source checks and `systemd-analyze verify` do not prove a booted listener. S10 must
show default-disabled behavior, exact effective units, authorized and unauthorized
peer cases, teardown, kill/recovery, and final-image absence of activation markers
and fixture binaries.
