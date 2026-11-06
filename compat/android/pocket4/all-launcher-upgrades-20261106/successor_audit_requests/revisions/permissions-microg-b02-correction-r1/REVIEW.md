# Independent microG b02 output-budget correction

This candidate is **source only**. It has not run on Pocket4. The root coordinator
must review and submit the one exact packet; this directory contains no ledger
claim or remote-execution code. Original permission batch 02 remains FAILED and
its serial gate remains STOP.

## Actual original failure

Job `1a1b2be17ec-fc05-7f8b` has a complete, durable failed terminal. Its second
command was the already approved `cmd package dump-package com.google.android.gms`.
The owned client recorded `CHILD_OUTPUT_BOUND` after 22,991,578 ns. It saved exactly
262,145 bytes of stdout, the original 256 KiB limit plus one byte. Both EOF flags
are false, the command returned -9 after the owned-process-group termination,
and the client was joined. The saved stream is an incomplete prefix. The field
`stream_artifacts_complete=true` only means that prefix and the empty captured
stderr were saved; it does not mean the service finished its output.

The original worker copied `termination_attempted` to `host_timed_out`, so the
original transport labeled this failure `HOST_COMMAND_TIMEOUT`. That label is
retained in every original receipt. The measured cause is the output bound,
not expiration of the command's time budget. AppOps was not executed. The
before-scope check completed, but there is no final scope check; the failed
batch cannot be described as a complete before/after 47-package observation.

Resource closure is separate from query completeness: the worker closed all
7,137 observation FDs and 20 lease FDs, released the action lock and held target,
and restored its 5→5 descriptor count. The owned observation child exited
normally with code 1, its original held pidfd observed exit and closed, and the
parent restored its descriptors. No Main process was killed by this local
analysis or by the new candidate preparation.

## Fixed adjustment

The exact three Android command vectors remain unchanged:

| Sequence | Command | stdout limit | stderr limit |
|---|---|---:|---:|
| 1 | `cmd package help` | 262,144 B | 262,144 B |
| 2 | `cmd package dump-package com.google.android.gms` | 2,097,152 B | 262,144 B |
| 3 | `cmd appops get --user 0 com.google.android.gms` | 262,144 B | 262,144 B |

Only sequence 2's exact command suffix can select the larger stdout budget.
The held runner checks that suffix again before launching. Every actual command
and intent records its two stream limits. The source and owned success gate
require the exact three-limit array and exact command suffixes. No other package,
command or stream gets a larger allowance. At a bound breach the original
owned-group stop, join, pipe close and incomplete-result algorithm remains in
place. It still captures no more than the selected limit plus one diagnostic byte.

The 30-second host call, 25-second Android timeout, 900-second worker budget,
1,100-second outer job, 1 GiB memory limit, CPU quota and nice value all remain
unchanged. The largest additional buffer is about 1.75 MiB for one stdout
stream. Captured service bodies stay in root-owned private output files, outside
public JSON. The existing core private writer already accepts up to 8 MiB;
its algorithm and bound are not changed. Public worker and owned-envelope bounds
remain unchanged because they contain only stream pins, not service bodies.

The full 47-package before/after/current scope, every-command runtime guard,
fixed native CLI/daemon/UID1000 path, current 45-component native catalog,
held namespace and classpaths, Meituan saved-location equality, Bili UNKNOWN
preservation, original action/flow locks and owned libffi/pidfd lifecycle remain.
The transport is byte-for-byte identical. Its original error-name mapping is
also preserved. This is a capture repair, so the output still claims no interpreted
grant, AppOps semantics, role, business readiness or cleanup eligibility.

## Failure lineage and new source closure

The new private source stage includes the exact original b02 worker artifact,
outer stdout, authoritative terminal and STOP record. The worker verifies their
bytes and failure/partial-stream/retirement semantics before observing Main and
again before successful completion. It reports the original failed job and pins,
not a replacement result for that job. New request, source root, output root,
schemas and idempotency key make the independent correction explicit.

Nine staged files total 159,121 bytes of exact JSON input, within the original
262,144-byte stage limit. The original O_EXCL/no-follow/root-private stage
algorithm is retained. The scope is still only microG as the permission target,
with all 47 packages serving as current identity guard scope. There is no new
dumpsys interface, ADB, shell, permission grant, App launch, UI action or install.

Successful capture must still be settled from the **full owned outer stdout and
authoritative durable terminal**, including each original child and all stream
receipts. Only then can a separately reviewed local linkage connect this
independent correction to the original later permission batches. This candidate
does not advance or rewrite the original ledger.

## Local controls

Four controls passed, no skips, with FD count 4→4. They check the actual original
failed evidence and run four self-owned local Python writers: 300 KiB stdout
fits the fixed new budget; the original cap still rejects that size; 2 MiB+1
stdout and 256 KiB+1 stderr still reject and join. A different target is rejected
before spawning. These are local buffer/lifecycle controls, not Android queries
or proof that microG's next actual dump will fit.

All original transport bytes and all original owned-lifetime definitions except
the result gate are exact. Only worker `held_bounded_child`, `validate_request`,
`run` and result schema in `main` change; the two added functions fix the exact
failure lineage and three-command stream-budget selection. Full diffs and
source pins are included. The assembler is reproducible and refuses to overwrite
any different existing candidate file.
