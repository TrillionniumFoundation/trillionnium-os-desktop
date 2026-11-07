// SPDX-License-Identifier: Apache-2.0
#ifndef DROIDLOOM_NATIVE_GENERATION_PROTOCOL_V1_H_
#define DROIDLOOM_NATIVE_GENERATION_PROTOCOL_V1_H_
#include <stdint.h>
// Private platform/engine protocol. Does not extend NativeBridgeCallbacks.
namespace droidloom::native_generation {
inline constexpr uint32_t kVersion=1;
inline constexpr uint64_t kProtocol0=UINT64_C(0x444c4f4f4d474531);
inline constexpr uint64_t kProtocol1=UINT64_C(0x50524f434d455431);
inline constexpr char kEngineSymbol[]="DroidloomBerberisGenerationV1";
enum Operation : uint32_t {
  kPrepareMemory=1, kBeforeZygoteFork=2, kAfterSpecialize=3, kBeforeUnload=4, kCheckReady=5
};
enum Flag : uint32_t {kPrivateForkChild=1, kChildZygote=2};
struct Request {
  uint32_t version, size, operation, flags;
  int32_t caller_tgid, previous_tgid;
  uint64_t protocol0, protocol1;
};
static_assert(sizeof(Request)==40);
using Entry=int(*)(const Request*);
inline Request MakeRequest(Operation operation,uint32_t flags,int32_t caller,int32_t previous) {
  return {kVersion,sizeof(Request),operation,flags,caller,previous,kProtocol0,kProtocol1};
}
}
#endif
