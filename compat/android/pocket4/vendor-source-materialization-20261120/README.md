# Pocket4 source materialization repairs

This source successor addresses two independent defects discovered while
continuing the Linux-hosted Android build.

| Repair | Current validation | Scope |
| --- | --- | --- |
| Committed `eol=crlf` with unspecified `text` | 29 real-Git controls | Exact checkout representation, without changing source bytes |
| Required tracked-file presence after materialization | Complete 2,351-file workspace; 100 Rust cases | Missing required files can no longer hide behind clean Git status |

`crlf/` contains the original and revised bookend helper, complete tests,
the exact observed libopus fixture, and the actual test evidence. `rust/`
contains a single-file patch bound to the complete current runtime source,
its full parent inventory and independent replay/build/test drivers.
`validation/` retains the complete-workspace host result and verified readback
manifest. GitHub CI reconstructs the parent from the unchanged original
archive, verifies the successor tree, and runs fresh affected-crate tests.

The original runtime packet and its 19 release binaries retain their original
tree and qualification. This successor does not claim new release binaries,
an Android boot, app acceptance, installation or production readiness.

## Operational restoration

The first new host restoration used the repaired CRLF helper with the original
651-project plan, original lock identities and bounded resource contract.
It stopped during its complete preimage scan before dispatching any restore
or reconcile command: a separate cleanup terminal was deleting the active
AOSP working copies while keeping their `.git` directories. In CTS alone,
9,607 files that the scan had just read were subsequently absent. The original
index, HEAD, source manifest and lock bodies were unchanged.

That exact deletion terminal was closed, and its original PIDs, unit and cgroup
were independently observed retired. A new complete loss census and a new
bounded restoration generation are required; the earlier 2,822-missing-file
catalog is retained as history. The failed preimage is not a successful source
bookend, and neither source-level repair transfers credit to host restoration.

User data and rollback images are outside this source-repair scope. No runtime
activation or deletion of the existing installed Android is performed here.
