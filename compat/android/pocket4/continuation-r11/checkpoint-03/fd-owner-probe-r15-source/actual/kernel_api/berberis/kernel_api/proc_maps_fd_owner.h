/* Copyright 2026. SPDX-License-Identifier: Apache-2.0 */
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_FD_OWNER_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_FD_OWNER_H_

#if defined(__GNUC__)
#pragma GCC visibility push(hidden)
#endif

namespace berberis::proc_maps_provenance::fd_owner {

// Run one metadata operation against the caller's real descriptor. The
// operation receives a kernel pin in a temporary thread's independent fd table.
// No descriptor is installed in, or closed from, the caller's table. The
// callback and context must remain valid until this synchronous call returns.
//
// A short-lived owner avoids a persistent queue/mutex/thread identity inherited
// by raw guest fork/clone. It does NOT move pathname resolution into that
// thread: cwd, dirfd and /proc/thread-self need their own protocol. Required
// kernel/policy APIs must be qualified with the owned capability probe before
// enabling the provenance candidate on Android.
using Operation = int (*)(int owned_fd, void* context);
int WithPinnedFd(int fd, Operation operation, void* context);

// Opt in before entering guest code, while normal startup resources are still
// available. Once enabled, WithPinnedFd uses one already-created owner and a
// fixed single-request slot, with no pthread creation or queue allocation per
// metadata query. This does not remove pidfd_open/getfd's RLIMIT_NOFILE needs.
// Pathname operations deliberately retain their per-request owner protocol.
int StartReusableMetadataOwner();

// Close admission first, finish the last accepted request, then stop and join
// the owned thread. Requests arriving after admission closes return ESHUTDOWN;
// they never restart the owner. Only an explicit Start opens admission again.
// Invoke before the zygote's wait-for-no-host-threads/fork boundary.
int StopReusableMetadataOwner();

// Only for a child with a PRIVATE copy of the parent's address space. Discard
// the copied queue/thread state without locking it, joining the vanished owner,
// or dereferencing a parent's outstanding request. This is also installed as a
// libc pthread_atfork child hook; raw guest clone(!CLONE_VM) must call it
// explicitly, then Start before resuming guest execution. A CLONE_VM child
// with a new TGID must never call this function: it shares the parent's state.
void ResetReusableMetadataOwnerAfterPrivateFork();

// Operations run under the caller's synchronous request lifetime. They must
// not throw or recursively submit to this owner. A different TGID sharing this
// address space is rejected with EOPNOTSUPP without changing the owner's state.

// The operation receives a PIDFD_THREAD for the calling thread, in the
// independent table. It may acquire caller dirfds with pidfd_getfd; passing a
// caller descriptor number directly to an owner syscall is never correct.
int WithPrivateTable(Operation operation, void* context);

// Prepare returns a descriptor owned solely by the independent table. Publish
// runs on the caller, while that descriptor and its owner remain alive. The
// caller performs one final open of private_path to publish a NEW descriptor;
// it must not reserve/overwrite a slot or inspect/close the public result.
// This protocol is for a regular snapshot that can be reopened without side
// effects, not arbitrary devices, sockets, pipes, or an OFD transfer.
using Publication = int (*)(const char* private_path, void* context);
int WithPreparedFile(Operation prepare, Publication publish, void* context);

}  // namespace berberis::proc_maps_provenance::fd_owner
#if defined(__GNUC__)
#pragma GCC visibility pop
#endif
#endif
