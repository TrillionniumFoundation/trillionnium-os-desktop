// SPDX-License-Identifier: Apache-2.0
#include <cstdarg>
#include <cstdio>
#include "raw_owner_cases.cc"

static char probe_result[32768];
static size_t result_used;
static bool result_overflow;
static void Append(const char* format,...) {
  if(result_overflow)return;
  va_list arguments;va_start(arguments,format);
  const int count=vsnprintf(probe_result+result_used,sizeof(probe_result)-result_used,format,arguments);
  va_end(arguments);
  if(count<0 || static_cast<size_t>(count)>=sizeof(probe_result)-result_used) {
    result_overflow=true;return;
  }
  result_used+=static_cast<size_t>(count);
}
static int RunOwnedRawOwner() {
  struct sigaction action{};
  if(sigaction(SIGCHLD,nullptr,&action)<0 || action.sa_handler!=SIG_DFL ||
     (action.sa_flags&SA_NOCLDWAIT)!=0)return 80;
  raw_details=static_cast<RawDetails*>(mmap(nullptr,sizeof(RawDetails),PROT_READ|PROT_WRITE,
                                          MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(raw_details==MAP_FAILED)return 81;
  constexpr unsigned expected=sizeof(kRawCases)/sizeof(kRawCases[0]);
  unsigned observed=0,started=0,reaped_count=0,nested_started=0,nested_reaped=0;
  uint64_t observed_mask=0;
  bool all=true,any_timeout=false,total_timeout=false;
  const int64_t began=RawNow();
  if(began<0)return 82;
  result_used=0;result_overflow=false;
  Append("{\"probe\":\"owned_fixed_raw_metadata_r17\",\"cases\":[");
  for(const RawCase& test:kRawCases) {
    const int64_t now=RawNow();
    if(now<0 || now-began>=15000){all=false;total_timeout=true;break;}
    *raw_details=RawDetails{};
    const pid_t parent=getpid(),child=fork();
    if(child<0){all=false;break;}
    if(child==0)_exit(RawGuard(parent) && test.function()?0:1);
    ++started;
    int status=0;bool timeout=false;
    const bool reaped=RawWaitOwned(child,3000,&status,&timeout);
    if(reaped)++reaped_count;
    const bool pass=reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0;
    const RawDetails& d=*raw_details;
    nested_started+=d.nested_started?1:0;
    nested_reaped+=d.nested_started&&d.child_reaped?1:0;
    if(pass)observed_mask|=UINT64_C(1)<<observed;
    Append("%s{\"case\":\"%s\",\"expected_behavior_observed\":%s,\"known_production_red\":%s,"
           "\"direct_child_reaped\":%s,\"timeout\":%s,\"signal\":%d,\"exit\":%d,\"setup\":%d,"
           "\"native_stat\":%d,\"native_fs\":%d,\"start\":%d,\"start_errno\":%d,"
           "\"read\":%d,\"read_errno\":%d,\"stop\":%d,\"worker_tid_cleared\":%d,"
           "\"inherited_stack\":%d,\"child_finished\":%d,\"nested_child_started\":%d,"
           "\"nested_child_reaped\":%d,\"nested_timeout\":%d,\"nested_status\":%d,"
           "\"parent_read\":%d,\"parent_stop\":%d,\"parent_fd_survived\":%d,"
           "\"joined_rounds\":%d,\"errno_preserved\":%d,\"mask_preserved\":%d}",
           observed?",":"",test.name,pass?"true":"false",test.known_red?"true":"false",
           reaped?"true":"false",timeout?"true":"false",
           reaped&&WIFSIGNALED(status)?WTERMSIG(status):0,
           reaped&&WIFEXITED(status)?WEXITSTATUS(status):-1,d.setup,d.native_stat,d.native_fs,
           d.start,d.start_error,d.read,d.read_error,d.stop,d.worker_tid_cleared,d.inherited_stack,
           d.child_finished,d.nested_started,d.child_reaped,d.child_timeout,d.child_status,
           d.parent_read,d.parent_stop,d.parent_fd_survived,d.joined_rounds,d.errno_preserved,d.mask_preserved);
    ++observed;all=all&&pass;any_timeout=any_timeout||timeout||d.child_timeout;
    if(timeout || !reaped)break;
  }
  const bool pass=all && observed==expected && observed_mask==((UINT64_C(1)<<expected)-1);
  const bool reaped=started==reaped_count && nested_started==nested_reaped && !any_timeout;
  Append("],\"pass\":%s,\"child_reaped\":%s,\"direct_children_started\":%u,"
         "\"direct_children_reaped\":%u,\"nested_children_started\":%u,\"nested_children_reaped\":%u,"
         "\"expected_cases\":%u,\"observed_cases\":%u,\"expected_behavior_mask\":\"0x%016llx\","
         "\"timeout\":%s,\"application_uid\":%u,",
         pass?"true":"false",reaped?"true":"false",started,reaped_count,nested_started,nested_reaped,
         expected,observed,static_cast<unsigned long long>(observed_mask),
         (any_timeout||total_timeout)?"true":"false",static_cast<unsigned>(getuid()));
  Append("\"scope\":\"fixed raw-syscall metadata primitive with an owned tag; no provenance projection\","
         "\"source_worker_has_arbitrary_callback\":false,\"host_copy_seam\":false,"
         "\"fault_injections\":[],\"rawfork_inflight_request_covered\":false,"
         "\"full_provenance_tested\":false,\"runtime_hooks_installed\":false,"
         "\"candidate_production_ready\":false,\"broker_positive_identity_tested\":false,"
         "\"known_reds\":[\"NOFILE0 remains EMFILE\",\"task-count and kernel-resource limits remain\","
         "\"host cancellation and credential/root/mount transitions unqualified\","
         "\"full provenance and pathname operations not integrated\",\"runtime lifecycle hooks absent\"]}");
  munmap(raw_details,sizeof(RawDetails));raw_details=nullptr;
  if(result_overflow)return 83;
  return pass?0:1;
}

int main(){const int result=RunOwnedRawOwner();puts(probe_result);return result;}
