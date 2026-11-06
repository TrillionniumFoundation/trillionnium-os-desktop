/*
 * Copyright (C) 2014 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "berberis/kernel_api/unistd_emulation.h"

#include <fcntl.h>  // AT_FDCWD, AT_SYMLINK_NOFOLLOW

#include <cerrno>
#include <cstring>  // memcpy

#include "berberis/kernel_api/main_executable_real_path_emulation.h"
#if defined(NATIVE_BRIDGE_GUEST_ARCH_ARM64) && defined(__x86_64__)
#include "berberis/kernel_api/proc_maps_path.h"
#include "berberis/kernel_api/proc_maps_provenance.h"
#include "berberis/kernel_api/proc_maps_raw_metadata_owner.h"
#endif

namespace berberis {

ssize_t ReadLinkAtForGuest(int dirfd, const char* path, char* buf, size_t buf_size) {
#if defined(NATIVE_BRIDGE_GUEST_ARCH_ARM64) && defined(__x86_64__) && \
    BERBERIS_PROCMAPS_RAW_METADATA_OWNER
  const int before = errno;
  const int32_t kernel_size = static_cast<int32_t>(static_cast<uint32_t>(buf_size));
  if (kernel_size <= 0) { errno = EINVAL; return -1; }
  char copied_path[proc_maps_provenance::path::kPathBytes];
  if (proc_maps_provenance::path::CopyFromCaller(path, copied_path) < 0) return -1;
  const char* translated = (dirfd == AT_FDCWD || copied_path[0] == '/')
      ? TryReadLinkToMainExecutableRealPath(copied_path) : nullptr;
  if (translated != nullptr) {
    size_t count = strlen(translated);
    if (count > static_cast<size_t>(kernel_size)) count = static_cast<size_t>(kernel_size);
    if (proc_maps_provenance::CopyToCaller(translated, buf, count) < 0) return -1;
    errno = before;
    return static_cast<ssize_t>(count);
  }
  ssize_t result;
  errno = before;
  proc_maps_provenance::Readlinkat(dirfd, copied_path, buf, buf_size,
                                  proc_maps_provenance::kCandidateConfiguration, &result);
  return result;
#else
  const char* real_path = TryReadLinkToMainExecutableRealPath(path);
  if (!real_path) {
    return readlinkat(dirfd, path, buf, buf_size);
  }
  // readlink have quite unusual semantic WRT handling of buffer length.  readlink should not add
  // terminating null byte if it doesn't fit in the buffer, so can't use strlcpy. readlink should
  // return the number of bytes placed in buffer thus strncpy doesn't help.
  size_t real_path_len = strlen(real_path);
  if (real_path_len + 1 > buf_size) {
    memcpy(buf, real_path, buf_size);
    return buf_size;
  }
  memcpy(buf, real_path, real_path_len + 1);
  return real_path_len;
#endif
}

ssize_t ReadLinkForGuest(const char* path, char* buf, size_t buf_size) {
  return ReadLinkAtForGuest(AT_FDCWD, path, buf, buf_size);
}

}  // namespace berberis
