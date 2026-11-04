// SPDX-License-Identifier: Apache-2.0
// Owned test ABI wrappers only; invoke unchanged real generation methods.
#include "berberis/kernel_api/proc_maps_generation.h"
extern "C" __attribute__((visibility("default"))) int TestBeforeExec() {
 return berberis::proc_maps_provenance::generation::BeforeGuestExec();
}
extern "C" __attribute__((visibility("default"))) void TestAfterExecFailure() {
 berberis::proc_maps_provenance::generation::AfterGuestExecFailure();
}
extern "C" __attribute__((visibility("default"))) int TestBeforeClone(unsigned long flags) {
 return berberis::proc_maps_provenance::generation::BeforeGuestClone(flags);
}
extern "C" __attribute__((visibility("default"))) int TestBeforeSyscall(long number,unsigned long a,unsigned long b) {
 return berberis::proc_maps_provenance::generation::BeforeGuestSyscall(number,a,b);
}
