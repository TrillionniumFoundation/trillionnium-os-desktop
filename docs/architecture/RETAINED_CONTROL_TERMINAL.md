# Retained control reporting and cancellation source contract

Plan revision: `2026-08-29-d6`. Status: source candidate, without installed
startup, approved principal provisioning, cross-UID broker or native effect
qualification. The closed API inventory is
[`retained-control-terminal.v1.json`](../../contracts/retained-control-terminal.v1.json).

The legacy descriptor APIs still close their control socket after handoff. The
additive retained route keeps the same existing connected seqpacket socket,
original OS challenge, submission sequence, socket cookie, local-path device
and inode, boot identity, time namespace and native deadline. It creates no
listener, replacement socket, second challenge or renewed accepted budget. The
old `send`/`receive` bodies and original test bodies stay unchanged.

`HandoffSender::send_retained(self, custody)` consumes sender custody before the
native submission and returns one pending owner. `receive_retained(self, wait)`
returns the opaque original accepted stream with a retained receiver. A closed
192-byte sideband frame carries either one cancellation request or one terminal
report; every message requires actual SCM credentials matching original
SO_PEERCRED, zero rights, the original challenge and complete original binding.
Unknown fields, ancillary records, truncation, wrong sequence, identity or
expiry permanently retire the same channel. Received rights are owned and
closed even on malformed messages. Neither publication is automatically retried.

`RemoteRetirementReport::new` deliberately accepts public transport data. Its
Completed/Interrupted/Indeterminate lifecycle and request/record digests are
remote assertions, not local durable facts. Completed includes failed, refused
and cancelled outcomes; it does not assert effect success. The report carries
no response delivery boolean, application payload, capability or replay permit.

The peer-attestation retained wrappers use only the actual default `/proc`
control constructor, explicit approved executable policy and same retained
original pidfd. The original sender is retired after transferring the pending
owner; dropping that empty sender does not revoke the pending request. Both
the original receiver control ceiling and the original accepted ceiling remain
fixed. Reporting uses their minimum; a shorter control ceiling cannot inherit
a longer accepted budget. Synchronous procfs work is checked before and after,
without claiming preemptive syscall timeout.

`request_cancel` and nonblocking `poll_retirement` let one custodian thread
watch its cancellation input while waiting on the same channel. Blocking
`wait_retirement` exclusively borrows its owner and cannot be cancelled through
a concurrent mutable borrow. Receiver cancellation revokes execution custody;
the reporting-only peer identity remains retained and cannot regrant dispatch.
Drop, EOF, malformed report, deadline, death or executable drift close the
current scope. Fork checks occur before copied channels or mutex access; child
teardown closes only child FD copies, without parent shutdown or unlock.

`RetainedProductConnection::from_control_retained_received` admits the original
Agent with the fixed default live attestor and a separately trusted configured
canonical approved Agent executable pin. It returns an opaque connection and
`ProductControlMonitor`. Move the monitor to one I/O worker in the same process
and run it while the coordinator owns the request on its actor worker. The
monitor has a private single-message channel and uses wait intervals of at most
five milliseconds under the fixed remaining ceiling. Synchronous attestation
and scheduling add latency; no hard five-millisecond cancellation guarantee is
claimed. Cancellation interrupts the original accepted
transport and current actor token. Drop cancels its own request, closes its
own descriptors and performs no thread join. Foreign child channel references
are deliberately forgotten to avoid copied standard-library mutex teardown.

`ProductRequestCoordinator::serve_retained_connection` is the only product
terminal association path. It accepts no caller boolean, outcome, digest,
`ServiceEvidence` or external `DurableReceiptFact`. The coordinator captures the
current private invocation's exact request ID, canonical request digest and
terminal record digest. Its lifecycle first appends and syncs the terminal,
then reads the complete owned managed journal before the existing AgentPort
response attempt. After request preparation/action custody retire, it rereads
that same journal by the same private request ID and digest and requires the
same terminal lifecycle and record digest. Only then can it send a private
`SealedTerminal` through the monitor's single-use link. The type and sending
interface are inaccessible to public callers.

A preflight refusal has no admission fact and emits no terminal report, even
when an unrelated request has completed in that journal. Storage damage refuses
the report and keeps recovery closed. Indeterminate and interrupted-after-
dispatch facts keep their existing recovery latch; sending a report cannot clear
it. A lost application response can coexist with a known local durable terminal.
Sending a report proves packet enqueue only. Losing it or the custodian after
the report does not rewrite history, prove delivery, manufacture success or
permit another dispatch. Missing reports do not prove that an effect failed.

The standalone transport kernel target exercises actual malformed credentials,
rights, bindings, truncation, full native buffers, fork and single-use retirement.
`product_terminal_wait_kernel` runs three actual independent same-UID processes
with actual `/proc`, pidfds, seqpacket and the original Agent stream. Its managed
journal, missing/lost reports, unrelated terminal history, cancellation, original
deadlines, exec, fork and FD cleanup are real host operations. Its engine
completion is explicitly a controlled source callback, never Servo execution.
The known test executable pin and inherited host service fixture do not provision
production policy. Original kernel and source tests remain separate unchanged
regressions. Rust tests must not skip unavailable required kernel/service facts.

The binaries still refuse installed product dispatch. A root-owned control
listener/connector, service lifetime wiring, approved cross-UID live-executable
authority, trusted principal policy, concrete installed Servo event-loop owner,
final engine-task peer/node/epoch gate and recovery UI remain open. Raw duplicate
FDs outside these owners, arbitrary asynchronous syscall/opcode interruptions
and language-runtime C-return ownership windows are not claimed fully closed.

## Host deadline fixture preparation

The terminal kernel fixture selects its explicit Agent/controller policies before
the custodian and receiver capture their first fixed deadlines. A one-time child
barrier retains the same raw accepted stream until this unrelated preparation
finishes; it does not reconnect, clone, recapture or renew a custody budget.
The original two-second accepted/control ceilings, twenty-second longer ceiling,
three-second monitor bound and complete eleven-group assertions remain unchanged.
This expiry experiment measures the first custody and control-wait deadlines,
not kernel accept or raw-stream time before capture. Separate delayed handoff and
queue tests retain their original elapsed-time assertions. Child/descriptor
cleanup uses the existing owned fixture groups and wait bound on barrier failure.

Prior complete and isolated fixture failures returned DeadlineExceeded during
final connection admission. Independent timing later measured roughly 1.8 seconds
of live attestation/preparation under a two-second fixture budget; this later
measurement is not timing evidence from the original failing run. Production
deadlines, live Procfs/ELF verification, dispatch and recovery code are unchanged
by this test preparation change.
