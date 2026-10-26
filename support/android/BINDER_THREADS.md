# Binder D1: actual-thread synchronous transaction ownership

Status: implementation work in progress. The test-only starting revision keeps
the kernel identical to Desktop `a0a9da78d81801f4198e72073771e9318ffcfa0d`.
No passing D1 guest evidence exists at that revision.

The current driver binds one open to one actual thread. Opening several Binder
files does not exercise a Binder thread pool. D1 first separates original
Process/image ownership from actual participating Thread allocation identities.
The intended limit is eight participating threads per open, with the existing
sixteen-event and sixteen-buffer limits shared by the entire endpoint. Returns
and completions belong to the original calling thread; only the worker that
received an incoming synchronous request may reply. Thread identity must use
the real allocation plus a checked monotonic token, including after exit.

The protocol reference is the [Linux v6.17 Binder driver](https://github.com/torvalds/linux/blob/v6.17/drivers/android/binder.c):
`binder_transaction` checks the replying thread's transaction stack and returns
to the original calling thread; `binder_thread_read` attaches synchronous
incoming work to its receiving thread; `BINDER_THREAD_EXIT` retires that thread.
D1 retains the existing bounded rejection of nested and oneway calls.

This stage uses manually entered actual workers. Automatic worker requests and
registration are a later stage. It must not claim those interfaces work merely
because a setter returns success. The exact supported automatic-thread quota
semantics must be documented with implementation and positive/negative tests.

The single endpoint-wide prepared-copyout slot remains an explicit limitation:
its original thread alone may retry a transaction descriptor after EFAULT.
Other threads receive EBUSY while it is retained. This is head-of-line blocking,
not parallel receive preparation. Every queued transaction needs a unique
identity so cleanup cannot substitute another event during unlocked FD work.
Outgoing terminal replies and incoming reply-completions reserve their bounded
queue space before publication. Failed admission refunds it atomically.

Object nodes, handles, delivered buffers, reference notifications and death
subscriptions remain endpoint/process resources. A worker exit must release
its unpublished transaction buffers and hidden FD reservations without killing
other workers or their objects. Process-wide node/death work must not be lost
if its preparing worker exits. Process death, original-image exec teardown,
unmap and final file release still close the endpoint. Existing charged cleanup
must keep arbitrary FileLike destruction outside Binder and VMAR locks.

`tests/kernel/binder/thread_run.py` injects the static `thread_probe.c` into an
isolated ordinary guest. Two real client threads share one client open, and two
real server workers share one manager open created by a third thread. The
probe prints actual PID/TID values, forces two outstanding requests, reverses
worker reply order, rejects a third thread's reply, and checks that the opener
cannot consume either caller's queued response. The exact initial fixture is
first run against the unchanged kernel to retain the real EPERM failure, then
rerun after D1 implementation. Exit, EFAULT, FD/ref/death lifetime and capacity
tests must be added before declaring the stage accepted, followed by the
existing five Binder probes and complete Core guest suite.

This is a kernel IPC compatibility component. Android servicemanager, automatic
thread pools, MAC policy, device support and Android boot remain unqualified.
