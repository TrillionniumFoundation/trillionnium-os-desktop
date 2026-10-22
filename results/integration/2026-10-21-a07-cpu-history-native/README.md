# A07 CPU history native validation

Rust 1.88.0 executed the exact tree `3ce19d617d52031bbb09813f96ea21f87895641c`
published as PR #229, head `81b88d932cee61c4b693135399dd1e0d6a69c047`.
The 11 CPU history tests passed. The original `cpu-history` service command
passed all 28 tests (1 library, 11 CPU history, 16 actual Linux socket tests),
and all-target Clippy with `-D warnings` passed. The commands used locked,
offline dependencies and one build thread. Source and lock files stayed clean.

The first full-service run reached an execution-environment restriction:
all 16 original socket tests were denied at their fixture's Unix socket bind.
Its complete output is retained. The same command then ran with local socket
permission and passed. No test, source, assertion or feature was changed.

`receipt.json` binds each raw log to its byte length, SHA-256 and deterministic
gzip payload. `python3 verify.py` checks those bytes and recorded test summaries;
it does not rerun Rust tests. The source tree and individual source hashes are
included so the tested implementation can be compared with a later merge.

These are local service results. Original exact-head/current-base A10 CI,
native Hepta owner assembly, real bootstrap authority, durable K-D handoff,
target-kernel recovery and physical device qualification remain separate.
No effect entry or authority was enabled by this evidence-only addition.
