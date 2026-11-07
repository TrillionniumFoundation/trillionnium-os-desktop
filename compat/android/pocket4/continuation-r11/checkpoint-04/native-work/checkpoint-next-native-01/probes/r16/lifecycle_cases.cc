// SPDX-License-Identifier: Apache-2.0
// Owned Android controls for the actual frozen revision-5 owner implementation.
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

#include "actual/kernel_api/berberis/kernel_api/proc_maps_provenance.h"
// Only these explicit failure/scheduling hooks differ from production calls.
// Every non-injected call invokes the actual libc operation.
extern "C" int __wrap_pthread_create(pthread_t*, const pthread_attr_t*, void*(*)(void*), void*);
extern "C" int __wrap_pthread_join(pthread_t, void**);
extern "C" int __real_pthread_create(pthread_t* t,const pthread_attr_t* a,void*(*f)(void*),void* p) {return pthread_create(t,a,f,p);}
extern "C" int __real_pthread_join(pthread_t t,void** r) {return pthread_join(t,r);}
#define pthread_create __wrap_pthread_create
#define pthread_join __wrap_pthread_join
#include "actual/kernel_api/proc_maps_fd_owner.cc"
#undef pthread_join
#undef pthread_create
#include "actual/kernel_api/proc_maps_path.cc"
#include "actual/kernel_api/proc_maps_provenance.cc"
// Private anonymous helpers collide when separate production units are
// amalgamated. Rename only their private identifiers; source bytes stay pinned.
#define Fd OpenFixturePrivateFd
#define Error OpenFixturePrivateError
#define SameInode OpenFixtureSameInode
#include "actual/kernel_api/proc_maps_open.cc"
#undef SameInode
#undef Error
#undef Fd

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
  const uint64_t entered=before|(UINT64_C(1)<<(SIGUSR1-1));
  if(syscall(SYS_rt_sigprocmask,SIG_SETMASK,&entered,nullptr,8UL)<0)return false;
  const bool operations=owner::StartReusableMetadataOwner()==0 &&
                        owner::WithPinnedFd(fd,CheckIdentity,&expected)==19 &&
                        owner::StopReusableMetadataOwner()==0;
  const bool queried=syscall(SYS_rt_sigprocmask,SIG_SETMASK,nullptr,&after,8UL)==0;
  const bool restored=syscall(SYS_rt_sigprocmask,SIG_SETMASK,&before,nullptr,8UL)==0;
  return operations && queried && restored && entered==after;
}

struct ForkAsDetails {
  int setup=0;
  int fork_error=0;
  int native_stat=-99,native_fs=-99;
  int child_start=-99,child_start_error=0;
  int projected_fs=-99,projected_error=0;
  int child_finished=0,child_reaped=0,child_signal=0,child_exit=-1,child_stop=-99;
  int parent_submit=-99,parent_join=-99,parent_stop=-99,parent_fd_survived=0;
  int inherited_stack_present=0;
};
static ForkAsDetails* fork_as_details;

static bool ForkAfterLimitedAs() {
  ForkAsDetails* d=fork_as_details;
  Blocked b;b.fd=Seed();
  if(b.fd<0 || owner::StartReusableMetadataOwner()<0){d->setup=1;return false;}
  struct stat parent_identity{};
  if(fstat(b.fd,&parent_identity)<0){d->setup=5;owner::StopReusableMetadataOwner();return false;}
  pthread_t submit;
  if(__real_pthread_create(&submit,nullptr,SubmitBlocked,&b)!=0){d->setup=2;return false;}
  while(!b.entered.load())sched_yield();
  // The owner's stack is live, and its admission gate belongs to another
  // thread when fork copies this address space. All setup precedes AS=1.
  const struct rlimit limit{1,1};
  if(setrlimit(RLIMIT_AS,&limit)<0) {
    d->setup=3;b.release.store(true);__real_pthread_join(submit,nullptr);
    owner::StopReusableMetadataOwner();return false;
  }
  const pid_t parent=getpid();errno=0;
  const pid_t child=static_cast<pid_t>(syscall(SYS_clone,static_cast<unsigned long>(SIGCHLD),
                                            0UL,0UL,0UL,0UL));
  d->fork_error=errno;
  if(child==0) {
    if(getppid()!=parent || prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=parent)_exit(64);
    owner::ResetReusableMetadataOwnerAfterPrivateFork();
    d->inherited_stack_present=owner::g_reusable.stack_mapping!=nullptr &&
                               owner::g_reusable.stack_base!=nullptr &&
                               owner::g_reusable.stack_size>=128u*1024u;
    struct stat st{};struct statfs fs{};
    d->native_stat=fstat(b.fd,&st);d->native_fs=fstatfs(b.fd,&fs);
    errno=0;d->child_start=owner::StartReusableMetadataOwner();d->child_start_error=errno;
    errno=0;d->projected_fs=provenance::Fstatfs(b.fd,&fs,provenance::kCandidateConfiguration);
    d->projected_error=errno;
    if(d->child_start==0)d->child_stop=owner::StopReusableMetadataOwner();
    d->child_finished=1;
    _exit(0);
  }
  if(child<0) {
    d->setup=4;b.release.store(true);__real_pthread_join(submit,nullptr);
    owner::StopReusableMetadataOwner();return false;
  }
  int status=0;pid_t done;
  do{done=waitpid(child,&status,0);}while(done<0 && errno==EINTR);
  d->child_reaped=done==child;
  if(done==child) {
    d->child_signal=WIFSIGNALED(status)?WTERMSIG(status):0;
    d->child_exit=WIFEXITED(status)?WEXITSTATUS(status):-1;
  }
  b.release.store(true);
  d->parent_join=__real_pthread_join(submit,nullptr);
  d->parent_submit=b.result;
  d->parent_stop=owner::StopReusableMetadataOwner();
  d->parent_fd_survived=Identity(b.fd,parent_identity);
  return d->setup==0 && d->child_reaped && d->child_signal==0 && d->child_exit==0 &&
         d->child_finished && d->inherited_stack_present && d->native_stat==0 && d->native_fs==0 &&
         d->child_start==0 && d->projected_fs==0 && d->child_stop==0 && d->parent_join==0 &&
         d->parent_submit==23 && d->parent_stop==0 && d->parent_fd_survived;
}

struct Case {const char* name;bool(*function)();bool known_red=false;};
