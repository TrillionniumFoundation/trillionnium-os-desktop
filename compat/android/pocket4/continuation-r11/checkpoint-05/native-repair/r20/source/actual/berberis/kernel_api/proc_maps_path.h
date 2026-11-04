/* Copyright 2026. SPDX-License-Identifier: Apache-2.0 */
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_PATH_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_PATH_H_

#include <stddef.h>
#include <sys/stat.h>

#if defined(__GNUC__)
#pragma GCC visibility push(hidden)
#endif

namespace berberis::proc_maps_provenance::path {

constexpr size_t kPathBytes = 4096;

// A kernel-mediated copy; never dereference the guest pathname in host code.
int CopyFromCaller(const char* source, char (&destination)[kPathBytes]);

struct CallerView {
  char thread_label[96]{};
  struct stat thread_self{};
};

// Capture on the original caller. The label is the actual canonical procfs
// mount's PID view, not an assumption about the process's PID namespace.
int CaptureCallerView(CallerView* view);

// Private-table operation only. Resolve O_PATH with the caller's real dirfd
// and thread-self semantics, including ordinary symlink aliases. Final links
// remain links when follow_final=false; an empty path is not accepted here.
// A final descriptor belongs exclusively to this owner's table.
int Resolve(int caller_pidfd, int caller_dirfd, const char* copied_path,
            const CallerView& view, bool follow_final);

}  // namespace berberis::proc_maps_provenance::path
#if defined(__GNUC__)
#pragma GCC visibility pop
#endif
#endif
