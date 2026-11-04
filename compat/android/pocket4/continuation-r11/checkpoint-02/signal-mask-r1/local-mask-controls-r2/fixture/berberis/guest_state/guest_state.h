
#pragma once
#include <cstdint>
namespace berberis {
using GuestAddr = uintptr_t;
template<class T> inline T* ToHostAddr(GuestAddr p) { return reinterpret_cast<T*>(p); }
template<class T> inline GuestAddr ToGuestAddr(T* p) { return reinterpret_cast<GuestAddr>(p); }
// Fixture storage only. No translator, assembly or real CPUState ABI is claimed.
struct CPUState {
  uint64_t x[31]{}, sp = 0, insn_addr = 0;
  uint16_t flags = 0;
  uint32_t emulated_fpsr = 0, cached_fpcr = 0;
  __uint128_t v[32]{};
  static constexpr uint16_t kFlagNegative=0x8000, kFlagZero=0x4000;
  static constexpr uint16_t kFlagCarry=0x0100, kFlagOverflow=0x0001;
};
constexpr uint16_t kFlagsNZCVMask = 0xc101;
struct ThreadState { CPUState cpu; };
inline CPUState& GetCPUState(ThreadState& state) { return state.cpu; }
inline GuestAddr GetStackRegister(const CPUState& cpu) { return cpu.sp; }
inline GuestAddr GetInsnAddr(const CPUState& cpu) { return cpu.insn_addr; }
}
