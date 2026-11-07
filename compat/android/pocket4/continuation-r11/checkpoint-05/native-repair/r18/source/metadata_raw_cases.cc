// SPDX-License-Identifier: Apache-2.0
// Owned real-source controls. No identity, fd-copy, namespace, or syscall seam.
#define BERBERIS_PROCMAPS_RAW_METADATA_OWNER 1
#include <atomic>
#include <cerrno>
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
#include <sys/syscall.h>
#include <sys/wait.h>
#include <sys/xattr.h>
#include <time.h>
#include <unistd.h>

#include "actual/proc_maps_raw_metadata_owner.cc"
#include "actual/proc_maps_fd_owner.cc"
#include "actual/proc_maps_path.cc"
#include "actual/proc_maps_provenance.cc"
namespace raw_owner=berberis::proc_maps_provenance::raw_metadata_owner;
namespace provenance=berberis::proc_maps_provenance;

struct MetadataDetails {
  int setup=0,start=-99,start_error=0,read=-99,read_error=0,stop=-99;
  int native_stat=-99,native_fs=-99,projected_stat=-99,projected_fs=-99,lookup=-99;
  int errno_preserved=0,mask_preserved=0,ordinary_tag_rejected=0;
  int caller_uid=-1,worker_uid=-1,worker_tid=-1,worker_tid_cleared=0;
  int same_namespace=0,inherited_stack=0,child_finished=0,nested_started=0;
  int child_reaped=0,child_timeout=0,child_status=-99,parent_read=-99,parent_stop=-99;
  int parent_fd_survived=0,rounds=0,quiesce=-99,restart=-99,restart_error=0;
  int thread_error=0,thread_fdtable_checked=0,shared_vm_rejected=0;
};
static MetadataDetails* details;
static int64_t Now() {
  struct timespec t{};
  if(clock_gettime(CLOCK_MONOTONIC,&t)<0)return -1;
  return static_cast<int64_t>(t.tv_sec)*1000+t.tv_nsec/1000000;
}
static bool Guard(pid_t parent) {
  return getppid()==parent && prctl(PR_SET_PDEATHSIG,SIGKILL)==0 && getppid()==parent;
}
static bool WaitOwned(pid_t child,int milliseconds,int* status,bool* timed_out) {
  *timed_out=false;const int64_t began=Now();
  if(began<0)return false;
  const struct timespec delay{0,1000000};
  for(;;) {
    const pid_t done=waitpid(child,status,WNOHANG);
    if(done==child)return true;
    if(done<0 && errno!=EINTR)return false;
    const int64_t now=Now();if(now<0 || now-began>=milliseconds)break;
    nanosleep(&delay,nullptr);
  }
  const pid_t check=waitpid(child,status,WNOHANG);
  if(check==child)return true;
  if(check!=0)return false;
  *timed_out=true;
  if(kill(child,SIGKILL)<0 && errno!=ESRCH)return false;
  const int64_t killed=Now();if(killed<0)return false;
  for(;;) {
    const pid_t done=waitpid(child,status,WNOHANG);
    if(done==child)return true;
    if(done<0 && errno!=EINTR)return false;
    const int64_t now=Now();if(now<0 || now-killed>=1000)return false;
    nanosleep(&delay,nullptr);
  }
}
static int Seed(bool forge=false,int length=23) {
  const int fd=static_cast<int>(syscall(SYS_memfd_create,"droidloom-proc-maps-v1",
      static_cast<unsigned long>(MFD_CLOEXEC|MFD_ALLOW_SEALING)));
  if(fd<0)return -1;
  if(ftruncate(fd,length)<0 ||
     (forge && fsetxattr(fd,provenance::kTagName,"forged",6,0)<0) || fchmod(fd,0444)<0 ||
     fcntl(fd,F_ADD_SEALS,F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_WRITE|F_SEAL_SEAL)<0) {
    const int saved=errno;close(fd);errno=saved;return -1;
  }
  return fd;
}
static bool SameStat(const struct stat& a,const struct stat& b) {
  return a.st_dev==b.st_dev && a.st_ino==b.st_ino && a.st_mode==b.st_mode &&
         a.st_uid==b.st_uid && a.st_gid==b.st_gid && a.st_nlink==b.st_nlink &&
         a.st_size==b.st_size && a.st_blocks==b.st_blocks && a.st_blksize==b.st_blksize;
}
static bool SameFs(const struct statfs& a,const struct statfs& b) {
  // Global free-space counters can legitimately change between observations.
  return a.f_type==b.f_type && a.f_bsize==b.f_bsize && a.f_namelen==b.f_namelen &&
         a.f_frsize==b.f_frsize && a.f_flags==b.f_flags &&
         memcmp(&a.f_fsid,&b.f_fsid,sizeof(a.f_fsid))==0;
}
static bool Start() {
  errno=0;details->start=raw_owner::Start();details->start_error=errno;
  details->worker_tid=raw_owner::state.tid.load(std::memory_order_acquire);
  return details->start==0 && raw_owner::Enabled() && details->worker_tid>0 &&
         details->worker_tid!=static_cast<int>(syscall(SYS_gettid));
}
static bool Stop() {
  details->stop=raw_owner::Stop();
  details->worker_tid_cleared=raw_owner::state.tid.load(std::memory_order_acquire)==0;
  return details->stop==0 && details->worker_tid_cleared && !raw_owner::Enabled();
}
static bool Check(int fd) {
  struct stat expected{},projected{};struct statfs expected_fs{},projected_fs{};
  details->native_stat=fstat(fd,&expected);details->native_fs=fstatfs(fd,&expected_fs);
  if(details->native_stat<0 || details->native_fs<0)return false;
  raw_owner::Snapshot snapshot{};errno=113;
  details->read=raw_owner::Read(fd,&snapshot);details->read_error=errno;
  details->errno_preserved=errno==113;
  if(details->read<0 || !details->errno_preserved || snapshot.tagged!=0 ||
     !SameStat(expected,snapshot.identity) || !SameFs(expected_fs,snapshot.filesystem))return false;
  details->caller_uid=static_cast<int>(getuid());
  details->worker_uid=static_cast<int>(snapshot.worker_before.uid[0]);
  details->same_namespace=raw_owner::SameContext(snapshot.worker_before,snapshot.worker_after);
  if(details->caller_uid<=0 || details->worker_uid!=details->caller_uid || !details->same_namespace)
    return false;
  errno=119;details->projected_stat=provenance::Fstat(fd,&projected,provenance::kCandidateConfiguration);
  if(details->projected_stat!=0 || errno!=119 || !SameStat(expected,projected))return false;
  errno=121;details->projected_fs=provenance::Fstatfs(fd,&projected_fs,provenance::kCandidateConfiguration);
  if(details->projected_fs!=0 || errno!=121 || !SameFs(expected_fs,projected_fs))return false;
  provenance::Origin origin{};errno=123;
  details->lookup=static_cast<int>(provenance::QueryOrigin(fd,provenance::kCandidateConfiguration,&origin));
  return details->lookup==static_cast<int>(provenance::Lookup::kOrdinary) && errno==123;
}
static bool Basic() {
  const int fd=Seed();return fd>=0 && Start() && Check(fd) && Stop();
}
static bool ForgedAppFile() {
  const int fd=Seed(true);if(fd<0 || !Start() || !Check(fd))return false;
  details->ordinary_tag_rejected=details->lookup==static_cast<int>(provenance::Lookup::kOrdinary);
  return details->ordinary_tag_rejected && Stop();
}
static bool OrdinaryOPath() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  char path[96];const int n=snprintf(path,sizeof(path),"/proc/thread-self/fd/%d",fd);
  if(n<=0 || static_cast<size_t>(n)>=sizeof(path))return false;
  const int opath=open(path,O_PATH|O_CLOEXEC);
  return opath>=0 && Check(opath) && Stop();
}
static bool WarmLimitedAddressSpace() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  const struct rlimit limit{1,1};if(setrlimit(RLIMIT_AS,&limit)<0)return false;
  if(!Check(fd) || !Stop() || !Start())return false;
  return Check(fd) && Stop();
}
static bool RawForkLimitedAddressSpace() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  struct stat before{};if(fstat(fd,&before)<0)return false;
  const struct rlimit limit{1,1};if(setrlimit(RLIMIT_AS,&limit)<0)return false;
  const pid_t parent=getpid();
  const pid_t child=static_cast<pid_t>(syscall(SYS_clone,static_cast<unsigned long>(SIGCHLD),
                                             0UL,0UL,0UL,0UL));
  if(child<0){details->setup=errno;return false;}
  if(child==0) {
    if(!Guard(parent))_exit(81);
    raw_owner::ResetAfterPrivateFork();details->inherited_stack=raw_owner::HasInheritedStack();
    const bool passed=details->inherited_stack && Start() && Check(fd) && Stop();
    details->child_finished=1;_exit(passed?0:1);
  }
  details->nested_started=1;
  bool timeout=false;int status=0;
  details->child_reaped=WaitOwned(child,2000,&status,&timeout);
  details->child_timeout=timeout;details->child_status=status;
  raw_owner::Snapshot after{};details->parent_read=raw_owner::Read(fd,&after);
  details->parent_stop=raw_owner::Stop();
  struct stat alive{};details->parent_fd_survived=fstat(fd,&alive)==0 && SameStat(before,alive);
  return details->child_reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0 &&
         details->parent_read==0 && details->parent_stop==0 && details->parent_fd_survived;
}
static bool FullCallerTable() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  const struct rlimit limit{64,64};if(setrlimit(RLIMIT_NOFILE,&limit)<0)return false;
  int fills[64];unsigned count=0;
  for(;;) {
    const int opened=open("/dev/null",O_RDONLY|O_CLOEXEC);if(opened<0)break;
    if(count==64){close(opened);return false;}fills[count++]=opened;
  }
  if(errno!=EMFILE)return false;
  const bool passed=Check(fd) && Stop();
  for(unsigned i=0;i<count;++i)close(fills[i]);
  return passed;
}
static bool BadFdAndMask() {
  uint64_t original=0,entered=0,after=0;
  if(syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),0UL,&original,8UL)<0)return false;
  entered=original|(UINT64_C(1)<<(SIGUSR1-1));
  if(syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),&entered,0UL,8UL)<0)return false;
  if(!Start())return false;
  raw_owner::Snapshot snapshot{};unsigned char before[sizeof(snapshot)];
  memcpy(before,&snapshot,sizeof(snapshot));errno=0;
  details->read=raw_owner::Read(INT_MAX,&snapshot);details->read_error=errno;
  bool passed=details->read==-1 && details->read_error==EBADF &&
              memcmp(before,&snapshot,sizeof(snapshot))==0 && Stop();
  if(syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),0UL,&after,8UL)<0)passed=false;
  details->mask_preserved=after==entered;
  const bool restored=syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),&original,0UL,8UL)==0;
  return passed && restored && details->mask_preserved;
}
static bool ExplicitQuiesce() {
  const int fd=Seed();if(fd<0 || !Start() || !Check(fd))return false;
  details->quiesce=raw_owner::QuiesceBeforeTransition();
  details->worker_tid_cleared=raw_owner::state.tid.load(std::memory_order_acquire)==0;
  errno=0;details->restart=raw_owner::Start();details->restart_error=errno;
  struct statfs fs{};errno=0;
  details->projected_fs=provenance::Fstatfs(fd,&fs,provenance::kCandidateConfiguration);
  details->read_error=errno;
  return details->quiesce==0 && details->worker_tid_cleared && !raw_owner::Enabled() &&
         details->restart==-1 && details->restart_error==ESHUTDOWN &&
         details->projected_fs==-1 && details->read_error==ESHUTDOWN;
}
static bool RestartRounds() {
  const int fd=Seed();if(fd<0)return false;
  for(int i=0;i<12;++i) {if(!Start() || !Check(fd) || !Stop())return false;++details->rounds;}
  return true;
}
static bool NoFileZeroKnownRed() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  const struct rlimit limit{0,0};if(setrlimit(RLIMIT_NOFILE,&limit)<0)return false;
  struct stat st{};struct statfs fs{};
  details->native_stat=fstat(fd,&st);details->native_fs=fstatfs(fd,&fs);
  errno=0;details->projected_fs=provenance::Fstatfs(fd,&fs,provenance::kCandidateConfiguration);
  details->read_error=errno;
  return details->native_stat==0 && details->native_fs==0 && details->projected_fs==-1 &&
         details->read_error==EMFILE && Stop();
}
struct PrivateTableArg {int fd;struct stat original;};
static void* PrivateTableThread(void* opaque) {
  const auto* argument=static_cast<PrivateTableArg*>(opaque);
  if(syscall(SYS_unshare,static_cast<unsigned long>(CLONE_FILES))<0) {
    details->thread_error=errno;return nullptr;
  }
  if(close(argument->fd)<0){details->thread_error=errno;return nullptr;}
  const int seed=Seed(false,41);
  if(seed<0 || (seed!=argument->fd && dup3(seed,argument->fd,O_CLOEXEC)<0)) {
    details->thread_error=errno;return nullptr;
  }
  struct stat own{};raw_owner::Snapshot value{};
  const bool passed=fstat(argument->fd,&own)==0 && raw_owner::Read(argument->fd,&value)==0 &&
                    own.st_ino!=argument->original.st_ino && SameStat(own,value.identity) &&
                    Check(argument->fd);
  details->thread_fdtable_checked=passed;
  return nullptr;
}
static bool PrivateCallerTable() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  PrivateTableArg argument{fd,{}};if(fstat(fd,&argument.original)<0)return false;
  pthread_t thread;
  const int created=pthread_create(&thread,nullptr,PrivateTableThread,&argument);
  if(created!=0){details->thread_error=created;return false;}
  const int joined=pthread_join(thread,nullptr);
  struct stat alive{};
  details->parent_fd_survived=fstat(fd,&alive)==0 && SameStat(argument.original,alive);
  return joined==0 && details->thread_error==0 && details->thread_fdtable_checked &&
         details->parent_fd_survived && Stop();
}
struct SharedVmArg {int fd;pid_t parent;};
static int SharedVmChild(void* opaque) {
  const auto* argument=static_cast<SharedVmArg*>(opaque);
  if(!Guard(argument->parent))return 81;
  raw_owner::Snapshot value{};
  errno=0;const int start=raw_owner::Start(),start_error=errno;
  errno=0;const int read=raw_owner::Read(argument->fd,&value),read_error=errno;
  details->shared_vm_rejected=start==-1 && start_error==EOPNOTSUPP &&
                              read==-1 && read_error==EOPNOTSUPP;
  return details->shared_vm_rejected?0:1;
}
static bool SharedVmGeneration() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  constexpr size_t size=128*1024;
  void* stack=mmap(nullptr,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
  if(stack==MAP_FAILED)return false;
  SharedVmArg argument{fd,getpid()};
  const pid_t child=clone(SharedVmChild,static_cast<char*>(stack)+size,CLONE_VM|SIGCHLD,&argument);
  if(child<0)return false;
  details->nested_started=1;bool timeout=false;int status=0;
  details->child_reaped=WaitOwned(child,2000,&status,&timeout);
  details->child_timeout=timeout;details->child_status=status;
  if(!details->child_reaped)return false;
  munmap(stack,size);
  return !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0 &&
         details->shared_vm_rejected && Check(fd) && Stop();
}
struct MetadataCase {const char* name;bool(*function)();bool known_red=false;};
static const MetadataCase kMetadataCases[]={
  {"real_metadata_three_entrypoints_same_app_context",Basic},
  {"forged_app_owned_tag_and_matching_name_stay_ordinary",ForgedAppFile},
  {"ordinary_O_PATH_metadata",OrdinaryOPath},
  {"warm_metadata_AS_1_and_explicit_restart",WarmLimitedAddressSpace},
  {"raw_private_fork_AS_1_real_metadata",RawForkLimitedAddressSpace},
  {"full_caller_fdtable_real_metadata",FullCallerTable},
  {"bad_fd_snapshot_atomicity_and_caller_mask",BadFdAndMask},
  {"quiesce_closes_generation_and_rejects_restart",ExplicitQuiesce},
  {"12_restart_kernel_clear_tid_rounds",RestartRounds},
  {"actual_caller_TID_private_fdtable",PrivateCallerTable},
  {"shared_VM_new_TGID_refuses_without_reset",SharedVmGeneration},
  {"NOFILE_0_metadata_EMFILE_known_red",NoFileZeroKnownRed,true},
};
