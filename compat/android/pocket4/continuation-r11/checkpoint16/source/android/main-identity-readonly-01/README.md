# Original Main identity diagnostic

This candidate is a read-only diagnostic, never an installation or UI admission.
It does not change Main, any cgroup limit, either configuration file, activation,
the original guard, or the original epoch helper. It does not read actor logs.

The exact existing 16,900-byte coordinator source and the existing epoch helper
are loaded only after their original SHA-256 pins pass. No function is replaced
or monkeypatched. The unchanged `main_guard(activation, epoch)` is invoked once.
Its return or first exception and traceback are recorded separately. A resource
mismatch remains an actual guard failure, even when the diagnostic exits zero
because its requested observations are complete. `runtime_authorized` is always
false and no consumer is permitted to use this result as QA admission.

Two independent observations flank that original call. Each checks the three
original activation/verified/cell file SHA pins, the original boot ID, complete
`process_identity` records for four framework roles and three host processes,
and the unchanged helper's `require_unchanged` epoch check. Each also records all
five original cgroup limits and their individual equality results, including
`pids.max`. No comparison is removed or softened. The original source/input FDs
remain held until final named rereads verify full hashes and metadata. The exact
cgroup directory must retain device 30 / inode 26651611.

The scope is the existing original guard's identity contract. It does not
requalify every application, all loaded runtime artifacts, current systemd
properties, or the cause/time of a daemon reload. Reads are sequential, not an
atomic snapshot. No new namespace entry, child process, Android command,
configuration read, service operation, or device file write is introduced.
The prior SHA-pinned helper performs its existing process observation only.

The regular input bound remains 1 MiB, fixed pseudo-file reads are limited to
4 KiB, and output to 1 MiB. The collector checks a 20-second monotonic deadline
around each inherited API call; it cannot interrupt a stuck inherited call.
The existing outer 30-second owned job timeout remains the final runtime bound.
Default execution is PLAN_ONLY. No device collection has been performed for
this package. Only source syntax, original helper AST reuse, exact reference
pins/API shape, retained activation schema and request bindings are checked
locally; this is not synthetic or real-device identity qualification.
