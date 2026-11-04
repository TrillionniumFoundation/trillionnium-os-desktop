// SPDX-License-Identifier: Apache-2.0
#include "raw_owner_cases.cc"
int main() {
  setvbuf(stdout,nullptr,_IONBF,0);
  struct sigaction action{};
  if(sigaction(SIGCHLD,nullptr,&action)<0 || action.sa_handler!=SIG_DFL ||
     (action.sa_flags&SA_NOCLDWAIT))return 70;
  raw_details=static_cast<RawDetails*>(mmap(nullptr,sizeof(RawDetails),PROT_READ|PROT_WRITE,
                                          MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(raw_details==MAP_FAILED)return 71;
  bool all=true;
  for(const RawCase& test:kRawCases) {
    *raw_details=RawDetails{};
    const pid_t parent=getpid(),child=fork();
    if(child<0)return 72;
    if(child==0)_exit(RawGuard(parent) && test.function()?0:1);
    int status=0;bool timeout=false;
    const bool reaped=RawWaitOwned(child,3000,&status,&timeout);
    const bool pass=reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0;
    const RawDetails& d=*raw_details;
    printf("{\"case\":\"%s\",\"expected_behavior_observed\":%s,\"known_production_red\":%s,"
           "\"direct_child_reaped\":%s,\"timeout\":%s,\"status\":%d,\"setup\":%d,"
           "\"native_stat\":%d,\"native_fs\":%d,\"start\":%d,\"start_errno\":%d,"
           "\"read\":%d,\"read_errno\":%d,\"stop\":%d,\"worker_tid_cleared\":%d,"
           "\"inherited_stack\":%d,\"child_finished\":%d,\"nested_child_reaped\":%d,"
           "\"nested_timeout\":%d,\"nested_status\":%d,\"parent_read\":%d,"
           "\"parent_stop\":%d,\"parent_fd_survived\":%d,\"joined_rounds\":%d,"
           "\"errno_preserved\":%d,\"mask_preserved\":%d}\n",
           test.name,pass?"true":"false",test.known_red?"true":"false",reaped?"true":"false",
           timeout?"true":"false",status,d.setup,d.native_stat,d.native_fs,d.start,d.start_error,
           d.read,d.read_error,d.stop,d.worker_tid_cleared,d.inherited_stack,d.child_finished,
           d.child_reaped,d.child_timeout,d.child_status,d.parent_read,d.parent_stop,
           d.parent_fd_survived,d.joined_rounds,d.errno_preserved,d.mask_preserved);
    all=all && pass;
    if(timeout || !reaped)break;
  }
  munmap(raw_details,sizeof(RawDetails));return all?0:1;
}
