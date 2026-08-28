# D0C-05 systemd socket custody evidence

**Date:** 2026-08-28  
**Claim class:** source/host/unit validation; listener remains disabled

Implemented:

- dedicated `hepta-browserd` and `hepta-agent` service identities;
- `/run/hepta/browserd/agent.sock` custody, mode and directory contracts;
- default-disabled systemd socket preset plus a non-shipped enable condition;
- one hardened short-lived service per accepted connection;
- inherited pathname verification before request processing;
- pidfd, procfs UID/GID/start-time and exact cgroup-v2/systemd-unit attestation;
- truthful `browser.runtime_unavailable` handling until BrowserActor exists;
- static unit/install validation and host self-checks.

This checkpoint does not claim that PID 1 started the socket, that the enable
marker exists, that Servo is running, that a BrowserActor accepted a command, or
that any network/web effect occurred. An actual systemd activation trace belongs
to the pinned Debian QEMU lane.
