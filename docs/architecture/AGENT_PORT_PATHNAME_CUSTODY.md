# AgentPort pathname custody

systemd owns `/run/hepta/browserd/agent.sock`. The socket inode remains
`hepta-browserd:hepta-agent` mode `0660`, but its parent directory is
`root:hepta-agent-socket` mode `0750`. Only the Agent client joins the traversal
group; the browser mechanism does not.

The accepted descriptor is inherited. A service drop-in clears explicit
supplementary groups and writable paths, then exposes `/run/hepta/browserd`
read-only. Consequently the connection process cannot unlink, replace, rename, or
rebind the listener path. The production package installs only product drop-ins
and never a development socket or fixture binary.

This is source policy until a booted PID-1 image proves effective merged unit
properties, account memberships, path ownership, activation-negative behavior,
and kill/recovery. QEMU evidence is S10 and physical hardware remains S12.


## Claim ceiling

This document proves source-level local mechanism constraints only. It does not prove a semantic principal, capability authorization, BrowserActor, Servo execution, an installed image, physical hardware, signing custody, publication, or release.
