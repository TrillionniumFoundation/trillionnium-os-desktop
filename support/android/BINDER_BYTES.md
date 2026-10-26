# Binder synchronous IPC: development and technical contract

This stage introduces a real `/dev/binder` device for Linux's 64-bit Binder v8
wire layout. It implements bounded synchronous transactions to the context manager
at handle 0 and to transferred strong object handles. Independently opened
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

An open is bound to the original `Process`, `Thread`, and VMAR allocation identity.
It cannot be operated through fork, SCM_RIGHTS to another process, another thread,
or after exec. PID/TID numbers are not authority identities. This restricted
profile has one participating thread per open, not a Binder thread pool.

The device supports `BINDER_VERSION` (8), `BINDER_SET_MAX_THREADS` (0 or 1),
`BINDER_SET_CONTEXT_MGR` (legacy ignored argument), `BINDER_WRITE_READ` and
`BINDER_THREAD_EXIT`. A context manager must map its receive area and enter its
looper before clients can send. The write stream supports `BC_TRANSACTION`,
`BC_REPLY`, `BC_FREE_BUFFER`, `BC_ENTER_LOOPER`, `BC_EXIT_LOOPER`, the four
handle reference commands (`BC_INCREFS`, `BC_ACQUIRE`, `BC_RELEASE`, `BC_DECREFS`),
and exact owner acknowledgements (`BC_INCREFS_DONE`, `BC_ACQUIRE_DONE`).

A synchronous call produces a transaction-complete event for the sender and a
`BR_TRANSACTION` for the manager. The manager's reply produces its completion and
`BR_REPLY` for the original caller. Sender PID and effective UID come from the
current kernel credentials; user-supplied sender fields are ignored. As in Linux,
a synchronous reply exposes sender PID zero and the responding effective UID. There is
one outstanding outgoing call per endpoint and no nested call. Delivery order is
owned by the driver's queue, not by a userspace test ledger.

Limits are 64 live endpoints, 16 queued events per endpoint, 32 commands per
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

Any partial unmap or complete unmap closes the endpoint. `BINDER_THREAD_EXIT`,
owner thread death and release also invalidate it. The old context manager is
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
must fit in one receive page. This bounded profile accepts zero object flags;
priority/security labels and FD acceptance are not silently ignored.

An object node is a real kernel allocation with a monotonic allocation identity.
Its owner is the original endpoint, whose original Process/Thread/VMAR identity
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
acknowledgements. Closing, exec's receive mapping teardown, thread exit, queued
sender death and endpoint unmap drop their actual queued/buffer/user contributions.
A prepared front event remains stable when its sender dies.

Additional bounds are 32 metadata objects per payload, 16 local nodes per owner,
256 simultaneously retained node allocations (including dead owners still held
by another endpoint), 128 live descriptors per endpoint, 32 explicit references
per strength per descriptor and 4096 contributions per node. Node and handle
identities are checked for integer exhaustion and are never reused. The full
payload is preflighted before publishing any node or contribution; receive
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

## Explicitly unsupported

FD/FD-array translation, scatter/gather, oneway calls, priority inheritance, nested calls,
thread-pool spawning, death subscriptions and transaction security contexts are
rejected. `BINDER_SET_CONTEXT_MGR_EXT` is not a fake success. The supported byte
profile uses zero transaction flags; even a request accepting FD replies must
wait for a future implemented FD contract. Unknown ioctls return ENOTTY;
recognized but unimplemented protocol commands return EOPNOTSUPP.

Do not use this driver's presence or version as an Android compatibility gate.
The historical A08 primitive probe requests two maximum threads and may correctly
fail against this restricted profile. Keep its result separate. Android boot,
servicemanager objects, framework services, FD/death semantics and MAC policy
remain unqualified until exercised by their own actual guest suites.

## Qualification and next work

The real guest probe is `tests/kernel/binder/binder_probe.c`; its runner reuses
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
ordinary guest, with Android/object/FD/death-conformance flags still false.
The initial Binder stage's native kernel rerun passed 313 tests with zero failures, covering the
owner/queue/file-status refinements. The targeted Rust formatting check and
static C compilation with warnings treated as errors also passed. Existing
upstream Rust warnings are not represented as a clean full Clippy gate.

Retain the earlier failed run as well: the first guest probe tried `mincore`,
which this kernel returns as ENOSYS. That run did not reach transaction delivery
and is not passing evidence. The replacement check actually reads the excluded
fork mapping in a child and verifies SIGSEGV. The initial OSDK setup failure
likewise remains distinct from executed kernel tests.

The bounded object stage above provides real reference ownership and translation.
Service-manager compatibility still requires descriptor installation/rollback,
death registration, nested transactions and thread-pool lifecycle. Each requires
negative and exit-race tests on actual processes. None should be represented by
returning success from an otherwise unimplemented ioctl.

The receiver's page-table admission is fallible. Each `MapHandle::map_frame`
error must reach mmap before `ReceiveArea` is installed. If a later frame fails,
the original VMAR population error path unmaps every populated prefix page;
remaining frame owners then refund at their real last reference. The endpoint
retains no receive area and can retry. Empty table nodes that remain allocated
continue to count against the original group. The real capped cross-PML4 mapping
regression in the Binder guest runbook covers this combined Binder/page-budget
contract, independently of normal transaction success.
