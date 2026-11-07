// SPDX-License-Identifier: Apache-2.0
// New recovery03 control source. No result from the lost harness is inherited.
#include <array>
#include <climits>
#include <cstdlib>
#include <linux/capability.h>
#include <new>
#include <type_traits>
#include "r21_cases_reused.cc"
static_assert(std::is_trivially_copyable_v<raw_owner::Snapshot>);

struct AddedRow {
  int attempted=0,stage=0;
  int raw_rc=-99,raw_errno=0,libc_rc=-99,libc_errno=0;
  int owner_rc=-99,owner_errno=0,kernel_rc=-99,kernel_errno=0;
  int guest_rc=-99,guest_errno=0,libc_projected_rc=-99,libc_projected_errno=0;
  int stat_rc=-99,stat_errno=0,origin_rc=-99,origin_errno=0;
  int raw_equal=0,kernel_equal=0,guest_equal=0,libc_equal=0,projected_libc_equal=0;
  int stat_equal=0,ordinary=0,context_equal=0;
  struct stat identity{},owner_identity{};
  provenance::KernelStatfs native{},owner{},kernel{},guest{};
  struct statfs libc{},owner_libc{},projected_libc{};
};
struct Extra {
  int setup_error=0,setup_done=0,limit_set=0,limit_errno=0;
  uint64_t limit_soft=UINT64_MAX,limit_hard=UINT64_MAX;
  int primary_attempts=0,primary_rc=-99,primary_errno=0,failed_snapshot_untouched=0;
  int pin_open_rc=-99,pin_open_errno=0,pin_getfd_rc=-99,pin_getfd_errno=0;
  int inherited_clear=0,rounds=0,rows=0;
  int raw_badfd_rc=-99,raw_badfd_errno=0,mask_preserved=0;
  int child_start=-99,child_start_errno=0,child_read=-99,child_read_errno=0;
  int child_native_rc=-99,child_stop=-99,child_tid_clear=0;
  int child_started=0,child_finished=0,child_reaped=0,child_timeout=0,child_status=-99;
  int parent_read=-99,parent_read_errno=0,parent_stop=-99,parent_fd_survives=0;
  int quiesce=-99,restart=-99,restart_errno=0;
  int thread_started=0,thread_joined=0,thread_error=0,private_table=0;
  int race_reads=0,race_a=0,race_b=0,race_rounds=0;
  int invalid_native_errno=0,invalid_guest_errno=0,readonly_native_errno=0,readonly_guest_errno=0;
  int split_native_errno=0,split_guest_errno=0,readonly_untouched=0,prefix_bounds=0;
  uint64_t native_prefix=0,guest_prefix=0;
  std::atomic<int> ready{0},go{0},done{0};
  AddedRow row[3]{};
};
struct CaseRecord {
  MetadataDetails metadata{};
  Extra extra{};
  std::atomic<int> entered{0},finished{0};
  int cap_clear=-99,cap_verified=0,guarded=0;
  uint32_t capabilities_before[6]{},capabilities_after[6]{};
  int function_passed=0,cleanup_stop=-99,persistent_tid_clear=0,inherited_tid_clear=0;
  int mask_preserved=0,child_status=-99,reaped=0,timed_out=0,unexpected_cleanup=0;
};
static CaseRecord* current;
static Extra* extra;

static int CapRead(uint32_t value[6]) {
  __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3,0};
  return static_cast<int>(syscall(SYS_capget,&header,value));
}
static bool ClearOwnedChildCapabilities() {
  if(CapRead(current->capabilities_before)<0)return false;
  __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3,0};
  const __user_cap_data_struct zero[2]{};
  current->cap_clear=static_cast<int>(syscall(SYS_capset,&header,zero));
  if(current->cap_clear<0 || CapRead(current->capabilities_after)<0)return false;
  current->cap_verified=1;
  for(uint32_t value:current->capabilities_after)if(value!=0)current->cap_verified=0;
  return current->cap_verified;
}
static bool ReadMask(uint64_t* value) {
  return syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),0UL,value,8UL)==0;
}
static bool InheritedClear() {
#if defined(OWNED_USE_PREIMAGE)
  return true;  // No one-shot worker exists in this exact preimage.
#else
  return raw_owner::state.inherited_tid.load(std::memory_order_acquire)==0;
#endif
}
static bool Limit(rlim_t value) {
  const rlimit limit{value,value};
  errno=0;extra->limit_set=setrlimit(RLIMIT_NOFILE,&limit);extra->limit_errno=errno;
  rlimit observed{};
  if(extra->limit_set!=0 || getrlimit(RLIMIT_NOFILE,&observed)!=0)return false;
  extra->limit_soft=observed.rlim_cur;extra->limit_hard=observed.rlim_max;
  return observed.rlim_cur==value && observed.rlim_max==value;
}
static bool AddedRead(int fd,raw_owner::Snapshot* snapshot,int sentinel=203) {
  unsigned char initial[sizeof(*snapshot)];
  memset(initial,0xa5,sizeof(initial));memcpy(snapshot,initial,sizeof(initial));
  errno=sentinel;const int result=raw_owner::Read(fd,snapshot);const int error=errno;
  if(extra->primary_attempts++==0) {
    extra->primary_rc=result;extra->primary_errno=error;
    extra->failed_snapshot_untouched=result<0 && memcmp(initial,snapshot,sizeof(initial))==0;
  }
  extra->inherited_clear=InheritedClear();
  return result==0 && error==sentinel && extra->inherited_clear;
}
static bool AllViews(int fd,unsigned index) {
  if(index>=3)return false;
  auto& row=extra->row[index];row.attempted=1;extra->rows=static_cast<int>(index)+1;
  errno=201;row.raw_rc=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),&row.native));row.raw_errno=errno;
  errno=202;row.libc_rc=::fstatfs(fd,&row.libc);row.libc_errno=errno;
  if(fstat(fd,&row.identity)<0 || row.raw_rc!=0 || row.libc_rc!=0 || row.raw_errno!=201 || row.libc_errno!=202)return false;
  row.stage=1;raw_owner::Snapshot value{};
  const bool read=AddedRead(fd,&value);row.owner_rc=extra->primary_attempts==1?extra->primary_rc:(read?0:-1);
  row.owner_errno=errno;
  if(!read)return false;
  row.owner=value.kernel_filesystem;row.owner_libc=value.filesystem;row.owner_identity=value.identity;
  row.ordinary=value.tagged==0;
  row.context_equal=raw_owner::SameContext(value.worker_before,value.worker_after) &&
      value.worker_before.uid[0]==static_cast<uint32_t>(getuid()) && value.worker_before.uid[0]!=0;
  errno=204;row.kernel_rc=provenance::FstatfsKernel(fd,&row.kernel,provenance::kCandidateConfiguration);row.kernel_errno=errno;
  errno=205;row.guest_rc=provenance::FstatfsForGuest(fd,&row.guest,provenance::kCandidateConfiguration);row.guest_errno=errno;
  errno=206;row.libc_projected_rc=provenance::Fstatfs(fd,&row.projected_libc,provenance::kCandidateConfiguration);row.libc_projected_errno=errno;
  struct stat projected{};provenance::Origin origin{};
  errno=211;row.stat_rc=provenance::Fstat(fd,&projected,provenance::kCandidateConfiguration);row.stat_errno=errno;
  errno=212;row.origin_rc=static_cast<int>(provenance::QueryOrigin(fd,provenance::kCandidateConfiguration,&origin));row.origin_errno=errno;
  row.raw_equal=memcmp(&row.native,&row.owner,sizeof(row.native))==0;
  row.kernel_equal=memcmp(&row.native,&row.kernel,sizeof(row.native))==0;
  row.guest_equal=memcmp(&row.native,&row.guest,sizeof(row.native))==0;
  row.libc_equal=memcmp(&row.libc,&row.owner_libc,sizeof(row.libc))==0;
  row.projected_libc_equal=memcmp(&row.libc,&row.projected_libc,sizeof(row.libc))==0;
  row.stat_equal=SameStat(row.identity,row.owner_identity) && SameStat(row.identity,projected);
  row.stage=2;
  return row.kernel_rc==0 && row.guest_rc==0 && row.libc_projected_rc==0 && row.stat_rc==0 &&
      row.origin_rc==static_cast<int>(provenance::Lookup::kOrdinary) && row.kernel_errno==204 && row.guest_errno==205 &&
      row.libc_projected_errno==206 && row.stat_errno==211 && row.origin_errno==212 && row.raw_equal && row.kernel_equal &&
      row.guest_equal && row.libc_equal && row.projected_libc_equal && row.stat_equal && row.ordinary && row.context_equal;
}
static bool ZeroAllViews() {
  const int fd=Seed();const int maps=open("/proc/thread-self/maps",O_RDONLY|O_CLOEXEC);
  char path[96];const int count=snprintf(path,sizeof(path),"/proc/thread-self/fd/%d",fd);
  if(fd<0 || maps<0 || count<=0 || static_cast<size_t>(count)>=sizeof(path))return false;
  const int opath=open(path,O_PATH|O_CLOEXEC);
  if(opath<0 || !Start())return false;
  extra->setup_done=1;if(!Limit(0))return false;
  errno=0;extra->pin_open_rc=static_cast<int>(syscall(SYS_pidfd_open,static_cast<long>(syscall(SYS_gettid)),static_cast<unsigned long>(O_EXCL)));
  extra->pin_open_errno=errno;
  if(extra->pin_open_rc!=-1 || extra->pin_open_errno!=EMFILE)return false;
  return AllViews(fd,0) && AllViews(maps,1) && AllViews(opath,2) && Stop();
}
static bool OneSlotPinGetfd() {
  const int fd=Seed();if(fd<3 || !Start())return false;
  extra->setup_done=1;if(!Limit(1))return false;
  // This is the case process's own fork-private table; its parent keeps fd0.
  if(close(0)<0 && errno!=EBADF)return false;
  errno=0;const int self=static_cast<int>(syscall(SYS_pidfd_open,static_cast<long>(syscall(SYS_gettid)),static_cast<unsigned long>(O_EXCL)));
  extra->pin_open_rc=self;extra->pin_open_errno=errno;
  if(self!=0){if(self>=0)close(self);return false;}
  errno=0;extra->pin_getfd_rc=static_cast<int>(syscall(SYS_pidfd_getfd,static_cast<long>(self),static_cast<long>(fd),0UL));
  extra->pin_getfd_errno=errno;close(self);
  if(extra->pin_getfd_rc!=-1 || extra->pin_getfd_errno!=EMFILE)return false;
  return AllViews(fd,0) && Stop();
}
static bool ZeroAndAddressSpaceOne() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  extra->setup_done=1;if(!Limit(0))return false;
  const rlimit limit{1,1};if(setrlimit(RLIMIT_AS,&limit)<0)return false;
  return AllViews(fd,0) && Stop();
}
static bool ZeroBadFdAtomicityMask() {
  uint64_t original=0,entered=0,after=0;
  if(!ReadMask(&original))return false;
  entered=original|(UINT64_C(1)<<(SIGUSR1-1));
  if(syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),&entered,0UL,8UL)<0 || !Start())return false;
  extra->setup_done=1;if(!Limit(0))return false;
  struct stat native{};errno=0;extra->raw_badfd_rc=fstat(INT_MAX,&native);extra->raw_badfd_errno=errno;
  raw_owner::Snapshot snapshot{};AddedRead(INT_MAX,&snapshot,0);
  bool result=extra->raw_badfd_rc==-1 && extra->raw_badfd_errno==EBADF &&
      extra->primary_rc==-1 && extra->primary_errno==EBADF && extra->failed_snapshot_untouched && Stop();
  if(!ReadMask(&after))result=false;
  extra->mask_preserved=after==entered;
  const bool restored=syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),&original,0UL,8UL)==0;
  return result && restored && extra->mask_preserved;
}
static bool ZeroGuestFaults() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  const long page=sysconf(_SC_PAGESIZE);if(page<120 || page>65536)return false;
  auto* buffer=static_cast<unsigned char*>(mmap(nullptr,static_cast<size_t>(page)*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
  if(buffer==MAP_FAILED)return false;
  memset(buffer,0x5a,static_cast<size_t>(page)*2);
  extra->setup_done=1;if(!Limit(0))return false;
  raw_owner::Snapshot value{};if(!AddedRead(fd,&value))return false;
  errno=0;const int native_invalid=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),1UL));extra->invalid_native_errno=errno;
  errno=0;const int guest_invalid=provenance::FstatfsForGuest(fd,reinterpret_cast<void*>(uintptr_t{1}),provenance::kCandidateConfiguration);extra->invalid_guest_errno=errno;
  if(mprotect(buffer,static_cast<size_t>(page),PROT_READ)<0)return false;
  errno=0;const int native_readonly=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),buffer));extra->readonly_native_errno=errno;
  errno=0;const int guest_readonly=provenance::FstatfsForGuest(fd,buffer,provenance::kCandidateConfiguration);extra->readonly_guest_errno=errno;
  extra->readonly_untouched=1;
  for(long i=0;i<page;++i)if(buffer[i]!=0x5a)extra->readonly_untouched=0;
  if(mprotect(buffer,static_cast<size_t>(page),PROT_READ|PROT_WRITE)<0 || mprotect(buffer+page,static_cast<size_t>(page),PROT_NONE)<0)return false;
  auto* crossing=buffer+page-8;
  errno=0;const int native_split=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),crossing));extra->split_native_errno=errno;
  memcpy(&extra->native_prefix,crossing,8);extra->prefix_bounds=1;
  for(long i=0;i<page-8;++i)if(buffer[i]!=0x5a)extra->prefix_bounds=0;
  memset(buffer,0x5a,static_cast<size_t>(page));
  errno=0;const int guest_split=provenance::FstatfsForGuest(fd,crossing,provenance::kCandidateConfiguration);extra->split_guest_errno=errno;
  memcpy(&extra->guest_prefix,crossing,8);
  for(long i=0;i<page-8;++i)if(buffer[i]!=0x5a)extra->prefix_bounds=0;
  const bool result=native_invalid==-1 && guest_invalid==-1 && extra->invalid_native_errno==EFAULT && extra->invalid_guest_errno==EFAULT &&
      native_readonly==-1 && guest_readonly==-1 && extra->readonly_native_errno==EFAULT && extra->readonly_guest_errno==EFAULT && extra->readonly_untouched &&
      native_split==-1 && guest_split==-1 && extra->split_native_errno==EFAULT && extra->split_guest_errno==EFAULT && extra->prefix_bounds;
  munmap(buffer,static_cast<size_t>(page)*2);
  return result && Stop();
}
static bool ZeroRepeatedOneShot() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  extra->setup_done=1;if(!Limit(0))return false;
  for(int i=0;i<24;++i) {
    raw_owner::Snapshot value{};
    if(!AddedRead(fd,&value) || value.tagged!=0 || !InheritedClear())return false;
    ++extra->rounds;
  }
  return Stop();
}
struct NewPrivateArg {int fd;struct stat original;};
static void* ZeroPrivateThread(void* opaque) {
  const auto* argument=static_cast<NewPrivateArg*>(opaque);
  if(syscall(SYS_unshare,static_cast<unsigned long>(CLONE_FILES))<0){extra->thread_error=errno;return nullptr;}
  if(close(argument->fd)<0){extra->thread_error=errno;return nullptr;}
  const int own=Seed(false,41);
  if(own<0 || (own!=argument->fd && dup3(own,argument->fd,O_CLOEXEC)<0)){extra->thread_error=errno;return nullptr;}
  struct stat stat{};if(fstat(argument->fd,&stat)<0 || SameStat(stat,argument->original)){extra->thread_error=EINVAL;return nullptr;}
  extra->private_table=1;extra->setup_done=1;
  if(!Limit(0)){extra->thread_error=errno;return nullptr;}
  raw_owner::Snapshot value{};
  const bool read=AddedRead(argument->fd,&value);
  if(!read)return nullptr;
  if(!SameStat(stat,value.identity) || !AllViews(argument->fd,0))extra->thread_error=EIO;
  return nullptr;
}
static bool ZeroPrivateCallerTable() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  NewPrivateArg argument{fd,{}};if(fstat(fd,&argument.original)<0)return false;
  pthread_t thread;const int created=pthread_create(&thread,nullptr,ZeroPrivateThread,&argument);
  if(created!=0){extra->thread_error=created;return false;}
  extra->thread_started=1;const int joined=pthread_join(thread,nullptr);extra->thread_joined=joined==0;
  struct stat alive{};extra->parent_fd_survives=fstat(fd,&alive)==0 && SameStat(alive,argument.original);
  return joined==0 && extra->thread_error==0 && extra->private_table && extra->primary_rc==0 &&
      extra->row[0].stage==2 && extra->parent_fd_survives && Stop();
}
static bool ZeroQuiesce() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  extra->setup_done=1;if(!Limit(0))return false;
  raw_owner::Snapshot value{};if(!AddedRead(fd,&value))return false;
  extra->quiesce=raw_owner::QuiesceBeforeTransition();
  errno=0;extra->restart=raw_owner::Start();extra->restart_errno=errno;
  errno=0;extra->child_read=raw_owner::Read(fd,&value);extra->child_read_errno=errno;
  return extra->quiesce==0 && extra->restart==-1 && extra->restart_errno==ESHUTDOWN &&
      extra->child_read==-1 && extra->child_read_errno==ESHUTDOWN && !raw_owner::Enabled() && InheritedClear();
}
static bool NestedReap(pid_t child) {
  bool timeout=false;int status=0;
  extra->child_reaped=WaitOwned(child,4000,&status,&timeout);
  extra->child_timeout=timeout;extra->child_status=status;
  return extra->child_reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0;
}
static bool ZeroAfterPrivateFork() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  const pid_t parent=getpid();const pid_t child=static_cast<pid_t>(syscall(SYS_clone,static_cast<unsigned long>(SIGCHLD),0UL,0UL,0UL,0UL));
  if(child<0){extra->setup_error=errno;return false;}
  if(child==0) {
    if(!Guard(parent))_exit(81);
    raw_owner::ResetAfterPrivateFork();errno=0;extra->child_start=raw_owner::Start();extra->child_start_errno=errno;
    bool ok=extra->child_start==0;
    if(ok){extra->setup_done=1;ok=Limit(0) && AllViews(fd,0);}
    extra->child_stop=raw_owner::Stop();extra->child_tid_clear=raw_owner::state.tid.load(std::memory_order_acquire)==0 && InheritedClear();
    extra->child_finished=1;_exit(ok && extra->child_stop==0 && extra->child_tid_clear?0:1);
  }
  extra->child_started=1;const bool child_ok=NestedReap(child);
  raw_owner::Snapshot after{};extra->parent_read=raw_owner::Read(fd,&after);extra->parent_read_errno=errno;
  extra->parent_stop=raw_owner::Stop();struct stat alive{};
  extra->parent_fd_survives=fstat(fd,&alive)==0 && SameStat(after.identity,alive);
  return child_ok && extra->child_finished && extra->parent_read==0 && extra->parent_stop==0 && extra->parent_fd_survives;
}
static bool ZeroCloseReuseRace() {
  const int first=Seed();const int second=open("/proc/thread-self/maps",O_RDONLY|O_CLOEXEC);
  const int target=first<0?-1:fcntl(first,F_DUPFD_CLOEXEC,8);
  if(first<0 || second<0 || target<0)return false;
  struct stat identities[2]{};provenance::KernelStatfs filesystems[2]{};
  if(fstat(first,&identities[0])<0 || fstat(second,&identities[1])<0 ||
     syscall(SYS_fstatfs,static_cast<long>(first),&filesystems[0])<0 ||
     syscall(SYS_fstatfs,static_cast<long>(second),&filesystems[1])<0 || !Start())return false;
  const pid_t parent=getpid();
  const pid_t child=static_cast<pid_t>(syscall(SYS_clone,static_cast<unsigned long>(CLONE_FILES|SIGCHLD),0UL,0UL,0UL,0UL));
  if(child<0){extra->setup_error=errno;return false;}
  if(child==0) {
    if(!Guard(parent))_exit(81);
    raw_owner::ResetAfterPrivateFork();errno=0;extra->child_start=raw_owner::Start();extra->child_start_errno=errno;
    bool ok=extra->child_start==0;
    if(ok){extra->setup_done=1;ok=Limit(0);}
    extra->ready.store(1,std::memory_order_release);
    const int64_t until=Now()+3000;const timespec delay{0,1000000};
    while(!extra->go.load(std::memory_order_acquire) && Now()<until)nanosleep(&delay,nullptr);
    if(!extra->go.load(std::memory_order_acquire))ok=false;
    for(int i=0;ok && i<64;++i) {
      raw_owner::Snapshot value{};ok=AddedRead(target,&value);
      if(!ok)break;
      const bool a=SameStat(identities[0],value.identity) && memcmp(&filesystems[0],&value.kernel_filesystem,sizeof(filesystems[0]))==0;
      const bool b=SameStat(identities[1],value.identity) && memcmp(&filesystems[1],&value.kernel_filesystem,sizeof(filesystems[1]))==0;
      ok=(a!=b) && value.tagged==0;
      if(ok){++extra->race_reads;if(a)++extra->race_a;else ++extra->race_b;}
    }
    extra->child_stop=raw_owner::Stop();extra->child_tid_clear=raw_owner::state.tid.load(std::memory_order_acquire)==0 && InheritedClear();
    extra->child_finished=1;extra->done.store(1,std::memory_order_release);
    _exit(ok && extra->race_reads==64 && extra->child_stop==0 && extra->child_tid_clear?0:1);
  }
  extra->child_started=1;const int64_t until=Now()+3500;const timespec delay{0,1000000};
  while(!extra->ready.load(std::memory_order_acquire) && Now()<until)nanosleep(&delay,nullptr);
  bool ok=extra->ready.load(std::memory_order_acquire)!=0;
  if(ok) {
    ok=dup3(second,target,O_CLOEXEC)==target;
    if(ok)++extra->race_rounds;
  }
  extra->go.store(1,std::memory_order_release);
  while(ok && !extra->done.load(std::memory_order_acquire) && Now()<until) {
    const int fd=(extra->race_rounds&1)?second:first;
    if(dup3(fd,target,O_CLOEXEC)!=target){ok=false;break;}
    ++extra->race_rounds;
    if((extra->race_rounds&31)==0)sched_yield();
  }
  const bool child_ok=NestedReap(child);extra->parent_stop=raw_owner::Stop();
  struct stat a{},b{};extra->parent_fd_survives=fstat(first,&a)==0 && fstat(second,&b)==0 && SameStat(a,identities[0]) && SameStat(b,identities[1]);
  return ok && child_ok && extra->child_finished && extra->race_reads==64 && extra->race_rounds>0 &&
      extra->parent_stop==0 && extra->parent_fd_survives;
}
static bool InitiallyZeroRemainsRejected() {
  const int fd=Seed();if(fd<0)return false;
  extra->setup_done=1;if(!Limit(0))return false;
  provenance::KernelStatfs raw{};extra->child_native_rc=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),&raw));
  errno=0;extra->child_start=raw_owner::Start();extra->child_start_errno=errno;
  raw_owner::Snapshot value{};unsigned char before[sizeof(value)];memset(before,0xa5,sizeof(before));memcpy(&value,before,sizeof(value));
  errno=0;extra->child_read=raw_owner::Read(fd,&value);extra->child_read_errno=errno;
  extra->failed_snapshot_untouched=memcmp(before,&value,sizeof(value))==0;
  extra->child_stop=raw_owner::Stop();extra->child_tid_clear=raw_owner::state.tid.load(std::memory_order_acquire)==0 && InheritedClear();
  return extra->child_native_rc==0 && extra->child_start==-1 && extra->child_start_errno==EMFILE &&
      extra->child_read==-1 && extra->child_read_errno==ESHUTDOWN && extra->failed_snapshot_untouched &&
      extra->child_stop==0 && extra->child_tid_clear && !raw_owner::Enabled();
}
static bool ForkAfterZeroRemainsRejectedParentWorks() {
  const int fd=Seed();if(fd<0 || !Start())return false;
  extra->setup_done=1;if(!Limit(0))return false;
  const pid_t parent=getpid();const pid_t child=static_cast<pid_t>(syscall(SYS_clone,static_cast<unsigned long>(SIGCHLD),0UL,0UL,0UL,0UL));
  if(child<0){extra->setup_error=errno;return false;}
  if(child==0) {
    if(!Guard(parent))_exit(81);
    raw_owner::ResetAfterPrivateFork();provenance::KernelStatfs raw{};
    extra->child_native_rc=static_cast<int>(syscall(SYS_fstatfs,static_cast<long>(fd),&raw));
    errno=0;extra->child_start=raw_owner::Start();extra->child_start_errno=errno;
    raw_owner::Snapshot value{};errno=0;extra->child_read=raw_owner::Read(fd,&value);extra->child_read_errno=errno;
    extra->child_stop=raw_owner::Stop();extra->child_tid_clear=raw_owner::state.tid.load(std::memory_order_acquire)==0 && InheritedClear();
    extra->child_finished=1;
    _exit(extra->child_native_rc==0 && extra->child_start==-1 && extra->child_start_errno==EMFILE &&
          extra->child_read==-1 && extra->child_read_errno==ESHUTDOWN && extra->child_stop==0 && extra->child_tid_clear?0:1);
  }
  extra->child_started=1;const bool child_ok=NestedReap(child);
  raw_owner::Snapshot after{};const bool parent_ok=AddedRead(fd,&after);
  extra->parent_read=extra->primary_rc;extra->parent_read_errno=extra->primary_errno;extra->parent_stop=raw_owner::Stop();
  struct stat alive{};extra->parent_fd_survives=fstat(fd,&alive)==0;
  return child_ok && extra->child_finished && parent_ok && extra->parent_stop==0 && extra->parent_fd_survives;
}

struct Case {const char* name;bool(*function)();int original=-1;bool baseline_failure=false;bool known_red=false;};
static const Case cases[]={
  {"legacy_real_metadata_three_entrypoints",Basic,0},
  {"legacy_forged_app_tag_stays_ordinary",ForgedAppFile,1},
  {"legacy_ordinary_O_PATH",OrdinaryOPath,2},
  {"legacy_warm_AS1_restart",WarmLimitedAddressSpace,3},
  {"legacy_raw_private_fork_AS1",RawForkLimitedAddressSpace,4},
  {"legacy_full_caller_table",FullCallerTable,5},
  {"legacy_badfd_atomicity_mask",BadFdAndMask,6},
  {"legacy_quiesce_closed_generation",ExplicitQuiesce,7},
  {"legacy_twelve_restart_clear_tid",RestartRounds,8},
  {"legacy_private_caller_fdtable",PrivateCallerTable,9},
  {"legacy_shared_VM_new_TGID_rejected",SharedVmGeneration,10},
  {"legacy_raw_and_libc_dual_oracles",KernelStatfsDualOracles,12},
  {"legacy_badfd_kernel_guest_atomicity",KernelStatfsBadFdAtomicity,13},
  {"legacy_guest_EFAULT_partial_bounds",KernelStatfsGuestFaults,14},
  {"NOFILE0_three_objects_all_metadata_views",ZeroAllViews,-1,true},
  {"NOFILE1_getfd_allocation_stage",OneSlotPinGetfd,-1,true},
  {"NOFILE0_AS1_warm_fixed_stacks",ZeroAndAddressSpaceOne,-1,true},
  {"NOFILE0_badfd_atomicity_mask",ZeroBadFdAtomicityMask,-1,true},
  {"NOFILE0_guest_EFAULT_partial_bounds",ZeroGuestFaults,-1,true},
  {"NOFILE0_24_one_shot_clear_tid_rounds",ZeroRepeatedOneShot,-1,true},
  {"NOFILE0_actual_private_caller_table",ZeroPrivateCallerTable,-1,true},
  {"NOFILE0_quiesce_and_restart_rejection",ZeroQuiesce,-1,true},
  {"private_fork_start_before_NOFILE0",ZeroAfterPrivateFork,-1,true},
  {"NOFILE0_shared_fdtable_close_reuse",ZeroCloseReuseRace,-1,true},
  {"initial_NOFILE0_authority_still_rejected",InitiallyZeroRemainsRejected,-1,false,true},
  {"fork_after_NOFILE0_child_rejected_parent_works",ForkAfterZeroRemainsRejectedParentWorks,-1,true,true},
};
static_assert(std::size(cases)==26);

// Only this executable's direct/adopted children are eligible for cleanup.
static int ReapUnexpectedOwnedChildren() {
  int count=0;
  const int64_t until=Now()+2000;
  while(Now()<until) {
    char path[96];snprintf(path,sizeof(path),"/proc/self/task/%d/children",getpid());
    const int fd=open(path,O_RDONLY|O_CLOEXEC);if(fd<0)return -1;
    char bytes[4096]{};const ssize_t size=read(fd,bytes,sizeof(bytes)-1);close(fd);
    if(size<0 || static_cast<size_t>(size)>=sizeof(bytes)-1)return -1;
    char* cursor=bytes;bool present=false;
    while(*cursor) {
      char* end=nullptr;const long parsed=strtol(cursor,&end,10);
      if(end==cursor){if(*cursor==' ' || *cursor=='\n'){++cursor;continue;}return -1;}
      cursor=end;if(parsed<=0 || parsed>INT_MAX)return -1;
      present=true;const pid_t pid=static_cast<pid_t>(parsed);int status=0;
      const pid_t reaped=waitpid(pid,&status,WNOHANG);
      if(reaped==pid){++count;continue;}
      if(reaped<0){if(errno==ECHILD)continue;return -1;}
      const int pidfd=static_cast<int>(syscall(SYS_pidfd_open,static_cast<long>(pid),0UL));
      if(pidfd<0)return -1;
      const int killed=static_cast<int>(syscall(SYS_pidfd_send_signal,static_cast<long>(pidfd),static_cast<long>(SIGKILL),0UL,0UL));
      const int error=errno;close(pidfd);if(killed<0 && error!=ESRCH)return -1;
      bool timeout=false;if(!WaitOwned(pid,1000,&status,&timeout))return -1;++count;
    }
    if(!present)return count;
  }
  return -1;
}
static void HexBytes(const void* bytes,size_t size) {
  const auto* p=static_cast<const unsigned char*>(bytes);putchar('"');
  for(size_t i=0;i<size;++i)printf("%02x",static_cast<unsigned>(p[i]));
  putchar('"');
}
static void PrintRecord(unsigned index,const CaseRecord& record,bool expected,bool matched) {
  const auto& m=record.metadata;const auto& x=record.extra;
  printf("{\"index\":%u,\"name\":\"%s\",\"expected_function_pass\":%s,\"function_pass\":%s,\"matches_expectation\":%s,\"known_red_boundary\":%s,",
      index,cases[index].name,expected?"true":"false",record.function_passed?"true":"false",matched?"true":"false",cases[index].known_red?"true":"false");
  printf("\"outer\":{\"entered\":%d,\"finished\":%d,\"reaped\":%d,\"timeout\":%d,\"status\":%d,\"cleanup_stop\":%d,\"persistent_tid_clear\":%d,\"inherited_tid_clear\":%d,\"cap_clear\":%d,\"caps_zero\":%d,\"guarded\":%d,\"mask_preserved\":%d,\"unexpected_cleanup\":%d},",
      record.entered.load(),record.finished.load(),record.reaped,record.timed_out,record.child_status,record.cleanup_stop,record.persistent_tid_clear,
      record.inherited_tid_clear,record.cap_clear,record.cap_verified,record.guarded,record.mask_preserved,record.unexpected_cleanup);
  printf("\"metadata\":{\"start\":%d,\"start_errno\":%d,\"read\":%d,\"read_errno\":%d,\"stop\":%d,\"native_stat\":%d,\"native_fs\":%d,\"projected_stat\":%d,\"projected_fs\":%d,\"lookup\":%d,\"caller_uid\":%d,\"worker_uid\":%d,\"same_namespace\":%d,\"inherited_stack\":%d,\"nested_started\":%d,\"child_finished\":%d,\"child_reaped\":%d,\"child_timeout\":%d,\"child_status\":%d,\"parent_read\":%d,\"parent_stop\":%d,\"parent_fd_survived\":%d,\"rounds\":%d,\"kernel_stage\":%d},",
      m.start,m.start_error,m.read,m.read_error,m.stop,m.native_stat,m.native_fs,m.projected_stat,m.projected_fs,m.lookup,m.caller_uid,m.worker_uid,m.same_namespace,
      m.inherited_stack,m.nested_started,m.child_finished,m.child_reaped,m.child_timeout,m.child_status,m.parent_read,m.parent_stop,m.parent_fd_survived,m.rounds,m.kernel_abi.stage);
  printf("\"added\":{\"setup_error\":%d,\"setup_done\":%d,\"limit_rc\":%d,\"limit_errno\":%d,\"limit_soft\":%llu,\"limit_hard\":%llu,\"primary_attempts\":%d,\"primary_rc\":%d,\"primary_errno\":%d,\"failed_snapshot_untouched\":%d,\"pin_open_rc\":%d,\"pin_open_errno\":%d,\"pin_getfd_rc\":%d,\"pin_getfd_errno\":%d,\"inherited_clear\":%d,\"rounds\":%d,",
      x.setup_error,x.setup_done,x.limit_set,x.limit_errno,static_cast<unsigned long long>(x.limit_soft),static_cast<unsigned long long>(x.limit_hard),
      x.primary_attempts,x.primary_rc,x.primary_errno,x.failed_snapshot_untouched,x.pin_open_rc,x.pin_open_errno,x.pin_getfd_rc,x.pin_getfd_errno,x.inherited_clear,x.rounds);
  printf("\"child_start\":%d,\"child_start_errno\":%d,\"child_read\":%d,\"child_read_errno\":%d,\"child_native_rc\":%d,\"child_stop\":%d,\"child_tid_clear\":%d,\"child_started\":%d,\"child_finished\":%d,\"child_reaped\":%d,\"child_timeout\":%d,\"child_status\":%d,\"parent_read\":%d,\"parent_read_errno\":%d,\"parent_stop\":%d,\"parent_fd_survives\":%d,\"quiesce\":%d,\"restart\":%d,\"restart_errno\":%d,\"thread_started\":%d,\"thread_joined\":%d,\"thread_error\":%d,\"private_table\":%d,\"race_reads\":%d,\"race_a\":%d,\"race_b\":%d,\"race_rounds\":%d,\"readonly_untouched\":%d,\"prefix_bounds\":%d,",
      x.child_start,x.child_start_errno,x.child_read,x.child_read_errno,x.child_native_rc,x.child_stop,x.child_tid_clear,x.child_started,x.child_finished,x.child_reaped,
      x.child_timeout,x.child_status,x.parent_read,x.parent_read_errno,x.parent_stop,x.parent_fd_survives,x.quiesce,x.restart,x.restart_errno,x.thread_started,
      x.thread_joined,x.thread_error,x.private_table,x.race_reads,x.race_a,x.race_b,x.race_rounds,x.readonly_untouched,x.prefix_bounds);
  printf("\"raw_badfd_rc\":%d,\"raw_badfd_errno\":%d,\"mask_preserved\":%d,\"invalid_native_errno\":%d,\"invalid_guest_errno\":%d,\"readonly_native_errno\":%d,\"readonly_guest_errno\":%d,\"split_native_errno\":%d,\"split_guest_errno\":%d,\"native_prefix\":%llu,\"guest_prefix\":%llu,\"rows\":[",
      x.raw_badfd_rc,x.raw_badfd_errno,x.mask_preserved,x.invalid_native_errno,x.invalid_guest_errno,x.readonly_native_errno,
      x.readonly_guest_errno,x.split_native_errno,x.split_guest_errno,static_cast<unsigned long long>(x.native_prefix),
      static_cast<unsigned long long>(x.guest_prefix));
  for(int i=0;i<x.rows && i<3;++i) {
    const auto& r=x.row[i];if(i)putchar(',');
    printf("{\"stage\":%d,\"raw_rc\":%d,\"raw_errno\":%d,\"libc_rc\":%d,\"libc_errno\":%d,\"owner_rc\":%d,\"owner_errno\":%d,\"kernel_rc\":%d,\"kernel_errno\":%d,\"guest_rc\":%d,\"guest_errno\":%d,\"libc_projected_rc\":%d,\"libc_projected_errno\":%d,\"stat_rc\":%d,\"stat_errno\":%d,\"origin_rc\":%d,\"origin_errno\":%d,\"raw_equal\":%d,\"kernel_equal\":%d,\"guest_equal\":%d,\"libc_equal\":%d,\"projected_libc_equal\":%d,\"stat_equal\":%d,\"ordinary\":%d,\"context_equal\":%d,\"raw120\":",
      r.stage,r.raw_rc,r.raw_errno,r.libc_rc,r.libc_errno,r.owner_rc,r.owner_errno,r.kernel_rc,r.kernel_errno,r.guest_rc,r.guest_errno,r.libc_projected_rc,r.libc_projected_errno,
      r.stat_rc,r.stat_errno,r.origin_rc,r.origin_errno,r.raw_equal,r.kernel_equal,r.guest_equal,r.libc_equal,r.projected_libc_equal,r.stat_equal,r.ordinary,r.context_equal);
    HexBytes(&r.native,sizeof(r.native));printf(",\"owner_raw120\":");HexBytes(&r.owner,sizeof(r.owner));
    printf(",\"kernel120\":");HexBytes(&r.kernel,sizeof(r.kernel));printf(",\"guest120\":");HexBytes(&r.guest,sizeof(r.guest));
    printf(",\"native_libc\":");HexBytes(&r.libc,sizeof(r.libc));printf(",\"owner_libc\":");HexBytes(&r.owner_libc,sizeof(r.owner_libc));
    printf(",\"projected_libc\":");HexBytes(&r.projected_libc,sizeof(r.projected_libc));putchar('}');
  }
  printf("]}}");
}
static bool RootRejection() {
  if(getuid()!=0 || geteuid()!=0)return false;
  uint64_t before=0,after=0;if(!ReadMask(&before))return false;
  const int fd=Seed();if(fd<0)return false;
  errno=0;const int start=raw_owner::Start(),error=errno;
  raw_owner::Snapshot value{};unsigned char unchanged[sizeof(value)];memset(unchanged,0xa5,sizeof(unchanged));memcpy(&value,unchanged,sizeof(value));
  errno=0;const int read=raw_owner::Read(fd,&value),read_error=errno;
  const int stop=raw_owner::Stop();const bool mask=ReadMask(&after) && before==after;
  const bool pass=start==-1 && error==EPERM && read==-1 && read_error==ESHUTDOWN &&
      memcmp(&value,unchanged,sizeof(value))==0 && stop==0 && mask && InheritedClear() && raw_owner::state.tid.load()==0;
  printf("{\"scope\":\"root admission negative only\",\"start\":%d,\"errno\":%d,\"read\":%d,\"read_errno\":%d,\"stop\":%d,\"mask_preserved\":%s,\"pass\":%s,\"positive_controls_executed\":false}\n",
      start,error,read,read_error,stop,mask?"true":"false",pass?"true":"false");
  close(fd);return pass;
}
int main(int argc,char** argv) {
#if defined(OWNED_USE_PREIMAGE)
  constexpr bool preimage=true;
#else
  constexpr bool preimage=false;
#endif
  if(argc==1) {
    printf("{\"mode\":\"PLAN\",\"revision\":\"recovery03\",\"case_count\":26,\"preimage\":%s,\"candidate_expected_pass\":26,\"preimage_expected_function_pass\":15,\"preimage_expected_EMFILE_failures\":11,\"lost_harness_results_inherited\":false,\"Main_actions\":0}\n",preimage?"true":"false");
    return 0;
  }
  if(argc==2 && strcmp(argv[1],"--root-rejection-only")==0)return RootRejection()?0:1;
  if(argc!=2 || strcmp(argv[1],"--execute-once")!=0)return 64;
  uid_t u[3]{};gid_t g[3]{};uint32_t caps_before[6]{},caps_after[6]{};
  if(getresuid(&u[0],&u[1],&u[2])<0 || getresgid(&g[0],&g[1],&g[2])<0 ||
     u[0]==0 || u[0]!=u[1] || u[1]!=u[2] || g[0]==0 || g[0]!=g[1] || g[1]!=g[2] || CapRead(caps_before)<0)return 65;
  struct sigaction action{};
  if(sigaction(SIGCHLD,nullptr,&action)<0 || action.sa_handler!=SIG_DFL || (action.sa_flags&SA_NOCLDWAIT))return 66;
  if(prctl(PR_SET_CHILD_SUBREAPER,1)<0 || ReapUnexpectedOwnedChildren()!=0)return 67;
  static_assert(sizeof(provenance::KernelStatfs)==120);
  auto* records=static_cast<CaseRecord*>(mmap(nullptr,sizeof(CaseRecord)*std::size(cases),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(records==MAP_FAILED)return 68;
  for(unsigned i=0;i<std::size(cases);++i)new(&records[i])CaseRecord();
  const int64_t began=Now();if(began<0)return 69;
  const int64_t deadline=began+105000;unsigned matches=0,passed=0,reaped=0,finished=0,observed=0,nested_started=0,nested_reaped=0;
  bool clean=true;
  printf("{\"revision\":\"recovery03\",\"preimage\":%s,\"uid\":%u,\"gid\":%u,\"cases\":[",preimage?"true":"false",static_cast<unsigned>(u[0]),static_cast<unsigned>(g[0]));fflush(stdout);
  for(unsigned index=0;index<std::size(cases);++index) {
    current=&records[index];details=&current->metadata;extra=&current->extra;
    if(cases[index].original>=0 && cases[index].function!=kMetadataCases[cases[index].original].function)return 69;
    const pid_t parent=getpid();pid_t child=-1;int fork_error=ETIMEDOUT;
    if(Now()<deadline-8000){child=fork();if(child<0)fork_error=errno;}
    if(child==0) {
      current->entered.store(1,std::memory_order_release);
      uint64_t mask_before=0,mask_after=0;
      bool ok=Guard(parent) && ClearOwnedChildCapabilities() && Guard(parent) && ReadMask(&mask_before);
      current->guarded=ok;
      if(ok)current->function_passed=cases[index].function();
      current->cleanup_stop=raw_owner::Stop();
      current->persistent_tid_clear=raw_owner::state.tid.load(std::memory_order_acquire)==0;
      current->inherited_tid_clear=InheritedClear();
      current->mask_preserved=ReadMask(&mask_after) && mask_before==mask_after;
      current->finished.store(1,std::memory_order_release);
      _exit(ok?0:1);
    }
    if(child>0) {
      bool timeout=false;int status=0;current->reaped=WaitOwned(child,8000,&status,&timeout);
      current->timed_out=timeout;current->child_status=status;
    } else {current->extra.setup_error=fork_error;clean=false;}
    const int leaked=ReapUnexpectedOwnedChildren();current->unexpected_cleanup=leaked;
    if(leaked!=0)clean=false;
    const bool expected=!preimage || !cases[index].baseline_failure;
    bool negative_reason=!expected && !current->function_passed && extra->setup_done && extra->primary_attempts>0 &&
        extra->primary_rc==-1 && extra->primary_errno==EMFILE && extra->failed_snapshot_untouched && extra->inherited_clear;
    if(index==17)negative_reason=negative_reason && extra->raw_badfd_rc==-1 && extra->raw_badfd_errno==EBADF && extra->mask_preserved;
    if(index==20)negative_reason=negative_reason && extra->thread_error==0 && extra->thread_joined && extra->private_table && extra->parent_fd_survives;
    if(index==22 || index==23)negative_reason=negative_reason && extra->child_start==0 && extra->child_finished && extra->child_stop==0 &&
        extra->child_tid_clear && extra->parent_stop==0 && extra->parent_fd_survives;
    if(index==22)negative_reason=negative_reason && extra->parent_read==0;
    if(index==25)negative_reason=negative_reason && extra->child_native_rc==0 && extra->child_start==-1 && extra->child_start_errno==EMFILE &&
        extra->child_read==-1 && extra->child_read_errno==ESHUTDOWN && extra->child_stop==0 && extra->child_tid_clear && extra->child_finished &&
        WIFEXITED(extra->child_status) && WEXITSTATUS(extra->child_status)==0 && extra->parent_stop==0 && extra->parent_fd_survives;
    const bool safe=current->reaped && !current->timed_out && WIFEXITED(current->child_status) && WEXITSTATUS(current->child_status)==0 &&
        current->finished.load(std::memory_order_acquire) && current->guarded && current->cap_verified && current->cleanup_stop==0 &&
        current->persistent_tid_clear && current->inherited_tid_clear && current->mask_preserved && leaked==0 &&
        (!details->nested_started || (details->child_reaped && !details->child_timeout)) &&
        (!extra->child_started || (extra->child_reaped && !extra->child_timeout));
    const bool match=safe && (expected?current->function_passed!=0:negative_reason);
    matches+=match;passed+=current->function_passed!=0;reaped+=current->reaped!=0;finished+=current->finished.load()!=0;observed+=current->entered.load()!=0;
    nested_started+=details->nested_started+extra->child_started;nested_reaped+=details->child_reaped+extra->child_reaped;
    if(index)putchar(',');
    PrintRecord(index,*current,expected,match);fflush(stdout);
  }
  const bool parent_caps=CapRead(caps_after)==0 && memcmp(caps_before,caps_after,sizeof(caps_before))==0;
  const int leftovers=ReapUnexpectedOwnedChildren();const bool all=matches==26 && clean && leftovers==0 && parent_caps && nested_started==nested_reaped;
  printf("],\"case_count\":26,\"observed\":%u,\"function_passed\":%u,\"matched_expected\":%u,\"direct_children_reaped\":%u,\"direct_children_finished\":%u,\"nested_started\":%u,\"nested_reaped\":%u,\"parent_capabilities_unchanged\":%s,\"unexpected_cleanup\":%d,\"pass\":%s,\"Main_actions\":0,\"Android_qualification\":false,\"trusted_factory_positive\":false,\"lost_harness_PASS_inherited\":false}\n",
      observed,passed,matches,reaped,finished,nested_started,nested_reaped,parent_caps?"true":"false",leftovers,all?"true":"false");
  munmap(records,sizeof(CaseRecord)*std::size(cases));return all?0:1;
}
