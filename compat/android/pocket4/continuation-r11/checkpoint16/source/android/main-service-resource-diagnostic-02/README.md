# Main systemd policy and kernel resource followup

This source follows the actual limits diagnostic: only `pids.max` differed,
12288 expected from the exact original activation versus 6144 in both kernel
samples. That observation does not explain who or what changed the limit.
The old activation, original failed Amazon02 request, guard, limits and service
are not changed. No new resource baseline or runtime admission is produced.

The same activation SHA and cgroup device 30/inode 26651611 are retained. The
five known limit files plus fixed `pids.current` and `pids.events` are read before
and after exactly one `/usr/bin/systemctl --system show --no-pager` invocation
with the twelve listed property options and fixed `droidloomd.service` operand.
No returned FragmentPath or DropInPaths file is opened. MainPID/InvocationID and
ControlGroup are compared as reported metadata; this is not a complete process
or framework identity recapture. Resource mismatch is data, not collection failure.

The tool is a held current root-owned regular executable, at most 4 MiB. Its
actual full hash and held/named metadata are verified before and after the child;
there is no invented external prior tool hash. Only its FD is passed to the child.
The fixed process has a 5-second deadline and separately bounded 16-KiB stdout
and stderr. Failure preserves the observed prefix and first error. Exact child
PIDFD termination, independent two-second wait, pipe/selector/FD cleanup, and
the later cgroup reads do not substitute success for the first error. The full
collector read deadline is 12 seconds and the outer request timeout is 30 seconds.
Full output is bounded at 2 MiB, with the exact activation bytes in base64.

Draft01 and its three owned-child observations remain retained. Before freezing,
the kill/wait tail was separated so a signal failure cannot skip wait. Four final
local controls exercise the actual capture function with explicitly substituted
local executable/argv/deadline and a signal-error seam: complete output, oversized
output, timeout, and signal error with independent reap. They do not execute the
Main collector. The first local harness had chosen the managed runtime Python,
which is 30 MiB and uid 65534; the production tool gate correctly rejected it
before spawning. This failure is preserved rather than weakening the tool gate.
Final control serialization encountered an already-present old result filename;
all four assertions had completed, and a new result was finalized from the exact
retained progress without rerunning children. Both old files remain unchanged.

Only Root may review and submit the exact request. It has not been submitted by
this agent. No Android/UI, configuration write, service change or limit change is
part of this source.
