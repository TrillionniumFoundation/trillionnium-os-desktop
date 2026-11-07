// SPDX-License-Identifier: Apache-2.0
#include <jni.h>
#include <cstdarg>
#include <cstdio>
#include "metadata_raw_cases.cc"

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
static int RunOwnedMetadata() {
  struct sigaction action{};
  if(sigaction(SIGCHLD,nullptr,&action)<0 || action.sa_handler!=SIG_DFL ||
     (action.sa_flags&SA_NOCLDWAIT)!=0)return 80;
  details=static_cast<MetadataDetails*>(mmap(nullptr,sizeof(MetadataDetails),PROT_READ|PROT_WRITE,
                                           MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(details==MAP_FAILED)return 81;
  constexpr unsigned expected=sizeof(kMetadataCases)/sizeof(kMetadataCases[0]);
  unsigned observed=0,started=0,reaped_count=0,nested_started=0,nested_reaped=0;
  uint64_t observed_mask=0;
  bool all=true,any_timeout=false,total_timeout=false;
  const int64_t began=Now();if(began<0)return 82;
  result_used=0;result_overflow=false;
  Append("{\"probe\":\"owned_real_metadata_r18\",\"cases\":[");
  for(const MetadataCase& test:kMetadataCases) {
    const int64_t now=Now();
    if(now<0 || now-began>=15000){all=false;total_timeout=true;break;}
    *details=MetadataDetails{};
    const pid_t parent=getpid(),child=fork();
    if(child<0){all=false;break;}
    if(child==0)_exit(Guard(parent) && test.function()?0:1);
    ++started;int status=0;bool timeout=false;
    const bool reaped=WaitOwned(child,3000,&status,&timeout);
    if(reaped)++reaped_count;
    const bool passed=reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0;
    const MetadataDetails& d=*details;
    nested_started+=d.nested_started?1:0;
    nested_reaped+=d.nested_started&&d.child_reaped?1:0;
    if(passed)observed_mask|=UINT64_C(1)<<observed;
    Append("%s{\"case\":\"%s\",\"expected_behavior_observed\":%s,\"known_production_red\":%s,"
           "\"direct_child_reaped\":%s,\"timeout\":%s,\"signal\":%d,\"exit\":%d,\"setup\":%d,"
           "\"start\":%d,\"start_errno\":%d,\"read\":%d,\"read_errno\":%d,\"stop\":%d,"
           "\"native_stat\":%d,\"native_fs\":%d,\"projected_stat\":%d,\"projected_fs\":%d,"
           "\"lookup\":%d,\"errno_preserved\":%d,\"mask_preserved\":%d,\"ordinary_tag_rejected\":%d,"
           "\"caller_uid\":%d,\"worker_uid\":%d,\"worker_tid\":%d,\"worker_tid_cleared\":%d,"
           "\"same_namespace\":%d,\"inherited_stack\":%d,\"child_finished\":%d,"
           "\"nested_child_started\":%d,\"nested_child_reaped\":%d,\"nested_timeout\":%d,"
           "\"nested_status\":%d,\"parent_read\":%d,\"parent_stop\":%d,\"parent_fd_survived\":%d,"
           "\"rounds\":%d,\"quiesce\":%d,\"restart\":%d,\"restart_errno\":%d,"
           "\"thread_error\":%d,\"thread_fdtable_checked\":%d,\"shared_vm_rejected\":%d}",
           observed?",":"",test.name,passed?"true":"false",test.known_red?"true":"false",
           reaped?"true":"false",timeout?"true":"false",
           reaped&&WIFSIGNALED(status)?WTERMSIG(status):0,
           reaped&&WIFEXITED(status)?WEXITSTATUS(status):-1,d.setup,d.start,d.start_error,
           d.read,d.read_error,d.stop,d.native_stat,d.native_fs,d.projected_stat,d.projected_fs,
           d.lookup,d.errno_preserved,d.mask_preserved,d.ordinary_tag_rejected,
           d.caller_uid,d.worker_uid,d.worker_tid,d.worker_tid_cleared,d.same_namespace,
           d.inherited_stack,d.child_finished,d.nested_started,d.child_reaped,d.child_timeout,
           d.child_status,d.parent_read,d.parent_stop,d.parent_fd_survived,d.rounds,d.quiesce,
           d.restart,d.restart_error,d.thread_error,d.thread_fdtable_checked,d.shared_vm_rejected);
    ++observed;all=all&&passed;any_timeout=any_timeout||timeout||d.child_timeout;
    if(timeout || !reaped)break;
  }
  const bool passed=all && observed==expected && observed_mask==((UINT64_C(1)<<expected)-1);
  const bool children_reaped=started==reaped_count && nested_started==nested_reaped && !any_timeout;
  Append("],\"pass\":%s,\"child_reaped\":%s,\"direct_children_started\":%u,"
         "\"direct_children_reaped\":%u,\"nested_children_started\":%u,\"nested_children_reaped\":%u,"
         "\"expected_cases\":%u,\"observed_cases\":%u,\"expected_behavior_mask\":\"0x%016llx\","
         "\"timeout\":%s,\"application_uid\":%u,",
         passed?"true":"false",children_reaped?"true":"false",started,reaped_count,
         nested_started,nested_reaped,expected,observed,static_cast<unsigned long long>(observed_mask),
         (any_timeout||total_timeout)?"true":"false",static_cast<unsigned>(getuid()));
  Append("\"scope\":\"real metadata wrappers with explicit qualified raw owner\","
         "\"worker_arbitrary_callback\":false,\"identity_seam\":false,\"host_copy_seam\":false,"
         "\"fault_injections\":[],\"source_default_raw_feature_enabled\":false,"
         "\"owned_probe_raw_feature_enabled\":true,\"runtime_hooks_installed\":false,"
         "\"candidate_production_ready\":false,\"broker_positive_identity_tested\":false,"
         "\"positive_root_owned_O_PATH_reopen_tested\":false,"
         "\"application_owned_Fstat_QueryOrigin_use_native_negative_filter\":true,"
         "\"credential_namespace_transition_guarantee\":false,"
         "\"known_reds\":[\"NOFILE0 remains EMFILE\",\"task-count and kernel resources remain\","
         "\"ART app-generation and retirement hooks absent\","
         "\"host-native credential root mount transitions not gated\","
         "\"positive trusted factory tag and O_PATH reopen not exercised\","
         "\"pathname owner resource and alias-admission race unresolved\"]}");
  munmap(details,sizeof(MetadataDetails));details=nullptr;
  if(result_overflow)return 83;
  return passed?0:1;
}
extern "C" JNIEXPORT jstring JNICALL
Java_local_pocket4_fdownerprobe_ProbeInstrumentation_runProbe(JNIEnv* env,jclass) {
  probe_result[0]=0;const int result=RunOwnedMetadata();
  if(result_overflow || probe_result[0]==0)
    snprintf(probe_result,sizeof(probe_result),"{\"probe\":\"owned_real_metadata_r18\",\"pass\":false,\"early_rc\":%d}",result);
  return env->NewStringUTF(probe_result);
}
