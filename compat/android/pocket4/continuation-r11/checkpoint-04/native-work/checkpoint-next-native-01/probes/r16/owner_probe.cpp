// SPDX-License-Identifier: Apache-2.0
#include <jni.h>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <ctime>
#include "lifecycle_cases.cc"

static char probe_result[16384];
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
static int64_t MonotonicMilliseconds() {
  struct timespec time{};
  if(clock_gettime(CLOCK_MONOTONIC,&time)<0)return -1;
  return static_cast<int64_t>(time.tv_sec)*1000+time.tv_nsec/1000000;
}
static int RunOwnedLifecycle() {
  struct sigaction action{};
  if(sigaction(SIGCHLD,nullptr,&action)<0 || action.sa_handler!=SIG_DFL ||
     (action.sa_flags&SA_NOCLDWAIT)!=0) {
    snprintf(probe_result,sizeof(probe_result),"{\"probe\":\"owned_reusable_metadata_lifecycle_r16\",\"pass\":false,\"setup\":\"exclusive wait ownership unavailable\",\"child_reaped\":true}");
    return 80;
  }
  const Case cases[]={
    {"prewarmed_actual_RLIMIT_AS_1_metadata",WarmAsLimit},
    {"prewarmed_reject_new_pthread_EAGAIN",RejectCreateAfterWarm},
    {"stop_inflight_closes_admission_and_restart",StopWithInflight},
    {"stop_during_paused_startup_no_reopen",StopDuringStartup},
    {"raw_clone_private_fork_inflight",RawFork},
    {"libc_fork_atfork_inflight",LibcFork},
    {"CLONE_VM_new_TGID_gate_parent_survives",SharedVmGate},
    {"startup_EAGAIN_explicit_retry",CreateFailureRetry},
    {"join_failure_sticky_poison",JoinFailurePoison},
    {"actual_caller_unshared_fdtable",CallerTableSelection},
    {"caller_mask_preserved",MaskPreserved},
    {"RLIMIT_NOFILE_0_still_EMFILE_known_red",NoFileZeroKnownRed,true},
    {"raw_fork_inflight_after_AS_1_reuses_inherited_stack",ForkAfterLimitedAs},
  };
  constexpr unsigned expected=sizeof(cases)/sizeof(cases[0]);
  uint64_t observed_mask=0;
  unsigned observed=0,started=0,reaped_count=0;
  bool all=true,total_timeout=false,any_timeout=false;
  const int64_t started_at=MonotonicMilliseconds();
  if(started_at<0)return 81;
  fork_as_details=static_cast<ForkAsDetails*>(mmap(nullptr,sizeof(ForkAsDetails),PROT_READ|PROT_WRITE,
                                                 MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(fork_as_details==MAP_FAILED)return 85;
  *fork_as_details=ForkAsDetails{};
  char records[8192]{};size_t records_used=0;
  const struct timespec delay{0,10000000};
  for(const auto& test:cases) {
    const int64_t now=MonotonicMilliseconds();
    if(now<0 || now-started_at>=15000){total_timeout=true;all=false;break;}
    const pid_t parent=getpid();
    const pid_t child=fork();
    if(child<0){all=false;break;}
    if(child==0) {
      if(getppid()!=parent || prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=parent)_exit(82);
      _exit(test.function()?0:1);
    }
    ++started;
    int status=0;bool reaped=false,timed_out=false;int wait_error=0;
    for(;;) {
      const pid_t done=waitpid(child,&status,WNOHANG);
      if(done==child){reaped=true;break;}
      if(done<0 && errno!=EINTR){wait_error=errno;break;}
      const int64_t tick=MonotonicMilliseconds();
      if(tick<0 || tick-now>=3000 || tick-started_at>=15000){timed_out=true;break;}
      nanosleep(&delay,nullptr);
    }
    if(timed_out && !reaped) {
      // Check ownership immediately before signalling. ECHILD is not a
      // licence to signal a potentially reused PID.
      const pid_t check=waitpid(child,&status,WNOHANG);
      if(check==child){reaped=true;timed_out=false;}
      else if(check==0) {
        kill(child,SIGKILL);
        const int64_t kill_at=MonotonicMilliseconds();
        for(;;) {
          const pid_t done=waitpid(child,&status,WNOHANG);
          if(done==child){reaped=true;break;}
          if(done<0 && errno!=EINTR){wait_error=errno;break;}
          const int64_t tick=MonotonicMilliseconds();
          if(tick<0 || kill_at<0 || tick-kill_at>=1000)break;
          nanosleep(&delay,nullptr);
        }
      } else if(check<0)wait_error=errno;
    }
    if(reaped)++reaped_count;
    const bool pass=reaped && !timed_out && WIFEXITED(status) && WEXITSTATUS(status)==0;
    if(pass)observed_mask|=UINT64_C(1)<<observed;
    const int count=snprintf(records+records_used,sizeof(records)-records_used,
      "%s{\"case\":\"%s\",\"expected_behavior_observed\":%s,\"known_production_red\":%s,\"direct_child_reaped\":%s,\"timeout\":%s,\"signal\":%d,\"exit\":%d,\"wait_errno\":%d}",
      observed?",":"",test.name,pass?"true":"false",test.known_red?"true":"false",
      reaped?"true":"false",timed_out?"true":"false",reaped&&WIFSIGNALED(status)?WTERMSIG(status):0,
      reaped&&WIFEXITED(status)?WEXITSTATUS(status):-1,wait_error);
    if(count<0 || static_cast<size_t>(count)>=sizeof(records)-records_used)return 83;
    records_used+=static_cast<size_t>(count);++observed;all=all&&pass;any_timeout=any_timeout||timed_out;
    // A timed-out child may have an unobserved nested result. Stop the suite;
    // never turn later green cases into a claim that its descendants reaped.
    if(timed_out || !reaped)break;
  }
  const bool pass=all && observed==expected && observed_mask==((UINT64_C(1)<<expected)-1);
  result_used=0;result_overflow=false;
  Append("{\"probe\":\"owned_reusable_metadata_lifecycle_r16\",\"pass\":%s,\"child_reaped\":%s,\"direct_children_started\":%u,\"direct_children_reaped\":%u,\"expected_cases\":%u,\"observed_cases\":%u,\"expected_behavior_mask\":\"0x%016llx\",\"timeout\":%s,\"cases\":[%s],",
         pass?"true":"false",pass&&started==reaped_count?"true":"false",started,reaped_count,
         expected,observed,static_cast<unsigned long long>(observed_mask),(total_timeout||any_timeout)?"true":"false",records);
  Append("\"application_uid\":%u,\"resource_fixture\":{\"tmpfs_fstatfs_uses_real_owner\":true,\"fstat_queryorigin_candidate_shape\":%s},",
         static_cast<unsigned>(getuid()),getuid()==0?"true":"false");
  const ForkAsDetails& d=*fork_as_details;
  Append("\"fork_after_AS_1\":{\"setup\":%d,\"fork_errno\":%d,\"native_stat_rc\":%d,\"native_statfs_rc\":%d,\"child_start_rc\":%d,\"child_start_errno\":%d,\"projected_statfs_rc\":%d,\"projected_statfs_errno\":%d,\"child_finished\":%d,\"child_reaped\":%d,\"child_signal\":%d,\"child_exit\":%d,\"child_stop_rc\":%d,\"parent_submit_rc\":%d,\"parent_join_rc\":%d,\"parent_stop_rc\":%d,\"parent_fd_survived\":%d,\"inherited_stack_present\":%d},",
         d.setup,d.fork_error,d.native_stat,d.native_fs,d.child_start,d.child_start_error,d.projected_fs,
         d.projected_error,d.child_finished,d.child_reaped,d.child_signal,d.child_exit,d.child_stop,d.parent_submit,
         d.parent_join,d.parent_stop,d.parent_fd_survived,d.inherited_stack_present);
  munmap(fork_as_details,sizeof(ForkAsDetails));fork_as_details=nullptr;
  Append("\"known_reds\":[\"RLIMIT_NOFILE=0 metadata remains EMFILE\",\"libc TLS allocation and task-count limits are not claimed eliminated\",\"CLONE_VM new TGID is a containment rejection, not guest support\",\"runtime lifecycle hooks not installed\",\"credential/root/mount transitions unqualified\",\"ordinary alias-to-maps admission race remains\"],");
  Append("\"fault_injections\":[\"pthread_create EAGAIN\",\"pthread_join EIO after real worker exit\"],\"host_copy_seam\":false,\"runtime_hooks_installed\":false,\"candidate_production_ready\":false,\"broker_positive_identity_tested\":false}");
  if(result_overflow) {
    snprintf(probe_result,sizeof(probe_result),"{\"probe\":\"owned_reusable_metadata_lifecycle_r16\",\"pass\":false,\"result_overflow\":true}");
    return 84;
  }
  return pass?0:1;
}

extern "C" JNIEXPORT jstring JNICALL
Java_local_pocket4_fdownerprobe_ProbeInstrumentation_runProbe(JNIEnv* env,jclass) {
  probe_result[0]=0;
  const int result=RunOwnedLifecycle();
  if(probe_result[0]==0)snprintf(probe_result,sizeof(probe_result),"{\"probe\":\"owned_reusable_metadata_lifecycle_r16\",\"pass\":false,\"early_rc\":%d}",result);
  return env->NewStringUTF(probe_result);
}
