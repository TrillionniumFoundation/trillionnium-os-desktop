// SPDX-License-Identifier: Apache-2.0
// Owned real-source controls. No identity, fd-copy, namespace, or syscall seam.
#define BERBERIS_PROCMAPS_RAW_METADATA_OWNER 1
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <cstddef>
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

#if defined(OWNED_USE_PREIMAGE)
#include "preimage/proc_maps_raw_metadata_owner.cc"
#else
#include "actual/proc_maps_raw_metadata_owner.cc"
#endif
#include "actual/proc_maps_fd_owner.cc"
#include "actual/proc_maps_path.cc"
#include "actual/proc_maps_provenance.cc"
namespace raw_owner=berberis::proc_maps_provenance::raw_metadata_owner;
namespace provenance=berberis::proc_maps_provenance;

struct MetadataDiagnostic {
  int captured=0,stage=0,raw_valid=0,tagged=-99,stat_equal=-1,fs_equal=-1;
  int native_fs_available=0;
  struct stat native_stat{},raw_stat{};
  struct statfs native_fs{},raw_fs{};
};
struct KernelAbiRow {
  int attempted=0,raw_rc=-99,libc_rc=-99,owner_rc=-99,kernel_rc=-99,guest_rc=-99,projected_libc_rc=-99;
  int raw_errno=0,libc_errno=0,owner_errno=0,kernel_errno=0,guest_errno=0,projected_libc_errno=0;
  int owner_raw_equal=0,kernel_equal=0,guest_equal=0,owner_libc_equal=0,projected_libc_equal=0;
  provenance::KernelStatfs raw{},owner_raw{},kernel{},guest{};
  struct statfs libc{},owner_libc{},projected_libc{};
};
struct KernelAbiControl {
  int rows=0,stage=0;
  KernelAbiRow row[2]{};
  int native_error=0,kernel_error=0,guest_error=0,output_untouched=0;
  int invalid_native=0,invalid_guest=0,readonly_native=0,readonly_guest=0;
  int split_native=0,split_guest=0,readonly_untouched=0,prefix_bounds=0;
  uint64_t split_native_prefix=0,split_guest_prefix=0;
  int native_limit_rc=-99,kernel_limit_rc=-99,guest_limit_rc=-99;
};
struct MetadataDetails {
  KernelAbiControl kernel_abi{};
  MetadataDiagnostic diagnostic{};
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

static void CaptureMetadataDiagnostic(const struct stat& expected,
                                      const struct statfs& expected_fs,
                                      const raw_owner::Snapshot& value,
                                      int raw_result,bool preserved,int stage=1) {
  // Caller-only recording. It neither edits the fixed worker nor changes
  // the pre-existing SameStat/SameFs assertions.
  MetadataDiagnostic& out=details->diagnostic;
  if(out.captured)return;
  out.captured=1;out.stage=stage;out.raw_valid=raw_result==0;
  out.tagged=value.tagged;out.native_stat=expected;out.native_fs=expected_fs;
  out.raw_stat=value.identity;out.raw_fs=value.filesystem;out.native_fs_available=1;
  out.stat_equal=SameStat(expected,value.identity);
  out.fs_equal=SameFs(expected_fs,value.filesystem);
  if(raw_result<0)out.stage=2;
  else if(!preserved)out.stage=3;
  else if(value.tagged!=0)out.stage=4;
  else if(!out.stat_equal)out.stage=5;
  else if(!out.fs_equal)out.stage=6;
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
  CaptureMetadataDiagnostic(expected,expected_fs,snapshot,details->read,details->errno_preserved);
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
                    ([&]() {
                      // This case has an additional comparison before Check().
                      // Capture that same observation before its original assertion.
                      struct statfs observed_fs{};
                      const int saved=errno;
                      if(fstatfs(argument->fd,&observed_fs)==0)
                        CaptureMetadataDiagnostic(own,observed_fs,value,0,true,7);
                      errno=saved;
                      return true;
                    })() &&
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

static bool KernelStatfsDualOracles() {
  const int descriptors[2]={Seed(),open("/proc/thread-self/maps",O_RDONLY|O_CLOEXEC)};
  if(descriptors[0]<0 || descriptors[1]<0 || !Start())return false;
  for(unsigned index=0;index<2;++index) {
    auto& row=details->kernel_abi.row[index];
    row.attempted=1;details->kernel_abi.rows=static_cast<int>(index)+1;
    const int fd=descriptors[index];
    errno=201;row.raw_rc=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),&row.raw));
    row.raw_errno=errno;
    errno=202;row.libc_rc=::fstatfs(fd,&row.libc);row.libc_errno=errno;
    raw_owner::Snapshot snapshot{};
    errno=203;row.owner_rc=raw_owner::Read(fd,&snapshot);row.owner_errno=errno;
    row.owner_raw=snapshot.kernel_filesystem;row.owner_libc=snapshot.filesystem;
    errno=204;row.kernel_rc=provenance::FstatfsKernel(fd,&row.kernel,provenance::kCandidateConfiguration);
    row.kernel_errno=errno;
    errno=205;row.guest_rc=provenance::FstatfsForGuest(fd,&row.guest,provenance::kCandidateConfiguration);
    row.guest_errno=errno;
    errno=206;row.projected_libc_rc=provenance::Fstatfs(fd,&row.projected_libc,provenance::kCandidateConfiguration);
    row.projected_libc_errno=errno;
    // These are actual independent kernel syscall and libc API oracles.
    // Both structs cover exactly 120 bytes with no unnamed ABI padding;
    // compare every field, fsid word, flag, spare word, and counter.
    row.owner_raw_equal=memcmp(&row.raw,&row.owner_raw,sizeof(row.raw))==0;
    row.kernel_equal=memcmp(&row.raw,&row.kernel,sizeof(row.raw))==0;
    row.guest_equal=memcmp(&row.raw,&row.guest,sizeof(row.raw))==0;
    row.owner_libc_equal=memcmp(&row.libc,&row.owner_libc,sizeof(row.libc))==0;
    row.projected_libc_equal=memcmp(&row.libc,&row.projected_libc,sizeof(row.libc))==0;
    details->kernel_abi.stage=1;
    if(row.raw_rc!=0 || row.libc_rc!=0 || row.owner_rc!=0 || row.kernel_rc!=0 ||
       row.guest_rc!=0 || row.projected_libc_rc!=0 || snapshot.tagged!=0)return false;
    details->kernel_abi.stage=2;
    if(row.raw_errno!=201 || row.libc_errno!=202 || row.owner_errno!=203 ||
       row.kernel_errno!=204 || row.guest_errno!=205 || row.projected_libc_errno!=206)return false;
    details->kernel_abi.stage=3;
    if(!row.owner_raw_equal || !row.kernel_equal || !row.guest_equal ||
       !row.owner_libc_equal || !row.projected_libc_equal)return false;
  }
  details->kernel_abi.stage=4;
  return Stop();
}
static bool KernelStatfsBadFdAtomicity() {
  auto& control=details->kernel_abi;
  provenance::KernelStatfs output{},native{};
  unsigned char untouched[sizeof(output)];
  memset(untouched,0xa5,sizeof(untouched));
  memcpy(&output,untouched,sizeof(output));memcpy(&native,untouched,sizeof(native));
  errno=0;const int native_result=static_cast<int>(syscall(SYS_fstatfs,-1L,&native));
  control.native_error=errno;
  errno=0;const int kernel_result=provenance::FstatfsKernel(-1,&output,provenance::kCandidateConfiguration);
  control.kernel_error=errno;
  control.output_untouched=memcmp(&output,untouched,sizeof(output))==0 &&
                            memcmp(&native,untouched,sizeof(native))==0;
  errno=0;const int guest_result=provenance::FstatfsForGuest(-1,reinterpret_cast<void*>(uintptr_t{1}),
                                                           provenance::kCandidateConfiguration);
  control.guest_error=errno;
  return native_result==-1 && kernel_result==-1 && guest_result==-1 &&
         control.native_error==EBADF && control.kernel_error==EBADF &&
         control.guest_error==EBADF && control.output_untouched;
}
static bool KernelStatfsGuestFaults() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  auto& control=details->kernel_abi;
  errno=0;const int raw_invalid=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),1UL));
  control.invalid_native=errno;
  errno=0;const int guest_invalid=provenance::FstatfsForGuest(fd,reinterpret_cast<void*>(uintptr_t{1}),
                                                            provenance::kCandidateConfiguration);
  control.invalid_guest=errno;
  if(raw_invalid!=-1 || guest_invalid!=-1 || control.invalid_native!=EFAULT ||
     control.invalid_guest!=EFAULT)return false;
  const long page=sysconf(_SC_PAGESIZE);if(page<120 || page>65536)return false;
  auto* mapping=static_cast<unsigned char*>(mmap(nullptr,static_cast<size_t>(page)*2,
      PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
  if(mapping==MAP_FAILED)return false;
  memset(mapping,0x5a,static_cast<size_t>(page)*2);
  if(mprotect(mapping,static_cast<size_t>(page),PROT_READ)<0)return false;
  errno=0;const int raw_readonly=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),mapping));
  control.readonly_native=errno;
  errno=0;const int guest_readonly=provenance::FstatfsForGuest(fd,mapping,provenance::kCandidateConfiguration);
  control.readonly_guest=errno;control.readonly_untouched=1;
  for(long index=0;index<page;++index)if(mapping[index]!=0x5a)control.readonly_untouched=0;
  if(raw_readonly!=-1 || guest_readonly!=-1 || control.readonly_native!=EFAULT ||
     control.readonly_guest!=EFAULT || !control.readonly_untouched)return false;
  if(mprotect(mapping,static_cast<size_t>(page),PROT_READ|PROT_WRITE)<0 ||
     mprotect(mapping+page,static_cast<size_t>(page),PROT_NONE)<0)return false;
  unsigned char* crossing=mapping+page-8;
  errno=0;const int raw_split=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),crossing));
  control.split_native=errno;memcpy(&control.split_native_prefix,crossing,8);
  control.prefix_bounds=1;
  for(long index=0;index<page-8;++index)if(mapping[index]!=0x5a)control.prefix_bounds=0;
  memset(mapping,0x5a,static_cast<size_t>(page));
  errno=0;const int guest_split=provenance::FstatfsForGuest(fd,crossing,provenance::kCandidateConfiguration);
  control.split_guest=errno;memcpy(&control.split_guest_prefix,crossing,8);
  for(long index=0;index<page-8;++index)if(mapping[index]!=0x5a)control.prefix_bounds=0;
  // A failed kernel copy may leave a partial prefix. Do not invent a stronger
  // atomicity contract for user memory or require identical copy chunk sizes.
  const bool passed=raw_split==-1 && guest_split==-1 && control.split_native==EFAULT &&
                    control.split_guest==EFAULT && control.prefix_bounds;
  munmap(mapping,static_cast<size_t>(page)*2);
  return passed && Stop();
}
static bool KernelStatfsNoFileZeroKnownRed() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  auto& control=details->kernel_abi;
  const struct rlimit limit{0,0};if(setrlimit(RLIMIT_NOFILE,&limit)<0)return false;
  provenance::KernelStatfs native{},output{};
  unsigned char untouched[sizeof(output)];memset(untouched,0xa5,sizeof(untouched));
  memcpy(&output,untouched,sizeof(output));
  errno=0;control.native_limit_rc=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),&native));
  control.native_error=errno;
  errno=0;control.kernel_limit_rc=provenance::FstatfsKernel(fd,&output,provenance::kCandidateConfiguration);
  control.kernel_error=errno;
  control.output_untouched=memcmp(&output,untouched,sizeof(output))==0;
  errno=0;control.guest_limit_rc=provenance::FstatfsForGuest(fd,&output,provenance::kCandidateConfiguration);
  control.guest_error=errno;
  control.output_untouched=control.output_untouched && memcmp(&output,untouched,sizeof(output))==0;
  return control.native_limit_rc==0 && control.kernel_limit_rc==-1 && control.guest_limit_rc==-1 &&
         control.kernel_error==EMFILE && control.guest_error==EMFILE &&
         control.output_untouched && Stop();
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
  {"raw_statfs_kernel_and_libc_dual_oracles_all_fields",KernelStatfsDualOracles},
  {"raw_statfs_bad_fd_errno_and_metadata_output_atomicity",KernelStatfsBadFdAtomicity},
  {"raw_statfs_guest_buffer_EFAULT_and_partial_copy_bounds",KernelStatfsGuestFaults},
  {"raw_statfs_NOFILE_0_EMFILE_known_red",KernelStatfsNoFileZeroKnownRed,true},
};
