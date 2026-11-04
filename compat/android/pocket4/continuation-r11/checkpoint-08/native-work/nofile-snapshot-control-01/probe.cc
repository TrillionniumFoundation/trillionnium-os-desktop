#include "owned_snapshot.h"
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <linux/futex.h>
#include <new>
#include <signal.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum Case { kNoFile, kNoFileAsOne, kCloseReuse, kBadFd, kRounds, kCases };
struct Result {
  int setup=0, pass=0, timed_out=0, reaped=0, wait_status=-1;
  long pidfd_before=-999, pidfd_after=-999, clone_result=-999;
  long native_stat=-999, native_statfs=-999;
  int worker_result=-999, tid_cleared=0, complete=0, caller_survives=0;
  int identity_equal=0, fs_all_120_bytes_equal=0, output_untouched=0;
  int caller_has_replacement=0, worker_kept_original=0, rounds=0;
  unsigned long long original_inode=0, worker_inode=0, caller_inode=0;
};
static_assert(sizeof(berberis::proc_maps_provenance::KernelStatfs)==120);
template<class T> long Address(T* p) {return reinterpret_cast<long>(p);}

bool WaitValue(std::atomic<int>* value,int wanted) {
  const struct timespec timeout{0,10000000};
  for(int i=0;i<200;++i) {
    const int now=value->load(std::memory_order_acquire);
    if(now==wanted)return true;
    // Shared FUTEX_WAIT is required for the kernel's final clear-tid wake.
    OwnedRaw(SYS_futex,Address(value),FUTEX_WAIT,now,Address(&timeout));
  }
  return value->load(std::memory_order_acquire)==wanted;
}

[[noreturn]] void Finish(bool okay,Result* result) {
  result->pass=okay;
  OwnedRaw(SYS_exit_group,okay?0:1);
  __builtin_unreachable();
}

void RunCase(Case selected,Result* result) {
  const int fd=static_cast<int>(OwnedRaw(SYS_memfd_create,Address("owned-nofile-original"),1));
  const int other=static_cast<int>(OwnedRaw(SYS_memfd_create,Address("owned-nofile-replacement"),1));
  if(fd<0 || other<0 || OwnedRaw(SYS_ftruncate,fd,4096)<0 || OwnedRaw(SYS_ftruncate,other,8192)<0) {
    result->setup=1;Finish(false,result);
  }
  OwnedMetadata expected{};
  if(OwnedRaw(SYS_fstat,fd,Address(&expected.identity))<0 ||
     OwnedRaw(SYS_fstatfs,fd,Address(&expected.filesystem))<0) {
    result->setup=2;Finish(false,result);
  }
  result->original_inode=expected.identity.st_ino;
  const long page=sysconf(_SC_PAGESIZE);
  const size_t bytes=128*1024+static_cast<size_t>(page);
  void* mapping=mmap(nullptr,bytes,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
  if(page<=0 || mapping==MAP_FAILED ||
     mprotect(static_cast<char*>(mapping)+page,128*1024,PROT_READ|PROT_WRITE)<0) {
    result->setup=3;Finish(false,result);
  }
  void* top=static_cast<char*>(mapping)+bytes;
  const uint64_t mask=~uint64_t{0};uint64_t old_mask=0;
  if(OwnedRaw(SYS_rt_sigprocmask,SIG_SETMASK,Address(&mask),Address(&old_mask),8)<0) {
    result->setup=4;Finish(false,result);
  }
  result->pidfd_before=OwnedRaw(SYS_pidfd_open,OwnedRaw(SYS_gettid),O_EXCL);
  if(result->pidfd_before>=0)OwnedRaw(SYS_close,result->pidfd_before);
  const struct rlimit zero{0,0}, as_one{1,1};
  if(selected!=kCloseReuse && OwnedRaw(SYS_prlimit64,0,RLIMIT_NOFILE,Address(&zero),0)<0) {
    result->setup=5;Finish(false,result);
  }
  if(selected==kNoFileAsOne && OwnedRaw(SYS_prlimit64,0,RLIMIT_AS,Address(&as_one),0)<0) {
    result->setup=6;Finish(false,result);
  }
  const int count=selected==kRounds?24:1;
  for(int round=0;round<count;++round) {
    OwnedSnapshotRequest request;
    request.fd=selected==kBadFd?-1:fd;
    std::atomic<int> tid{0};
    OwnedMetadata published;
    std::memset(reinterpret_cast<unsigned char*>(&published),0xa5,sizeof(published));
    unsigned char before[sizeof(published)];std::memcpy(before,&published,sizeof(before));
    result->clone_result=SpawnOwnedFdSnapshot(top,&tid,&request);
    if(result->clone_result<0)Finish(false,result);
    if(!WaitValue(&request.ready,1)) {
      result->timed_out=1;Finish(false,result);
    }
    if(selected==kCloseReuse) {
      if(OwnedRaw(SYS_close,fd)!=0 || OwnedRaw(SYS_dup2,other,fd)!=fd ||
         OwnedRaw(SYS_prlimit64,0,RLIMIT_NOFILE,Address(&zero),0)!=0) {
        result->setup=7;Finish(false,result);
      }
    }
    OwnedMetadata native{};
    result->native_stat=OwnedRaw(SYS_fstat,request.fd,Address(&native.identity));
    result->native_statfs=OwnedRaw(SYS_fstatfs,request.fd,Address(&native.filesystem));
    result->pidfd_after=OwnedRaw(SYS_pidfd_open,OwnedRaw(SYS_gettid),O_EXCL);
    if(result->pidfd_after>=0)OwnedRaw(SYS_close,result->pidfd_after);
    request.go.store(1,std::memory_order_release);
    OwnedRaw(SYS_futex,Address(&request.go),FUTEX_WAKE_PRIVATE,INT_MAX);
    if(!WaitValue(&tid,0)) {
      result->timed_out=1;Finish(false,result);
    }
    result->tid_cleared=1;
    result->complete=request.complete.load(std::memory_order_acquire);
    result->worker_result=request.result;
    if(request.result==0)std::memcpy(&published,&request.internal,sizeof(published));
    result->output_untouched=std::memcmp(&published,before,sizeof(before))==0;
    result->worker_inode=published.identity.st_ino;
    result->caller_inode=native.identity.st_ino;
    result->identity_equal=std::memcmp(&published.identity,&expected.identity,sizeof(expected.identity))==0;
    result->fs_all_120_bytes_equal=std::memcmp(&published.filesystem,&expected.filesystem,120)==0;
    struct stat survived{};
    result->caller_survives=OwnedRaw(SYS_fstat,fd,Address(&survived))==0;
    result->caller_has_replacement=selected==kCloseReuse && native.identity.st_size==8192 &&
                                  native.identity.st_ino!=expected.identity.st_ino;
    result->worker_kept_original=selected==kCloseReuse && published.identity.st_size==4096 &&
                                 published.identity.st_ino==expected.identity.st_ino;
    const bool values=selected==kBadFd?
        result->worker_result==-EBADF && result->native_stat==-EBADF && result->native_statfs==-EBADF &&
          result->output_untouched:
        result->worker_result==0 && result->native_stat==0 && result->native_statfs==0 &&
          result->identity_equal && result->fs_all_120_bytes_equal;
    const bool race=selected!=kCloseReuse || (result->caller_has_replacement && result->worker_kept_original);
    if(!values || !race || !result->caller_survives || !result->complete || result->pidfd_after!=-EMFILE)
      Finish(false,result);
    ++result->rounds;
  }
  // Both statements only run after the kernel has cleared the final thread ID.
  const bool restored=OwnedRaw(SYS_rt_sigprocmask,SIG_SETMASK,Address(&old_mask),0,8)==0;
  const bool unmapped=OwnedRaw(SYS_munmap,Address(mapping),bytes)==0;
  Finish(restored && unmapped,result);
}

int main() {
  struct sigaction action{};action.sa_handler=SIG_DFL;
  if(sigaction(SIGCHLD,&action,nullptr)<0)return 2;
  auto* all=static_cast<Result*>(mmap(nullptr,sizeof(Result)*kCases,PROT_READ|PROT_WRITE,
                                    MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(all==MAP_FAILED)return 2;
  const char* names[kCases]={"NOFILE0_clone_inherited_snapshot","NOFILE0_AS1_clone_inherited_snapshot",
                            "private_table_close_reuse_then_NOFILE0","NOFILE0_EBADF_output_unchanged",
                            "NOFILE0_24_clear_tid_restarts"};
  bool okay=true;
  const pid_t parent=getpid();
  for(int i=0;i<kCases;++i) {
    new(all+i) Result{};
    const pid_t child=fork();
    if(child==0) {
      if(prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=parent)_exit(2);
      RunCase(static_cast<Case>(i),&all[i]);
    }
    if(child<0)return 2;
    int status=-1;pid_t observed=0;
    for(int n=0;n<500 && observed==0;++n) {
      observed=waitpid(child,&status,WNOHANG);
      if(observed<0 && errno==EINTR)observed=0;
      if(observed==0)usleep(10000);
    }
    if(observed==0) {
      all[i].timed_out=1;
      // This single-threaded supervisor never reaps this child elsewhere. Its
      // PID cannot be reused before this exact wait, including if it is zombie.
      if(kill(child,SIGKILL)<0 && errno!=ESRCH)return 2;
      do{observed=waitpid(child,&status,0);}while(observed<0 && errno==EINTR);
    }
    all[i].reaped=observed==child;all[i].wait_status=status;
    okay=okay && all[i].pass && all[i].reaped && !all[i].timed_out && WIFEXITED(status) && WEXITSTATUS(status)==0;
    const Result& r=all[i];
    std::printf("{\"case\":\"%s\",\"pass\":%s,\"setup\":%d,\"pidfd_before\":%ld,\"pidfd_after\":%ld,"
                "\"clone_result\":%ld,\"native_stat\":%ld,\"native_statfs\":%ld,\"worker_result\":%d,"
                "\"identity_equal\":%d,\"fs_all_120_bytes_equal\":%d,\"output_untouched\":%d,"
                "\"caller_survives\":%d,\"caller_has_replacement\":%d,\"worker_kept_original\":%d,"
                "\"original_inode\":%llu,\"worker_inode\":%llu,\"caller_inode\":%llu,"
                "\"tid_cleared\":%d,\"complete\":%d,\"rounds\":%d,\"timed_out\":%s,\"reaped\":%s,\"wait_status\":%d}\n",
                names[i],r.pass?"true":"false",r.setup,r.pidfd_before,r.pidfd_after,r.clone_result,
                r.native_stat,r.native_statfs,r.worker_result,r.identity_equal,r.fs_all_120_bytes_equal,
                r.output_untouched,r.caller_survives,r.caller_has_replacement,r.worker_kept_original,
                r.original_inode,r.worker_inode,r.caller_inode,r.tid_cleared,r.complete,r.rounds,
                r.timed_out?"true":"false",r.reaped?"true":"false",r.wait_status);
  }
  munmap(all,sizeof(Result)*kCases);
  return okay?0:1;
}
