# Isolated signal runtime r2

This is a new, unexecuted runtime revision. The r1 source, a01 prepared images,
run nonce, original failed receipt and exact cleanup evidence are unchanged.
The complete candidate native build and full host suite already passed under
their recorded source and executable identities. Android signal behavior is
still unqualified until a new private-cell run completes its four cases.

## Observed failure

On a01, Android reported boot completion, Android 17/SDK 37, one system_server
start, stopped adbd and the correct new engine hash. The initial strict epoch
capture raised `FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING`. No probe was
installed or run. All four private services and the original private init were
confirmed gone; Main retained its exact epoch. The original controller remains
recorded failed with MainPID 0 and no remaining cgroup. Its memory.max counter
was 59202 with zero OOM counters; a causal connection is not established.

The old helper did not preserve the role census. The retained boot log tails do
not identify which role was missing or ambiguous. Transient zygote descendants,
argv shape, permissions and a framework restart remain hypotheses, not findings.

## Changes and invariant boundaries

`framework_census.py` adds diagnostics restricted to the owned private daemon
cgroup. It does not replace or modify the pinned framework guard. The runtime
allows at most 30 seconds of read-only initial readiness observations for its
single missing/ambiguous-role error. It preserves each error and fixes the first
strictly verified epoch before package operations. It never reacquires an epoch
after a case starts or retries an instrumentation invocation.

The existing actual host-suite qualification remains bound to the complete
frozen r1 wrapper manifest, the identical host parser and 3793-registration
contract. The new Android-only source manifest has a separate identity. This
avoids claiming the prior host execution used code which did not yet exist.

No native engine/probe source, Main target, resource budget, security setting,
original v5 startup function or cleanup function changes in this revision.

## Local controls

`verify_census_local.py` reads actual bounded local files and owned child `/proc`
records, including an oversized command line and a reaped child. The executor's
mounted procfs uses outer namespace PIDs, so the control reads the visible PID
from `/proc/self/stat` and obtains the child's visible PID from that exact
owned child. It never guesses that `getpid()` indexes the mounted procfs.

The readiness tests explicitly inject a fake clock, census and guard. They
exercise bounded waiting, original error retention, no retries for other
failures, changed Main/init identity, late success rejection and refusal after
probe operations. They are control logic evidence, not Android execution.

The original admission/loader controls and host parser controls are rerun
locally. No new complete native host suite or Android run is claimed here.

Independent parent review and a fresh owned device attempt are required next.
