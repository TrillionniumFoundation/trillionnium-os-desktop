# Audio: preserve the real Error Prone provider

The strict r5 Audio graph retained `systemfeatures-errorprone-tests` while its
existing source projection removed `error_prone_test_helpers` from the already
materialized Error Prone source. The full build failed on that real dependency.

This six-file patch preserves the complete original provider in Audio mode.
The other target routes retain their previous scope. It adds the one original
Jimfs project required by the helper, at the official superproject Gitlink,
with its complete `jimfs` source cone. All previous 316 project revisions and
cones remain unchanged; the normal source lock now contains 317 projects.
The consumer, transitive dependencies and strict missing-dependency behavior
are preserved. There are no stub providers or allow-missing switches.

The normal tools compiled with locked, offline Cargo and passed 17 source
tests plus 30 Audio tests. The additional checks reproduce the old removal,
retain the actual consumer edge, reject wrong provider bytes/commits and an
incomplete source cone, preserve the other routes and verify restoration.
Historical source-extension tests reconstruct their exact earlier lock.

The subsequent normal source continuation passed all ten commands, including
the real reconcile, independent materialized-source verification and clean
recipe check. The reconcile may retrieve exact pinned objects from the normal
partial clone; the independent after-verification disables lazy fetching.
Its projection, children, unit and work locks retired successfully.

`source-reconciliation.json` contains the actual immutable result pins.
The before/after public source inventories bind the patch, and `FILES.json`
binds every file in this capsule. The complete APEX build, artifact checks
and Android runtime acceptance remain separate, unpassed release gates.
