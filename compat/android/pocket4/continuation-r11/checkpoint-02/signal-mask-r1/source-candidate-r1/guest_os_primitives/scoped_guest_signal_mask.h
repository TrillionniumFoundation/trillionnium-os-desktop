/* Copyright 2026 Droidloom contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef BERBERIS_GUEST_OS_PRIMITIVES_SCOPED_GUEST_SIGNAL_MASK_H_
#define BERBERIS_GUEST_OS_PRIMITIVES_SCOPED_GUEST_SIGNAL_MASK_H_

#include <signal.h>
#include <cstdint>
#include <cstring>

#include "berberis/base/host_signal.h"

namespace berberis {

// A guest handler's saved mask is the interrupted mask, before sa_mask and
// the optional self bit are applied. A host signal frame already has those
// temporary bits in its live mask, so that frame must supply its saved mask.
// Deferred delivery outside a host signal frame instead captures the mask at
// its real guest-delivery point. No frame pointer is retained past this scope.
class ScopedGuestSignalMask {
 public:
  ScopedGuestSignalMask(const HostSigset* action_mask, HostSigset* host_resume_mask)
      : host_resume_mask_(host_resume_mask) {
    if (host_resume_mask_) {
      interrupted_mask_ = ReadKernelMask(host_resume_mask_);
      HostSigset live_mask{};
      WriteKernelMask(&live_mask, interrupted_mask_ | ReadKernelMask(action_mask));
      RTSigprocmaskSyscallOrDie(SIG_SETMASK, &live_mask, &restore_live_mask_);
    } else {
      RTSigprocmaskSyscallOrDie(SIG_BLOCK, action_mask, &restore_live_mask_);
      interrupted_mask_ = ReadKernelMask(&restore_live_mask_);
    }
  }

  ScopedGuestSignalMask(const ScopedGuestSignalMask&) = delete;
  ScopedGuestSignalMask& operator=(const ScopedGuestSignalMask&) = delete;

  ~ScopedGuestSignalMask() {
    RTSigprocmaskSyscallOrDie(SIG_SETMASK, &restore_live_mask_, nullptr);
  }

  uint64_t interrupted_mask() const { return interrupted_mask_; }

  void Commit(uint64_t guest_resume_mask) {
    // Linux set_current_blocked() never permits SIGKILL or SIGSTOP in the
    // restored mask, including masks edited in a user signal frame.
    constexpr uint64_t kUnblockable =
        (uint64_t{1} << (SIGKILL - 1)) | (uint64_t{1} << (SIGSTOP - 1));
    guest_resume_mask &= ~kUnblockable;
    if (host_resume_mask_) {
      // Keep the host handler's temporary live mask until host sigreturn.
      // Only the kernel's low 64 bits belong to this contract; glibc exposes
      // a larger sigset_t and its trailing bytes must not be overwritten.
      WriteKernelMask(host_resume_mask_, guest_resume_mask);
    } else {
      WriteKernelMask(&restore_live_mask_, guest_resume_mask);
    }
  }

 private:
  static uint64_t ReadKernelMask(const HostSigset* mask) {
    static_assert(sizeof(HostSigset) >= sizeof(uint64_t));
    uint64_t value;
    std::memcpy(&value, mask, sizeof(value));
    return value;
  }
  static void WriteKernelMask(HostSigset* mask, uint64_t value) {
    std::memcpy(mask, &value, sizeof(value));
  }

  HostSigset* host_resume_mask_;
  HostSigset restore_live_mask_{};
  uint64_t interrupted_mask_ = 0;
};

}  // namespace berberis
#endif
