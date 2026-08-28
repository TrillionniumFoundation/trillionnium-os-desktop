# hepta-agent-transport

D0C-02 authenticated bounded AF_UNIX carrier core.

The crate accepts an already-connected `UnixStream`; it does not bind a socket
path or start a production listener. It verifies peer PID/UID/GID, establishes a
fresh 256-bit session nonce, enforces strictly increasing request sequences,
bounds payloads to 256 KiB, binds payloads with SHA-256, and applies one absolute
deadline to each complete frame.

Production listener lifecycle, systemd socket activation, dedicated service
identities, cgroup/unit binding, and policy-to-TaskFlow identity mapping remain
explicit later gates.
