// SPDX-License-Identifier: Apache-2.0
#include <jni.h>
#include <cstdarg>
#include <cstdio>
static char probe_result[4096];
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
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
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
static void Child(Probe* p) {
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
  pid_t child=fork(); if(child<0) return 71; if(child==0) Child(p);
  int status=0; bool timeout=true;
  const struct timespec delay{0,20000000};
  for(int i=0;i<250;++i) {
    pid_t done=waitpid(child,&status,WNOHANG);
    if(done==child) {timeout=false;break;}
    if(done<0 && errno!=EINTR) return 72;
    nanosleep(&delay,nullptr);
  }
  if(timeout) {kill(child,SIGKILL);while(waitpid(child,&status,0)<0 && errno==EINTR) {}}
  int signal=WIFSIGNALED(status)?WTERMSIG(status):0;
  int exit_code=WIFEXITED(status)?WEXITSTATUS(status):-1;
  bool pass=!timeout && signal==0 && exit_code==0 && p->step==7 && p->unshare_rc==0 && p->clear_rc==0 && p->pidfd_rc>=0 && p->getfd_rc>=0 && p->stat_rc==0 && p->statfs_rc==0 && p->identity_matches && p->source_survived && p->fd_limit_reached && p->thread_error==0;
  ProbePrint("{\"probe\":\"owned_private_fd_owner\",\"pass\":%s,\"child_reaped\":true,\"timeout\":%s,\"child_signal\":%d,\"child_exit\":%d,\"step\":%d,\"unshare_rc\":%d,\"unshare_errno\":%d,\"clear_rc\":%d,\"clear_errno\":%d,\"pidfd_rc\":%d,\"pidfd_errno\":%d,\"getfd_rc\":%d,\"getfd_errno\":%d,\"stat_rc\":%d,\"stat_errno\":%d,\"statfs_rc\":%d,\"statfs_errno\":%d,\"identity_matches\":%d,\"caller_fd_survived\":%d,\"fd_limit_reached\":%d,\"setup_error\":%d,\"thread_error\":%d}\n",pass?"true":"false",timeout?"true":"false",signal,exit_code,p->step,p->unshare_rc,p->unshare_error,p->clear_rc,p->clear_error,p->pidfd_rc,p->pidfd_error,p->getfd_rc,p->getfd_error,p->stat_rc,p->stat_error,p->statfs_rc,p->statfs_error,p->identity_matches,p->source_survived,p->fd_limit_reached,p->setup_error,p->thread_error);
  munmap(p,sizeof(Probe)); return pass?0:1;
}

extern "C" JNIEXPORT jstring JNICALL
Java_local_pocket4_fdownerprobe_ProbeInstrumentation_runProbe(JNIEnv* env, jclass) {
  probe_result[0]=0;
  int rc=RunOwnedProbe();
  if(probe_result[0]==0) snprintf(probe_result,sizeof(probe_result),"{\"pass\":false,\"early_rc\":%d}",rc);
  return env->NewStringUTF(probe_result);
}
