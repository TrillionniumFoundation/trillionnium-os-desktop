// Actual owner source, without identity/context seams. This environment's
// UID 0 must continue to be refused; this is not a positive metadata test.
#include "berberis/kernel_api/proc_maps_raw_metadata_owner.h"
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <signal.h>
#include <sys/syscall.h>
#include <unistd.h>

namespace owner=berberis::proc_maps_provenance::raw_metadata_owner;
int main() {
  if(getuid()!=0 || geteuid()!=0) {
    std::puts("{\"state\":\"SETUP_NOT_UID0\",\"production_positive\":false}");return 3;
  }
  uint64_t before=0,after=0;
  if(syscall(SYS_rt_sigprocmask,0L,nullptr,&before,8L)!=0)return 2;
  errno=193;
  const int prepare=owner::PrepareInheritedStack();
  const int prepare_errno=errno;
  const bool both_stacks=owner::HasInheritedStack();
  errno=194;
  const int start=owner::Start();
  const int start_errno=errno;
  owner::Snapshot snapshot;
  std::memset(reinterpret_cast<unsigned char*>(&snapshot),0xa5,sizeof(snapshot));
  unsigned char preimage[sizeof(snapshot)];std::memcpy(preimage,&snapshot,sizeof(preimage));
  errno=195;
  const int read=owner::Read(STDOUT_FILENO,&snapshot);
  const int read_errno=errno;
  const bool untouched=std::memcmp(&snapshot,preimage,sizeof(snapshot))==0;
  const bool enabled=owner::Enabled();
  const int quiesce=owner::QuiesceBeforeTransition();
  errno=196;
  const int restart=owner::Start();
  const int restart_errno=errno;
  const int stop=owner::Stop();
  if(syscall(SYS_rt_sigprocmask,0L,nullptr,&after,8L)!=0)return 2;
  const bool okay=prepare==0 && prepare_errno==193 && both_stacks && start==-1 && start_errno==EPERM &&
      read==-1 && read_errno==ESHUTDOWN && untouched && !enabled && quiesce==0 &&
      restart==-1 && restart_errno==ESHUTDOWN && stop==0 && before==after;
  std::printf("{\"state\":\"%s\",\"prepare\":%d,\"prepare_errno\":%d,\"both_stacks\":%s,"
              "\"root_start\":%d,\"root_start_errno\":%d,\"closed_read\":%d,\"closed_read_errno\":%d,"
              "\"output_untouched\":%s,\"enabled\":%s,\"quiesce\":%d,\"restart\":%d,"
              "\"restart_errno\":%d,\"stop\":%d,\"signal_mask_preserved\":%s,"
              "\"identity_seams\":false,\"positive_owner_execution\":false,\"production_ready\":false}\n",
              okay?"ACTUAL_SOURCE_NEGATIVE_GATES_PASS":"FAIL",prepare,prepare_errno,both_stacks?"true":"false",
              start,start_errno,read,read_errno,untouched?"true":"false",enabled?"true":"false",quiesce,
              restart,restart_errno,stop,before==after?"true":"false");
  return okay?0:1;
}
