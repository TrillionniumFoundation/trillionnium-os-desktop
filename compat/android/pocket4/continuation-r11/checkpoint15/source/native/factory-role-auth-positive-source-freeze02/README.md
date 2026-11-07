# Owned authorization positive fixture, revision 02

The four production registry/context sources are byte-for-byte revision 01.
Only the owned child command-idle wait changes from 2 to 5 seconds. The last
case intentionally waits 2.05 seconds for a pending lease to expire, and must
keep its subject alive during that interval. All frame waits remain 2 seconds,
the production pending deadline stays 2 seconds, and the whole fixture remains
bounded by its existing 30-second deadline. All ten cases and assertions are
unchanged.

The earlier build01 completed strict compilation and default PLAN only. Its
actual receipt is retained, SHA256
`6ff2ec191bc185de8377bf232494afca17913b7eeac3a55b769e56226a9f7a0e`.
No positive runtime was performed for that build. The source-discovered timeout
conflict is preserved in the preimage and diff; it is not labeled an observed
runtime failure. This new revision is awaiting matching compilation and an
independently admitted root-owned run.

The fixture uses only its own root parent, ten role clients and one nested
child. It exercises the actual PIDFD / SCM_PIDFD registry API through anonymous
socketpairs. It does not start a listener, change namespaces, create a snapshot,
load Android, install production policy, or modify Main. The role-client filter
is fixture-only. All direct and nested children must exit normally and be
reaped, each case must return its descriptors, and any forced cleanup is a
failure. COW child use of the parent's registry and copying a parent's grant
into a fork child are negative controls. No forced PID reuse or shared-VM PID
namespace collision is claimed.
