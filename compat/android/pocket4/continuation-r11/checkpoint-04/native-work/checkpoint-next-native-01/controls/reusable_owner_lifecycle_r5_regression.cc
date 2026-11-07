// SPDX-License-Identifier: Apache-2.0
// Owned host controls for the actual revision-5 owner implementation.
// Each case gets its own process; only those forked children are waited/killed.
// The .cc inclusion permits read-only observation of admission/slot state to
// make stop interleavings deterministic. No production operation is replaced.
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <linux/memfd.h>
#include <pthread.h>
#include <sched.h>
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

#include "berberis/kernel_api/proc_maps_provenance.h"
#include "reusable-owner-snapshot-05/kernel_api/proc_maps_fd_owner.cc"

namespace owner = berberis::proc_maps_provenance::fd_owner;
namespace provenance = berberis::proc_maps_provenance;

static std::atomic<int> creates{0};
static std::atomic<int> create_error{0};
static std::atomic<int> join_error{0};
static std::atomic<bool> pause_create{false}, create_entered{false}, release_create{false};
extern "C" int __real_pthread_create(pthread_t*, const pthread_attr_t*, void*(*)(void*), void*);
extern "C" int __real_pthread_join(pthread_t, void**);
extern "C" int __wrap_pthread_create(pthread_t* thread, const pthread_attr_t* attributes,
                                     void*(*function)(void*), void* context) {
  creates.fetch_add(1);
  if (pause_create.load()) {
    create_entered.store(true);
    while (!release_create.load()) sched_yield();
  }
  if (const int error=create_error.load()) return error;
  return __real_pthread_create(thread, attributes, function, context);
}
extern "C" int __wrap_pthread_join(pthread_t thread, void** result) {
  if (const int error=join_error.load()) return error;
  return __real_pthread_join(thread, result);
}

static bool Identity(int a, const struct stat& b) {
  struct stat result{};
  return fstat(a, &result)==0 && result.st_dev==b.st_dev && result.st_ino==b.st_ino &&
         result.st_mode==b.st_mode && result.st_rdev==b.st_rdev;
}
static int CheckIdentity(int pinned, void* opaque) {
  if (!Identity(pinned, *static_cast<const struct stat*>(opaque))) {errno=ESTALE;return -1;}
  return 19;
}
static int Seed() {
  const int fd=static_cast<int>(syscall(SYS_memfd_create, "owned-resource-control", MFD_CLOEXEC));
  if(fd<0)return -1;
  if(write(fd,"owned",5)!=5 || fchmod(fd,0444)<0) {close(fd);return -1;}
  return fd;
}
static bool WarmAsLimit() {
  const int fd=Seed(); if(fd<0)return false;
  struct stat expected{}; struct statfs expected_fs{};
  if(fstat(fd,&expected)<0 || fstatfs(fd,&expected_fs)<0 || owner::StartReusableMetadataOwner()<0)return false;
  const int initial=creates.load();
  const struct rlimit limit{1,1}; if(setrlimit(RLIMIT_AS,&limit)<0)return false;
  // This is the real address-space limit, not an injected pthread error.
  struct stat native{}; struct statfs native_fs{};
  if(fstat(fd,&native)<0 || fstatfs(fd,&native_fs)<0)return false;
  provenance::Configuration config{};
  provenance::Origin origin{};
  for(int i=0;i<20;++i) {
    struct stat actual{}; struct statfs actual_fs{};
    errno=73;
    if(provenance::Fstat(fd,&actual,config)!=0 || errno!=73 || actual.st_ino!=expected.st_ino)return false;
    errno=79;
    if(provenance::Fstatfs(fd,&actual_fs,config)!=0 || errno!=79 ||
       memcmp(&actual_fs,&expected_fs,sizeof(actual_fs))!=0)return false;
    errno=83;
    if(provenance::QueryOrigin(fd,config,&origin)!=provenance::Lookup::kOrdinary || errno!=83)return false;
  }
  return creates.load()==initial && owner::StopReusableMetadataOwner()==0 && fcntl(fd,F_GETFD)>=0;
}
static bool NoFileZeroKnownRed() {
  const int fd=Seed();if(fd<0 || owner::StartReusableMetadataOwner()<0)return false;
  const struct rlimit limit{0,0};if(setrlimit(RLIMIT_NOFILE,&limit)<0)return false;
  struct stat value{};struct statfs fs{};
  if(fstat(fd,&value)<0 || fstatfs(fd,&fs)<0)return false;
  provenance::Configuration config{};
  errno=0;const int result=provenance::Fstatfs(fd,&fs,config);const int error=errno;
  return result==-1 && error==EMFILE && owner::StopReusableMetadataOwner()==0 && fstat(fd,&value)==0;
}
static bool RejectCreateAfterWarm() {
  const int fd=Seed();if(fd<0 || owner::StartReusableMetadataOwner()<0)return false;
  struct stat expected{};if(fstat(fd,&expected)<0)return false;
  const int initial=creates.load();create_error.store(EAGAIN);
  for(int i=0;i<32;++i)if(owner::WithPinnedFd(fd,CheckIdentity,&expected)!=19)return false;
  create_error.store(0);
  return creates.load()==initial && owner::StopReusableMetadataOwner()==0;
}
struct Blocked {
  int fd=-1;
  int result=-1;
  int error=0;
  std::atomic<bool> entered{false}, release{false};
};
static int BlockingOperation(int pinned,void* opaque) {
  auto* b=static_cast<Blocked*>(opaque);
  struct stat value{};if(fstat(pinned,&value)<0)return -1;
  b->entered.store(true);
  while(!b->release.load())sched_yield();
  return 23;
}
static void* SubmitBlocked(void* opaque) {
  auto* b=static_cast<Blocked*>(opaque);
  b->result=owner::WithPinnedFd(b->fd,BlockingOperation,b);b->error=errno;return nullptr;
}
struct Call {int result=-99;int error=0;};
static void* StopCall(void* opaque) {
  auto* call=static_cast<Call*>(opaque);
  call->result=owner::StopReusableMetadataOwner();call->error=errno;return nullptr;
}
static void* StartCall(void* opaque) {
  auto* call=static_cast<Call*>(opaque);
  call->result=owner::StartReusableMetadataOwner();call->error=errno;return nullptr;
}
static bool StopWithInflight() {
  Blocked b;b.fd=open("/dev/null",O_RDONLY|O_CLOEXEC);
  if(b.fd<0 || owner::StartReusableMetadataOwner()<0)return false;
  pthread_t submit;
  if(__real_pthread_create(&submit,nullptr,SubmitBlocked,&b)!=0)return false;
  while(!b.entered.load())sched_yield();
  Call stopped;pthread_t stopper;
  if(__real_pthread_create(&stopper,nullptr,StopCall,&stopped)!=0)return false;
  while(owner::g_reusable.admission.load()!=2)sched_yield();
  struct stat expected{};if(fstat(b.fd,&expected)<0)return false;
  errno=0;const int late=owner::WithPinnedFd(b.fd,CheckIdentity,&expected);const int late_error=errno;
  errno=0;const int reopening=owner::StartReusableMetadataOwner();const int reopen_error=errno;
  b.release.store(true);
  if(__real_pthread_join(submit,nullptr)!=0 || __real_pthread_join(stopper,nullptr)!=0)return false;
  errno=0;const int after=owner::WithPinnedFd(b.fd,CheckIdentity,&expected);const int after_error=errno;
  const bool retired=!owner::g_reusable.joinable && owner::g_reusable.slot.load()==nullptr &&
                     owner::g_reusable.admission.load()==0;
  if(owner::StartReusableMetadataOwner()<0)return false;
  const bool restarted=owner::WithPinnedFd(b.fd,CheckIdentity,&expected)==19;
  return late==-1 && late_error==ESHUTDOWN && reopening==-1 && reopen_error==EBUSY &&
         b.result==23 && stopped.result==0 && after==-1 && after_error==ESHUTDOWN && retired &&
         restarted && owner::StopReusableMetadataOwner()==0;
}
static bool StopDuringStartup() {
  pause_create.store(true);Call started,stopped;pthread_t starter,stopper;
  if(__real_pthread_create(&starter,nullptr,StartCall,&started)!=0)return false;
  while(!create_entered.load())sched_yield();
  if(__real_pthread_create(&stopper,nullptr,StopCall,&stopped)!=0)return false;
  while(owner::g_reusable.admission.load()!=2)sched_yield();
  release_create.store(true);
  if(__real_pthread_join(starter,nullptr)!=0 || __real_pthread_join(stopper,nullptr)!=0)return false;
  return started.result==-1 && started.error==EBUSY && stopped.result==0 &&
         !owner::g_reusable.joinable && owner::g_reusable.admission.load()==0;
}
static bool ForkWithInflight(bool raw) {
  Blocked b;b.fd=open("/dev/null",O_RDONLY|O_CLOEXEC);
  if(b.fd<0 || owner::StartReusableMetadataOwner()<0)return false;
  pthread_t submit;if(__real_pthread_create(&submit,nullptr,SubmitBlocked,&b)!=0)return false;
  while(!b.entered.load())sched_yield();
  const pid_t parent=getpid();
  const pid_t child=raw?static_cast<pid_t>(syscall(SYS_clone,static_cast<unsigned long>(SIGCHLD),
                                       0UL,0UL,0UL,0UL)):fork();
  if(child<0)return false;
  if(child==0) {
    if(getppid()!=parent || prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=parent)_exit(62);
    if(raw)owner::ResetReusableMetadataOwnerAfterPrivateFork();
    struct stat expected{};
    const bool pass=fstat(b.fd,&expected)==0 && owner::StartReusableMetadataOwner()==0 &&
                    owner::WithPinnedFd(b.fd,CheckIdentity,&expected)==19 &&
                    owner::StopReusableMetadataOwner()==0;
    _exit(pass?0:61);
  }
  int status=0;while(waitpid(child,&status,0)<0)if(errno!=EINTR)return false;
  b.release.store(true);
  if(__real_pthread_join(submit,nullptr)!=0)return false;
  struct stat expected{};
  const bool parent_ok=fstat(b.fd,&expected)==0 && owner::WithPinnedFd(b.fd,CheckIdentity,&expected)==19;
  return WIFEXITED(status) && WEXITSTATUS(status)==0 && b.result==23 && parent_ok &&
         owner::StopReusableMetadataOwner()==0;
}
static bool RawFork(){return ForkWithInflight(true);}
static bool LibcFork(){return ForkWithInflight(false);}
struct SharedChild {int fd;pid_t parent;int results[3];int errors[3];};
static int SharedVmChild(void* opaque) {
  auto* child=static_cast<SharedChild*>(opaque);struct stat expected{};fstat(child->fd,&expected);
  if(getppid()!=child->parent || prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=child->parent)return 63;
  child->results[0]=owner::WithPinnedFd(child->fd,CheckIdentity,&expected);child->errors[0]=errno;
  child->results[1]=owner::StartReusableMetadataOwner();child->errors[1]=errno;
  child->results[2]=owner::StopReusableMetadataOwner();child->errors[2]=errno;
  return 0;
}
static bool SharedVmGate() {
  const int fd=open("/dev/null",O_RDONLY|O_CLOEXEC);
  if(fd<0 || owner::StartReusableMetadataOwner()<0)return false;
  constexpr size_t size=128*1024;
  void* stack=mmap(nullptr,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
  if(stack==MAP_FAILED)return false;
  SharedChild child{fd,getpid(),{0,0,0},{0,0,0}};
  const pid_t pid=clone(SharedVmChild,static_cast<char*>(stack)+size,CLONE_VM|SIGCHLD,&child);
  if(pid<0)return false;
  int status=0;while(waitpid(pid,&status,0)<0)if(errno!=EINTR)return false;
  bool pass=WIFEXITED(status) && WEXITSTATUS(status)==0;
  for(int i=0;i<3;++i)pass=pass && child.results[i]==-1 && child.errors[i]==EOPNOTSUPP;
  struct stat expected{};
  pass=pass && fstat(fd,&expected)==0 && owner::WithPinnedFd(fd,CheckIdentity,&expected)==19;
  munmap(stack,size);
  return pass && owner::StopReusableMetadataOwner()==0;
}
static bool CreateFailureRetry() {
  create_error.store(EAGAIN);errno=0;
  const int result=owner::StartReusableMetadataOwner();const int error=errno;
  create_error.store(0);
  return result==-1 && error==EAGAIN && !owner::g_reusable.joinable &&
         owner::StartReusableMetadataOwner()==0 && owner::StopReusableMetadataOwner()==0;
}
static bool JoinFailurePoison() {
  if(owner::StartReusableMetadataOwner()<0)return false;
  join_error.store(EIO);errno=0;
  const int first=owner::StopReusableMetadataOwner();const int first_error=errno;
  join_error.store(0);errno=0;
  const int second=owner::StopReusableMetadataOwner();const int second_error=errno;
  errno=0;const int restart=owner::StartReusableMetadataOwner();const int restart_error=errno;
  return first==-1 && first_error==EIO && second==-1 && second_error==EIO &&
         restart==-1 && restart_error==EIO && owner::g_reusable.admission.load()==0 &&
         owner::g_reusable.exited.load();
}
struct Independent {int fd;int result=-1;};
static void* DifferentTable(void* opaque) {
  auto* test=static_cast<Independent*>(opaque);
  if(syscall(SYS_unshare,CLONE_FILES)<0)return nullptr;
  if(syscall(SYS_close,test->fd)<0)return nullptr;
  const int other=open("/dev/zero",O_RDONLY|O_CLOEXEC);if(other<0)return nullptr;
  if(other!=test->fd && syscall(SYS_dup3,other,test->fd,O_CLOEXEC)<0)return nullptr;
  struct stat expected{};if(fstat(test->fd,&expected)<0)return nullptr;
  test->result=owner::WithPinnedFd(test->fd,CheckIdentity,&expected);return nullptr;
}
static bool CallerTableSelection() {
  Independent test{open("/dev/null",O_RDONLY|O_CLOEXEC)};
  if(test.fd<0 || owner::StartReusableMetadataOwner()<0)return false;
  struct stat expected{};if(fstat(test.fd,&expected)<0)return false;
  pthread_t child;if(__real_pthread_create(&child,nullptr,DifferentTable,&test)!=0)return false;
  if(__real_pthread_join(child,nullptr)!=0)return false;
  return test.result==19 && Identity(test.fd,expected) &&
         owner::WithPinnedFd(test.fd,CheckIdentity,&expected)==19 && owner::StopReusableMetadataOwner()==0;
}
static bool MaskPreserved() {
  const int fd=open("/dev/null",O_RDONLY|O_CLOEXEC);struct stat expected{};
  uint64_t before=0,after=0;
  if(fd<0 || fstat(fd,&expected)<0 || syscall(SYS_rt_sigprocmask,SIG_SETMASK,nullptr,&before,8UL)<0)return false;
  if(owner::StartReusableMetadataOwner()<0 || owner::WithPinnedFd(fd,CheckIdentity,&expected)!=19 ||
     owner::StopReusableMetadataOwner()<0)return false;
  return syscall(SYS_rt_sigprocmask,SIG_SETMASK,nullptr,&after,8UL)==0 && before==after;
}

struct Case {const char* name;bool(*function)();bool known_red=false;};
int main() {
  struct sigaction action{};
  if(sigaction(SIGCHLD,nullptr,&action)<0 || action.sa_handler!=SIG_DFL || (action.sa_flags&SA_NOCLDWAIT))return 80;
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
  };
  bool all=true;
  for(const auto& test:cases) {
    const pid_t parent=getpid();
    const pid_t child=fork();if(child<0)return 81;
    if(child==0) {
      if(getppid()!=parent || prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=parent)_exit(82);
      _exit(test.function()?0:1);
    }
    int status=0;bool reaped=false,timeout=true;const struct timespec delay{0,10000000};
    for(int i=0;i<800;++i) {
      const pid_t done=waitpid(child,&status,WNOHANG);
      if(done==child){reaped=true;timeout=false;break;}
      if(done<0 && errno!=EINTR)break;
      nanosleep(&delay,nullptr);
    }
    if(timeout && !reaped) {
      // Only this exact, owned and not-yet-reaped child is signalled.
      const pid_t check=waitpid(child,&status,WNOHANG);
      if(check==child){reaped=true;timeout=false;}
      else if(check==0) {
        kill(child,SIGKILL);pid_t done;
        do{done=waitpid(child,&status,0);}while(done<0 && errno==EINTR);
        reaped=done==child;
      }
    }
    const bool pass=reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0;
    printf("{\"case\":\"%s\",\"expected_behavior_observed\":%s,\"known_production_red\":%s,\"child_reaped\":%s,\"timeout\":%s,\"signal\":%d,\"exit\":%d}\n",
           test.name,pass?"true":"false",test.known_red?"true":"false",reaped?"true":"false",timeout?"true":"false",
           reaped && WIFSIGNALED(status)?WTERMSIG(status):0,reaped && WIFEXITED(status)?WEXITSTATUS(status):-1);
    fflush(stdout);all=all&&pass;
  }
  return all?0:1;
}
