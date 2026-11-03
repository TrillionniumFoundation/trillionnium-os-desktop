# Unix socket credential snapshot qualification

Frozen22e0 completed the unchanged original pipeline in659.472s: core365
(all126 required), OSTD230 (the original3 TCG skips), allocator20 and MLSDisk15.
The same fresh ordinary ELF passed boot18 and every prior user-space probe,
plus the Linux-referenced credential59 and supplementary-group16 probes.
All expected QEMU/probe exits were33/0, with no timeout, all controlled children
reaped, and every tracked source byte identical before and after execution.

Socket credentials now retain scalar IDs and the immutable original group Arc
from connection/message creation. Later credential changes, exec and exit no
longer change an old SO_PEERCRED, queued SCM_CREDENTIALS or SO_PEERGROUPS result.
The old same-binary15 credential and4 group failures, original Linux output,
first compilation failures, and incomplete MSG_DONTWAIT run are all retained.
Original forged Root/foreign-PID credential denials still pass.

This closes the selected credential lifetime defect. The separate per-call
MSG_DONTWAIT blocking defect remains open. This does not establish complete
Linux socket semantics, general OOM recovery, Root/Host/Session recovery,
native mobile/GPU support or persistent CPU G2. Binary products remain at the
original retained paths/hashes; only text artifacts are published here.
See [all original byte hashes](publication.json),
[source-bound receipt](../socket-credential-22e0.json), and
[module contract](../../../../docs/agents/SOCKET_CREDENTIAL_SNAPSHOTS.md).
