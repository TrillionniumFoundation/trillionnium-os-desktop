
#pragma once
#include <cstdint>
#include <signal.h>
#include "berberis/guest_state/guest_state.h"
namespace berberis {
void FixtureGuestHandler(GuestAddr, int, siginfo_t*, void*);
class GuestCall {
 public:
  void AddArgInt32(int signal) { signal_=signal; }
  void AddArgGuestAddr(GuestAddr address) { args_[count_++]=address; }
  void RunVoid(GuestAddr handler) {
    FixtureGuestHandler(handler,signal_,reinterpret_cast<siginfo_t*>(args_[0]),reinterpret_cast<void*>(args_[1]));
  }
 private:
  int signal_=0, count_=0;
  GuestAddr args_[2]{};
};
}
