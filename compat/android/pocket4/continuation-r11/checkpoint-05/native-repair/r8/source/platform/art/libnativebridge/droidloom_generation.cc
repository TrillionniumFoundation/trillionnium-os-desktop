// SPDX-License-Identifier: Apache-2.0
#include "droidloom_generation.h"
#include "nativebridge/droidloom_generation_protocol.h"
#include <dlfcn.h>
#include <errno.h>
#include <sys/syscall.h>
#include <unistd.h>
namespace android::droidloom_generation {
namespace {
using namespace droidloom::native_generation;
Entry entry=nullptr;
int process=0,last_error=0;
int CurrentProcess() {return static_cast<int>(syscall(SYS_getpid));}
bool Invoke(Operation operation,bool allow_private_child) {
  if(entry==nullptr){last_error=EPROTONOSUPPORT;return false;}
  const int current=CurrentProcess();
  const uint32_t flags=allow_private_child && current!=process?static_cast<uint32_t>(kPrivateForkChild):0u;
  const Request request=MakeRequest(operation,flags,current,process);
  const int result=entry(&request);
  last_error=result<0?-result:(result==0?0:EPROTO);
  return result==0;
}
}
bool Prepare(void* handle) {
#if DROIDLOOM_NATIVE_GENERATION_RUNTIME
  if(handle==nullptr || entry!=nullptr){last_error=EPROTO;return false;}
  entry=reinterpret_cast<Entry>(dlsym(handle,kEngineSymbol));
  if(entry==nullptr){last_error=EPROTONOSUPPORT;return false;}
  const int current=CurrentProcess();
  const Request request=MakeRequest(kPrepareMemory,0,current,0);
  const int result=entry(&request);
  last_error=result<0?-result:(result==0?0:EPROTO);
  if(result!=0){entry=nullptr;return false;}
  process=current;return true;
#else
  (void)handle;(void)&Invoke;return true;
#endif
}
bool BeforeFork() {
#if DROIDLOOM_NATIVE_GENERATION_RUNTIME
  return Invoke(kBeforeZygoteFork,false);
#else
  return true;
#endif
}
bool AfterSpecialize() {
#if DROIDLOOM_NATIVE_GENERATION_RUNTIME
  if(!Invoke(kAfterSpecialize,true))return false;
  process=CurrentProcess();return true;
#else
  return true;
#endif
}
bool BeforeUnload() {
#if DROIDLOOM_NATIVE_GENERATION_RUNTIME
  if(!Invoke(kBeforeUnload,true))return false;
  entry=nullptr;process=0;return true;
#else
  return true;
#endif
}
bool RequireReady() {
#if DROIDLOOM_NATIVE_GENERATION_RUNTIME
  return Invoke(kCheckReady,false);
#else
  return true;
#endif
}
int LastError() {return last_error;}
}
extern "C" __attribute__((visibility("default"),used,retain)) const char DroidloomArtGenerationMarker[]=
#if DROIDLOOM_NATIVE_GENERATION_RUNTIME
  "DROIDLOOM_NATIVE_GENERATION=1;ROLE=ART_BRIDGE;ABI=1;PROTOCOL=DLOOMGE1-PROCMET1;";
#else
  "DROIDLOOM_NATIVE_GENERATION=0;ROLE=ART_BRIDGE;ABI=1;PROTOCOL=DLOOMGE1-PROCMET1;";
#endif
