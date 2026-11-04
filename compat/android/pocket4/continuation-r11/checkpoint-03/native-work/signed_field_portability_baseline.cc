// SPDX-License-Identifier: Apache-2.0
// The actual source's private conversion templates are exercised directly.
// unsigned long models the Bionic x86_64 field that rejected r13 compilation;
// long models its glibc counterpart. No memory-copy or kernel behavior is mocked.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <type_traits>
#include "copy-word-snapshot-03/kernel_api/proc_maps_provenance.cc"
namespace p=berberis::proc_maps_provenance;

static unsigned cases=0,failures=0;
template<typename T>
static void Check(const char* name,int64_t number,bool accepted,T expected=T{}) {
  uint64_t wire;memcpy(&wire,&number,sizeof(wire));
  const T canary=static_cast<T>(37);T result=canary;
  const bool actual=p::SignedField(wire,&result);
  const bool pass=actual==accepted && result==(accepted?expected:canary);
  printf("{\"case\":\"%s\",\"target_bits\":%zu,\"target_signed\":%s,\"pass\":%s}\n",
         name,sizeof(T)*8,std::is_signed_v<T>?"true":"false",pass?"true":"false");
  ++cases;if(!pass)++failures;
}
int main() {
  static_assert(sizeof(long)==8 && sizeof(unsigned long)==8);
  Check<long>("glibc_long_4096",4096,true,4096);
  Check<unsigned long>("bionic_ulong_4096",4096,true,4096);
  Check<unsigned long>("bionic_ulong_zero",0,true,0);
  Check<unsigned long>("bionic_ulong_high32",INT64_C(4294967296),true,static_cast<unsigned long>(UINT64_C(4294967296)));
  Check<long>("glibc_long_negative_preserved",-1,true,-1);
  Check<unsigned long>("bionic_ulong_negative_rejected",-1,false);
  Check<long>("signed64_min",INT64_MIN,true,static_cast<long>(INT64_MIN));
  Check<long>("signed64_max",INT64_MAX,true,static_cast<long>(INT64_MAX));
  Check<unsigned long>("unsigned64_signed_wire_max",INT64_MAX,true,static_cast<unsigned long>(INT64_MAX));
  Check<unsigned long>("unsigned64_minwire_negative_rejected",INT64_MIN,false);
  Check<int32_t>("signed32_min",INT32_MIN,true,INT32_MIN);
  Check<int32_t>("signed32_max",INT32_MAX,true,INT32_MAX);
  Check<int32_t>("signed32_below_min",static_cast<int64_t>(INT32_MIN)-1,false);
  Check<int32_t>("signed32_above_max",static_cast<int64_t>(INT32_MAX)+1,false);
  Check<uint32_t>("unsigned32_max",UINT32_MAX,true,UINT32_MAX);
  Check<uint32_t>("unsigned32_overflow",static_cast<int64_t>(UINT32_MAX)+1,false);
  Check<uint32_t>("unsigned32_negative",-1,false);
  Check<int8_t>("signed8_min",-128,true,-128);
  Check<int8_t>("signed8_max",127,true,127);
  Check<int8_t>("signed8_underflow",-129,false);
  Check<int8_t>("signed8_overflow",128,false);
  Check<uint8_t>("unsigned8_zero",0,true,0);
  Check<uint8_t>("unsigned8_max",255,true,255);
  Check<uint8_t>("unsigned8_overflow",256,false);
  Check<uint8_t>("unsigned8_negative",-1,false);
  p::Origin origin{};
  origin.words[p::kFsType]=PROC_SUPER_MAGIC;
  origin.words[p::kFsBlockSize]=4096;
  origin.words[p::kFsFragmentSize]=4096;
  origin.words[p::kFsNameLength]=255;
  struct statfs decoded{};
  const bool decoded_ok=p::DecodeStatfs(origin,&decoded) && decoded.f_bsize==4096 &&
                        decoded.f_frsize==4096 && decoded.f_namelen==255;
  printf("{\"case\":\"actual_native_statfs_decode\",\"pass\":%s}\n",decoded_ok?"true":"false");
  ++cases;if(!decoded_ok)++failures;
  printf("{\"cases\":%u,\"failures\":%u,\"android_ndk_compile_claimed\":false}\n",cases,failures);
  return failures?1:0;
}
