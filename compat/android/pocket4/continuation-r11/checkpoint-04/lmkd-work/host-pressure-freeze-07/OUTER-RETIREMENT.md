# Revision07 retains final outer resources before the driver exits

Revision06 source and its actual first pressure records remain unchanged. Its
one-shot coordinator failed after the owned driver had successfully retired:
systemd had removed the now-empty unit cgroup before `resource_snapshot()` could
open it. The original coordinator result SHA-256 is
`472fd8bafb8f7c544d697db353f8a004e950e274eb4a6e675f1a69f5165e8473`.
The separate read-only qualifier accepted the pinned scoped pressure evidence,
including both default PSI registrations, a native critical cached-victim kill,
and normal exit of all four nonvictims. That later check did not fill in the
missing final outer counters, so the original invocation remains unqualified.

The revision07 driver writes `outer-final.json` after joining the broker and
reaping the exact owner/init, checking the held domain is empty, and checking
the original domain budget. The driver still occupies its `host` subgroup. It
holds an outer cgroup descriptor, records both outer/domain device and inode,
and confirms root membership is empty, host membership contains only itself,
and the domain is unpopulated. It checks the original five outer limits,
requires all outer max/OOM counters to remain zero, and records current/peak
memory and swap with a monotonic timestamp. The driver result also records
the actual driver PID. A failed resource check prevents a success receipt.

The qualifier now requires the extra immutable file. It binds the record to
the same phase, nonce, driver PID, scoped domain, joined-retirement time and
fixed budgets, and returns its outer identity for external comparison. The
coordinator must compare that identity with the cgroup observed while the
exact service invocation was running and compare the driver PID to terminal
`ExecMainPID`. It still separately requires successful unit exit, exact
invocation cleanup and an unchanged Main epoch. Passing the pure qualifier
does not establish those external fences.

There is no additional keeper process, no service lifetime extension, and no
change to PSI defaults, allocator size, actor code, broker code, the Android
r6 binary, target priorities or resource limits. The next pressure and stale
trials must each use a newly staged cell and matching revision07 binaries.
Revision06 runs cannot be relabeled as revision07 executions.

The local qualification controls add outer OOM/limit/swap rejection, old
generation and remaining-member rejection, and explicit external-identity
handoff coverage. They are synthetic records, not device or PSI evidence.
Matching host compilation, actual pressure, stale-queue behavior, installed
supervisor recovery, cgroup.kill, PID reuse and application qualification
remain separate gates.
