
#pragma once
#include <csignal>
#include <cstring>
#include "berberis/base/host_signal.h"
#include "berberis/base/struct_check.h"
#include "berberis/guest_os_primitives/guest_thread.h"
namespace berberis {
using Guest_siginfo_t = siginfo_t;
struct Guest_sigset_t { uint64_t bits[1]; };
constexpr GuestAddr Guest_SIG_DFL=0, Guest_SIG_IGN=1, Guest_SIG_ERR=~GuestAddr{0};
template<class S, class B> void ConvertToBigSigset(const S& small, B* big) {
  static_assert(sizeof(S)<=sizeof(B)); std::memset(big,0,sizeof(B)); std::memcpy(big,&small,sizeof(S));
}
struct Guest_sigaction;
#if CANDIDATE
void ProcessGuestSignal(GuestThread*, const Guest_sigaction*, Guest_siginfo_t*);
void ProcessGuestSignal(GuestThread*, const Guest_sigaction*, Guest_siginfo_t*, HostSigset*);
#else
void ProcessGuestSignal(GuestThread*, const Guest_sigaction*, Guest_siginfo_t*);
#endif
}
