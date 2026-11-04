# Actual original seed lifecycle: first-signal retirement

The once-only original seed test actually passed on `main`, job
`1a1a3cb8614-96a-7761`. The original process status is succeeded, exit 0,
output complete, with neither timeout nor cancellation. The exact selected
test reports **1 passed, 0 failed, 0 ignored, 27 filtered**. The prior failed
installed Root startup at `/var/lib/trill/o1103n1` remains a separate failure.

This execution used a fresh `/var/lib/trill/s1103as1` prefix, the actual
product-linux App Server from Hepta
`857d8f61b96453c06a7f93dfba79dcdebca31bf8`, and the original Desktop seed test
from `92a06c4b4b041a9e94d83480bc2c4cdcd6afa3d2`. The latter links the unchanged
`a39a0871d9601ffccb5e0d95d8f39d54b3a63360` original library. These mixed
component identities are retained explicitly. They are not a qualified new
joint product pair.

## What actually completed

The selected test calls the original `Product::create` and seed construction,
uses the real App Server Start/Resume path, closes the original client, and
lets the original `ChildOwner` send its first termination signal. The existing
**10,000 ms child termination bound was not changed**. The recorded 14,360 ms
is the entire create operation, including work before child termination; it
is not a 14-second child exit allowance.

The durable [observation](prefix-evidence/admin/seed-lifecycle-observation.json)
records seed creation returning, retirement of its socket and detachment of
the fresh mount. It binds the actual App Server SHA256
`fd1fed2f97e218f77d6a3d682579d1681785e93de72781419684d849bd278254`.
The original authority state remained absent, and no Session or turn was
submitted by this fixture.

All three commands returned zero: root-owned component staging, the exact
original seed test in a private mount namespace, and a read-only postmortem
of the new prefix. [The complete final result](result.json) is 13,296 bytes,
SHA256 `f87224b2f64d7899bb02f9d72c1c743d4c44769f99cba7257b9cdd9815319f2b`.
[Original test stdout](actual-original-seed-test.stdout.log) retains the exact
libtest summary; its stderr was empty.

## Evidence and remaining acceptance

[The source index](source-index.json) binds 18 result, transport,
status, small-output, derived metadata and explicitly labelled operational-input files by size
and SHA256. Root independently read the final result, checked the six complete
small-file payloads against their original RPC bytes and receipt hashes, and
checked the authoritative original process status. The additional complete job
stdout/stderr were extracted by the owner reviewer before the tool-session reset;
Root checked their hashes and exact byte counts against the original status.
Their original RPC wrapper is not available in this archive. The
[private-source index](private-source-index.json) is explicitly derived metadata.
The build and its complete
41-member archive are [recorded separately](../original-appserver-signal-component/README.md).

The initialization material is not copied into this public archive. The
postmortem output embeds that material and is retained on the execution host;
its recorded digest does not assert that its private bytes are published here.
The index identifies all such remote-only inputs explicitly.

This closes the observed seed component lifecycle gate. A canonical joint
Desktop/Hepta build, installed Root composition, authenticated user submission,
real Notes or Calculator action, independent application readback, original
writer durable terminal and reconnect/restart reconciliation still require
their own actual receipts. `production_qualified` remains false.
