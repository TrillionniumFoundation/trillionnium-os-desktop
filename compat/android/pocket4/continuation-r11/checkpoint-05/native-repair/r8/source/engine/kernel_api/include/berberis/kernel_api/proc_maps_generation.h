// SPDX-License-Identifier: Apache-2.0
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_GENERATION_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_GENERATION_H_
#include "proc_maps_generation_protocol.h"
namespace berberis::proc_maps_provenance::generation {
// Normal initialization consumes a platform grant. It never starts an owner
// from generic attach, a signal callback, a metadata query, or ExecuteGuest.
int RequireReadyForNativeBridge();
int BeforeGuestClone(unsigned long flags);
void AfterPrivateGuestFork();
// Return 0 to continue, -1 with errno to reject. This revision explicitly
// rejects unsupported changing operations before issuing the kernel syscall.
int BeforeGuestSyscall(long guest_number,unsigned long first_argument,unsigned long second_argument);
// exec() closes admission before entering the kernel. A failed exec uses its
// explicit paired return hook, never a lazy metadata-triggered restart.
int BeforeGuestExec();
void AfterGuestExecFailure();
// Raw exit_group is a process-wide boundary. Ordinary thread exit remains
// outside this protocol until the host-thread lifetime protocol is qualified.
int BeforeGuestExitGroup();
}
#endif
