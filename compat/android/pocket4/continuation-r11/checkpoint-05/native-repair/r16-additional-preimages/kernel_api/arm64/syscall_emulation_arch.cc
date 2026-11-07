// Modified by the Droidloom contributors in 2026; see Git history and NOTICE.

/*
 * Copyright (C) 2026 utzcoz
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

#include <signal.h>
#include <sys/ptrace.h>
#include <sys/stat.h>

#include <cstddef>
#include <tuple>

#include "berberis/base/tracing.h"
#include "berberis/guest_state/guest_addr.h"
#include "berberis/kernel_api/fcntl_emulation.h"
#include "berberis/kernel_api/sys_ptrace_emulation.h"

#include "arm64/guest_types.h"
#include "arm64/ptrace_regset.h"

namespace berberis {

std::tuple<bool, int> GuestFcntlArch(int, int, long) {
  return {false, -1};
}

std::tuple<bool, int> PtraceForGuestArch(int request, pid_t pid, void* addr, void* data) {
  // ARM64 and x86_64 share the Linux LP64 siginfo/event-message layout.
  // Forward the actual query, including kernel pointer/permission checks.
  // Emulated BRK supplies guest fault metadata before the ptrace stop, so
  // GETSIGINFO must not turn it back into a host software-signal description.
  // Register-set requests remain separate: host registers are NOT guest GPRs.
  static_assert(sizeof(long) == 8);
  static_assert(sizeof(siginfo_t) == 128);
  switch (request) {
    case PTRACE_GETREGSET:
    case PTRACE_SETREGSET: {
      int result = PtraceRegsetForGuestArm64(request, pid, addr, data);
      int saved_errno = errno;
      TRACE("ARM64 ptrace regset result: request=0x%x tid=%d note=%p result=%d errno=%d",
            request, pid, addr, result, result < 0 ? saved_errno : 0);
      errno = saved_errno;
      return {true, result};
    }
    case PTRACE_GETSIGINFO:
    case PTRACE_GETEVENTMSG:
#if defined(__GLIBC__)
      return {true, ptrace(static_cast<enum __ptrace_request>(request), pid, addr, data)};
#else
      return {true, ptrace(request, pid, addr, data)};
#endif
  }
  return {false, -1};
}

void ConvertHostStatToGuestArch(const struct stat& host_stat, GuestAddr guest_addr) {
  auto* guest_stat = ToHostAddr<Guest_stat>(guest_addr);
  guest_stat->st_dev = host_stat.st_dev;
  guest_stat->st_ino = host_stat.st_ino;
  guest_stat->st_mode = host_stat.st_mode;
  guest_stat->st_nlink = host_stat.st_nlink;
  guest_stat->st_uid = host_stat.st_uid;
  guest_stat->st_gid = host_stat.st_gid;
  guest_stat->st_rdev = host_stat.st_rdev;
  guest_stat->st_size = host_stat.st_size;
  guest_stat->st_blksize = host_stat.st_blksize;
  guest_stat->st_blocks = host_stat.st_blocks;
  guest_stat->st_atim = host_stat.st_atim;
  guest_stat->st_mtim = host_stat.st_mtim;
  guest_stat->st_ctim = host_stat.st_ctim;
}

}  // namespace berberis
