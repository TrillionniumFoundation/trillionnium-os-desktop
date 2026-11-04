// SPDX-License-Identifier: Apache-2.0
#include <jni.h>
#include <cstdarg>
#include <cstdio>
static char probe_result[16384];
static bool capability_child_reaped;
static int ProbePrint(const char* format, ...) {
  va_list args; va_start(args,format);
  int n=vsnprintf(probe_result,sizeof(probe_result),format,args);
  va_end(args); return n;
}
// SPDX-License-Identifier: Apache-2.0
// Owned capability probe. All potentially policy-blocked syscalls run in a
// disposable child, with a parent watchdog. No Android app or external fd is used.
#include <cerrno>
#include <cstdio>
#include <cstdint>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <cstring>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
struct CopyProbe {
  long read_rc, write_rc, bad_read_rc, bad_write_rc;
  int read_error, write_error, bad_read_error, bad_write_error;
  int read_matches, write_matches, source_unchanged, tid_is_self;
};
static __attribute__((noinline)) void ProbeOwnCopyLegacy(CopyProbe* p) {
  const uint64_t expected[2] = {UINT64_C(0x317ac25e4d98f601), UINT64_C(0x6ce2028f39145abd)};
  uint64_t source[2] = {expected[0], expected[1]}, readback[2] = {}, written[2] = {};
  const pid_t tid=static_cast<pid_t>(syscall(SYS_gettid));
  p->tid_is_self=tid>0;
  struct iovec local{readback,sizeof(readback)}, remote{source,sizeof(source)};
  errno=0;
  p->read_rc=syscall(SYS_process_vm_readv,tid,&local,1,&remote,1,0);
  p->read_error=errno;
  p->read_matches=p->read_rc==static_cast<long>(sizeof(source)) && memcmp(readback,expected,sizeof(source))==0;
  local={source,sizeof(source)};remote={written,sizeof(written)};
  errno=0;
  p->write_rc=syscall(SYS_process_vm_writev,tid,&local,1,&remote,1,0);
  p->write_error=errno;
  p->write_matches=p->write_rc==static_cast<long>(sizeof(source)) && memcmp(written,expected,sizeof(source))==0;
  local={readback,sizeof(readback)};remote={reinterpret_cast<void*>(uintptr_t{1}),sizeof(source)};
  errno=0;
  p->bad_read_rc=syscall(SYS_process_vm_readv,tid,&local,1,&remote,1,0);
  p->bad_read_error=errno;
  local={source,sizeof(source)};
  errno=0;
  p->bad_write_rc=syscall(SYS_process_vm_writev,tid,&local,1,&remote,1,0);
  p->bad_write_error=errno;
  p->source_unchanged=memcmp(source,expected,sizeof(source))==0;
}
static __attribute__((noinline)) void ProbeOwnCopy(CopyProbe* p) {
  const uint64_t expected[2] = {UINT64_C(0x317ac25e4d98f601), UINT64_C(0x6ce2028f39145abd)};
  uint64_t source[2] = {expected[0], expected[1]}, readback[2] = {}, written[2] = {};
  const pid_t tid=static_cast<pid_t>(syscall(SYS_gettid));
  p->tid_is_self=tid>0;
  struct iovec local{readback,sizeof(readback)}, remote{source,sizeof(source)};
  errno=0;
  p->read_rc=syscall(SYS_process_vm_readv,static_cast<long>(tid),&local,1UL,&remote,1UL,0UL);
  p->read_error=errno;
  p->read_matches=p->read_rc==static_cast<long>(sizeof(source)) && memcmp(readback,expected,sizeof(source))==0;
  local={source,sizeof(source)};remote={written,sizeof(written)};
  errno=0;
  p->write_rc=syscall(SYS_process_vm_writev,static_cast<long>(tid),&local,1UL,&remote,1UL,0UL);
  p->write_error=errno;
  p->write_matches=p->write_rc==static_cast<long>(sizeof(source)) && memcmp(written,expected,sizeof(source))==0;
  local={readback,sizeof(readback)};remote={reinterpret_cast<void*>(uintptr_t{1}),sizeof(source)};
  errno=0;
  p->bad_read_rc=syscall(SYS_process_vm_readv,static_cast<long>(tid),&local,1UL,&remote,1UL,0UL);
  p->bad_read_error=errno;
  local={source,sizeof(source)};
  errno=0;
  p->bad_write_rc=syscall(SYS_process_vm_writev,static_cast<long>(tid),&local,1UL,&remote,1UL,0UL);
  p->bad_write_error=errno;
  p->source_unchanged=memcmp(source,expected,sizeof(source))==0;
}
static __attribute__((noinline)) void ProbeOwnCopyTyped(CopyProbe* p) {
  const uint64_t expected[2] = {UINT64_C(0x317ac25e4d98f601), UINT64_C(0x6ce2028f39145abd)};
  uint64_t source[2] = {expected[0], expected[1]}, readback[2] = {}, written[2] = {};
  const pid_t tid=static_cast<pid_t>(syscall(SYS_gettid));
  p->tid_is_self=tid>0;
  struct iovec local{readback,sizeof(readback)}, remote{source,sizeof(source)};
  errno=0;
  p->read_rc=process_vm_readv(tid,&local,1UL,&remote,1UL,0UL);
  p->read_error=errno;
  p->read_matches=p->read_rc==static_cast<long>(sizeof(source)) && memcmp(readback,expected,sizeof(source))==0;
  local={source,sizeof(source)};remote={written,sizeof(written)};
  errno=0;
  p->write_rc=process_vm_writev(tid,&local,1UL,&remote,1UL,0UL);
  p->write_error=errno;
  p->write_matches=p->write_rc==static_cast<long>(sizeof(source)) && memcmp(written,expected,sizeof(source))==0;
  local={readback,sizeof(readback)};remote={reinterpret_cast<void*>(uintptr_t{1}),sizeof(source)};
  errno=0;
  p->bad_read_rc=process_vm_readv(tid,&local,1UL,&remote,1UL,0UL);
  p->bad_read_error=errno;
  local={source,sizeof(source)};
  errno=0;
  p->bad_write_rc=process_vm_writev(tid,&local,1UL,&remote,1UL,0UL);
  p->bad_write_error=errno;
  p->source_unchanged=memcmp(source,expected,sizeof(source))==0;
}
static bool CopyPass(const CopyProbe& p) {
  return p.tid_is_self && p.read_matches && p.write_matches && p.source_unchanged &&
    p.bad_read_rc==-1 && p.bad_read_error==EFAULT && p.bad_write_rc==-1 && p.bad_write_error==EFAULT;
}
struct Probe {
  volatile int step;
  int source_fd, caller_tid;
  int unshare_rc, unshare_error;
  int clear_rc, clear_error;
  int pidfd_rc, pidfd_error;
  int getfd_rc, getfd_error;
  int stat_rc, stat_error, statfs_rc, statfs_error;
  int setup_error, thread_error, source_survived, identity_matches, fd_limit_reached;
  struct stat source_stat;
  CopyProbe caller_copy, owner_copy, caller_typed, owner_typed, caller_legacy, owner_legacy;
};
static void* Owner(void* arg) {
  auto* p=static_cast<Probe*>(arg);
  p->step=2; errno=0; p->unshare_rc=syscall(SYS_unshare,CLONE_FILES); p->unshare_error=errno;
  if(p->unshare_rc<0) return nullptr;
  p->step=3; errno=0;
#ifdef SYS_close_range
  p->clear_rc=syscall(SYS_close_range,0,UINT_MAX,0);
#else
  p->clear_rc=-1; errno=ENOSYS;
#endif
  p->clear_error=errno; if(p->clear_rc<0) return nullptr;
  ProbeOwnCopyLegacy(&p->owner_legacy);
  ProbeOwnCopy(&p->owner_copy);
  ProbeOwnCopyTyped(&p->owner_typed);
  p->step=4; errno=0;
#ifdef SYS_pidfd_open
  p->pidfd_rc=syscall(SYS_pidfd_open,p->caller_tid,O_EXCL);
#else
  p->pidfd_rc=-1; errno=ENOSYS;
#endif
  p->pidfd_error=errno; if(p->pidfd_rc<0) return nullptr;
  p->step=5; errno=0;
#ifdef SYS_pidfd_getfd
  p->getfd_rc=syscall(SYS_pidfd_getfd,p->pidfd_rc,p->source_fd,0);
#else
  p->getfd_rc=-1; errno=ENOSYS;
#endif
  p->getfd_error=errno;
  if(p->getfd_rc>=0) {
    p->step=6; struct stat actual{}; errno=0;
    p->stat_rc=fstat(p->getfd_rc,&actual); p->stat_error=errno;
    p->identity_matches=p->stat_rc==0 && actual.st_dev==p->source_stat.st_dev && actual.st_ino==p->source_stat.st_ino && actual.st_mode==p->source_stat.st_mode;
    struct statfs fs{}; errno=0; p->statfs_rc=fstatfs(p->getfd_rc,&fs); p->statfs_error=errno;
    close(p->getfd_rc);
  }
  close(p->pidfd_rc); p->step=7; return nullptr;
}
static void Child(Probe* p,pid_t expected_parent) {
  if(getppid()!=expected_parent || prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=expected_parent)_exit(83);
  ProbeOwnCopyLegacy(&p->caller_legacy);
  ProbeOwnCopy(&p->caller_copy);
  ProbeOwnCopyTyped(&p->caller_typed);
  p->step=1; p->source_fd=open("/dev/null",O_RDONLY|O_CLOEXEC);
  if(p->source_fd<0 || fstat(p->source_fd,&p->source_stat)<0) {p->setup_error=errno;_exit(80);}
  p->caller_tid=syscall(SYS_gettid);
  struct rlimit limit{64,64}; if(setrlimit(RLIMIT_NOFILE,&limit)<0) {p->setup_error=errno;_exit(81);}
  while(fcntl(p->source_fd,F_DUPFD_CLOEXEC,0)>=0) {}
  p->fd_limit_reached=errno==EMFILE;
  pthread_t owner;
  p->thread_error=pthread_create(&owner,nullptr,Owner,p);
  if(p->thread_error) _exit(82);
  p->thread_error=pthread_join(owner,nullptr);
  p->source_survived=fcntl(p->source_fd,F_GETFD)>=0;
  _exit(0);
}
static int RunOwnedProbe() {
  auto* p=static_cast<Probe*>(mmap(nullptr,sizeof(Probe),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(p==MAP_FAILED) return 70;
  pid_t expected_parent=getpid();
  pid_t child=fork(); if(child<0) return 71; if(child==0) Child(p,expected_parent);
  int status=0; bool timeout=true;
  const struct timespec delay{0,20000000};
  for(int i=0;i<250;++i) {
    pid_t done=waitpid(child,&status,WNOHANG);
    if(done==child) {timeout=false;capability_child_reaped=true;break;}
    if(done<0 && errno!=EINTR) return 72;
    nanosleep(&delay,nullptr);
  }
  if(timeout) {kill(child,SIGKILL);pid_t reaped;do{reaped=waitpid(child,&status,0);}while(reaped<0 && errno==EINTR);capability_child_reaped=reaped==child;}
  int signal=WIFSIGNALED(status)?WTERMSIG(status):0;
  int exit_code=WIFEXITED(status)?WEXITSTATUS(status):-1;
  bool pass=capability_child_reaped && !timeout && signal==0 && exit_code==0 && p->step==7 && p->unshare_rc==0 && p->clear_rc==0 && p->pidfd_rc>=0 && p->getfd_rc>=0 && p->stat_rc==0 && p->statfs_rc==0 && p->identity_matches && p->source_survived && p->fd_limit_reached && p->thread_error==0 && CopyPass(p->caller_copy) && CopyPass(p->owner_copy) && CopyPass(p->caller_typed) && CopyPass(p->owner_typed);
  ProbePrint("{\"probe\":\"owned_private_fd_owner\",\"pass\":%s,\"child_reaped\":true,\"timeout\":%s,\"child_signal\":%d,\"child_exit\":%d,\"step\":%d,\"unshare_rc\":%d,\"unshare_errno\":%d,\"clear_rc\":%d,\"clear_errno\":%d,\"pidfd_rc\":%d,\"pidfd_errno\":%d,\"getfd_rc\":%d,\"getfd_errno\":%d,\"stat_rc\":%d,\"stat_errno\":%d,\"statfs_rc\":%d,\"statfs_errno\":%d,\"identity_matches\":%d,\"caller_fd_survived\":%d,\"fd_limit_reached\":%d,\"setup_error\":%d,\"thread_error\":%d}\n",pass?"true":"false",timeout?"true":"false",signal,exit_code,p->step,p->unshare_rc,p->unshare_error,p->clear_rc,p->clear_error,p->pidfd_rc,p->pidfd_error,p->getfd_rc,p->getfd_error,p->stat_rc,p->stat_error,p->statfs_rc,p->statfs_error,p->identity_matches,p->source_survived,p->fd_limit_reached,p->setup_error,p->thread_error);
  size_t used=strlen(probe_result);
  if(used>0 && probe_result[used-1]=='\n') probe_result[--used]=0;
  if(used>0 && probe_result[used-1]=='}') probe_result[--used]=0;
  const CopyProbe* copies[6]={&p->caller_copy,&p->owner_copy,&p->caller_typed,&p->owner_typed,&p->caller_legacy,&p->owner_legacy};
  const char* names[6]={"caller_word_syscall","owner_word_syscall","caller_typed_libc","owner_typed_libc","caller_legacy_diagnostic","owner_legacy_diagnostic"};
  for(unsigned i=0;i<6;++i) {
    const CopyProbe& c=*copies[i];
    int n=snprintf(probe_result+used,sizeof(probe_result)-used,
      ",\"%s\":{\"pass\":%s,\"read_rc\":%ld,\"read_errno\":%d,\"write_rc\":%ld,\"write_errno\":%d,"
      "\"bad_read_rc\":%ld,\"bad_read_errno\":%d,\"bad_write_rc\":%ld,\"bad_write_errno\":%d,"
      "\"read_matches\":%d,\"write_matches\":%d,\"source_unchanged\":%d,\"tid_is_self\":%d}",
      names[i],CopyPass(c)?"true":"false",c.read_rc,c.read_error,c.write_rc,c.write_error,
      c.bad_read_rc,c.bad_read_error,c.bad_write_rc,c.bad_write_error,
      c.read_matches,c.write_matches,c.source_unchanged,c.tid_is_self);
    if(n<0 || static_cast<size_t>(n)>=sizeof(probe_result)-used) return 73;
    used+=static_cast<size_t>(n);
  }
  snprintf(probe_result+used,sizeof(probe_result)-used,"}\n");
  munmap(p,sizeof(Probe)); return pass?0:1;
}

#include "owned_cases.cc"

#if defined(P4_HOST_COPY_SEAM)
static constexpr const char* kHostCopySeam="true";
#else
static constexpr const char* kHostCopySeam="false";
#endif
static int RunAllOwnedChecks() {
  probe_result[0]=0;
  struct sigaction child_action{};
  if(sigaction(SIGCHLD,nullptr,&child_action)<0 || child_action.sa_handler!=SIG_DFL ||
     (child_action.sa_flags&SA_NOCLDWAIT)!=0) {
    ProbePrint("{\"probe\":\"owned_actual_fd_paths_r13\",\"pass\":false,\"setup\":\"SIGCHLD policy does not establish exclusive wait ownership\"}");
    return 75;
  }
  int capability_rc=RunOwnedProbe();
  if(probe_result[0]==0)snprintf(probe_result,sizeof(probe_result),"{\"pass\":false,\"early_rc\":%d}",capability_rc);
  char capability[8192];size_t capability_size=strlen(probe_result);
  if(capability_size>=sizeof(capability))return 74;
  memcpy(capability,probe_result,capability_size+1);
  while(capability_size && (capability[capability_size-1]=='\n' || capability[capability_size-1]=='\r'))capability[--capability_size]=0;
  char actual[2048];int actual_rc=RunActualSourceCases(actual,sizeof(actual));
  ProbePrint("{\"probe\":\"owned_actual_fd_paths_r13\",\"pass\":%s,\"child_reaped\":%s,\"host_copy_seam\":%s,\"capability\":%s,\"actual_source\":%s}",capability_rc==0&&actual_rc==0?"true":"false",capability_child_reaped&&actual_children_reaped?"true":"false",kHostCopySeam,capability,actual);
  return capability_rc==0&&actual_rc==0?0:1;
}
extern "C" JNIEXPORT jstring JNICALL
Java_local_pocket4_fdownerprobe_ProbeInstrumentation_runProbe(JNIEnv* env, jclass) {
  RunAllOwnedChecks();return env->NewStringUTF(probe_result);
}
