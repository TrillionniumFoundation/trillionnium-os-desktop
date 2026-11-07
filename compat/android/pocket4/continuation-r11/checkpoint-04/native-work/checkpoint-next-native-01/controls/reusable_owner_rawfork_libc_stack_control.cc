// SPDX-License-Identifier: Apache-2.0
// Actual-owner host control: raw-clone inherited user stack, subsequent normal
// pthread lifecycle and libc fork. Only owned children are killed/reaped.
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <new>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "berberis/kernel_api/proc_maps_fd_owner.h"
namespace owner=berberis::proc_maps_provenance::fd_owner;

struct Report {
  std::atomic<int> stage{0};
  int start=-99,start_error=0,metadata=-99,stop=-99,thread_rounds=0;
  int nested_fork=-99,nested_error=0,nested_reaped=0,nested_status=-99;
  int raw_reaped=0,raw_timeout=0,raw_status=-99,parent_submit=-99,parent_stop=-99;
};
struct Blocked {
  int fd;
  std::atomic<bool> entered{false},release{false};
  int result=-99;
};
static long long Now() {
  struct timespec t{};clock_gettime(CLOCK_MONOTONIC,&t);
  return static_cast<long long>(t.tv_sec)*1000+t.tv_nsec/1000000;
}
static bool WaitOwned(pid_t child,int millis,int* status,bool* timed_out) {
  *timed_out=false;const long long until=Now()+millis;
  const struct timespec pause{0,1000000};
  while(Now()<until) {
    const pid_t got=waitpid(child,status,WNOHANG);
    if(got==child)return true;
    if(got<0 && errno!=EINTR)return false;
    nanosleep(&pause,nullptr);
  }
  const pid_t check=waitpid(child,status,WNOHANG);
  if(check==child)return true;
  if(check!=0)return false; // ECHILD must never authorize kill.
  *timed_out=true;
  if(kill(child,SIGKILL)<0 && errno!=ESRCH)return false;
  const long long cleanup=Now()+1000;
  while(Now()<cleanup) {
    const pid_t got=waitpid(child,status,WNOHANG);
    if(got==child)return true;
    if(got<0 && errno!=EINTR)return false;
    nanosleep(&pause,nullptr);
  }
  return false;
}
static bool Guard(pid_t parent) {
  return getppid()==parent && prctl(PR_SET_PDEATHSIG,SIGKILL)==0 && getppid()==parent;
}
static int Identity(int fd,void*) {
  struct stat value{};return fstat(fd,&value)==0?19:-1;
}
static int Block(int fd,void* opaque) {
  auto* b=static_cast<Blocked*>(opaque);
  if(Identity(fd,nullptr)!=19)return -1;
  b->entered.store(true);
  while(!b->release.load())sched_yield();
  return 23;
}
static void* Submit(void* opaque) {
  auto* b=static_cast<Blocked*>(opaque);
  b->result=owner::WithPinnedFd(b->fd,Block,b);return nullptr;
}
static void* Ordinary(void* opaque) {return opaque;}
static bool CheckOrdinaryThreads(Report* report) {
  for(int i=0;i<8;++i) {
    pthread_t thread;void* returned=nullptr;
    if(pthread_create(&thread,nullptr,Ordinary,report)!=0 ||
       pthread_join(thread,&returned)!=0 || returned!=report)return false;
    ++report->thread_rounds;
  }
  return true;
}
static bool CheckLibcFork(Report* report) {
  const pid_t parent=getpid();errno=0;
  const pid_t child=fork();
  report->nested_fork=child<0?-1:0;report->nested_error=errno;
  if(child<0)return false;
  if(child==0)_exit(Guard(parent)?0:76);
  int status=0;bool timeout=false;
  report->nested_reaped=WaitOwned(child,500,&status,&timeout);
  report->nested_status=status;
  return report->nested_reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0;
}
static bool ChildWork(int fd,Report* report,bool raw,bool threads_first) {
  report->stage.store(10);
  if(raw)owner::ResetReusableMetadataOwnerAfterPrivateFork();
  errno=0;report->start=owner::StartReusableMetadataOwner();report->start_error=errno;
  if(report->start!=0)return false;
  report->stage.store(11);
  report->metadata=owner::WithPinnedFd(fd,Identity,nullptr);
  report->stop=owner::StopReusableMetadataOwner();
  if(report->metadata!=19 || report->stop!=0)return false;
  report->stage.store(12);
  if(threads_first && !CheckOrdinaryThreads(report))return false;
  report->stage.store(13);
  if(!CheckLibcFork(report))return false;
  report->stage.store(14);
  if(!threads_first && !CheckOrdinaryThreads(report))return false;
  // Restart after the second fork/ordinary libc operations as a final control.
  if(owner::StartReusableMetadataOwner()!=0 ||
     owner::WithPinnedFd(fd,Identity,nullptr)!=19 ||
     owner::StopReusableMetadataOwner()!=0)return false;
  report->stage.store(15);return true;
}
static bool Scenario(Report* report,bool raw,bool inflight,bool quiesce,bool threads_first) {
  const int fd=open("/dev/null",O_RDONLY|O_CLOEXEC);
  if(fd<0 || owner::StartReusableMetadataOwner()!=0)return false;
  report->stage.store(1);
  Blocked b{fd};pthread_t submit{};
  if(inflight) {
    if(pthread_create(&submit,nullptr,Submit,&b)!=0)return false;
    const long long until=Now()+1000;
    while(!b.entered.load() && Now()<until)sched_yield();
    if(!b.entered.load())return false;
  }
  if(quiesce && owner::StopReusableMetadataOwner()!=0)return false;
  report->stage.store(2);
  const pid_t parent=getpid();
  const pid_t child=raw?static_cast<pid_t>(syscall(SYS_clone,
      static_cast<unsigned long>(SIGCHLD),0UL,0UL,0UL,0UL)):fork();
  if(child<0)return false;
  if(child==0)_exit(Guard(parent) && ChildWork(fd,report,raw,threads_first)?0:71);
  int status=0;bool timeout=false;
  report->raw_reaped=WaitOwned(child,3000,&status,&timeout);
  report->raw_timeout=timeout;report->raw_status=status;
  if(inflight) {
    b.release.store(true);
    if(pthread_join(submit,nullptr)!=0)return false;
    report->parent_submit=b.result;
  }
  report->parent_stop=owner::StopReusableMetadataOwner();
  return report->raw_reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0 &&
         (!inflight || b.result==23) && report->parent_stop==0;
}
int main() {
  setvbuf(stdout,nullptr,_IONBF,0);
  struct sigaction action{};
  if(sigaction(SIGCHLD,nullptr,&action)<0 || action.sa_handler!=SIG_DFL ||
     (action.sa_flags&SA_NOCLDWAIT))return 70;
  struct Case {const char* name;bool raw,inflight,quiesce,threads_first;};
  const Case cases[]={
    {"raw_idle_nested_libc_fork_first",true,false,false,false},
    {"raw_inflight_ordinary_threads_first",true,true,false,true},
    {"libc_inflight_control",false,true,false,true},
    {"quiesced_raw_control",true,false,true,true}
  };
  bool all=true;
  for(const Case& test:cases) {
    void* memory=mmap(nullptr,sizeof(Report),PROT_READ|PROT_WRITE,
                      MAP_SHARED|MAP_ANONYMOUS,-1,0);
    if(memory==MAP_FAILED)return 72;
    auto* report=new(memory)Report;
    const pid_t parent=getpid();const pid_t child=fork();
    if(child<0)return 73;
    if(child==0)_exit(Guard(parent) && Scenario(report,test.raw,test.inflight,
                                             test.quiesce,test.threads_first)?0:1);
    int status=0;bool timeout=false;
    const bool reaped=WaitOwned(child,6500,&status,&timeout);
    const bool passed=reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0;
    printf("{\"case\":\"%s\",\"passed\":%s,\"controller_child_reaped\":%s,"
           "\"controller_timeout\":%s,\"controller_status\":%d,\"stage\":%d,"
           "\"child_start\":%d,\"start_errno\":%d,\"metadata\":%d,\"stop\":%d,"
           "\"ordinary_threads_joined\":%d,\"nested_fork\":%d,\"nested_errno\":%d,"
           "\"nested_reaped\":%d,\"nested_status\":%d,\"raw_reaped\":%d,"
           "\"raw_timeout\":%d,\"raw_status\":%d,\"parent_submit\":%d,\"parent_stop\":%d}\n",
           test.name,passed?"true":"false",reaped?"true":"false",timeout?"true":"false",
           status,report->stage.load(),report->start,report->start_error,report->metadata,
           report->stop,report->thread_rounds,report->nested_fork,report->nested_error,
           report->nested_reaped,report->nested_status,report->raw_reaped,report->raw_timeout,
           report->raw_status,report->parent_submit,report->parent_stop);
    all=all && passed;munmap(memory,sizeof(Report));
  }
  return all?0:1;
}
