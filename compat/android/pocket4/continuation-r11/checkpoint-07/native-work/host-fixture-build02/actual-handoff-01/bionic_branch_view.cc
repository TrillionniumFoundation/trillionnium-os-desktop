// SPDX-License-Identifier: Apache-2.0
// Host-only branch fixture, NOT a Bionic executable or libc syscall oracle.
// Renaming the namespace prevents differently compiled inline definitions
// from violating the ODR or selecting the glibc conversion at link time.
#define __BIONIC__ 1
#define berberis owned_fixture_bionic_berberis
#include "berberis/kernel_api/proc_maps_kernel_statfs.h"
#undef berberis
#undef __BIONIC__
extern "C" void FixtureBionicBranchView(const void* input,void* output) {
 using owned_fixture_bionic_berberis::proc_maps_provenance::KernelStatfs;
 KernelStatfs value{};memcpy(&value,input,sizeof(value));struct statfs result{};
 owned_fixture_bionic_berberis::proc_maps_provenance::KernelStatfsToLibc(value,&result);
 memcpy(output,&result,sizeof(result));
}
