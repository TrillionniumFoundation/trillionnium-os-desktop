# ordinary14 ACK reconciliation reader

One read-only UID 1000 metadata scan under the fixed worker jobs root. It
matches the approved ordinary14 executable, exact arguments, cwd, empty env
and four resource fields. Only matching metadata admits fixed stdin.bin;
its 35,263 bytes and SHA are externally bound.

Bounds: 4,096 entries, 131,072 bytes per request, 32 MiB total input, eight
matching tuples, 64 KiB output and a checked ten-second monotonic deadline.
The separate tool timeout is 30 seconds. Output contains only matching job
IDs, identities/digests, safe counts and fixed error codes. No unrelated
argv, environment, stdin or job IDs are emitted. Production has no writes,
children, tests, namespaces, Android actions or task resubmissions.

The worker request file has no original idempotency key. A stored execution
tuple plus matching stdin identifies a job for Root to reconcile. Zero
matches means only NOT_FOUND_AT_OBSERVATION and cannot authorize replay.
Partial scans remain explicit. No task or lifecycle qualification is claimed.

Nineteen local parser/owned-temporary-file controls passed. Their JOBS/UID
seams exist only in the test module, not as production CLI options. They
never read the real worker jobs root or executed ordinary14.
