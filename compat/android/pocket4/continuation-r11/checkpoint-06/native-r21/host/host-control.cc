#include "owner_probe.cpp"
#include <linux/capability.h>
int main() {
  struct __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3,0};
  struct __user_cap_data_struct caps[2]{};
  if(syscall(SYS_capset,&header,caps)<0 || syscall(SYS_capget,&header,caps)<0)return 90;
  for(const auto& cap:caps)if(cap.effective||cap.permitted||cap.inheritable)return 91;
  const int result=RunOwnedMetadata();
  std::puts(probe_result);
  return result;
}
