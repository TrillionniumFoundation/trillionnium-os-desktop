# Fixed reader for the completed observation after the search rejection

This candidate reads historical evidence from the completed readonly inspection
`inspect-after-search-rejection-01`. It does not observe the live target, execute
Android commands, or authorize a new action. The failed two-step case and its
original UNKNOWN remain unchanged.

## Actual evidence bound before preparation

The root agent collected the authoritative terminal for job
`1a1b285c279-fc05-7e67`: succeeded, exit 0, complete and durable, no timeout,
cancellation, retry, stderr, truncation or log error. The exact 733-byte terminal
is embedded, not presented as a new controller query. Its SHA-256 is
`b314bd6a3cc8304d5d00038ece8f811e88bacadf0df09798c87cb42e613a5ede`.

The original parent stdout is 13,961 bytes with SHA-256
`50890b7a1c8a591f493a1af26606da2279f5b3c0cc1e7a893b19b77d200c0401`.
Unlike the earlier inspection's submission, this execution has one stdout line
and no stage line. The reader reconstructs that exact line from the pinned
13,706-byte joint artifact, SHA-256
`9eab29efce2bf0506e9b5c3dfb7282859e8310a4235f9885c108ecc546f93665`,
and checks the full original stdout hash. This is explicitly deterministic
reconstruction from the actual artifact, not a claim to reread the controller.

The actual owned child was PID 2010422. The held pidfd recorded its normal exit 0,
was closed, and the parent's descriptors were restored. Its 10,677-byte stdout
and the 5,752-byte original adapter stdout are independently hash bound.

The original adapter result is 6,362 bytes, SHA-256
`8abc17cc8fb4983792f1ec09270abd8eaeb29d56f80ea3a1fe2c76dcba523b4d`.
It reports no action attempted or unknown outcome for this readonly observation,
no secondary errors, restored accessibility state, the unchanged task 878 and
helper UID 10157/APK identity, and matching before/after Beike MainActivity scope
with historical window token `2dfbb60`. None of these statements clear the prior
failed case's UNKNOWN.

The inspection nonce is `d4be175e3d9f09f49cac2f7ac9dd7fc2`; its exact wire hash is
`36174e091c45db20baf2c192ecc677abc52b6565d7c68b25ff50b5b8ec0f0aaa`.
The plan remains readonly and has distinct before, inspect and after nonces.

## Finite reader and unchanged checks

The source is a metadata-only derivative of the previously executed
`inspect878_reader_r1/read_completed_inspect878.py`, 27,620 bytes, SHA-256
`f068d9907ba9fe4bc5f22ca76a273156c6f1e39d7e19927ddc157eada4122272`.
`SOURCE_DIFF.patch` records every difference. The six utility, bootstrap, census
and node-projection functions are byte identical. The remaining function differs
only in the explicit actual size/PID/window literals and the truthful no-stage
stdout reconstruction label. The pure original QA contract is unchanged.

The same 21-file closed set contains five pinned sources, scope, launch scope,
plan, joint and step result, plus the exact step intent, held binding, inspection
request/assessment, four command-005 files and three transport-006 files. Paths
are selected by literal closed names, not by scanning other steps. There is no
read of user files, other flows, installed APK contents, or other UI windows.

The original raw inspection is reparsed with `qa.parse_completed`, including
the exact request nonce, UID and successful instrumentation finish. Its saved
assessment and full wire/tree/node hashes must match. The recorded command must
have the exact instrumentation argv, seven authority descriptors, original owned
parent PID, environment and classpaths; successful joined command and matching
transport/post-guard receipts are required. This validates historical receipts;
the reader does not instantiate a runtime binding or enter a namespace.

Every file is read through the unchanged no-follow, bounded root-file reader,
then its full bytes and stat are rechecked. Whole-process FD identities before
and after must match. The fixed file total is at most 4 MiB, the internal deadline
90 seconds, the process deadline 120 seconds and stdout at most 1 MiB. Excess
output fails; no output is silently truncated. There are no subprocesses,
signals, Main locks, native commands, instrumentation, file writes, grants,
installs, cleanup, focus changes or retries in this reader.

## Privacy and meaning

**Successful stdout contains private UI node text and must stay out of Git.**
It includes all original visible, non-password, unredacted nodes, original string
truncation flags and hashes. Invisible or password nodes are omitted and counted.
Originally truncated fields are not exact-selector candidates. The reader writes
no bundle and does not alter existing evidence or permissions.

The result is a read of a completed observation. It provides no current action
authority and publishes no reconciliation. Any later partial-case proof must
still be separately reviewed against the actual node evidence, failed action's
full protocol, current held runtime/App/helper/task identity and original Flow
and fresh foreground/window/tree guards. This candidate does not implement that
producer or claim a verified business postcondition.

## Local preparation and single execution boundary

`prepare_packet.py` ran only locally. It hash checked the executed source and
actual parent/child/adapter/terminal/plan bytes, round-tripped the original parent
and joint representation with Python integer precision, compiled the candidate,
and asserted that the run-function changes are exactly the declared actual
metadata replacements. All new output files use exclusive create, fsync and
readback. Original files were not changed. Its raw stdout and empty stderr are
retained alongside `LOCAL_PACKET_PROOF.json`; no private UI was read locally.

The fixed request invokes `sudo -n /usr/bin/python3 -I -B -c <exact source>` with
no stdin, CPU 100%, 256 MiB memory and 120 seconds. Its new idempotency key is
`pocket4-beike-inspect-after-search-rejection-fixed-reader-r1-20261106`.
Only the root agent may submit it after review. The candidate has not been
submitted by this agent. Acceptance requires the actual complete private stdout
and durable terminal, not source review or local preparation alone.
