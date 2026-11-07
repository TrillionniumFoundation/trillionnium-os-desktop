// SPDX-License-Identifier: Apache-2.0
// Owned controls for the fixed raw-syscall experiment, not provenance wrappers.
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <linux/memfd.h>
#include <new>
#include <sched.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <sys/xattr.h>
#include <time.h>
#include <unistd.h>
#include "raw_metadata_owner.cc"
namespace raw_owner=pocket4::raw_metadata_owner;

struct RawDetails {
  int setup=0,native_stat=-99,native_fs=-99,start=-99,start_error=0;
  int read=-99,read_error=0,stop=-99,restarted=0,worker_tid_cleared=0;
  int inherited_stack=0,child_finished=0,child_reaped=0,child_timeout=0,nested_started=0;
  int child_status=-99,parent_read=-99,parent_stop=-99,parent_fd_survived=0;
  int joined_rounds=0,errno_preserved=0,mask_preserved=0;
};
static RawDetails* raw_details;
static constexpr char kOwnedTag[]="user.pocket4.raw-owner-control";
static constexpr char kOwnedValue[]="owned-raw-metadata";
static int64_t RawNow() {
  struct timespec t{};
  if(clock_gettime(CLOCK_MONOTONIC,&t)<0)return -1;
  return static_cast<int64_t>(t.tv_sec)*1000+t.tv_nsec/1000000;
}
static bool RawGuard(pid_t parent) {
  return getppid()==parent && prctl(PR_SET_PDEATHSIG,SIGKILL)==0 && getppid()==parent;
}
static bool RawWaitOwned(pid_t child,int milliseconds,int* status,bool* timeout) {
  *timeout=false;const int64_t began=RawNow();
  if(began<0)return false;
  const struct timespec delay{0,1000000};
  for(;;) {
    const pid_t done=waitpid(child,status,WNOHANG);
    if(done==child)return true;
    if(done<0 && errno!=EINTR)return false;
    const int64_t now=RawNow();
    if(now<0 || now-began>=milliseconds)break;
    nanosleep(&delay,nullptr);
  }
  const pid_t check=waitpid(child,status,WNOHANG);
  if(check==child)return true;
  if(check!=0)return false;
  *timeout=true;
  if(kill(child,SIGKILL)<0 && errno!=ESRCH)return false;
  const int64_t killed=RawNow();
  if(killed<0)return false;
  for(;;) {
    const pid_t done=waitpid(child,status,WNOHANG);
    if(done==child)return true;
    if(done<0 && errno!=EINTR)return false;
    const int64_t now=RawNow();
    if(now<0 || now-killed>=1000)return false;
    nanosleep(&delay,nullptr);
  }
}
static int RawSeed() {
  const int fd=static_cast<int>(syscall(SYS_memfd_create,"owned-raw-metadata",
                                       static_cast<unsigned long>(MFD_CLOEXEC|MFD_ALLOW_SEALING)));
  if(fd<0)return -1;
  if(write(fd,kOwnedValue,sizeof(kOwnedValue))!=sizeof(kOwnedValue) ||
     fsetxattr(fd,kOwnedTag,kOwnedValue,sizeof(kOwnedValue),0)<0 ||
     fcntl(fd,F_ADD_SEALS,F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_WRITE|F_SEAL_SEAL)<0) {
    const int saved=errno;close(fd);errno=saved;return -1;
  }
  return fd;
}
static bool RawSameIdentity(int fd,const struct stat& expected) {
  struct stat value{};
  return fstat(fd,&value)==0 && value.st_dev==expected.st_dev &&
         value.st_ino==expected.st_ino && value.st_size==expected.st_size;
}
static bool RawCheck(int fd) {
  struct stat expected{};struct statfs expected_fs{};
  if(fstat(fd,&expected)<0 || fstatfs(fd,&expected_fs)<0)return false;
  raw_owner::Snapshot value;
  errno=113;
  const int result=raw_owner::Read(fd,&value);const int error=errno;
  raw_details->read=result;raw_details->read_error=error;
  raw_details->errno_preserved=error==113;
  const uint64_t worker_mask=~(UINT64_C(1)<<(SIGKILL-1)|UINT64_C(1)<<(SIGSTOP-1));
  return result==0 && error==113 && value.stat_result==0 && value.statfs_result==0 &&
         value.identity.st_dev==expected.st_dev && value.identity.st_ino==expected.st_ino &&
         value.identity.st_size==expected.st_size && value.filesystem.f_type==expected_fs.f_type &&
         value.filesystem.f_bsize==expected_fs.f_bsize &&
         memcmp(&value.filesystem.f_fsid,&expected_fs.f_fsid,sizeof(expected_fs.f_fsid))==0 &&
         value.seals_result==(F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_WRITE|F_SEAL_SEAL) &&
         value.tag_result==sizeof(kOwnedValue) &&
         memcmp(value.tag,kOwnedValue,sizeof(kOwnedValue))==0 &&
         value.worker_mask==worker_mask && value.worker_tgid==static_cast<int>(syscall(SYS_getpid)) &&
         value.worker_tid!=static_cast<int>(syscall(SYS_gettid)) && RawSameIdentity(fd,expected);
}
static bool RawStart() {
  errno=0;raw_details->start=raw_owner::Start();raw_details->start_error=errno;
  return raw_details->start==0;
}
static bool RawStop() {
  raw_details->stop=raw_owner::Stop();
  raw_details->worker_tid_cleared=raw_owner::state.tid.load()==0;
  return raw_details->stop==0 && raw_details->worker_tid_cleared;
}
static bool RawBasic() {
  const int fd=RawSeed();return fd>=0 && RawStart() && RawCheck(fd) && RawStop();
}
static bool RawWarmAs() {
  const int fd=RawSeed();if(fd<0 || !RawStart())return false;
  const struct rlimit limit{1,1};if(setrlimit(RLIMIT_AS,&limit)<0)return false;
  struct stat st{};struct statfs fs{};
  raw_details->native_stat=fstat(fd,&st);raw_details->native_fs=fstatfs(fd,&fs);
  if(!RawCheck(fd) || !RawStop() || !RawStart())return false;
  raw_details->restarted=1;
  return RawCheck(fd) && RawStop();
}
static bool RawForkAs() {
  const int fd=RawSeed();if(fd<0 || !RawStart())return false;
  struct stat parent_identity{};if(fstat(fd,&parent_identity)<0)return false;
  const struct rlimit limit{1,1};if(setrlimit(RLIMIT_AS,&limit)<0)return false;
  const pid_t parent=getpid();
  const pid_t child=static_cast<pid_t>(syscall(SYS_clone,
      static_cast<unsigned long>(SIGCHLD),0UL,0UL,0UL,0UL));
  if(child<0){raw_details->setup=errno;return false;}
  if(child==0) {
    if(!RawGuard(parent))_exit(81);
    raw_owner::ResetAfterPrivateFork();
    raw_details->inherited_stack=raw_owner::HasInheritedStack();
    struct stat st{};struct statfs fs{};
    raw_details->native_stat=fstat(fd,&st);raw_details->native_fs=fstatfs(fd,&fs);
    const bool pass=raw_details->native_stat==0 && raw_details->native_fs==0 &&
                    raw_details->inherited_stack && RawStart() && RawCheck(fd) && RawStop();
    raw_details->child_finished=1;
    _exit(pass?0:1);
  }
  raw_details->nested_started=1;
  int status=0;bool timeout=false;
  raw_details->child_reaped=RawWaitOwned(child,1500,&status,&timeout);
  raw_details->child_timeout=timeout;raw_details->child_status=status;
  raw_owner::Snapshot parent_value;
  raw_details->parent_read=raw_owner::Read(fd,&parent_value);
  raw_details->parent_stop=raw_owner::Stop();
  raw_details->parent_fd_survived=RawSameIdentity(fd,parent_identity);
  return raw_details->child_reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0 &&
         raw_details->parent_read==0 && raw_details->parent_stop==0 && raw_details->parent_fd_survived;
}
static bool RawRestartRounds() {
  const int fd=RawSeed();if(fd<0)return false;
  for(int i=0;i<24;++i) {
    if(!RawStart() || !RawCheck(fd) || !RawStop())return false;
    ++raw_details->joined_rounds;
  }
  return true;
}
static bool RawFullTable() {
  const int fd=RawSeed();if(fd<0 || !RawStart())return false;
  const struct rlimit limit{64,64};if(setrlimit(RLIMIT_NOFILE,&limit)<0)return false;
  int fills[64];unsigned count=0;
  for(;;) {
    const int opened=open("/dev/null",O_RDONLY|O_CLOEXEC);
    if(opened<0)break;
    if(count==64){close(opened);return false;}
    fills[count++]=opened;
  }
  if(errno!=EMFILE)return false;
  const bool pass=RawCheck(fd) && RawStop();
  for(unsigned i=0;i<count;++i)close(fills[i]);
  return pass;
}
static bool RawNoFileZeroKnownRed() {
  const int fd=RawSeed();if(fd<0 || !RawStart())return false;
  const struct rlimit limit{0,0};if(setrlimit(RLIMIT_NOFILE,&limit)<0)return false;
  struct stat st{};struct statfs fs{};
  raw_details->native_stat=fstat(fd,&st);raw_details->native_fs=fstatfs(fd,&fs);
  raw_owner::Snapshot value;errno=0;
  raw_details->read=raw_owner::Read(fd,&value);raw_details->read_error=errno;
  return raw_details->native_stat==0 && raw_details->native_fs==0 &&
         raw_details->read==-1 && raw_details->read_error==EMFILE && RawStop();
}
static bool RawMaskErrno() {
  uint64_t original=0,entered=0,after=0;
  if(syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),0UL,&original,8UL)<0)return false;
  entered=original|(UINT64_C(1)<<(SIGUSR1-1));
  if(syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),&entered,0UL,8UL)<0)return false;
  const int fd=open("/dev/null",O_RDONLY|O_CLOEXEC);
  raw_owner::Snapshot value;
  bool pass=fd>=0 && RawStart();
  if(pass) {
    errno=119;const int read=raw_owner::Read(fd,&value);
    raw_details->errno_preserved=errno==119;
    // The fixed tag query on an ordinary device fails inside the worker. A
    // raw negative result must not write the caller's inherited libc errno.
    pass=read==0 && value.tag_result<0 && raw_details->errno_preserved && RawStop();
  }
  if(syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),0UL,&after,8UL)<0)pass=false;
  raw_details->mask_preserved=after==entered;
  const bool restored=syscall(SYS_rt_sigprocmask,static_cast<long>(SIG_SETMASK),&original,0UL,8UL)==0;
  return pass && raw_details->mask_preserved && restored;
}
static bool RawBadFd() {
  if(!RawStart())return false;
  raw_owner::Snapshot value;
  unsigned char before[sizeof(value)];memcpy(before,&value,sizeof(value));
  errno=0;raw_details->read=raw_owner::Read(INT_MAX,&value);raw_details->read_error=errno;
  return raw_details->read==-1 && raw_details->read_error==EBADF &&
         memcmp(before,&value,sizeof(value))==0 && RawStop();
}
struct RawCase {const char* name;bool(*function)();bool known_red=false;};
static const RawCase kRawCases[]={
  {"fixed_stat_statfs_tag_seals_identity",RawBasic},
  {"warm_AS_1_and_stop_restart_without_TLS_mapping",RawWarmAs},
  {"raw_private_fork_AS_1_inherited_stack",RawForkAs},
  {"24_stop_restart_kernel_clear_tid_rounds",RawRestartRounds},
  {"full_caller_fdtable_native_fd_survives",RawFullTable},
  {"worker_negative_result_preserves_caller_errno_mask",RawMaskErrno},
  {"invalid_fd_preserves_snapshot",RawBadFd},
  {"NOFILE_0_remains_EMFILE_known_red",RawNoFileZeroKnownRed,true},
};
