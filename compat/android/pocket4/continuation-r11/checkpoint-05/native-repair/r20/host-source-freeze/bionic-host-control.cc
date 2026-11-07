#include <sys/statfs.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <linux/capability.h>
// This host control compiles the exact pinned Bionic wrapper body with its
// public functions in a separate namespace; only the syscall stubs and strong
// alias declarations are supplied by the host fixture.
extern "C" int __fstatfs(int fd, struct statfs* out) {
  return static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),out));
}
extern "C" int __statfs(const char* path, struct statfs* out) {
  return static_cast<int>(syscall(SYS_statfs,path,out));
}
#define __strong_alias(alias, original) static_assert(true)
namespace r20_bionic_reference {
#include "references/sys_statfs.cpp"
}
#undef __strong_alias
extern "C" int __wrap_fstatfs(int fd, struct statfs* out) {
  return r20_bionic_reference::fstatfs(fd,out);
}
extern "C" int __wrap_statfs(const char* path, struct statfs* out) {
  return r20_bionic_reference::statfs(path,out);
}
#include "owner_probe.cpp"
int main() {
  struct __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3,0};
  struct __user_cap_data_struct caps[2]{};
  if(syscall(SYS_capset,&header,caps)<0 || syscall(SYS_capget,&header,caps)<0)return 90;
  for(const auto& cap:caps)if(cap.effective||cap.permitted||cap.inheritable)return 91;
  const int result=RunOwnedMetadata();
  std::puts(probe_result);
  return result;
}
