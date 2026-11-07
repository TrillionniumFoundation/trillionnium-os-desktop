/* Copyright 2026. SPDX-License-Identifier: Apache-2.0 */
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_OPEN_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_OPEN_H_
#include <sys/types.h>
#if defined(__GNUC__)
#pragma GCC visibility push(hidden)
#endif

namespace berberis::proc_maps_provenance {

// Called in an independent owner table, with an actual readable proc/maps fd.
// Return a private CLOEXEC regular snapshot, or -1 with the real error. This
// callback must not throw or retain its stack context after returning.
using SnapshotOperation = int (*)(int source_fd, int original_flags, void* context);

// No helper fd is ever allocated in the calling table. A positive identity
// observation is retained by opening the process's immutable canonical maps
// object in the owner, even if an ordinary alias is renamed afterwards. The
// final public fd is installed by ONE caller open while the owner holds it.
//
// A false return still delegates an ordinary open to its existing adapter.
// That adapter's ordinary-path-to-maps replacement race is a separate open
// admission problem: this helper does not claim to close that broader gap.
bool TryOpenSelfMaps(int dirfd, const char* path, int flags, mode_t mode,
                     SnapshotOperation snapshot, void* context, int* result);

}  // namespace berberis::proc_maps_provenance
#if defined(__GNUC__)
#pragma GCC visibility pop
#endif
#endif
