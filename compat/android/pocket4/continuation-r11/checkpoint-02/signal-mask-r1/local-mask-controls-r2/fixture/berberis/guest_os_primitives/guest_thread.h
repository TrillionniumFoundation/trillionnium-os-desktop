
#pragma once
#include "berberis/guest_state/guest_state.h"
namespace berberis {
class GuestThread {
 public:
  ThreadState* state() { return &state_; }
  void SwitchToSigAltStack() {}
 private:
  ThreadState state_;
};
}
