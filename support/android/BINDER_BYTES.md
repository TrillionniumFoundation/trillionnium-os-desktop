# Binder synchronous IPC: development and technical contract

This stage introduces a real `/dev/binder` device for Linux's 64-bit Binder v8
wire layout. It implements bounded synchronous transactions to the context manager
at handle 0 and to transferred strong object handles, including actual open-file
transfer when the target or original caller accepts it. Independently opened
endpoints exchange actual transactions, object references and replies through
kernel-owned receive pages. This restricted profile is not Android boot
qualification.

The ABI constants and structure layout follow the
[Linux v6.17 UAPI](https://github.com/torvalds/linux/blob/v6.17/include/uapi/linux/android/binder.h).
The implementation is safe Rust in `kernel/core/src/device/misc/binder/`; no new
unsafe block or userspace proxy is involved. The device is created by devtmpfs
with its normal root:root 0600 ownership. Context-manager registration additionally
requires an effective UID of zero. Access policy is ordinary device DAC; no
SELinux/Binder MAC policy is claimed.

## Supported protocol

An open is bound to the original `Process` and VMAR allocation identity. It
cannot be operated through fork, SCM_RIGHTS to another process, or after exec.
D1 admits at most eight actual participating Thread allocations in that process,
each with a checked monotonic identity, incoming call, outgoing call and manual
looper state. PID/TID numbers are not authority identities. An ordinary worker's
exit does not close the other workers or the endpoint's objects. The current D1
implementation and its acceptance status are detailed in [BINDER_THREADS.md](BINDER_THREADS.md);
this paragraph does not qualify automatic thread-pool spawning.

The device supports `BINDER_VERSION` (8), `BINDER_SET_MAX_THREADS` (zero only),
`BINDER_SET_CONTEXT_MGR` (legacy ignored argument), `BINDER_WRITE_READ` and
`BINDER_THREAD_EXIT`. A context manager must map its receive area and have a manually entered actual
worker before clients can send. The automatic-thread quota may only be zero:
nonzero values conservatively return EOPNOTSUPP until actual spawn/register
support exists. Manual ENTER_LOOPER participants are independent of that disabled
automatic quota, subject to the eight-participant bound. The write stream supports `BC_TRANSACTION`,
`BC_REPLY`, `BC_FREE_BUFFER`, `BC_ENTER_LOOPER`, `BC_EXIT_LOOPER`, the four
handle reference commands (`BC_INCREFS`, `BC_ACQUIRE`, `BC_RELEASE`, `BC_DECREFS`),
exact owner acknowledgements (`BC_INCREFS_DONE`, `BC_ACQUIRE_DONE`), and
`BC_REQUEST_DEATH_NOTIFICATION`, `BC_CLEAR_DEATH_NOTIFICATION`,
`BC_DEAD_BINDER_DONE` for nonzero object handles.

A synchronous call produces a transaction-complete event for the sender and a
`BR_TRANSACTION` for the manager. The manager's reply produces its completion and
`BR_REPLY` for the original caller. Sender PID and effective UID come from the
current kernel credentials; user-supplied sender fields are ignored. As in Linux,
a synchronous reply exposes sender PID zero and the responding effective UID. There is
one outstanding outgoing call per actual participant and no nested call. Delivery order is
owned by the driver's queue, not by a userspace test ledger.

Limits are 64 live endpoints, eight participants per endpoint, 16 shared event
slots (including reserved terminal/completion work), 32 commands per
4096-byte write stream, one page of payload per transaction, and at most 16 live
receive buffers. Mapping lengths are page aligned and at most 1 MiB. Receive
pages are allocated through the original cgroup page allocator and retain their
original charge until their actual frame lifetime ends. The endpoint's bounded
kernel queue is not an Android low-memory policy.

All input command bytes and payloads are copied and checked before the first
command in a batch executes. Unsupported commands cannot partially execute an
earlier command in the same batch. Execution failures preserve successfully
consumed command progress in `binder_write_read` when its copyout is still
possible. A userspace transport-copy failure after a command was accepted is
not proof that the command did not execute. In particular, the final
`binder_write_read` copyout can fail after commands were enqueued or a read event
was consumed. This transport is not an exactly-once ledger. Callers must not
replay the original command merely because write-consumed could not be copied
back. The real guest test uses a read-only transport structure, observes EFAULT,
and still receives the original request/reply without resending it.

## Receive memory and lifetime

The receiver maps the device at offset zero using read-only private or shared
mapping semantics. The kernel installs owned UFrames and copies payload bytes
into those frames, never into a sender-supplied receiver address. Write and
execute permissions are forbidden both at mmap and at later mprotect calls.
The mapping is excluded from fork inheritance and cannot be moved or resized
with mremap. The private opt-in is specific to drivers implementing these
requirements; existing device mappings keep their previous default behavior.

Each delivered buffer must be returned by its exact start address with
`BC_FREE_BUFFER`. Out-of-range, interior and double frees fail. Pages are zeroed
before reuse and when returned. Receiving a transaction into an undersized output
buffer leaves it queued. If copying its descriptor to userspace fails, the exact
prepared descriptor and receive slot remain available for another read; the
payload is not sent again. If the caller dies while its descriptor is prepared,
the manager can still receive those already prepared bytes; replying to that
now absent incoming caller returns EINVAL. The descriptor must not be replaced
by a newer caller's event during copyout.

Any partial unmap or complete unmap closes the endpoint. Process death, original
image exec teardown and final file release also invalidate it. `BINDER_THREAD_EXIT`
and actual thread exit retire only that participant's calls. The normal exit
path notifies Binder after publishing the real Thread exit state and releasing
TaskSet/cgroup locks, before waking a joining sibling. Retained Thread Arcs do not
keep that participant alive. A dead receiving worker causes a dead reply only
for its own pending synchronous caller. The old context manager is
not reused by a later manager. An outstanding call to a manager that closes
without replying receives `BR_DEAD_REPLY`; an already queued reply remains a
reply. Endpoint allocation identities are monotonic and checked for exhaustion.
A stopped manager cannot manufacture a reply; signal-interrupted readers receive
an interruption with write progress retained. An O_NONBLOCK status snapshot is
passed through the original file ioctl dispatch and an empty read returns EAGAIN.

The lock order is VMAR, then Binder domain. The domain lock never acquires a VMAR
or process lock and never copies userspace. Mapping frames are allocated before
taking the domain lock. Output copying takes place after preparing a bounded
event and releasing the domain lock. Unmap notifications run before the PTEs are
removed; remaining UFrame/PTE references preserve memory safety through teardown.

## Object and handle development contract

The supported metadata objects are 24-byte strong/weak local Binder objects and
strong/weak remote handle objects. Offset arrays use native 64-bit entries;
offsets must be eight-byte aligned, strictly ordered, nonoverlapping, and fully
inside the snapshotted data. Data rounded up to eight bytes plus the offset array
must fit in one receive page. Local/remote Binder objects allow only the
`FLAT_BINDER_FLAG_ACCEPTS_FDS` flag; priority and security flags are rejected.
Nodes retain their original FD acceptance flag across handle forwarding and
return to the owner; an existing pointer cannot change cookie or flags.

An object node is a real kernel allocation with a monotonic allocation identity.
Its owner is the original endpoint, whose original Process/VMAR identity
is enforced. The userspace pointer and cookie are opaque local object labels,
never kernel addresses or authority tokens. Re-exporting an existing pointer with
a different cookie fails. Receiving a foreign object creates a per-endpoint,
monotonic nonzero descriptor. Forwarding resolves the actual node and allocates
a descriptor in the next endpoint's namespace; returning to the original owner
restores its original pointer, cookie and strong/weak object kind. A nonzero
transaction target must resolve an existing strong reference and delivers the
original target pointer/cookie to that owner, not to the current manager.

Queued transfers, delivered receive buffers, and explicit userspace handle
references are separately owned contributions. Preparing an event or retrying a
failed descriptor copy shares the existing contribution, rather than incrementing
it again. `BC_FREE_BUFFER` drops the buffer's contributions and removes descriptors
with no remaining buffer or explicit reference. `BC_ACQUIRE`/`BC_INCREFS` retain
existing strong/weak handles; `BC_RELEASE`/`BC_DECREFS` drop only explicit references
and reject underflow. A pure weak handle cannot be called or promoted with
`BC_ACQUIRE`. Dead-owner handles retain the old node identity and calls report
completion plus `BR_DEAD_REPLY`; creating another endpoint cannot redirect them.

The owner receives real `BR_INCREFS`, `BR_ACQUIRE`, `BR_RELEASE`, `BR_DECREFS` work
from aggregate node state. The first two require matching pending pointer/cookie
acknowledgements. Invalid, duplicate and mismatched acknowledgements fail.
Reference work is scanned independently of the transaction queue, so a full queue
cannot discard required owner notifications. Release/decref work waits for pending
acknowledgements. Closing, exec's receive mapping teardown and endpoint unmap drop their actual
queued/buffer/user contributions. Participant exit removes its queued work and
unpublished transaction preparation, while delivered buffers, explicit handles
and local nodes remain process resources until their own release.
A prepared front event remains stable when its sender dies.

Additional bounds are 32 metadata objects per payload, 16 local nodes per owner,
256 simultaneously retained node allocations (including dead owners still held
by another endpoint), 128 live descriptors per endpoint, 32 explicit references
per strength per descriptor and 4096 contributions per node. Node and handle
identities are checked for integer exhaustion and are never reused. The full
payload's object references are preflighted before publishing any node or contribution; receive
handle allocation is drafted and committed only after a receive slot is available.
Metadata uses the bounded kernel heap; these caps do not claim Android's full
memory-pressure policy.

Developers should keep `objects.rs` responsible for reference lifetime and owner
work, `mod.rs` responsible for domain routing/receive ownership, and `uapi.rs`
responsible for POD wire layouts. Lock order is DOMAIN then Node.state. Reference
Drop only takes Node.state, never DOMAIN. No native PID lookup, userspace service,
path reopen or synthetic handle substitutes for the actual node allocation.

`tests/kernel/binder/object_run.py` compiles a static guest-only probe and uses
the ordinary kernel build/boot gate before injecting it into an isolated QEMU
initramfs. The three-process test covers local export, namespace forwarding,
strong target invocation, return to original owner, exact sender identity,
buffer-only and retained references, weak/forged handle denial, offset validation,
copyout retry, reference underflow/acknowledgements, last-reference owner work and
dead-owner identity nonreuse. The original byte probe remains required, including
its real cgroup mapping-admission rollback. No probe runs on the host.

## Actual open-file transfer and receive transaction

`BINDER_TYPE_FD` transfers a snapshot of the sender's actual `Arc<dyn FileLike>`.
The source FD is looked up while parsing outside DOMAIN. A later close, numeric
FD reuse, path rename or new open cannot substitute a different file. This
profile requires zero FD object padding/flags/cookie and a nonnegative 32-bit
FD; FD arrays and pointer/buffer objects remain rejected.

Request FDs require the resolved target node's original
`FLAT_BINDER_FLAG_ACCEPTS_FDS`. The legacy context manager has no such flag and
rejects request FDs with EPERM; `BINDER_SET_CONTEXT_MGR_EXT` is still unsupported.
Reply FDs require `TF_ACCEPT_FDS` on the original received request, not a flag
chosen by the replying process. Acceptance and CLOEXEC reservation are constrained
by `binder_translate_fd` and `binder_apply_fd_fixups` in the
[Linux v6.17 driver](https://github.com/torvalds/linux/blob/v6.17/drivers/android/binder.c).
The delayed installation across a failed userspace descriptor copy described
below is this profile's explicit contract; it is not a claim of identical Linux
copy-fault timing. Rejected FD replies leave the incoming call
available for a valid ordinary reply. No Hepta authorization rule or device DAC
changes as a result of this IPC compatibility feature.

Receiving an FD message pins its exact queue front before dropping DOMAIN and
reserves all target descriptors using the original file table's reservation API.
Every target FD has CLOEXEC. If any reservation fails, all earlier reservations
are released outside DOMAIN and no file is installed. A failed user descriptor
copy retains the exact prepared bytes, receive buffer and still-hidden FD
reservations; retry uses the same numbers and does not install a second batch.
Reserved descriptors return EBADF to lookup/close and cannot be stolen by another
allocation. After successful descriptor copy, DOMAIN commits the event, then
the reservations install the original FileLike objects outside DOMAIN. Returning
the receive buffer or closing the Binder endpoint does not close already
installed FDs. The final `binder_write_read` transport copyout can still fail
after commit/installation; this remains an IPC transport, not an exactly-once
operation ledger.

Both domain-lock reacquisition and receive preparation conservatively reject an
FD payload without a complete reservation batch, including a new front that
arrives between locks. If a sender exits while reservations are being created,
its pinned descriptor can still be delivered and freed, but no dead incoming
reply stack is installed. This prevents a dead sender from blocking future
requests. Endpoint allocation identities and the single original thread/image
rule remain in force through this two-stage preparation.

There are at most 256 retained FD snapshots globally, including queued/prepared
messages and deferred destruction. The 32-object/page/queue limits also apply to
FD objects. FileLike and reservation destruction never takes a file-table lock
under DOMAIN. Before looking up and retaining a source FileLike, the sender
acquires a global permit and prepares a charged cleanup stack/task through
`ThreadOptions::try_build` and the existing `PreparedTaskStack` admission API.
Budget, physical allocation and mapping failures return an error before message
publication; dropping an unstarted task refunds its permit. The cleanup stack is
charged to the original source account and each frame retains that charge until
its real final destruction. This covers these particular cleanup tasks, not all
system kernel stacks or complete `memory.max` isolation. Normal bounded metadata
continues to use the kernel heap.

`files.rs` uses two bounded, preallocated retirement vectors. A dedicated kernel
coordinator drains outside DOMAIN/VMAR/retirement locks, and ordinary Binder
open/poll/write-read paths may also drain. They refund hidden descriptor
reservations and schedule already prepared cleanup tasks; they never wait for an
arbitrary FileLike destructor. Each retained snapshot's separate task drops its
actual file and returns its permit only when that close finishes. A socket with
SO_LINGER can therefore block its own task without blocking unrelated descriptor
refunds or Binder requests. There are at most 256 such outstanding cleanup tasks;
the current default stack size is 128 pages per task, so 256 admitted prebuilt
tasks account for 128 MiB of stack pages. Exited tasks can still retain charged
frames through scheduler/RCU references after the file permit returns. The
128 MiB figure describes admitted prebuilt tasks, not a hard global physical
stack ceiling; those deferred frames keep their original account charge until
actual final destruction. Android-scale reclamation policy and stack-pool
optimization remain future work.

This coordinator is necessary because unmap and final image teardown retire
endpoints while still holding a VMAR lock; cleanup does not depend on a future
userspace request. Its initial stack allocation is also fallible. If initialization
cannot prepare it, ordinary byte/object IPC remains available and FD snapshots
return ENOMEM. A draining flag serializes concurrent scheduling without recursive
cleanup stacks or lost retirements.

`object_run.py` also runs `fd_probe.c` in the same isolated ordinary guest. It
verifies source close/reuse against actual file contents and shared file offsets,
FD acceptance and rejection, CLOEXEC, two-FD EMFILE rollback at the second
reservation, repeated EFAULT with hidden stable reservations, exactly one actual
installation, live FDs after FREE/endpoint close, and prepared-close release by
observing EPIPE on the original pipe. A 128-round concurrent enqueue test checks
real FD request/reply transfer and alternating reads from the same file object.
`cleanup_probe.c` holds eight real 32-FD messages, confirms that the 257th
snapshot fails with zero consumption and no ghost event, then observes actual FD
transfer recovering after cleanup. It also establishes a multi-second TCP
SO_LINGER close in the guest and checks that retiring an equivalent prepared TCP
FD leaves another pipe's real EPIPE and descriptor refunds under one second. This
is a real socket destructor, not a timer substituted for file cleanup. A native
kernel test refuses stack admission and checks that the task callback was never
run and the unpublished global permit was returned.
The kernel core reference tests and original byte/resource-admission guest gate
remain required. Android service-manager startup, thread pools and boot are
separate outstanding gates.

## Bounded death subscriptions

The wire commands use the native 64-bit UAPI's packed 12-byte handle/cookie pair,
parsed as a four-byte handle followed by an eight-byte cookie. `BC_DEAD_BINDER_DONE`
uses an eight-byte cookie. `BR_DEAD_BINDER` and
`BR_CLEAR_DEATH_NOTIFICATION_DONE` return four-byte command plus eight-byte cookie.
No C packed pointer is dereferenced by the safe Rust driver. The reference
cleanup, CLEAR detachment and dead/clear ordering were checked against
`binder_cleanup_ref_olocked`, the death command cases, and death work in the
[Linux v6.17 driver](https://github.com/torvalds/linux/blob/v6.17/drivers/android/binder.c).

`death.rs` owns at most 32 records per endpoint, including detached records still
awaiting an acknowledgement. Each record holds the resolved original node
allocation and original owner endpoint identity, a monotonic checked delivery ID,
and the subscriber's cookie. It contributes no strong or weak reference and
cannot keep a handle callable. Every handle has at most one attached subscription.
Because DONE carries only a cookie, this bounded profile rejects duplicate cookies
within an endpoint until the earlier record finishes. Invalid handles, mismatched
cookies, duplicate subscriptions and premature/duplicate acknowledgements return
errors. Handle 0 and unimplemented freeze notifications are not silently accepted.

The implemented state progression is Live, DeadQueued, DeadDelivered,
Acknowledged, then ClearQueued when clearing an acknowledged record. An already
closed original owner starts a new subscription in DeadQueued. Closing a live
original endpoint queues exactly one death for each attached Live record; a
replacement process, VMAR, endpoint or node with the same pointer/cookie cannot
satisfy it. This endpoint's lifetime rules include process death, successful exec teardown,
unmap and final release. D1 thread exit retires only that participant and cannot
manufacture a process object's death notification.

CLEAR checks the exact handle/cookie and detaches immediately. For a still-live
or already acknowledged record, it queues clear-complete. For a queued or delivered
death, it retains the pending clear and requires the actual sequence
`BR_DEAD_BINDER`, `BC_DEAD_BINDER_DONE`, `BR_CLEAR_DEATH_NOTIFICATION_DONE`.
It does not cancel an already triggered death. Last buffer/user reference removal
prunes the handle and cancels any still-attached record, including queued or
already delivered work. A detached record instead keeps its owed handshake even
if that handle is subsequently pruned. Endpoint closure cancels all its records.

Death work uses the bounded record scan independently of ordinary transaction
queue admission, so a full request queue cannot discard it. Node reference work
is considered first, then death work, then transaction work; this is the profile's
explicit scheduling order, not a claim of identical Linux global work ordering.
Poll observes pending death/clear work. Preparing a death read does not mark it
delivered. Insufficient output capacity or EFAULT keeps the same exact prepared
notification; the state commits only after successful copyout. As with the rest
of this profile, commands while an EFAULT-prepared read is outstanding return
EBUSY until that event is read successfully. Final write-read transport copyout
can still fail after event commit; this remains outside an exactly-once ledger.

`death_probe.c` uses independently opened endpoints in real owner/subscriber
processes. Its gate checks actual SIGKILL and exec, subscriber death, 32-record
saturation/refund, forged handles/cookies and duplicate DONE, weak/buffer/user
reference lifetime, attached cancellation versus detached owed work, small read,
EFAULT retry, poll and death delivery with all 15 ordinary request admission slots
occupied while preserving the original queued request. Sixteen real child-owner
close/CLEAR races accept only the two legal linearizations and print the observed
ordering counts; deterministic queued/delivered cases separately require death
before clear-complete. A new image's old FD is rejected and a replacement node
cannot redirect the old handle. Native state tests cover capacity, attachment,
detachment and copyout-commit acknowledgement gates. These tests do not qualify
Android thread pools, Binder freeze support, oneway IPC or Android boot.

## Explicitly unsupported

FD arrays, scatter/gather, oneway calls, priority inheritance, nested calls,
thread-pool spawning, freeze subscriptions and transaction security contexts are
rejected. `BINDER_SET_CONTEXT_MGR_EXT` is not a fake success. The supported transaction flags are zero or `TF_ACCEPT_FDS`. Other flags are
rejected; accepting FD replies does not imply support for oneway or scatter/gather. Unknown ioctls return ENOTTY;
recognized but unimplemented protocol commands return EOPNOTSUPP.

Do not use this driver's presence or version as an Android compatibility gate.
The historical A08 primitive probe requests two maximum threads and may correctly
fail against this restricted profile. Keep its result separate. Android boot,
servicemanager integration, framework services, complete FD/death conformance and
MAC policy remain separate unqualified gates. The bounded object/FD/death subset
above has its own actual guest suites; this does not qualify those broader gates.

## Historical initial byte qualification and current next work

The initial byte-only guest probe is `tests/kernel/binder/binder_probe.c`; its runner reuses
the existing source/artifact-bound ordinary kernel boot harness. It checks
cross-process payload/reply bytes, sender identity, inherited-FD and foreign-thread
rejection, read-only/fork/remap boundaries, unsupported operations, output faults,
partial-unmap wakeup, real manager SIGKILL, replacement-manager cleanup, exec,
receive-buffer exhaustion/reuse and request-queue backpressure with reply progress.
Build and execution evidence is retained outside the checkout. The frozen ordinary
kernel ELF `8988f7c8519cadfe81204bbaa9ceddafa3ad13790ec22108a069a21262cfc5fc`
passed the SMP2 byte/lifetime suite and the expanded SMP4 suite. The final SMP4
run reports 557 parent assertions, plus child-process payload/identity checks;
its source and artifact snapshots are unchanged. All execution is inside the
ordinary guest; that initial receipt kept Android/object/FD/death-conformance
flags false and must not be relabelled as later-stage evidence.
The initial Binder stage's native kernel rerun passed 313 tests with zero failures, covering the
owner/queue/file-status refinements. The targeted Rust formatting check and
static C compilation with warnings treated as errors also passed. Existing
upstream Rust warnings are not represented as a clean full Clippy gate.

Retain the earlier failed run as well: the first guest probe tried `mincore`,
which this kernel returns as ENOSYS. That run did not reach transaction delivery
and is not passing evidence. The replacement check actually reads the excluded
fork mapping in a child and verifies SIGSEGV. The initial OSDK setup failure
likewise remains distinct from executed kernel tests.

The bounded object-reference, descriptor installation/rollback and death stages
above now have separate actual guest suites. Outstanding work includes Android
service-manager integration, FD arrays, nested transactions, oneway IPC and
thread-pool lifecycle. Each requires negative and exit-race tests on actual
processes. None should be represented by returning success from an otherwise
unimplemented ioctl.

The receiver's page-table admission is fallible. Each `MapHandle::map_frame`
error must reach mmap before `ReceiveArea` is installed. If a later frame fails,
the original VMAR population error path unmaps every populated prefix page;
remaining frame owners then refund at their real last reference. The endpoint
retains no receive area and can retry. Empty table nodes that remain allocated
continue to count against the original group. The real capped cross-PML4 mapping
regression in the Binder guest runbook covers this combined Binder/page-budget
contract, independently of normal transaction success.
