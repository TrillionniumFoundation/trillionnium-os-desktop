// SPDX-License-Identifier: Apache-2.0
#ifndef BERBERIS_KERNEL_API_PROC_MAPS_SNAPSHOT_REOPEN_H_
#define BERBERIS_KERNEL_API_PROC_MAPS_SNAPSHOT_REOPEN_H_

#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/syscall.h>
#include <unistd.h>

namespace droidloom::proc_maps_factory {

// Only the trusted factory's own freshly created, held and sealed memfd may
// reach this helper. It never accepts a file handle or mount identifier from
// the peer. Callers retain their complete final inode, seal, tag, offset and
// exact F_GETFL checks before publication.
//
// A proc-fd magic link cannot be opened with O_NOFOLLOW. Reopening the same
// inode by its kernel-produced handle avoids that lookup and preserves the
// actual file-status bit. In particular, do not clear the bit or simulate it
// in a returned status value. Kernel support and the factory's existing
// CAP_DAC_READ_SEARCH are required; this entry never changes credentials or
// policy, and propagates failures without a different opening fallback.
inline int ReopenOwnSnapshotByHandle(int descriptor, int status_flags) {
  if (!(status_flags & O_NOFOLLOW) ||
      (status_flags & (O_ACCMODE | O_PATH)) != O_RDONLY) {
    errno = EINVAL;
    return -1;
  }
#if defined(SYS_name_to_handle_at) && defined(SYS_open_by_handle_at)
  // Linux struct file_handle ABI, with the fixed MAX_HANDLE_SZ bound. Avoid a
  // C++ flexible-array extension or relying on a libc struct declaration.
  struct Handle {
    uint32_t bytes;
    int32_t type;
    unsigned char data[128];
  } handle{};
  static_assert(offsetof(Handle, data) == 8 && sizeof(Handle) == 136);
  handle.bytes = sizeof(handle.data);
  int mount_id = 0;
  if (syscall(SYS_name_to_handle_at, static_cast<long>(descriptor), "", &handle,
              &mount_id, static_cast<unsigned long>(AT_EMPTY_PATH)) < 0) return -1;
  if (!handle.bytes || handle.bytes > sizeof(handle.data) || handle.type < 0) {
    errno = EPROTO;
    return -1;
  }
  // The internal shmem mount can have legacy mount_id zero. The same held
  // descriptor supplies the mount; no mount-table/path reconstruction occurs.
  return static_cast<int>(syscall(SYS_open_by_handle_at, static_cast<long>(descriptor),
                                  &handle, static_cast<unsigned long>(
                                      static_cast<unsigned int>(status_flags | O_CLOEXEC))));
#else
  errno = ENOSYS;
  return -1;
#endif
}

}  // namespace droidloom::proc_maps_factory
#endif  // BERBERIS_KERNEL_API_PROC_MAPS_SNAPSHOT_REOPEN_H_
