// SPDX-License-Identifier: Apache-2.0
#ifndef DROIDLOOM_PROC_MAPS_FACTORY_CONTEXT_H_
#define DROIDLOOM_PROC_MAPS_FACTORY_CONTEXT_H_
#include <stddef.h>
#include <stdint.h>
namespace droidloom::proc_maps_factory {
inline constexpr size_t kMaxNamespaceDepth=32;
struct ProcessStatus {
  uint32_t uid[4]{},gid[4]{};
  uint64_t inheritable{},permitted{},effective{},ambient{};
  uint32_t tgid{};
  uint32_t namespace_tgids[kMaxNamespaceDepth]{},namespace_pids[kMaxNamespaceDepth]{};
  size_t tgid_depth{},pid_depth{};
};
bool ParseStatus(const char* text,size_t size,ProcessStatus* result);
bool ParseStartTicks(const char* text,size_t size,uint32_t expected_pid,uint64_t* result);
bool SameAuthority(const ProcessStatus& a,const ProcessStatus& b);
bool Unprivileged(const ProcessStatus& status,uint32_t uid,uint32_t gid);
bool ParseDecimal(const char* text,size_t size,uint64_t maximum,uint64_t* value);
}  // namespace droidloom::proc_maps_factory
#endif
