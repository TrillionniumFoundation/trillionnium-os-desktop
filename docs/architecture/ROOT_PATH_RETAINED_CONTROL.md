# Root pathname custody into retained control

This source bridge consumes `RootPathControlConnection` through its existing
`consume_before` callback. The same `OwnedFd`, original `Instant` and unique
`RootControlPathCustody` enter the default live control-owner admission path.
It does not create a socket, policy loader, broker, installed service or principal.

`RootPathAttestedHandoffSender` and `RootPathAttestedHandoffReceiver` expose only
retained handoff operations. They cannot return a bare received stream or an old
non-retained owner that would discard the pathname scope. A private shared
object owns the one non-cloneable root-path custody. The original control
identity owner and action lease retain that object; read-only verifier aliases
cannot mint, replace or reactivate custody. The last private owner drops the
unique custody. Observed path failure latches the original transport scope.

The original control peer still requires the exact configured kernel policy,
fixed default `/proc`, original pidfd and live executable SHA256, uniform IDs
and exact unit/cgroup. The explicit approved digest is supplied by the trusted
caller. Observing an executable is not policy approval. Inaccessible cross-UID
procfs refuses without the qualification static source or configurable roots.
The root-path connector alone does not independently prove server SIOCUNIXFILE
binding; the original server listener performs that check in its own role.

Every `ControlRequestVerifier` public entry retains the root gate, including
`ensure_alive`, `ensure_pair_alive`, `verify_current`, `verify_pair_current` and
`deadline`. Those same checks already reach Agent admission, the actor queue,
preflight, dispatch and native completion. Path checks run before and after
peer observations, with creator PID checked first. The request and consumer
receive the minimum of the original accepted ceiling and original root-control
ceiling. Neither queue time nor control setup allocates a replacement budget.
Synchronous reads have before/after expiry checks, not preemptive cancellation.
The sender constructor consumes an existing opaque `AcceptedStreamCustody`;
it cannot recapture the stream or allocate another accepted budget. Before
publication, `ensure_control_current` checks the root-control ceiling only.
The existing low-level `send_retained` gate checks the original accepted ceiling
before publishing any descriptor packet. The pending owner checks their minimum.
This preserves the first custody object's ceiling, not kernel accept time or
waiting before that custody was originally captured.

Dropping or revoking action custody cannot regrant execution. The reporting
owner independently retains the same path and original peer, so it may report
an already durable local terminal after action retirement. Path failure or
expiry refuses that report; neither reporting nor lost response rewrites the
terminal journal fact or grants replay. The existing coordinator privately
rereads its own complete managed journal and binds the exact request/record
digests. Public remote reports and ServiceEvidence remain asserted data.

The privileged source corpus creates temporary owned root/nobody fixtures and
an explicit pre-launch owned executable policy. It uses a safe private copy
under a root-owned `/var/lib` fixture because the local `/run` can be noexec;
it does not repair existing executable permissions or install any service.
Actual three distinct root processes traverse original Agent stream, root
pathname control, live procfs and the same coordinator/journal. Each queued
completion callback is synthetic: these tests do not execute Servo. Eleven
required kernel groups cover all five verifier entrypoints with actual path
mutation/restoration, a completed own-journal report, fork copies, native-final
path loss, final reporting path loss, active cancel with report-only lifetime,
earlier fixed root and accepted deadlines, expired original accepted custody
refusal before descriptor publication, actual nobody-to-root procfs refusal, wrong
explicit executable pin and actual descriptor inventories. Missing sudo or
kernel capabilities fail; there are no ignored tests.

The existing main executable, socket units, presets and default policy/feature
graph remain closed. This package is not installed broker, cross-UID live
broker qualification, approved provisioning, principal or native Servo effect
evidence. The closed API and source index are in
`contracts/root-path-retained-control.v1.json`; the workflow runs the kernel
target in the same workspace graph as the existing coordinator tests.
