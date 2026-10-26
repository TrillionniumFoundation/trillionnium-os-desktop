# Binder D1: actual-thread synchronous transaction ownership

Status: D1 implementation in progress; full acceptance remains pending. The
starting test-only revision `5be72c51b3ab398f29d018bcd436aed7774d0bd8` kept
the kernel identical to Desktop `a0a9da78d81801f4198e72073771e9318ffcfa0d`.
Its actual SMP4 guest failed on two real sibling workers (PID19, TID21/TID22)
sharing FD7: BINDER_VERSION returned EPERM. The ordinary product gate passed;
the Binder thread fixture returned exit1. That receipt remains a failure.

The pre-D1 driver binds one open to one actual thread. Opening several Binder
files does not exercise a Binder thread pool. D1 first separates original
Process/image ownership from actual participating Thread allocation identities.
The D1 implementation limits admission to eight participating threads per open, with the existing
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
registration are a later stage. BINDER_SET_MAX_THREADS accepts zero to keep that
automatic mechanism disabled and rejects every nonzero value with EOPNOTSUPP.
Manual ENTER_LOOPER workers are subject to the separate eight-participant bound,
not an invented automatic quota. BC_REGISTER_LOOPER and BR_SPAWN_LOOPER remain
unimplemented. The older byte/object fixtures now explicitly select zero;
accepting one without any automatic behavior is no longer represented as support.

The single endpoint-wide prepared-copyout slot remains an explicit limitation:
its original thread alone may retry a transaction descriptor after EFAULT.
Other threads receive EBUSY while it is retained. This is head-of-line blocking,
not parallel receive preparation. Every queued transaction needs a unique
identity so cleanup cannot substitute another event during unlocked FD work.
Outgoing terminal replies and incoming reply-completions reserve their bounded
queue space before publication. Failed admission refunds it atomically.

An active copyout or unlocked FD reservation is distinguished from a retained
EFAULT descriptor. Blocking writes keep their original unpublished command and
wait for active preparation to finish; blocking reads wait and reselect work.
Nonblocking operations report EAGAIN for that transient activity. DOMAIN is
released before parking on the existing signal-aware condition/recheck wait
queue. Copy success, copy failure, FD-stage completion/failure, thread retirement
and endpoint closure wake rechecks. Earlier accepted commands keep their actual
write_consumed offset if the later wait is interrupted. The driver never resends
an accepted transaction.

Keep the first expanded D1 failure: revision `7612dd6d` let ordinary sibling
commands observe EBUSY during successful copyout. It made the two-caller fixture
fail intermittently and the eight-caller terminal fixture fail under contention.
Six thread-exit/EFAULT/real object/FD lifetime rows and participant quota/refund
passed before that contention failure. The passing basic run at `dd799201` did
not certify that race fixed. Both receipts remain separate from later results.

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
