// SPDX-License-Identifier: Apache-2.0
// Cross-condition negative control: private raw fork after a successful warmup
// and a real RLIMIT_AS reduction. Only this program's own child is signalled.
#include <cerrno>
#include <cstdio>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "berberis/kernel_api/proc_maps_fd_owner.h"
#include "berberis/kernel_api/proc_maps_provenance.h"
namespace o=berberis::proc_maps_provenance::fd_owner;
namespace p=berberis::proc_maps_provenance;
struct Result {int native_stat=-99,native_fs=-99,start=-99,start_error=0,guest_fs=-99,guest_error=0,finished=0;};
int main() {
  setvbuf(stdout,nullptr,_IONBF,0);
  struct sigaction action{};
  if(sigaction(SIGCHLD,nullptr,&action)<0 || action.sa_handler!=SIG_DFL || (action.sa_flags&SA_NOCLDWAIT))return 70;
  auto* result=static_cast<Result*>(mmap(nullptr,sizeof(Result),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(result==MAP_FAILED)return 71;
  *result=Result{};
  const int fd=static_cast<int>(syscall(SYS_memfd_create,"owned-fork-as-limit",1UL));
  if(fd<0 || o::StartReusableMetadataOwner()<0)return 72;
  const struct rlimit limit{1,1};if(setrlimit(RLIMIT_AS,&limit)<0)return 73;
  const pid_t parent=getpid();errno=0;
  const pid_t child=static_cast<pid_t>(syscall(SYS_clone,static_cast<unsigned long>(SIGCHLD),0UL,0UL,0UL,0UL));
  const int fork_error=errno;
  if(child<0) {
    printf("{\"case\":\"raw_fork_after_AS_1\",\"setup_fork_succeeded\":false,\"fork_errno\":%d,\"resource_regression_observed\":false}\n",fork_error);
    o::StopReusableMetadataOwner();return 74;
  }
  if(child==0) {
    if(getppid()!=parent || prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=parent)_exit(75);
    o::ResetReusableMetadataOwnerAfterPrivateFork();
    struct stat st{};struct statfs fs{};
    result->native_stat=fstat(fd,&st);result->native_fs=fstatfs(fd,&fs);
    errno=0;result->start=o::StartReusableMetadataOwner();result->start_error=errno;
    errno=0;result->guest_fs=p::Fstatfs(fd,&fs,p::kCandidateConfiguration);result->guest_error=errno;
    result->finished=1;
    if(result->start==0)o::StopReusableMetadataOwner();
    _exit(0);
  }
  int status=0;bool reaped=false,timeout=true;const struct timespec delay{0,10000000};
  for(int i=0;i<300;++i) {
    const pid_t done=waitpid(child,&status,WNOHANG);
    if(done==child){reaped=true;timeout=false;break;}
    if(done<0 && errno!=EINTR)break;
    nanosleep(&delay,nullptr);
  }
  if(timeout && !reaped) {
    const pid_t check=waitpid(child,&status,WNOHANG);
    if(check==child){reaped=true;timeout=false;}
    else if(check==0) {
      kill(child,SIGKILL);pid_t done;
      do{done=waitpid(child,&status,0);}while(done<0 && errno==EINTR);
      reaped=done==child;
    }
  }
  const bool red=reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0 && result->finished &&
                 result->native_stat==0 && result->native_fs==0 && result->start==-1 &&
                 (result->start_error==EAGAIN || result->start_error==ENOMEM) && result->guest_fs==-1;
  const int stopped=o::StopReusableMetadataOwner();
  printf("{\"case\":\"raw_fork_after_AS_1\",\"setup_fork_succeeded\":true,\"child_reaped\":%s,\"timeout\":%s,\"child_signal\":%d,\"child_exit\":%d,\"native_stat_rc\":%d,\"native_statfs_rc\":%d,\"child_owner_start_rc\":%d,\"child_owner_start_errno\":%d,\"child_projected_statfs_rc\":%d,\"child_projected_statfs_errno\":%d,\"resource_regression_observed\":%s,\"parent_owner_stop_rc\":%d}\n",
         reaped?"true":"false",timeout?"true":"false",reaped&&WIFSIGNALED(status)?WTERMSIG(status):0,
         reaped&&WIFEXITED(status)?WEXITSTATUS(status):-1,result->native_stat,result->native_fs,result->start,
         result->start_error,result->guest_fs,result->guest_error,red?"true":"false",stopped);
  const bool corrected=reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0 &&
                       result->finished && result->native_stat==0 && result->native_fs==0 &&
                       result->start==0 && result->guest_fs==0 && stopped==0;
  printf("{\"corrected_behavior_observed\":%s}\n",corrected?"true":"false");
  return corrected?0:1;
}
