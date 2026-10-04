# Retained Control readiness source profile v1

This additive profile selects a nonconsuming idle wait on the original Control
endpoint inside the explicitly root-approved source factory. Product `main`
activation remains disabled. Source correspondence, real kernel tests and
original native budget qualification are separate gates. This profile neither
installs a service nor closes G2 or production readiness.

## API and call direction

`PendingHandoffReceiver::cancel_readable_now(&mut self) -> Result<bool,
HandoffError>` accepts no descriptor, clock, peer snapshot or authority input.
The private `ControlChannel::new` captures that actual Control socket's device,
inode and `SO_COOKIE` before publication. This is a separate private
`OriginalControlIdentity`: the existing `Transaction.identity` denotes the
accepted Agent stream and cannot identify Control. Each channel carries its
own creation-time identity, including when its stream moves into detached
terminal reporting custody.

The first explicit readiness call selects the profile's private transaction
marker. It does not capture a new identity. Every subsequent private
`Transaction::verify_channel` verifies the same captured Control identity
before and after the original boot/time-namespace/monotonic/Instant checks.
Thus the message and detached report paths retain the identity gate as well as
the idle poll. The two new inherent methods live in explicitly registered production child
modules `retained_control/readiness.rs` and `retained_request/readiness.rs`.
Their compiled module declarations and full 38-method closure (36 original
plus these two) are required by the new checker. The original public raw
`poll_cancel`, `send_report`,
`request_cancel`, `poll_report` and `wait_report` bodies remain byte exact.

`AttestedRetainedReceiver::poll_cancel_when_readable(&mut self) -> Result<bool,
ControlOwnerError>` requires the held reporting owner, original root pathname,
whole root-approved source and its actual Control role, the original live
Control pidfd, creator and original deadlines before and after observation.
The held source checks all thirteen fields; its admitted Control UID/GID/unit,
cgroup and executable pin must match the selected Control entry. It cannot
use a caller policy, positional guard count or a revoked action lease as
reporting authority. The policy pin comparison uses the originally admitted
snapshot; it is explicitly not a fresh executable-byte assertion.

`ProductControlMonitor` selects the private `ApprovedReadinessV1` route only
when constructed through the real approved factory with the existing fixed
`ProcfsPeerAttestor::default()` and opaque source selections. The legacy
factory selects `FullV1`. The profile enum, monitor routing helper, reporting
scope and Control identity are private; no caller boolean or raw descriptor
can choose them. The same actor, principal, journal and receipt call chain
continues to perform its existing full effect checks.

## Idle and true full boundaries

An idle `false` result grants no action, runtime, report or journal permission.
The new idle scope observes root source/path drift and actual Control death,
but does not rehash either executable on every five-millisecond local wait.
A live process that executes another image while idle is therefore not asserted
to retain its approved executable by that result. It must be refused by the
unchanged complete default-proc readback before actual cancellation consumption
or terminal reporting. An executable check already required at a native,
queue, actor, callback, URL or journal effect boundary is not moved or omitted.
There is no executable cache, future `Instant` or shared stale proof.

Readable, HUP and error observations delegate the unchanged public raw full
cancel poll. Its complete owner readbacks surround packet consumption, nonce,
sequence and kernel-credential checks, and its existing cancellation latch
revokes action custody. Terminal reporting still uses the unchanged full
`send_remote_report` and transport `send_report`, including final readback,
single send attempt and the original ceiling. Reporting after legitimate
action revocation is possible only through the independent original reporting
owner. A transport report by itself is a remote assertion; the product monitor
requires its own sealed journal terminal and supplies no caller report permit.

All accepted budgets remain at most twenty seconds, native budgets at most
five seconds, and the separate sixty-second service-health requirement remains
open. Readiness is not a lifetime renewal or a persistent service owner.

## Failures and descriptor ownership limits

Fork refusal precedes descriptor/clock access. Unknown source, path drift,
Control death, cookie substitution and expiry retire the same scope without
reconnect or automatic recovery. Observation does not consume a packet; a
queued duplicate or malformed cancellation still reaches the original full
parser and is rejected there.

The existing `ControlChannel::retire` and Drop behavior are unchanged. A test
that substitutes a same-credential socket proves refusal before parsing or
sending; it does not prove that retiring the owned descriptor avoids closing a
substituted duplicate. Querying identity and closing a descriptor also has a
same-process concurrent `dup2` race. This package supplies no cleanup guarantee
against arbitrary malicious unsafe descriptor manipulation within the process.

## Required checks and evidence separation

`contracts/retained-control-readiness.v1.json` defines the two public signatures,
private authority boundary, exact source correspondence and claim limits.
`tools/verify_retained_control_readiness.py` requires every actual new source
byte and a finite inverse transfer that reconstructs each changed parent Rust
source. Original source contracts and their mutation tests are byte preserved;
the scope/constructor checkers apply only that explicit inverse before their
unchanged rules. The native source validator also requires the actual new
profile checker. Direct legacy checkers failed on the additive source before
this transfer; those failures are retained separately from successor checks.

The Cargo exception is one appended `harness = false` browserd test target.
Removing its exact suffix must restore the whole original Cargo file. The old
support, test cases, Cargo dependencies, lock, pinned native sources, workflow
commands and 20/5-second budgets remain unchanged. Both full unfiltered Rust
graphs run the new target; no original test is filtered or skipped.

The new transport module has eleven groups: same-process real socket/SCM
exchange, idle/nonconsumption, same-credential atomic replacement, isolated
closed-descriptor reuse, cookie fault injection, repeated/malformed actual
packets, HUP, creator fault injection and original expiry. The close/reuse gap
runs in a self-exec single-case child so other unit harness threads cannot
acquire that descriptor. The creator mutation is synthetic; it is not fork
evidence. Old default unit harness parallelism remains enabled.

The new `control_readiness_kernel` target has nine groups using real
root-selected Control and Agent processes, default `/proc`, original pidfds,
protected configuration and an actual transient root unit: idle/report after
action revocation, cancellation/report, source drift/restore, Control death,
real fork refusal with parent reporting, original twenty-second expiry, product
journal/terminal completion, queued cancellation after Control exec, and idle
exec followed by full terminal refusal. The exec stimulus preserves both real
FDs of one original Control object only after their actual dev/inode/cookie
agree; the second FD is the existing retained pathname-custody duplicate.
Synthetic runtime callbacks and direct remote reports are recorded separately
from real process/kernel observations. These tests do not execute native Servo,
install a service, qualify cross-UID deployment or measure a speedup. A fresh
exact-source original six-case native run is required after independent review
and final composition.
